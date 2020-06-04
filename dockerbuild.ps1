$version = "v0.1.3"

docker build . -t hub.global.cloud.sap/monsoon/redfish-exporter:$version
docker push hub.global.cloud.sap/monsoon/redfish-exporter:$version

docker build . -t keppel.eu-de-1.cloud.sap/ccloud/redfish-exporter:$version
docker push keppel.eu-de-1.cloud.sap/ccloud/redfish-exporter:$version
