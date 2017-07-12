BUILD_DIR="${WORKSPACE}/${BUILD_ID}"
INVENTORY_TEMPLATE_PATH="${WORKSPACE}/inventory-template.ini"
INVENTORY_PATH="${BUILD_DIR}/inventory.ini"
COPY_ID="${WORKSPACE}/copy-id.sh"
OPENSHIFT_ANSIBLE_PATH="${BUILD_DIR}/openshift-ansible"
ID_FILE="${WORKSPACE}/../id_rsa"
REDHAT_IT_ROOT_CA_PATH="/etc/pki/ca-trust/source/anchors/RH-IT-Root-CA.crt"

ansible --version
env

mkdir ${BUILD_DIR}
echo "#######################################################################"
echo "# Running in: ${BUILD_DIR}"
echo "# Revision:   $(git log --oneline -1)"
echo "#######################################################################"

#
# Checkout openshift-ansible
#
(cd ${BUILD_DIR} && git clone $OPENSHIFT_ANSIBLE_REPO_URL $OPENSHIFT_ANSIBLE_PATH)

(cd $OPENSHIFT_ANSIBLE_PATH && exec git checkout -B deployment $OPENSHIFT_ANSIBLE_REF)

#
# Build inventory Variables for substitution
#
MASTER_HOSTNAME="ocp-master.${MASTER_IP}.nip.io"
MASTER_HOST_SPEC="${MASTER_HOSTNAME} openshift_hostname=${MASTER_HOSTNAME}"

INFRA_HOST_SPEC_LIST=""
COUNTER=1
for INFRA_IP in $INFRA_IPS
do
  INFRA_HOST="ocp-infra${COUNTER}.${INFRA_IP}.nip.io"
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
  COMPUTE_HOST="ocp-compute${COUNTER}.${COMPUTE_IP}.nip.io"
  COMPUTE_HOST_SPEC_LIST="${COMPUTE_HOST_SPEC_LIST}${COMPUTE_HOST} openshift_hostname=${COMPUTE_HOST} openshift_node_labels=\"{'region': 'primary', 'zone': 'default'}\"
"
  COUNTER=$((COUNTER+1))
done

export MASTER_HOST_SPEC REDHAT_IT_ROOT_CA_PATH INFRA_ROUTER_IP DEPLOYERS_IMAGE_VERSION ADDITIONAL_REPOS
export MASTER_HOST_SPEC INFRA_HOST_SPEC_LIST COMPUTE_HOST_SPEC_LIST

envsubst < ${INVENTORY_TEMPLATE_PATH} > ${INVENTORY_PATH}
echo "#######################################################################"
echo "# Using inventory: "
cat ${INVENTORY_PATH}
echo "#######################################################################"

sshpass -p${ROOT_PASSWORD} \
                ansible-playbook \
                  --user root \
                  --connection=ssh \
                  --ask-pass \
                  --private-key=${ID_FILE} \
                  --inventory=${INVENTORY_PATH} \
                  ${OPENSHIFT_ANSIBLE_PATH}/playbooks/byo/config.yml
