#!/usr/bin/env bash
# This script cleans NFS mounts and iSCSI PVs that belong to non-existing clusters
# it assumes that the "name prefix" used to deploy the cluster is used in the
# vms names in ovirt.

# "Bash strict mode" settings - http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -e          # exit on error (like a normal programming langauge)
set -u          # fail when undefined variables are used
set -o pipefail # prevent errors in a pipeline from being masked


function unmount {
    set +e
    sudo umount nfsmount
    rmdir nfsmount
}
# Make sure NFS is always unmounted, even if we exit early
trap umount EXIT

echo "Cleaning up LUNs..."

python lun_manager.py --server="${NETAPP_SERVER}" \
                      --user="${NETAPP_USER}" \
                      --vserver="${NETAPP_VSERVER}" \
                      --ovirt-url="${OVIRT_URL}"\
                      --ovirt-user="${OVIRT_USER}"\
                      --ovirt-ca-pem-file="${PEMFILE}"
                      --action=clean


echo "Cleaning up NFS..."
mkdir nfsmount
MOUNT_PATH="$(realpath nfsmount)"
sudo mount "${EXT_NFS_SERVER}":"${EXT_NFS_BASE_EXPORT_PATH}" nfsmount


TO_DELETE=$(python get_clusters_to_delete.py --ovirt-url="${OVIRT_URL}"\
                                             --ovirt-user="${OVIRT_USER}"\
                                             --ovirt-ca-pem-file="${PEMFILE}"\
                                             --mountpoint="${MOUNT_PATH}")

for CLUSTER_DIRECTORY in ${TO_DELETE}; do
    echo "Deleting ${CLUSTER_DIRECTORY}..."
    rm -rf "${CLUSTER_DIRECTORY}"
done

echo "Done"
