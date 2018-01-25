# -*- coding: utf-8 -*-
# get_clusters.py - Get list of Openshift clusters from an ovirt host
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
import argparse
import os
import ovirt_utils


def main():
    parser = argparse.ArgumentParser(description='Get list of Openshift clusters from an ovirt host')
    ovirt_utils.add_ovirt_args(parser, required=True)
    parser.add_argument('--mountpoint', type=str, required=True,
                        help='Path to the NFS PV mount')
    args = parser.parse_args()
    current_clusters = set(ovirt_utils.get_vm_clusters(args.ovirt_url, args.ovirt_user,
                                                       args.ovirt_ca_pem_file,
                                                       os.environ[args.ovirt_pass]))

    cluster_directories_on_nfs = set(os.listdir(args.mountpoint))

    to_delete = cluster_directories_on_nfs - current_clusters
    print(' '.join(to_delete))


if __name__ == "__main__":
    main()
