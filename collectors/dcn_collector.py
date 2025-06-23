from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from collectors.bus_collector import BusCollector
from collectors.utils import _extract_kv_metrics, get_leaf_name


class DistributedControlNodeCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

    def collect(self):
        dcn_url = self.urls.get("DistributedControlNode")
        if not dcn_url:
            return []

        dcn_data = self.connect_server(dcn_url)
        dcn_id = get_leaf_name(dcn_data.get("Id", "dcn"))

        clean_labels = {
            "host": self.labels.get("host", ""),
            "server_manufacturer": self.labels.get("server_manufacturer", ""),
            "server_model": self.labels.get("server_model", ""),
            "server_serial": self.labels.get("server_serial", ""),
            "system": get_leaf_name(self.labels.get("system", "")),
            "dcn": dcn_id
        }

        metrics = self._extract_metrics(dcn_data, clean_labels)

        busses_link = dcn_data.get("Busses", {}).get("@odata.id")
        if busses_link:
            bus_collector = BusCollector(
                self.host, self.target, clean_labels,
                {"Busses": busses_link},
                self.connect_server
            )
            metrics += bus_collector.collect()

        return metrics

    def _extract_metrics(self, data, labels):
        return _extract_kv_metrics("dcn", data, labels)
