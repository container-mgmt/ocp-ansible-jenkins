#!/usr/bin/env bash

#
# Run from the parent library of this repo
# ./openshift-ansible-deployment/deployer-test.sh
#

BUILD_ID=8
OPENSHIFT_ANSIBLE_REPO_URL=https://github.com/openshift/openshift-ansible
OPENSHIFT_ANSIBLE_REF=openshift-ansible-3.6.140-1
MASTER_IP=10.35.48.200
INFRA_IPS="10.35.48.201 10.35.48.202"
COMPUTE_IPS="10.35.48.203 10.35.48.204"
WORKSPACE=$(realpath ../test_workspace)
ADDITIONAL_REPOS="[{'id': 'example', 'name': 'EXAMPLE', 'baseurl': 'http://example.com/$basearch/os', 'enabled': 1, 'gpgcheck': 0}, {'id': 'fast-datapath', 'name': 'Fast Datapath', 'baseurl': 'http://pulp.dist.prod.ext.phx2.redhat.com/content/dist/rhel/server/7/7Server/$basearch/fast-datapath/os', 'enabled': 1, 'gpgcheck': 0}]"
ROOT_PASSWORD="qum5net"
DEPLOYERS_VERSION=v3.6

# Imitate jenkins, works only with THIS repository and master
rm -rf ${WORKSPACE}/*
mkdir ${WORKSPACE}
cp -r ../ocp-ansible-jenkins/* ${WORKSPACE}/

. ${WORKSPACE}/deployer.sh