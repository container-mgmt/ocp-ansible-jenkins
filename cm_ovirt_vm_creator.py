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
import traceback
import argparse
import logging
import time
import ovirtsdk4 as sdk
import ovirtsdk4.types as types

# CONSTANTS

DEFAULT_OVIRT_PASS_ENV_VAR = "OV_PASS"
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



logging.basicConfig(level=logging.DEBUG, filename="ocp-on-rhev-deployer.log")



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
        print (cluster_nodes)
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
    masters = []
    infra_nodes = []
    nodes = []
    for node in vm_iterator(cluster_nodes):
        node_name = node.get().name
        print (node_name)
        for dev in node.reported_devices_service().list():
            if dev.name == 'eth0':
                for ip in dev.ips:
                    if ip.version == types.IpVersion.V4:
                        vm_dict[node_name] = ip.address

    if len(vm_dict) != len(cluster_nodes):
        print (" PROBLEM - not all VMs were detected on the system ")
        sys.exit(-1)
    vm_names = vm_dict.keys()
    vm_names.sort()
    for vm_name in vm_names:
        if vm_name.find("master") >= 0:
            masters.append(vm_dict[vm_name])
        elif vm_name.find("infra") >= 0:
            infra_nodes.append(vm_dict[vm_name])
        else:
            nodes.append(vm_dict[vm_name])
    print ("#################################################################")
    print ("masters: " + " ".join(masters))
    print ("infra  : " + " ".join(infra_nodes))
    print ("nodes  : " + " ".join(nodes))
    print ("#################################################################")



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


def create_vms(cluster_nodes, args):
    """ creates the vms in cluster_nodes list, and skipps if they exist """
    vm_dict = {}
    for node in cluster_nodes:
        print ("node=%s"%(node))
        tmp = vms_service.list(search=constructSearchByNameQuery(node))
        if len(tmp) == 1:
            vm_dict[node] = tmp[0].id
            print ("VM %s was found ... skipping creation"%(node))
        else:
            vm = vms_service.add(types.Vm(name=node,
                                          cluster=types.Cluster(name=args.ovirt_cluster),
                                          template=types.Template(name=args.ovirt_template)))
            vm_dict[node] = vm.id
            vm_service = vms_service.vm_service(vm.id)
            counter = 1
            while counter < args.num_of_iterations:
                time.sleep(args.sleep_between_iterations)
                vm = vm_service.get()
                print ("vm.status = %s" % (vm.status))
                if vm.status == types.VmStatus.DOWN:
                    break
            pub_sshkey = os.environ[args.pub_sshkey]
            vm_service.start(use_cloud_init=True,
                             vm=types.Vm(initialization=types.Initialization(authorized_ssh_keys=pub_sshkey)))
            counter = 1
            while counter < args.num_of_iterations:
                time.sleep(args.sleep_between_iterations)
                vm = vm_service.get()
                print ("vm.status = %s, vm.fqdn= '%s'" % (vm.status, vm.fqdn))
                if vm.status == types.VmStatus.UP  or counter > 20:
                    break
            time.sleep(args.sleep_between_iterations)


def main():
    # Parse command line arguments
    parser_description = 'Creates a set of VMs to be used by cm-jenkins as  openshift nodes'
    parser = argparse.ArgumentParser(description=parser_description)
    # Mandatory Parameters
    parser.add_argument('--name-prefix', type=str, required=True,
                        help='The name to be used as a prefix for all the created VMs')
    parser.add_argument('--ovirt-url', type=str, required=True,
                        help='The url pointing to the oVirt Engine API end point')
    parser.add_argument('--ovirt-user', type=str, required=True,
                        help='The user to use to authenticate with the oVirt Engine')
    parser.add_argument('--ovirt-ca-pem-file', type=str, required=True,
                        help='Path to the ca pem file to use when connecting to tyhe engine')
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
    parser.add_argument('--ovirt-pass', const=DEFAULT_OVIRT_PASS_ENV_VAR, nargs='?',
                        type=str, default=DEFAULT_OVIRT_PASS_ENV_VAR,
                        help='Env variables to use to get the password to authenticate to oVirt')
    parser.add_argument('--pub-sshkey', const=DEFAULT_OVIRT_PUB_SSHKEY_ENV_VAR, nargs='?',
                        type=str, default=DEFAULT_OVIRT_PUB_SSHKEY_ENV_VAR,
                        help='Env variables to use to get the pub ssh key to use with cloud init')
    parser.add_argument('--num-of-iterations', const=20, nargs='?', type=int, default=20,
                        help='Number of iterations to wait for long VM operations (create & run)')
    parser.add_argument('--sleep-between-iterations', const=5, nargs='?', type=int, default=5,
                        help='sleep time between iterations iterations')

    args = parser.parse_args()
    if not os.environ.has_key(args.ovirt_pass):
        print ("No env var named '{env_var}' was found, \
               see option '--ovirt-pass'".format(env_var=args.ovirt_pass))
        sys.exit(-1)
    if not os.environ.has_key(args.pub_sshkey):
        print ("No env var named '{env_var}' was foundi, \
               see option --pub-sshkey".format(env_var=args.pub_sshkey))
        sys.exit(-1)

    do_work(args)

if __name__ == '__main__':
    main()
