#! /bin/bash
BUILD_DIR="${WORKSPACE}/${BUILD_ID}"
PV_FILE_TEMPLATE="${WORKSPACE}/pv-template.yaml"
INVENTORY_PATH="${BUILD_DIR}/inventory.ini"
OPENSHIFT_ANSIBLE_PATH="${BUILD_DIR}/openshift-ansible"
ENVIRONMENT_FILE="${BUILD_DIR}/environment"
ID_FILE="${WORKSPACE}/../id_rsa"
REDHAT_IT_ROOT_CA_PATH="/etc/pki/ca-trust/source/anchors/RH-IT-Root-CA.crt"
NAME_PREFIX="${NAME_PREFIX:-ocp}"
EXT_NFS_BASE_EXPORT_PATH_NORMALIZED=$(echo ${EXT_NFS_BASE_EXPORT_PATH} | sed 's./.\\/.g')
CLUSTER_EXT_NFS_BASE_EXPORT_PATH="${EXT_NFS_BASE_EXPORT_PATH_NORMALIZED}\/${NAME_PREFIX}"
CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED="${EXT_NFS_BASE_EXPORT_PATH}/${NAME_PREFIX}"
TMP_MNT_PATH="${BUILD_DIR}/mnt"
TMP_RESOURCE_DIR="${BUILD_DIR}/${NAME_PREFIX}_PVs"
PREDEFINED_PVS_TO_CREATE="registry metrics logging logging-ops prometheus prometheus-alertmanager prometheus-alertbuffer miq-app miq-db"
MANAGEIQ_IMAGE="${MANAGEIQ_IMAGE:-docker.io/containermgmt/manageiq-pods}"
SSH_ARGS="-o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPersist=600s"
WILDCARD_DNS_SERVICE="${WILDCARD_DNS_SERVICE:-xip.io}"
STORAGE_TYPE="${STORAGE_TYPE:-external_nfs}"

ansible --version


sudo_mkdir_if_not_exist () {
	DIRECTORY=${1}
	if [ ! -d "${DIRECTORY}" ]; then
		sudo mkdir "${DIRECTORY}"
	else
		echo "directory '${DIRECTORY}' already exist , skipping ..."
	fi
}



mkdir ${BUILD_DIR}
export| tee ${ENVIRONMENT_FILE}
echo "#######################################################################"
echo "# Running in: ${BUILD_DIR}"
echo "# Revision:   $(git log --oneline -1)"
echo "# Rerun with: "
echo ". ${ENVIRONMENT_FILE} ; $(realpath deployer)"
echo "#######################################################################"

if [ "${STORAGE_TYPE}" == "external_nfs" ]; then
    #Creting the different nfs exports on the external NFS server by mounting it locally
    mkdir ${TMP_MNT_PATH}
    sudo mount ${EXT_NFS_SERVER}:${EXT_NFS_BASE_EXPORT_PATH} ${TMP_MNT_PATH}
    sudo_mkdir_if_not_exist  "${TMP_MNT_PATH}/${NAME_PREFIX}"
    mkdir ${TMP_RESOURCE_DIR}
    cd ${TMP_MNT_PATH}/${NAME_PREFIX}
    for PV_FOLDER in ${PREDEFINED_PVS_TO_CREATE}
    do
	    sudo_mkdir_if_not_exist "${PV_FOLDER}"
    done
    for PV_FOLDER in `seq -f "vol-%03g" 1 ${NUM_OF_PVS}`
    do
	    sudo_mkdir_if_not_exist  "${PV_FOLDER}"
	    cp ${PV_FILE_TEMPLATE} ${TMP_RESOURCE_DIR}/${PV_FOLDER}.yaml
	    sed -i "s/#VOL_NAME#/${PV_FOLDER}/g" ${TMP_RESOURCE_DIR}/${PV_FOLDER}.yaml
	    sed -i "s/#EXPORT_BASE#/${CLUSTER_EXT_NFS_BASE_EXPORT_PATH}/g" ${TMP_RESOURCE_DIR}/${PV_FOLDER}.yaml
	    sed -i "s/#NFS_SERVER#/${EXT_NFS_SERVER}/g" ${TMP_RESOURCE_DIR}/${PV_FOLDER}.yaml

    done
    sudo chmod 777 *
    cd ${BUILD_DIR}
    sudo umount ${TMP_MNT_PATH}
fi



#
# Checkout openshift-ansible
#
(cd ${BUILD_DIR} && git clone $OPENSHIFT_ANSIBLE_REPO_URL $OPENSHIFT_ANSIBLE_PATH)

(cd $OPENSHIFT_ANSIBLE_PATH && exec git checkout -B deployment $OPENSHIFT_ANSIBLE_REF)

#
# Build inventory Variables for substitution
#
MASTER_HOSTNAME="${NAME_PREFIX}-master001.${MASTER_IP}.${WILDCARD_DNS_SERVICE}"

# Create inventory
set -e
if [ "$STORAGE_TYPE" == "internal_nfs" ]; then
    NFS_SERVER_PARAM=""  # NFS on the cluster master
else
    # NFS on a custom server (external or part of the cluster)
    NFS_SERVER_PARAM="--nfs-server=\"${EXT_NFS_SERVER}\""
fi
if [ "$STORAGE_TYPE" == "internal_nfs_custom" ]; then
    STORAGE_TYPE="internal_nfs"
fi
python "${WORKSPACE}/create_inventory.py" --master-ip="${MASTER_IP}" \
                                          --infra-ips="${INFRA_IPS}" \
                                          --compute-ips="${COMPUTE_IPS}" \
                                          --name-prefix="${NAME_PREFIX}" \
                                          --storage="${STORAGE_TYPE}" \
                                          --image-version="${DEPLOYERS_IMAGE_VERSION}" \
                                          --wildcard-dns="${WILDCARD_DNS_SERVICE}" \
                                          --enable-manageiq="${INSTALL_MANAGEIQ}" \
                                          --enable-metrics="${INSTALL_METRICS}" \
                                          --enable-logging="${INSTALL_LOGGING}" \
                                          --enable-loggingops="${INSTALL_LOGGING_OPS}" \
                                          --enable-prometheus="${INSTALL_PROMETHEUS}" \
                                          --additional-repos="${ADDITIONAL_REPOS}" \
                                          --additional-registries="${ADDITIONAL_INSECURE_REGISTRIES}" \
                                          --install-examples="${INSTALL_EXAMPLES}" \
                                          --ldap-providers="${LDAP_PROVIDERS}" \
                                          --ca-path="${REDHAT_IT_ROOT_CA_PATH}" \
                                          --nfs-export-path="${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}" \
                                          ${NFS_SERVER_PARAM} \
                                          --manageiq-image="${MANAGEIQ_IMAGE}" \
                                     > "${INVENTORY_PATH}"
set +e
echo "#######################################################################"
echo "# Using inventory: "
cat ${INVENTORY_PATH}
echo "#######################################################################"


if [ "${INSTALL_PROMETHEUS}" == "true" ]; then
    # We're installing Prometheus, this means we have to connect to all
    # nodes on the cluster to make sure the iscsi initator name is set correctly
    # and to collect the initator names so we can create the iscsi LUN.
    echo "Setting initator names..."
    INITATORS=""

    function set_iname() {
        NODE_TYPE=${1}
        NODE_NUMBER=${2}
        IP=${3}

        printf -v NODE_NUMBER_PADDED "%03d" "${NODE_NUMBER}"
        INAME="iqn.1994-05.com.redhat:${NAME_PREFIX}-${NODE_TYPE}${NODE_NUMBER_PADDED}"
        sshpass -p"${ROOT_PASSWORD}" ssh ${SSH_ARGS} "root@${IP}" "echo InitiatorName=${INAME} > /etc/iscsi/initiatorname.iscsi; systemctl restart iscsi.service"
        INITIATORS="${INITIATORS} ${INAME}"
    }

    set_iname master 1 ${MASTER_HOSTNAME}

    NODE_NUMBER=1;
    for IP in ${INFRA_IPS}; do
        set_iname infra ${NODE_NUMBER} "${IP}"
        NODE_NUMBER=$((NODE_NUMBER+1))
    done

    NODE_NUMBER=1;
    for IP in ${COMPUTE_IPS}; do
        set_iname compute ${NODE_NUMBER} "${IP}"
        NODE_NUMBER=$((NODE_NUMBER+1))
    done

    echo "Initiators: ${INITIATORS}"
    echo
    echo "Creating iscsi LUN..."

    set -e
    ISCSI_LUN_ID=$(python "${WORKSPACE}/lun_manager.py" --server="${NETAPP_SERVER}" \
                                                        --user="${NETAPP_USER}" \
                                                        --name="cm-${NAME_PREFIX}" \
                                                        --volume="${NETAPP_VOLUME}" \
                                                        --vserver="${NETAPP_VSERVER}" \
                                                        --size="${ISCSI_PV_SIZE}" \
                                                        --initiators="${INITIATORS}")
    set +e
    export ISCSI_LUN_ID
fi

RETRCODE=0
SSH_COMMAND="sshpass -p${ROOT_PASSWORD} ssh ${SSH_ARGS} root@${MASTER_HOSTNAME}"

sshpass -p${ROOT_PASSWORD} \
                ansible-playbook \
                  --user root \
                  --connection=ssh \
                  --ask-pass \
                  --private-key=${ID_FILE} \
                  --inventory=${INVENTORY_PATH} \
                  ${OPENSHIFT_ANSIBLE_PATH}/playbooks/byo/config.yml

if [ $? -ne '0' ]; then
  RETRCODE=1
else
    if [ "${INSTALL_PROMETHEUS}" == "true" ]; then
        echo "Creating iSCSI pv (for Prometheus)..."
        export ISCSI_TARGET_PORTAL
        export ISCSI_IQN
        envsubst < "${WORKSPACE}/iscsi-pv-template.yaml" > iscsi_pv.yaml
        sshpass -p${ROOT_PASSWORD} rsync -e "ssh ${SSH_ARGS}" -Pahvz iscsi_pv.yaml root@${MASTER_HOSTNAME}:
        ${SSH_COMMAND} oc create -f iscsi_pv.yaml
    fi
    if [ "${STORAGE_TYPE}" == "external_nfs" ]; then
          echo "Creating PVs..."
          sshpass -p${ROOT_PASSWORD} rsync -e "ssh ${SSH_ARGS}" -Pahvz ${TMP_RESOURCE_DIR} root@${MASTER_HOSTNAME}:

          PV_YAML_DIR=$(basename ${TMP_RESOURCE_DIR})

          for PV in $(seq -f "vol-%03g.yaml" 1 ${NUM_OF_PVS})
          do
            ${SSH_COMMAND} oc create -f ${PV_YAML_DIR}/${PV}
          done
    fi

    if [ "$INSTALL_MANAGEIQ" == "true" ] && [ "$CONFIGURE_MANAGEIQ_PROVIDER" == "true" ]; then
      echo "Checking out Ansible 2.4..."
      git clone https://github.com/ansible/ansible.git
      pushd ansible
      git checkout stable-2.4
      source hacking/env-setup
      popd
      ansible --version
      echo "Configuring OpenShift provider in ManageIQ..."

      export OPENSHIFT_HAWKULAR_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-infra' -o go-template --template='{{.spec.host}}' hawkular-metrics 2> /dev/null)"
      export OPENSHIFT_PROMETHEUS_ALERTS_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-metrics' -o go-template --template='{{.spec.host}}' alerts 2> /dev/null)"
      export OPENSHIFT_PROMETHEUS_METRICS_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-metrics' -o go-template --template='{{.spec.host}}' metrics 2> /dev/null)"
      export OPENSHIFT_CFME_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-management' -o go-template --template='{{.spec.host}}' httpd 2> /dev/null)"
      export OPENSHIFT_MASTER_HOST="$(${SSH_COMMAND} oc get nodes -o name |grep master |sed -e 's/nodes\///g')"
      export OPENSHIFT_CA_CRT="$(${SSH_COMMAND} cat /etc/origin/master/ca.crt)"
      export OPENSHIFT_MANAGEMENT_ADMIN_TOKEN="$(${SSH_COMMAND} oc sa get-token -n management-infra management-admin)"

      ansible-playbook --extra-vars "provider_name=${NAME_PREFIX} cfme_route=https://${OPENSHIFT_CFME_ROUTE}" ${WORKSPACE}/miqplaybook.yml
      if [ $? -ne '0' ]; then
        RETRCODE=1
      fi
    fi
fi

COUNTER=1
for URL in $PLUGIN_URLS
do
  echo "EXECUTING SCRIPT [${URL}] ON [${MASTER_HOSTNAME}]:"
  sshpass -p${ROOT_PASSWORD} \
                ssh ${SSH_ARGS} root@${MASTER_HOSTNAME} \
                wget --quiet -O /root/script_"$(printf %02d $COUNTER)".sh  ${URL}

  # -o ConnectTimeout=${TIMEOUT}
  sshpass -p${ROOT_PASSWORD} \
                ssh ${SSH_ARGS} root@${MASTER_HOSTNAME} bash script_$(printf %02d $COUNTER).sh
  if [ $? -ne '0' ]; then
    RETRCODE=1
  fi
  COUNTER=$((COUNTER+1))
done

exit ${RETRCODE}
