#!/usr/bin/env python
# -*- coding: utf-8 -*-
# cm_ovirt_vm_creator.py - Creates a set of VMs to be used by cm-jenkins as openshift nodes
#
# Copyright © 2018 Red Hat Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import print_function, unicode_literals
import os
import sys
import argparse
import logging
import time
import ovirtsdk4 as sdk
import ovirtsdk4.types as types
import ovirt_utils

# CONSTANTS

DEFAULT_OVIRT_PUB_SSHKEY_ENV_VAR = "OV_SSH_KEY"

# GLOBALS
connection = None
system_service = None
vms_service = None


def str2bool(val):
    """ Convert str argument to bool """
    if val.lower() in ('', 'yes', 'true', 't', 'y', '1'):
        return True
    elif val.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


logging.basicConfig(level=logging.DEBUG, filename="cm_ovirt_vm_creator.log")


def do_work(args):
    """ creates the base constructs & configs required to run the operation  """
    global connection
    global system_service
    global vms_service
    try:
        connection = sdk.Connection(url=args.ovirt_url,
                                    username=args.ovirt_user,
                                    password=os.environ[args.ovirt_pass],
                                    ca_file=args.ovirt_ca_pem_file,
                                    debug=True,
                                    log=logging.getLogger())
        system_service = connection.system_service()
        vms_service = system_service.vms_service()
        cluster_nodes = []
        vm_name_template = "{name_prefix}-{node_type}{i:03d}"
        for idx in range(1, args.masters+1):
            cluster_nodes.append(vm_name_template.format(name_prefix=args.name_prefix,
                                                         node_type="master", i=idx))
        for idx in range(1, args.infra_nodes+1):
            cluster_nodes.append(vm_name_template.format(name_prefix=args.name_prefix,
                                                         node_type="infra", i=idx))
        for idx in range(1, args.nodes+1):
            cluster_nodes.append(vm_name_template.format(name_prefix=args.name_prefix,
                                                         node_type="compute", i=idx))
        print(cluster_nodes, file=sys.stderr)
        if args.info:
            get_vms_info(cluster_nodes, args)
        else:
            create_vms(cluster_nodes, args)
    finally:
        if connection:
            connection.close()


def get_vms_info(cluster_nodes, args):
    """ Gets the ips of all the vms in cluster_nodes list  """
    vm_dict = {}
    for node in vm_iterator(cluster_nodes):
        node_name = node.get().name
        print(node_name, file=sys.stderr)
        vm_dict[node_name] = find_vm_ip(node)

    if len(vm_dict) != len(cluster_nodes):
        print("PROBLEM - not all VMs were detected on the system", file=sys.stderr)
        sys.exit(-1)

    print_ips(vm_dict)


def find_vm_ip(vm):
    """ Find the IPv4 address of a given VM """
    for dev in vm.reported_devices_service().list():
        if dev.name == 'eth0':
            for ip in dev.ips:
                if ip.version == types.IpVersion.V4:
                    return ip.address


def print_ips(vm_dict):
    """ Print IPs for VMs in a bash env var format """
    masters = []
    infra_nodes = []
    nodes = []
    for vm_name, vm_ip in sorted(vm_dict.items()):
        if "master" in vm_name:
            masters.append(vm_ip)
        elif "infra" in vm_name:
            infra_nodes.append(vm_ip)
        else:
            nodes.append(vm_ip)
    print()
    print("#################################################################")
    print('MASTER_IP="{0}"'.format(" ".join(masters)))
    print('INFRA_IPS="{0}"'.format(" ".join(infra_nodes)))
    print('NODE_IPS="{0}"'.format(" ".join(nodes)))
    print("#################################################################")


def vm_iterator(cluster_nodes):
    """ Iterates through the nodes in cluster_nodes list and obtains its vm_service object """
    for node in cluster_nodes:
        vm = vms_service.list(search=construct_search_by_name_query(node))[0]
        vm_service = vms_service.vm_service(vm.id)
        yield vm_service


def construct_search_by_name_query(node_name):
    """  Constructs the vm query string buy name  """
    search_string = "name={node_name}"
    return search_string.format(node_name=node_name).__str__()


def chunks(l, n):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


def create_vms(cluster_nodes, args):
    """ creates the vms in cluster_nodes list, and skipps if they exist """
    vm_dict = {}
    to_create = []

    # Figure out which nodes we need to create, and which are already running
    for node in cluster_nodes:
        print("node=%s" % (node), file=sys.stderr)
        tmp = vms_service.list(search=construct_search_by_name_query(node))
        if len(tmp) == 1:
            vm_dict[node] = vms_service.vm_service(tmp[0].id)
            print("VM %s was found ... skipping creation" % (node), file=sys.stderr)
        else:
            to_create.append(node)

    # Create the VM in "blocks"
    for block in chunks(to_create, args.block_size):
        block_futures = []
        for node in block:
            vm_future = vms_service.add(types.Vm(name=node,
                                                 cluster=types.Cluster(name=args.ovirt_cluster),
                                                 template=types.Template(name=args.ovirt_template)), wait=False)
            block_futures.append((node, vm_future))
        # wait for all the VMs from this block to be created
        for node_name, future_vm in block_futures:
            vm = future_vm.wait()
            vm_dict[node_name] = vms_service.vm_service(vm.id)
        # sleep before the next block
        time.sleep(args.sleep_between_iterations)

    # Start each VM when it's created, but try to batch the calls
    counter = 1
    starting = set()
    pub_sshkey = os.environ[args.pub_sshkey]
    # number of attempts is bigger here because it's not attempts per VM
    # like in the other nodes.
    while counter < args.num_of_iterations * len(cluster_nodes):
        start_futures = []
        for node_name, vm_service in vm_dict.items():
            if node_name in starting:
                continue
            vm = vm_service.get()
            print("%s: vm.status = %s" % (node_name, vm.status), file=sys.stderr)
            if vm.status == types.VmStatus.DOWN:
                print("%s: starting" % (node_name), file=sys.stderr)
                future = vm_service.start(use_cloud_init=True, wait=False,
                                          vm=types.Vm(initialization=types.Initialization(authorized_ssh_keys=pub_sshkey)))
                start_futures.append(future)
                starting.add(node_name)
            elif vm.status == types.VmStatus.UP:
                # make sure we don't wait forever for VMs to be down when they're
                # already up.
                starting.add(node_name)

        # wait for this batch of VMs
        print("batch size = %s" % len(start_futures))
        for future in start_futures:
            future.wait()

        if len(starting) == len(cluster_nodes):
            # We called .start() on all VMs
            break

        time.sleep(args.sleep_between_iterations)
        counter += 1
    else:
        # else clause on while will run when while is finished without "break".
        # This means not all VMs were created, and that's an error
        not_started = set(cluster_nodes) - set(starting)
        total_time_waited = args.num_of_iterations * args.sleep_between_iterations
        print("ERROR - VMs {0} still not created after {1} seconds".format(not_started, total_time_waited), file=sys.stderr)
        sys.exit(-1)

    # Wait for all the VMs to be up before we wait for IPs,
    # this serves two functions:
    # 1) a more useful error message if the VM takes too long to start
    # 2) effectively a more graceful timeout waiting for IPs
    for node, vm_service in vm_dict.items():
        counter = 1
        while counter < args.num_of_iterations:
            vm = vm_service.get()
            print("%s: vm.status = %s, vm.fqdn= '%s'" % (node, vm.status, vm.fqdn), file=sys.stderr)
            if vm.status == types.VmStatus.UP:
                break
            counter += 1
            time.sleep(args.sleep_between_iterations)

        if vm.status != types.VmStatus.UP:
            print("ERROR - VM {0} still not up after {1} retries".format(node, args.num_of_iterations), file=sys.stderr)
            sys.exit(-1)

    ips_dict = {}
    for node, vm_service in vm_dict.items():
        ip = None
        counter = 1
        while counter < args.num_of_iterations:
            ip = find_vm_ip(vm_service)
            if ip is not None:
                break
            counter += 1
            msg = "{0} waiting for ip... {1}/{2} attempts".format(node,
                                                                  counter,
                                                                  args.num_of_iterations)
            print(msg, file=sys.stderr)
            time.sleep(args.sleep_between_iterations)

        if ip is None:
            print("ERROR - Node {0} still has no IP after {1} retries".format(node, args.num_of_iterations), file=sys.stderr)
            sys.exit(-1)
        ips_dict[node] = ip

    print_ips(ips_dict)


def main():
    # Parse command line arguments
    parser_description = 'Creates a set of VMs to be used by cm-jenkins as  openshift nodes'
    parser = argparse.ArgumentParser(description=parser_description)
    # Mandatory Parameters
    ovirt_utils.add_ovirt_args(parser, required=True)

    parser.add_argument('--name-prefix', type=str, required=True,
                        help='The name to be used as a prefix for all the created VMs')
    parser.add_argument('--ovirt-cluster', type=str, required=True,
                        help='The cluster name where to create the VMs on')
    parser.add_argument('--ovirt-template', type=str, required=True,
                        help='The Template to use for the VM creation')
    # optional arguments
    parser.add_argument('--info', const=True, nargs='?', type=str2bool, default=False,
                        help='Used to obtain all the VM ips')
    parser.add_argument('--masters', const=1, nargs='?', type=int, default=1,
                        help='Number of master nodes to create in the cluster')
    parser.add_argument('--nodes', const=2, nargs='?', type=int, default=2,
                        help='Number of compute nodes to create in the cluster')
    parser.add_argument('--infra-nodes', const=2, nargs='?', type=int, default=2,
                        help='Number of infra nodes to create in the cluster')

    parser.add_argument('--pub-sshkey', const=DEFAULT_OVIRT_PUB_SSHKEY_ENV_VAR, nargs='?',
                        type=str, default=DEFAULT_OVIRT_PUB_SSHKEY_ENV_VAR,
                        help='Env variables to use to get the pub ssh key to use with cloud init')
    parser.add_argument('--num-of-iterations', const=30, nargs='?', type=int, default=20,
                        help='Number of iterations to wait for long VM operations (create & run)')
    parser.add_argument('--block-size', const=10, nargs='?', type=int, default=10,
                        help='Number of VMs to create in each "block"')
    parser.add_argument('--sleep-between-iterations', const=5, nargs='?', type=int, default=5,
                        help='sleep time between iterations iterations')

    args = parser.parse_args()

    if not args.name_prefix.strip():
        print("Prefix can't be empty", file=sys.stderr)
        sys.exit(-1)

    if args.ovirt_pass not in os.environ:
        print("No env var named '{env_var}' was found, \
               see option '--ovirt-pass'".format(env_var=args.ovirt_pass), file=sys.stderr)
        sys.exit(-1)
    if args.pub_sshkey not in os.environ:
        print("No env var named '{env_var}' was found, \
               see option --pub-sshkey".format(env_var=args.pub_sshkey), file=sys.stderr)
        sys.exit(-1)

    do_work(args)


if __name__ == '__main__':
    main()
