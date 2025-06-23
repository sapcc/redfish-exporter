from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from collectors.module_collector import ModuleCollector
from collectors.utils import _extract_kv_metrics, get_leaf_name

class BusCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

    def collect(self):
        busses_url = self.urls.get("Busses")
        if not busses_url:
            return []

        data = self.connect_server(busses_url)
        metrics = []

        for member in data.get("Members", []):
            member_path = member["@odata.id"]
            bus_id = get_leaf_name(member_path)

            clean_labels = {
                "host": self.labels.get("host", ""),
                "server_manufacturer": self.labels.get("server_manufacturer", ""),
                "server_model": self.labels.get("server_model", ""),
                "server_serial": self.labels.get("server_serial", ""),
                "system": get_leaf_name(self.labels.get("system", "")),
                "dcn": get_leaf_name(self.labels.get("dcn", "")),
                "bus": bus_id
            }

            member_data = self.connect_server(member_path)
            metrics += self._extract_metrics(member_data, clean_labels)

            mod_link = member_data.get("IOModules", {}).get("@odata.id")
            if mod_link:
                mod_collector = ModuleCollector(
                    self.host, self.target, clean_labels,
                    {"IOModules": mod_link},
                    self.connect_server
                )
                metrics += mod_collector.collect()

        return metrics

    def _extract_metrics(self, data, labels):
        return _extract_kv_metrics("bus", data, labels)
