$image = "redfish-exporter"

$version = get-date -Format yyyyMMddHHmmss

docker login keppel.eu-de-1.cloud.sap
docker build . -t keppel.eu-de-1.cloud.sap/ccloud/${image}:$version
docker image tag keppel.eu-de-1.cloud.sap/ccloud/${image}:$version keppel.eu-de-1.cloud.sap/ccloud/${image}:latest
docker push keppel.eu-de-1.cloud.sap/ccloud/${image} --all-tags
