from prometheus_client.core import GaugeMetricFamily
import re

def _sanitize_metric_name(name):
    return re.sub(r'[^a-zA-Z0-9_]', '_', name).lower()

def get_leaf_name(path):
    if isinstance(path, str) and '/' in path:
        return path.rstrip('/').split('/')[-1]
    return path

def _extract_kv_metrics(prefix, data, labels):
    metrics = []
    excluded_keys = ["@odata.id", "@odata.type", "Id"]

    for key, value in data.items():
        if key in excluded_keys:
            continue

        metric_key = _sanitize_metric_name(f"{prefix}_{key}")
        label_copy = labels.copy()

        if isinstance(value, dict):
            # Handle nested objects like Status
            if key.lower() == "status":
                for sub_key, sub_value in value.items():
                    metric_name = _sanitize_metric_name(f"{prefix}_{key}_{sub_key}_info")
                    labels_with_status = label_copy.copy()
                    labels_with_status[sub_key] = str(sub_value)
                    metric = GaugeMetricFamily(metric_name, f"{prefix} {key} info for {sub_key}", labels=list(labels_with_status.keys()))
                    metric.add_metric(list(labels_with_status.values()), 1.0)
                    metrics.append(metric)
            else:
                metrics.extend(_extract_kv_metrics(f"{prefix}_{key}", value, label_copy))

        elif isinstance(value, list):
            continue  # We don't need lists as metrics directly

        else:
            if isinstance(value, str) and value.startswith('/redfish/v1'):
                clean_value = get_leaf_name(value)
            else:
                clean_value = str(value)

            if key.lower() == "id":
                # If key is Id, clean it directly
                label_copy[key] = get_leaf_name(value)
            else:
                label_copy[key] = clean_value

            if isinstance(value, (int, float)):
                metric = GaugeMetricFamily(metric_key, f"{prefix} metric for {key}", labels=list(label_copy.keys()))
                metric.add_metric(list(label_copy.values()), float(value))
                metrics.append(metric)
            else:
                metric = GaugeMetricFamily(f"{metric_key}_info", f"{prefix} info for {key}", labels=list(label_copy.keys()))
                metric.add_metric(list(label_copy.values()), 1.0)
                metrics.append(metric)

    return metrics
