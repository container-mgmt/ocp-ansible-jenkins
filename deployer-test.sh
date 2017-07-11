#!/usr/bin/env bash

#
# Run from the parent library of this repo
# ./openshift-ansible-deployment/deployer-test.sh
#

ADDITIONAL_INSECURE_REGISTRIES="example.com:8888"
ADDITIONAL_REPOS="[{'id': 'example', 'name': 'EXAMPLE', 'baseurl': 'http://example.com/$basearch/os', 'enabled': 1, 'gpgcheck': 0}]"
BUILD_ID=8
COMPUTE_IPS="10.35.48.203 10.35.48.204"
DEPLOYERS_VERSION=v3.6
INFRA_IPS="10.35.48.201 10.35.48.202"
MASTER_IP=10.35.48.200
OPENSHIFT_ANSIBLE_REF=openshift-ansible-3.6.140-1
OPENSHIFT_ANSIBLE_REPO_URL=https://github.com/openshift/openshift-ansible
ROOT_PASSWORD="pass"
WORKSPACE=$(realpath ../test_workspace)

# Imitate jenkins, works only with THIS repository and master
rm -rf ${WORKSPACE}/*
mkdir ${WORKSPACE}
cp -r ../ocp-ansible-jenkins/* ${WORKSPACE}/

. ${WORKSPACE}/deployer.sh