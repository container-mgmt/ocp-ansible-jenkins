echo "management-admin token:"
oc sa get-token -n management-infra management-admin
echo ""

echo "OpenShift Master ca crtificate"
cat /etc/origin/master/ca.crt
echo ""

echo HAWKULAR_ROUTE=\"$(oc get route --namespace='openshift-infra' -o go-template --template='{{.spec.host}}' hawkular-metrics 2> /dev/null)\"
echo PROMETHEUS_ALERTS_ROUTE=\"$(oc get route --namespace='openshift-metrics' -o go-template --template='{{.spec.host}}' alerts 2> /dev/null)\"
echo PROMETHEUS_METRICS_ROUTE=\"$(oc get route --namespace='openshift-metrics' -o go-template --template='{{.spec.host}}' prometheus 2> /dev/null)\"
echo OSH_HOST=\"$(oc get nodes -o name |grep master |sed -e 's/nodes\///g')\"
echo OSH_TOKEN=\"$(oc sa get-token -n management-infra management-admin)\"
echo OSH_CERT=\""$(cat /etc/origin/master/ca.crt)"\"
