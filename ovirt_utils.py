# -*- coding: utf-8 -*-
# ovirt_utils.py - Varius utility functions for ovirt
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
import ovirtsdk4
import re

# CONSTANTS

DEFAULT_OVIRT_PASS_ENV_VAR = "OV_PASS"
CLUSTER_PATTERN = re.compile("^(.*)-(?:infra|compute|master)[0-9]+")
POOL_PATTERN = re.compile("^(.*)-[0-9]+")


def add_ovirt_args(parser, required=False):
    """ Add ovirt arguments to an argumentparser """
    parser.add_argument('--ovirt-url', type=str, required=required,
                        help='The url pointing to the oVirt Engine API end point')
    parser.add_argument('--ovirt-user', type=str, required=required,
                        help='The user to use to authenticate with the oVirt Engine')
    parser.add_argument('--ovirt-ca-pem-file', type=str, required=required,
                        help='Path to the ca pem file to use when connecting to tyhe engine')
    parser.add_argument('--ovirt-pass', const=DEFAULT_OVIRT_PASS_ENV_VAR, nargs='?',
                        type=str, default=DEFAULT_OVIRT_PASS_ENV_VAR,
                        help='Env variables to use to get the password to authenticate to oVirt')


def get_vm_clusters(ovirt_url, ovirt_user, ovirt_ca, ovirt_pass):
    """ Get all openshift clusters on the ovirt """
    ret = set()
    try:
        connection = ovirtsdk4.Connection(url=ovirt_url, username=ovirt_user,
                                          password=ovirt_pass, ca_file=ovirt_ca)
        vms_service = connection.system_service().vms_service()
        for vm in vms_service.list():
            match = CLUSTER_PATTERN.match(vm.name)
            pool_match = POOL_PATTERN.match(vm.name)
            if match is not None:
                ret.add(match.group(1))
            elif pool_match is not None:
                ret.add(pool_match.group(1))
    finally:
        if connection:
            connection.close()
    return ret
