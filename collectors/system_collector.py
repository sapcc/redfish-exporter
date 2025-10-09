import logging
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from collectors.dcn_collector import DistributedControlNodeCollector

class SystemCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn
        self.logger = logging.getLogger(__name__)
        self.metrics = {}

    def collect(self):
        system_url = self.urls.get("Systems")
        if not system_url:
            return []

        systems_data = self.connect_server(system_url)
        if not systems_data:
            return []

        all_metrics = []
        members = systems_data.get("Members", [])
        for member in members:
            sys_url = member.get("@odata.id")
            sys_data = self.connect_server(sys_url)
            if not sys_data:
                continue

            sys_id = sys_data.get("Id", "unknown")
            labels = {**self.labels, "host": self.host, "system": sys_id}
            all_metrics += self._extract_metrics(sys_data, labels)

            # Trigger DCN Collector
            dcn_link = sys_data.get("DistributedControlNode", {}).get("@odata.id")
            if dcn_link:
                dcn_collector = DistributedControlNodeCollector(
                    self.host, self.target, labels,
                    {"DistributedControlNode": dcn_link},
                    self.connect_server
                )
                all_metrics += dcn_collector.collect()

        return all_metrics

    def _extract_metrics(self, data, labels):
        metrics = []
        status = data.get("Status", {})
        for key, value in status.items():
            if isinstance(value, str):
                m = InfoMetricFamily(f"redfish_status_{key.lower()}_info", "System status field", labels=list(labels.keys()) + ["value"])
                m.add_metric({**labels, "value": value}, {})
                metrics.append(m)

        for key, value in data.items():
            if isinstance(value, (int, float)):
                m = GaugeMetricFamily(f"redfish_system_{key.lower()}", f"System metric {key}", labels=labels.keys())
                m.add_metric(labels.values(), value)
                metrics.append(m)

        return metrics
