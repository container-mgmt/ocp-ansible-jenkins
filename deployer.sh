#! /bin/bash
BUILD_DIR="${WORKSPACE}/${BUILD_ID}"
INVENTORY_TEMPLATE_PATH="${WORKSPACE}/inventory-template_ext_nfs.ini"
PV_FILE_TEMPLATE="${WORKSPACE}/pv-template.yaml"
INVENTORY_PATH="${BUILD_DIR}/inventory.ini"
OPENSHIFT_ANSIBLE_PATH="${BUILD_DIR}/openshift-ansible"
ENVIRONMENT_FILE="${BUILD_DIR}/environment"
ID_FILE="${WORKSPACE}/../id_rsa"
REDHAT_IT_ROOT_CA_PATH="/etc/pki/ca-trust/source/anchors/RH-IT-Root-CA.crt"
NAME_PREFIX=${NAME_PREFIX:ocp}
EXT_NFS_BASE_EXPORT_PATH_NORMALIZED=$(echo ${EXT_NFS_BASE_EXPORT_PATH} | sed 's./.\\/.g')
CLUSTER_EXT_NFS_BASE_EXPORT_PATH="${EXT_NFS_BASE_EXPORT_PATH_NORMALIZED}\/${NAME_PREFIX}"
CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED="${EXT_NFS_BASE_EXPORT_PATH}/${NAME_PREFIX}"
TMP_MNT_PATH="${BUILD_DIR}/mnt"
TMP_RESOURCE_DIR="${BUILD_DIR}/${NAME_PREFIX}_PVs"
PREDEFINED_PVS_TO_CREATE="registry metrics logging logging-ops prometheus prometheus-alertmanager prometheus-alertbuffer miq-app miq-db"
MANAGEIQ_IMAGE=${MANAGEIQ_IMAGE:docker.io/ilackarms/miq-app-frontend-unstable}
SSH_ARGS="-o StrictHostKeyChecking=no -o ControlMaster=auto -o ControlPersist=60s"

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





#
# Checkout openshift-ansible
#
(cd ${BUILD_DIR} && git clone $OPENSHIFT_ANSIBLE_REPO_URL $OPENSHIFT_ANSIBLE_PATH)

(cd $OPENSHIFT_ANSIBLE_PATH && exec git checkout -B deployment $OPENSHIFT_ANSIBLE_REF)

#
# Build inventory Variables for substitution
#
MASTER_HOSTNAME="${NAME_PREFIX}-master01.${MASTER_IP}.nip.io"
MASTER_HOST_SPEC="${MASTER_HOSTNAME} openshift_hostname=${MASTER_HOSTNAME}"

INFRA_HOST_SPEC_LIST=""
COUNTER=1
for INFRA_IP in $INFRA_IPS
do
  INFRA_HOST="${NAME_PREFIX}-infra$(printf %02d $COUNTER).${INFRA_IP}.nip.io"
  INFRA_HOST_SPEC_LIST="${INFRA_HOST_SPEC_LIST}${INFRA_HOST} openshift_hostname=${INFRA_HOST} openshift_node_labels=\"{'region': 'infra', 'zone': 'default'}\"
"
  INFRA_ROUTER_IP="${INFRA_IP}"
  COUNTER=$((COUNTER+1))
done
INFRA_ROUTER_IP=$(echo $INFRA_IPS | awk '{print $1;}')

COMPUTE_HOST_SPEC_LIST=""
COUNTER=1
for COMPUTE_IP in $COMPUTE_IPS
do
  COMPUTE_HOST="${NAME_PREFIX}-compute$(printf %02d $COUNTER).${COMPUTE_IP}.nip.io"
  COMPUTE_HOST_SPEC_LIST="${COMPUTE_HOST_SPEC_LIST}${COMPUTE_HOST} openshift_hostname=${COMPUTE_HOST} openshift_node_labels=\"{'region': 'primary', 'zone': 'default'}\"
"
  COUNTER=$((COUNTER+1))
done

METRICS_BLOCK="# no metrics"
if [ "$INSTALL_METRICS" == "true" ]; then
  METRICS_BLOCK="openshift_metrics_install_metrics=true
openshift_metrics_image_version=${DEPLOYERS_IMAGE_VERSION}
openshift_metrics_image_prefix=openshift3/
openshift_metrics_storage_kind=nfs
openshift_metrics_storage_host=${EXT_NFS_SERVER}
openshift_metrics_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_metrics_storage_volume_name=metrics
openshift_metrics_storage_labels={'storage': 'metrics'}"
fi

LOGGING_BLOCK="# no logging"
if [ "$INSTALL_LOGGING" == "true" ]; then
  LOGGING_BLOCK="openshift_logging_install_logging=true
openshift_logging_image_prefix=openshift3/
openshift_logging_image_version=${DEPLOYERS_IMAGE_VERSION}
openshift_logging_storage_kind=nfs
openshift_logging_storage_host=${EXT_NFS_SERVER}
openshift_logging_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_logging_storage_volume_name=logging
openshift_logging_storage_labels={'storage': 'logging'}"
fi

LOGGING_OPS_BLOCK="# no logging ops"
if [ "$INSTALL_LOGGING_OPS" == "true" ]; then
  LOGGING_OPS_BLOCK="openshift_logging_enable_ops_cluster=true
openshift_loggingops_storage_kind=nfs
openshift_loggingops_storage_host=${EXT_NFS_SERVER}
openshift_loggingops_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_loggingops_storage_volume_name=logging-ops
openshift_loggingops_storage_labels={'storage': 'logging-ops'}"
fi

PROMETHEUS_BLOCK="# no prometheus"
if [ "$INSTALL_PROMETHEUS" == "true" ]; then
  PROMETHEUS_BLOCK="openshift_hosted_prometheus_deploy=true
openshift_prometheus_image_prefix=openshift3/
openshift_prometheus_storage_kind=nfs
openshift_prometheus_storage_host=${EXT_NFS_SERVER}
openshift_prometheus_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_prometheus_storage_volume_name=prometheus
openshift_prometheus_storage_labels={'storage': 'prometheus'}
openshift_prometheus_storage_type=pvc

openshift_prometheus_alertmanager_image_prefix=openshift3/
openshift_prometheus_alertmanager_storage_kind=nfs
openshift_prometheus_alertmanager_storage_host=${EXT_NFS_SERVER}
openshift_prometheus_alertmanager_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_prometheus_alertmanager_storage_volume_name=prometheus-alertmanager
openshift_prometheus_alertmanager_storage_labels={'storage': 'prometheus-alertmanager'}
openshift_prometheus_alertmanager_storage_type=pvc

openshift_prometheus_alertbuffer_image_prefix=openshift3/
openshift_prometheus_alertbuffer_storage_kind=nfs
openshift_prometheus_alertbuffer_storage_host=${EXT_NFS_SERVER}
openshift_prometheus_alertbuffer_storage_nfs_directory=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
openshift_prometheus_alertbuffer_storage_volume_name=prometheus-alertbuffer
openshift_prometheus_alertbuffer_storage_labels={'storage': 'prometheus-alertbuffer'}
openshift_prometheus_alertbuffer_storage_type=pvc

openshift_prometheus_proxy_image_prefix=openshift3/
"
fi

MANAGEIQ_BLOCK="# No ManageIQ"
if [ "$INSTALL_MANAGEIQ" == "true" ]; then
  MANAGEIQ_BLOCK="openshift_management_install_management=true
openshift_management_app_template=cfme-template
openshift_management_template_parameters={'APPLICATION_IMG_NAME': '${MANAGEIQ_IMAGE}', 'FRONTEND_APPLICATION_IMG_TAG': 'latest'}
openshift_management_install_beta=true
openshift_management_storage_class=nfs_external
openshift_management_storage_nfs_external_hostname=${EXT_NFS_SERVER}
openshift_management_storage_nfs_base_dir=${CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED}
"
fi

#
# Substitute variables
#
export ADDITIONAL_INSECURE_REGISTRIES
export ADDITIONAL_REPOS
export COMPUTE_HOST_SPEC_LIST
export DEPLOYERS_IMAGE_VERSION
export INFRA_HOST_SPEC_LIST
export INFRA_ROUTER_IP
export INSTALL_EXAMPLES
export LDAP_PROVIDERS
export MASTER_HOST_SPEC
export REDHAT_IT_ROOT_CA_PATH
export EXT_NFS_SERVER
export EXT_NFS_BASE_EXPORT_PATH
export CLUSTER_EXT_NFS_BASE_EXPORT_PATH_UNESCAPED
export METRICS_BLOCK
export LOGGING_BLOCK
export LOGGING_OPS_BLOCK
export PROMETHEUS_BLOCK
export MANAGEIQ_BLOCK

envsubst < ${INVENTORY_TEMPLATE_PATH} > ${INVENTORY_PATH}

echo "#######################################################################"
echo "# Using inventory: "
cat ${INVENTORY_PATH}
echo "#######################################################################"

RETRCODE=0

sshpass -p${ROOT_PASSWORD} \
                ansible-playbook \
                  --user root \
                  --connection=ssh \
                  --ask-pass \
                  --private-key=${ID_FILE} \
                  --inventory=${INVENTORY_PATH} \
                  ${OPENSHIFT_ANSIBLE_PATH}/playbooks/byo/config.yml

SSH_COMMAND="sshpass -p${ROOT_PASSWORD} ssh ${SSH_ARGS} root@${MASTER_HOSTNAME}"

if [ $? -ne '0' ]; then
  RETRCODE=1
else
  echo "Creating PVs..."
  sshpass -p${ROOT_PASSWORD} rsync -e "ssh ${SSH_ARGS}" -Pahvz ${TMP_RESOURCE_DIR} root@${MASTER_HOSTNAME}:

  PV_YAML_DIR=`basename ${TMP_RESOURCE_DIR}`

  for PV in `seq -f "vol-%03g.yaml" 1 ${NUM_OF_PVS}`
  do
    ${SSH_COMMAND} oc create -f ${PV_YAML_DIR}/${PV}
  done
fi


if [ "$INSTALL_MANAGEIQ" == "true" ]; then
  echo "Configuring OpenShift provider in ManageIQ..."

  HAWKULAR_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-infra' -o go-template --template='{{.spec.host}}' hawkular-metrics 2> /dev/null)"
  PROMETHEUS_ALERTS_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-metrics' -o go-template --template='{{.spec.host}}' alerts 2> /dev/null)"
  HTTPD_ROUTE="$(${SSH_COMMAND}  oc get route --namespace='openshift-management' -o go-template --template='{{.spec.host}}' httpd 2> /dev/null)"
  CA_CRT="$(${SSH_COMMAND} cat /etc/origin/master/ca.crt)"
  OC_TOKEN="$(${SSH_COMMAND} oc sa get-token -n management-infra management-admin)"

  sshpass -p${ROOT_PASSWORD} \
                ansible-playbook \
                  --user root \
                  --connection=ssh \
                  --ask-pass \
                  --private-key=${ID_FILE} \
                  --inventory=${INVENTORY_PATH} \
                  --extra-vars \
                    "provider_name=OCP_with_Prometheus \
                    mgmt_infra_sa_token=${OC_TOKEN} \
                    ca_crt=\"${CA_CRT}\" \
                    oo_first_master=${MASTER_HOSTNAME} \
                    httpd_route=${HTTPD_ROUTE} \
                    hawkular_route=${HAWKULAR_ROUTE} \
                    alerts_route=${PROMETHEUS_ALERTS_ROUTE}" \
                ${WORKSPACE}/miqplaybook.yml
  if [ $? -ne '0' ]; then
    RETRCODE=1
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
