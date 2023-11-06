from prometheus_client.core import GaugeMetricFamily

import logging
from re import search

class FirmwareCollector(object):

    def __enter__(self):
        return self

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
                fw_item = self.col.connect_server(fw_member_url)
                if not fw_item:
                    continue

                item_name = fw_item['Name'].split(",", 1)[0]
                current_labels = {"item_name": item_name}

                if self.col.manufacturer == 'Lenovo':
                    # Lenovo has always Firmware: in front of the names, let's remove it
                    item_name = fw_item['Name'].replace('Firmware:','')
                    current_labels.update({"item_name": item_name})
                    # we need an additional label to distinguish the metrics because
                    # the device ID is not in the name in case of Lenovo
                    if "Id" in fw_item:
                        current_labels.update({"item_id": fw_item['Id']})

                if "Manufacturer" in fw_item:
                    current_labels.update({"item_manufacturer": fw_item['Manufacturer']})

                if "Version" in fw_item:
                    version = fw_item['Version']
                    if version != "N/A" and version != None:
                        current_labels.update({"version": version})
                        current_labels.update(self.col.labels)
                        self.fw_metrics.add_sample("redfish_firmware", value=1, labels=current_labels)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb is not None:
            logging.exception(f"Target {self.target}: An exception occured in {exc_tb.f_code.co_filename}:{exc_tb.tb_lineno}")
