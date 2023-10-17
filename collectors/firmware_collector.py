from prometheus_client.core import GaugeMetricFamily

import logging
from re import search

class FirmwareCollector(object):
    def __init__(self, redfish_metrics_collector):

        self.col = redfish_metrics_collector

        self.fw_metrics = GaugeMetricFamily(
            "redfish_firmware",
            "Server Monitoring Firmware Data",
            labels=self.col.labels,
        )

    def collect(self):

        logging.info(f"Target {self.col.target}: Get the firmware information.")

        fw_collection = self.col.connect_server(
            "/redfish/v1/UpdateService/FirmwareInventory"
        )
        if not fw_collection:
            logging.warning(f"Target {self.target}: Cannot get Firmware data!")
            return

        for fw_member in fw_collection['Members']:
            fw_member_url = fw_member['@odata.id']
            # only look at entries on a Dell server if the device is markedd as installed
            if (search(".*Dell.*", self.col.manufacturer) and ("Installed" in fw_member_url)) or not search(".*Dell.*", self.col.manufacturer):
                server_response = self.col.connect_server(fw_member_url)
                if not server_response:
                    continue

                if self.col.manufacturer == 'Lenovo':
                    # Lenovo has always Firmware: in front of the names, let's remove it
                    name = server_response['Name'].replace('Firmware:','')
                    # we need an additional label to distinguish the metrics because
                    # the device ID is not in the name in case of Lenovo
                    if "Id" in server_response:
                        current_labels.update({"id": server_response['Id']})
                else:
                    name = server_response['Name'].split(",", 1)[0]

                current_labels = {"name": name}

                if "Manufacturer" in server_response:
                    current_labels.update({"manufacturer": server_response['Manufacturer']})

                if "Version" in server_response:
                    version = server_response['Version']
                    if version != "N/A" and version != None:
                        current_labels.update({"version": version})
                        current_labels.update(self.col.labels)
                        self.fw_metrics.add_sample("redfish_firmware", value=1, labels=current_labels)
