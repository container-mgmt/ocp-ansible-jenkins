#!/usr/bin/env python
# -*- coding: utf-8 -*-
# create_inventory.py - Create inventory file for openshift-ansible
#
# Copyright © 2017 Red Hat Inc.
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
import ipaddress
import argparse
import sys
import os.path

# These are compoments that a user can disable or enable
OPTIONAL_COMPONENTS = ['logging', 'loggingops', 'metrics', 'prometheus', 'manageiq']

# These are components that are mandatory
MANDATORY_COMPONENTS = ['hosted_registry']


ALL_COMPONENTS = MANDATORY_COMPONENTS + OPTIONAL_COMPONENTS

DEFAULT_IMAGE_VERSION = 'v3.7'
DEFAULT_WILDCARD_DNS = 'nip.io'

PATH = os.path.dirname(os.path.abspath(__file__))
BLOCKS_PATH = os.path.join(PATH, "inventory_blocks")


def str2bool(s):
    """ Convert str argument to bool """
    if s.lower() in ('', 'yes', 'true', 't', 'y', '1'):
        return True
    elif s.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def validate_ip(ipaddr):
    """ Ensure a given IP address is valid """
    try:
        ipaddress.ip_address(u''+ipaddr)
        return True
    except ValueError:
        return False


def validate_ips(ips, name):
    """ Validate ip addresses and return a list of invalid ones """
    invalid = []
    for ip in ips:
        if not validate_ip(ip):
            print("Invalid ip '{0}' in {1}".format(ip, name), file=sys.stderr)
            invalid.append(ip)
    return invalid


def format_host(node_type, name_prefix, index, ip, wildcard_dns):
    """ Build a hostname for a node """
    host = "{name_prefix}-{node_type}{i:03d}.{ip}.{wildcard_dns}"
    host = host.format(name_prefix=name_prefix,
                       node_type=node_type,
                       i=index,
                       ip=ip,
                       wildcard_dns=wildcard_dns)
    if len(host) > 63:
        raise SystemExit("hostname too long: {0}".format(host))
    return host


def build_spec(node_type, ips, name_prefix, wildcard_dns):
    """ Build spec for compute/infra nodes """
    spec_list = ""
    if node_type == "infra":
        node_labels = "{'region': 'infra', 'zone': 'default', 'node-role.kubernetes.io/infra': 'true'}"
    else:
        node_labels = "{'region': 'primary', 'zone': 'default', 'node-role.kubernetes.io/compute': 'true'}"

    for i, ip in enumerate(ips, 1):
        host = format_host(node_type, name_prefix, i, ip, wildcard_dns)
        spec = "{host} openshift_hostname={host} openshift_node_labels=\"{node_labels}\"\n"
        spec = spec.format(node_labels=node_labels, host=host)
        spec_list += spec
    return spec_list


def format_block(component, storage_type, format_args):
    """ Format the block from the templates """

    # Main block - settings that are required no matter what is the storage type
    block_file = BLOCKS_PATH + "/{0}.ini".format(component)

    if not os.path.exists(block_file):
        block_file = BLOCKS_PATH + "/DEFAULT.ini"

    with open(block_file, 'r') as f:
        component_block_template = f.read()

    # Storage_type specific settings
    storage_block_file = BLOCKS_PATH + "/{component}_{storage}.ini".format(component=component,
                                                                           storage=storage_type)
    if not os.path.exists(storage_block_file):
        storage_block_file = BLOCKS_PATH + "/DEFAULT_{0}.ini".format(storage_type)

    with open(storage_block_file, 'r') as f:
        component_block_template += '\n'
        component_block_template += f.read()

    format_args['component'] = component
    return component_block_template.format(**format_args)


def create_inventory(master, infra, compute, args):
    """ Create inventory file from template. `args` are the command line arguments """

    # Build host specs
    master_hostname = format_host("master", args.name_prefix, 1, master,
                                  args.wildcard_dns)
    node_labels = "{'node-role.kubernetes.io/infra': 'true', 'node-role.kubernetes.io/master': 'true'}"
    master_spec = "{master_hostname} openshift_hostname={master_hostname} openshift_node_labels=\"{node_labels}\"".format(node_labels=node_labels, master_hostname=master_hostname)

    # prepare arguments for formatting the template
    format_args = vars(args)  # start with the command line arguments

    # Build the spec for the nodes
    format_args['master_hostname'] = master_hostname
    format_args['master_spec'] = master_spec
    format_args['infra_spec'] = build_spec("infra", infra, args.name_prefix, args.wildcard_dns)
    format_args['compute_spec'] = build_spec("compute", compute, args.name_prefix, args.wildcard_dns)
    format_args['infra_router_ip'] = infra[0]

    if args.storage == 'internal_nfs':
        # Add "nfs" to OSv3:children
        format_args['nfs_child'] = 'nfs'
        # Add the nfs block and point it to the selected NFS server
        # (or master, if nfs server is not defined)
        if not args.nfs_server:
            format_args['nfs_block'] = '[nfs]\n' + master_spec
        else:
            format_args['nfs_block'] = '[nfs]\n' + args.nfs_server
    else:
        # No internal NFS
        format_args['nfs_child'] = ''
        format_args['nfs_block'] = ''

    # Build the component blocks
    for component in ALL_COMPONENTS:
        if component in OPTIONAL_COMPONENTS and not format_args['enable_' + component]:
            # This component is optional and is disabled
            format_args[component + '_block'] = "# No {0}".format(component)
            continue

        # This componet is enabled, fromat the block
        format_args[component + '_block'] = format_block(component,
                                                         args.storage,
                                                         format_args)

    # read the main template

    with open(PATH+"/inventory-template.ini", "r") as f:
        template = f.read()

    print(template.format(**format_args))


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Build inventory file for openshift-ansible')

    # options for storage
    parser.add_argument('--storage', nargs='?', default="external_nfs",
                        choices=['external_nfs', 'internal_nfs'])
    parser.add_argument('--nfs-server', nargs='?', type=str)
    parser.add_argument('--nfs-export-path', nargs='?', type=str)

    # Enable/Disable various components
    for component in OPTIONAL_COMPONENTS:
        is_default = component != "manageiq"
        parser.add_argument('--enable-{0}'.format(component), nargs='?',
                            type=str2bool, const=True, default=is_default)
    parser.add_argument('--install-examples', const=True, nargs='?', type=str2bool, default=True)

    # optional parameters
    parser.add_argument('--additional-registries', type=str, default="")
    parser.add_argument('--internal-registry', type=str, default="")
    parser.add_argument('--additional-repos', type=str, default="")
    parser.add_argument('--image-version', type=str, default=DEFAULT_IMAGE_VERSION)
    parser.add_argument('--ldap-providers', type=str, default="")
    parser.add_argument('--ca-path', type=str, default="")
    parser.add_argument('--wildcard-dns', type=str, default=DEFAULT_WILDCARD_DNS)
    parser.add_argument('--manageiq-image', type=str, default="docker.io/containermgmt/manageiq-pods")

    # Mandatory parameters: cluster IPs, name prefix
    parser.add_argument('--name-prefix', type=str, required=True)
    parser.add_argument('--master-ip', type=str, required=True)
    parser.add_argument('--infra-ips', type=str, required=True)
    parser.add_argument('--compute-ips', type=str, required=True)

    args = parser.parse_args()

    # Make sure external NFS is properly defined
    if args.storage == "external_nfs":
        if args.nfs_server is None or args.nfs_export_path is None:
            raise SystemExit("--nfs-server and --nfs-export-path are required when storage is set to ext_nfs")

    # Validate IPs and provide detailed information if any is invalid
    master = args.master_ip.strip()
    infra_list = args.infra_ips.strip().split(" ")
    compute_list = args.compute_ips.strip().split(" ")

    invalid = []
    invalid += validate_ips([master], "master")
    invalid += validate_ips(infra_list, "infra")
    invalid += validate_ips(compute_list, "compute")

    if invalid:
        raise SystemExit("Can't create inventory: {0} invalid IPs specified".format(len(invalid)))

    if master in infra_list or master in compute_list:
        raise SystemExit("Can't create inventory: Master IP ({0}) present in compute / infra".format(master))

    if not set(infra_list).isdisjoint(compute_list):
        raise SystemExit("Can't create inventory: Same IP used for both an infra node and a compute node. This is not supported.")

    create_inventory(master, infra_list, compute_list, args)

if __name__ == "__main__":
    main()
