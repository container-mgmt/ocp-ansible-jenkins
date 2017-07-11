

TODO: enable repo url

wget https://raw.githubusercontent.com/zgalor/origin/bc74c7c6c03199c9462d2a01808fd5b956238132/examples/prometheus/prometheus.yaml
oc create namespace prometheus
oc process -p NAMESPACE="prometheus"  -f prometheus.yaml | oc create -f -
