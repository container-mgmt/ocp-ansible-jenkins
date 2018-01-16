#!/usr/bin/env python2
# -*- coding: utf-8 -*-
# netapp_iscsi_lun_manager.py
#
# Copyright © 2018 Red Hat, Inc.
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

from __future__ import unicode_literals, print_function
import argparse
import paramiko
import sys
import ovirtsdk4
import re
import os
from paramiko import SSHClient

DEFAULT_OVIRT_PASS_ENV_VAR = "OV_PASS"
cluster_pattern = re.compile("^(.*)-(?:infra|compute|master)[0-9]+")


def exec_command(client, command):
    """ execute a command on an ssh client, return the output streams """
    stdin, stdout, stderr = client.exec_command(command)
    out = stdout.read().strip()
    err = stderr.read().strip()
    if out:
        print(out, file=sys.stderr)
    if err:
        print(err, file=sys.stderr)
    return out, err


def create_lun(client, volume, vserver, lun_name, size):
    """ Create a LUN """
    command = "lun create -vserver {0} -volume {1} -lun {2} -size {3} -ostype linux"
    command = command.format(vserver, volume, lun_name, size)
    out, err = exec_command(client, command)
    if not out.startswith("Created a LUN of size"):
        raise Exception("Lun creation failed\n" + out + '\n' + err)


def create_igroup(client, vserver, igroup_name, initator_list):
    """ Create an igroup """
    command = "igroup create -vserver {0} -igroup {1} -protocol iscsi  -ostype linux -initiator {2}"
    command = command.format(vserver, igroup_name, ", ".join(initator_list))
    out, err = exec_command(client, command)
    if out or err:
        raise Exception("igroup creation failed!")


def _mapping(mode, client, vserver, volume, lun_name, igroup_name):
    if mode not in ["delete", "create"]:
        raise ValueError(mode)

    command = "mapping {0} -vserver {1} -volume {2} -lun {3} -igroup {4}"
    command = command.format(mode, vserver, volume, lun_name, igroup_name)
    out, err = exec_command(client, command)
    if out != "(lun mapping {0})".format(mode):
        raise Exception("mapping {0} failed".format(mode))


def map_lun(client, vserver, volume, lun_name, igroup_name):
    """ Map LUN to igroup """
    _mapping("create", client, vserver, volume, lun_name, igroup_name)

    # Find the lun ID (useful for the PV file)
    out, err = exec_command(client, "mapping show")
    for line in out.splitlines():
        splitted = line.split()
        if splitted[2] == lun_name:
            print(splitted[3])
            return

    raise Exception("Could not find LUN ID number")


def delete_lun_mapping(client, vserver, volume, lun_name, igroup_name):
    """ Delete LUN mapping """
    _mapping("delete", client, vserver, volume, lun_name, igroup_name)


def delete_lun(client, volume, vserver, lun_name):
    """ Delete a LUN """
    command = "lun delete -vserver {0} -volume {1} -lun {2} -force"
    command = command.format(vserver, volume, lun_name)
    out, err = exec_command(client, command)
    if out or err:
        raise Exception("Lun deletion failed\n" + out + '\n' + err)


def delete_igroup(client, vserver, igroup_name):
    """ Delete an igroup """
    command = "igroup delete -vserver {0} -igroup {1}"
    command = command.format(vserver, igroup_name)
    out, err = exec_command(client, command)
    if out or err:
        raise Exception("igroup deletion failed!")


def get_luns(client, vserver):
    """ Get a list of LUNs from the NetApp server """
    out, err = exec_command(client, "lun show -vserver {0}".format(vserver))
    if "Error" in out:
        raise Exception("Can't get luns: {0}".format(out))
    ret = []
    for line in out.splitlines():
        splitted = line.strip().split()
        if len(splitted) < 2:
            continue
        if splitted[0] != vserver:
            # If the line doesn't start with the vserver name, it's probably
            # a warning or the header
            continue
        path = splitted[1].split('/')
        ret.append({"volume": path[2], "name": path[3]})
    return ret


def get_vm_clusters(ovirt_url, ovirt_user, ovirt_ca, ovirt_pass):
    """ Get all openshift clusters on the ovirt """
    ret = set()
    try:
        connection = ovirtsdk4.Connection(url=ovirt_url, username=ovirt_user,
                                          password=ovirt_pass, ca_file=ovirt_ca)
        vms_service = connection.system_service().vms_service()
        for vm in vms_service.list():
            match = cluster_pattern.match(vm.name)
            if match is not None:
                ret.add(match.group(1))
    finally:
        if connection:
            connection.close()
    return ret


def cleanup(client, vserver, ovirt_url, ovirt_user, ovirt_ca, ovirt_pass):
    clusters = get_vm_clusters(ovirt_url, ovirt_user, ovirt_ca, ovirt_pass)
    print("Found {0} clusters".format(len(clusters)))
    to_delete = []
    for lun in get_luns(client, vserver):
        # split to remove lun prfix from the search
        if lun['name'].split('-', 1)[1] not in clusters:
            to_delete.append(lun)

    print("Will delete {0} LUNs".format(len(to_delete)))
    for lun in to_delete:
        print("Deleting lun {0}".format(lun['name']))
        delete_lun_mapping(client, vserver, lun['volume'], lun['name'], lun['name'])
        delete_igroup(client, vserver, lun['name'])
        delete_lun(client, lun['volume'], vserver, lun['name'])


def main():
    parser = argparse.ArgumentParser(description='Manage LUNs, mappings and igroups on a NetApp cluster')

    # netapp parameters
    parser.add_argument('--server', nargs='?', type=str, help="NetApp server address", required=True)
    parser.add_argument('--username', nargs='?', type=str, help="Username for the NetApp cluster", required=True)
    parser.add_argument('--action', nargs='?', choices=["create", "delete", "clean"], default="create")
    parser.add_argument('--name', nargs='?', type=str, help="LUN name")
    parser.add_argument('--volume', nargs='?', type=str)
    parser.add_argument('--vserver', nargs='?', type=str, help="vserver for the LUN")
    parser.add_argument('--size', nargs='?', type=str, help="LUN Size")
    parser.add_argument('--initiators', nargs='?', type=str, help="List of initiators for the lun igroup")

    # ovirt parameters, only required for "cleanup" mode
    parser.add_argument('--ovirt-url', type=str,
                        help='The url pointing to the oVirt Engine API end point')
    parser.add_argument('--ovirt-user', type=str,
                        help='The user to use to authenticate with the oVirt Engine')
    parser.add_argument('--ovirt-ca-pem-file', type=str,
                        help='Path to the ca pem file to use when connecting to tyhe engine')
    parser.add_argument('--ovirt-pass', const=DEFAULT_OVIRT_PASS_ENV_VAR, nargs='?',
                        type=str, default=DEFAULT_OVIRT_PASS_ENV_VAR,
                        help='Env variables to use to get the password to authenticate to oVirt')

    args = parser.parse_args()
    if args.action == "create":
        if not args.name or not args.volume or not args.vserver or not args.size or not args.initiators:
            raise SystemExit("name, volume, vserver, size and initators are required for create")
    elif args.action == "delete":
        if not args.name or not args.volume or not args.vserver:
            raise SystemExit("name, volume and vserver are required for delete")
    elif args.action == "clean":
        if not args.ovirt_url or not args.ovirt_user or not args.ovirt_ca_pem_file:
            raise SystemExit("missing ovirt arguments")
        if args.ovirt_pass not in os.environ:
            raise SystemExit("missing ovirt password env var")

    client = SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.WarningPolicy())

    try:
        client.connect(args.server, username=args.username)
        exec_command(client, "rows 0")  # For easier output parsing

        if args.action == "create":
            # Creating a new LUN
            create_lun(client, args.volume, args.vserver, args.name, args.size)
            create_igroup(client, args.vserver, args.name, args.initiators.split())
            map_lun(client, args.vserver, args.volume, args.name, args.name)
        elif args.action == "delete":
            # Deleting a LUN
            delete_lun_mapping(client, args.vserver, args.volume, args.name, args.name)
            delete_igroup(client, args.vserver, args.name)
            delete_lun(client, args.volume, args.vserver, args.name)
        elif args.action == "clean":
            cleanup(client, args.vserver, args.ovirt_url, args.ovirt_user,
                    args.ovirt_ca_pem_file, os.environ[args.ovirt_pass])

        print("Done!", file=sys.stderr)
    finally:
        client.close()


if __name__ == "__main__":
    main()
