version="v0.1.12"
image = "redfish-exporter"

docker login keppel.eu-de-1.cloud.sap
docker build . -t keppel.eu-de-1.cloud.sap/ccloud/${image}:${version}
docker push keppel.eu-de-1.cloud.sap/ccloud/${image}:${version}
