from prometheus_client.core import GaugeMetricFamily
from collectors.utils import _extract_kv_metrics, get_leaf_name

class ChannelCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

    def collect(self):
        ch_url = self.urls.get("IOChannels")
        if not ch_url:
            return []

        data = self.connect_server(ch_url)
        metrics = []

        for ch in data.get("Members", []):
            ch_data = self.connect_server(ch["@odata.id"])

            # Extract the clean names for labels
            system = get_leaf_name(self.labels.get("system", ""))
            dcn = get_leaf_name(self.labels.get("dcn", ""))
            bus = get_leaf_name(self.labels.get("bus", ""))
            module = get_leaf_name(self.labels.get("module", ""))
            channel = get_leaf_name(ch_data.get("Id", "channel"))

            scoped_labels = {
                "host": self.host,
                "server_manufacturer": self.labels.get("server_manufacturer", ""),
                "server_model": self.labels.get("server_model", ""),
                "server_serial": self.labels.get("server_serial", ""),
                "system": system,
                "dcn": dcn,
                "bus": bus,
                "module": module,
                "channel": channel
            }

            metrics += self._extract_metrics(ch_data, scoped_labels)

        return metrics

    def _extract_metrics(self, data, labels):
        return _extract_kv_metrics("channel", data, labels)
