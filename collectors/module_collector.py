from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from collectors.channel_collector import ChannelCollector
from collectors.utils import _extract_kv_metrics, get_leaf_name

class ModuleCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

    def collect(self):
        mod_url = self.urls.get("IOModules")
        if not mod_url:
            return []

        data = self.connect_server(mod_url)
        metrics = []

        for mod in data.get("Members", []):
            mod_path = mod["@odata.id"]
            mod_id = get_leaf_name(mod_path)

            # Clean all labels here
            clean_labels = {
                "host": self.labels.get("host", ""),
                "server_manufacturer": self.labels.get("server_manufacturer", ""),
                "server_model": self.labels.get("server_model", ""),
                "server_serial": self.labels.get("server_serial", ""),
                "system": get_leaf_name(self.labels.get("system", "")),
                "dcn": get_leaf_name(self.labels.get("dcn", "")),
                "bus": get_leaf_name(self.labels.get("bus", "")),
                "module": mod_id
            }

            mod_data = self.connect_server(mod_path)

            metrics += self._extract_metrics(mod_data, clean_labels)

            ch_link = mod_data.get("IOChannels", {}).get("@odata.id")
            if ch_link:
                ch_collector = ChannelCollector(
                    self.host,
                    self.target,
                    clean_labels,
                    {"IOChannels": ch_link},
                    self.connect_server
                )
                metrics += ch_collector.collect()

        return metrics

    def _extract_metrics(self, data, labels):
        return _extract_kv_metrics("module", data, labels)
