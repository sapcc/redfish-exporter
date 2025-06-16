import logging
from prometheus_client.core import GaugeMetricFamily

class OperatingSystemCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

        self.os_metric = GaugeMetricFamily(
            "redfish_operating_system_info",
            "Redfish OS information from server",
            labels=["os_id", "os_name"] + list(labels.keys())
        )

    def collect(self):
        os_url = self.urls.get("OperatingSystem")
        if not os_url:
             return []

        os_info = self.connect_server(os_url)
        if not os_info:
             return []

        self.os_metric.add_sample(
            "redfish_operating_system_info",
            value=1,
            labels={
                "os_id": os_info.get("Id", "unknown"),
                "os_name": os_info.get("Name", "unknown"),
                **self.labels
            }
        )

        return [self.os_metric]
