echo "management-admin token:"
oc sa get-token -n management-infra management-admin
echo ""

echo "OpenShift Master ca crtificate"
cat /etc/origin/master/ca.crt
echo ""
