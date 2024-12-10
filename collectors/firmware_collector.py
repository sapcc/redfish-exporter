"""
The collector for firmware information is implemented in the FirmwareCollector class.
The collect method retrieves the firmware information from the Redfish API and adds it to the firmware metrics.
The collect method is called by the collect method of the RedfishMetricsCollector class.
The __enter__ and __exit__ methods are used to manage the lifecycle of the FirmwareCollector class.
"""

import logging
from re import search

from prometheus_client.core import GaugeMetricFamily

class FirmwareCollector:
    """
    Collects firmware information from the Redfish API.
    """

    def __enter__(self):
        return self

    def __init__(self, redfish_metrics_collector):

        self.col = redfish_metrics_collector

        self.fw_metrics = GaugeMetricFamily(
            "redfish_firmware",
            "Redfish Server Monitoring Firmware Data",
            labels=self.col.labels,
        )

    def collect(self):
        """
        Collects firmware information from the Redfish API.
        """

        logging.info("Target %s: Get the firmware information.", self.col.target)

        fw_collection = self.col.connect_server(
            "/redfish/v1/UpdateService/FirmwareInventory"
        )
        if not fw_collection:
            logging.warning("Target %s: Cannot get Firmware data!", self.col.target)
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
                    if version != "N/A" and version is not None:
                        current_labels.update({"version": version})
                        current_labels.update(self.col.labels)
                        self.fw_metrics.add_sample(
                            "redfish_firmware",
                            value=1,
                            labels=current_labels
                        )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb is not None:
            logging.exception(
                "Target %s: An exception occured in {exc_tb.f_code.co_filename}:{exc_tb.tb_lineno}",
                self.col.target
            )
