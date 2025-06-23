import logging
from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily

class RecursiveCollector:
    def __init__(self, host, target, labels, start_path, connect_fn, config=None):
        self.host = host
        self.target = target
        self.labels = labels
        self.start_path = start_path
        self.connect_server = connect_fn
        self.metrics = {}
        self.status_map = {"OK": 1.0, "Warning": 0.5, "Critical": 0.0}
        self.max_depth = 20

        recursive_config = config.get("recursive", {}) if config else {}
        include_logs = recursive_config.get("include_logs", False)
        self.skip_paths = ["/LogServices/Log/Entries"] if not include_logs else []

    def collect(self):
        self.metrics = {}
        self.walk_and_collect(self.start_path, self.labels.copy(), 0)
        return list(self.metrics.values())

    def walk_and_collect(self, path, inherited_labels, depth):
        if depth > self.max_depth:
            return
        if any(skip in path for skip in self.skip_paths):
            return

        data = self.connect_server(path)
        if not isinstance(data, dict):
            return

        context_labels = inherited_labels.copy()
        context_labels["host"] = self.host
        context_labels["odata_id"] = path
        context_labels.update(self.extract_labels_from_path(path))

        self.extract_fields_as_metrics(data, context_labels)

        # Follow child links
        visited = set()
        for val in data.values():
            if isinstance(val, dict) and "@odata.id" in val:
                next_path = val["@odata.id"]
                if next_path not in visited:
                    visited.add(next_path)
                    self.walk_and_collect(next_path, context_labels, depth + 1)

        if "Members" in data and isinstance(data["Members"], list):
            for member in data["Members"]:
                if isinstance(member, dict) and "@odata.id" in member:
                    next_path = member["@odata.id"]
                    if next_path not in visited:
                        visited.add(next_path)
                        self.walk_and_collect(next_path, context_labels, depth + 1)

    def extract_fields_as_metrics(self, data, labels):
        flat = self.flatten_dict(data)
        for raw_key, raw_val in flat.items():
            key = self.sanitize_key(raw_key)
            if key in {"@odata_id", "odata_context", "odata_type", "id"}:
                continue
            if isinstance(raw_val, (int, float)):
                self.add_gauge_metric(key, float(raw_val), labels)
            elif isinstance(raw_val, str):
                if raw_val.strip().lower() in {"", "value", "id", "none", "unknown", "null"}:
                    continue
                self.add_info_metric(key, raw_val.strip(), labels)

        # Extract from status dict
        status = data.get("Status", {})
        for skey in ["Health", "HealthRollup", "State"]:
            if skey in status:
                val = status[skey]
                metric_key = f"status_{skey.lower()}"
                self.add_info_metric(metric_key, val, labels)
                if val in self.status_map:
                    self.add_gauge_metric(metric_key + "_score", self.status_map[val], labels)

        # Handle common keys
        for key in ["ErrorCode", "ErrorText", "Name"]:
            if key in data:
                val = str(data[key])
                if val.lower() not in {"null", "none", "unknown", ""}:
                    self.add_info_metric(key.lower(), val, labels)

    def flatten_dict(self, d, parent_key="", sep="_"):
        items = {}
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                # ⚠️ Skip link-only children like {"@odata.id": "/..."}
                if "@odata.id" in v and len(v.keys()) == 1:
                    continue
                items.update(self.flatten_dict(v, new_key, sep=sep))
            elif isinstance(v, list):
                continue  # Skipping list
            else:
                items[new_key] = v
        return items

    def extract_labels_from_path(self, path):
        parts = path.strip("/").split("/")
        labels = {}
        for i, part in enumerate(parts):
            if part.lower() == "systems" and i + 1 < len(parts):
                labels["system"] = parts[i + 1]
            elif part.lower() == "distributedcontrolnode":
                labels["dcn"] = parts[i + 1] if i + 1 < len(parts) else ""
            elif part.lower() == "busses" and i + 1 < len(parts):
                labels["bus"] = parts[i + 1]
            elif part.lower() == "iomodules" and i + 1 < len(parts):
                labels["module"] = parts[i + 1]
            elif part.lower() == "iochannels" and i + 1 < len(parts):
                labels["channel"] = parts[i + 1]
        return labels

    def sanitize_key(self, key):
        return (
            key.lower()
            .strip()
            .replace(" ", "_")
            .replace("-", "_")
            .replace(".", "_")
            .replace("/", "_")
            .replace("@", "")
        )

    def add_gauge_metric(self, key, value, labels):
        metric_name = f"redfish_{key}"
        if metric_name not in self.metrics:
            self.metrics[metric_name] = GaugeMetricFamily(
                metric_name, f"Redfish numeric metric for '{key}'", labels=list(labels.keys())
            )
        self.metrics[metric_name].add_sample(metric_name, value=value, labels=labels)

    def add_info_metric(self, key, value, labels):
        metric_name = f"redfish_{key}_info"
        if metric_name not in self.metrics:
            self.metrics[metric_name] = InfoMetricFamily(
                metric_name, f"Redfish info for '{key}'", labels=list(labels.keys()) + ["value"]
            )
        self.metrics[metric_name].add_metric({**labels, "value": value}, {})
