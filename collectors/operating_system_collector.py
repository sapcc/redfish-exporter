import logging
from prometheus_client.core import GaugeMetricFamily

class OperatingSystemCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn

    def collect(self):
        os_url = self.urls.get("OperatingSystem")
        if not os_url:
            logging.warning("OperatingSystem URL not found in provided URLs")
            return []

        os_info = self.connect_server(os_url)
        if not os_info:
            logging.warning("No data returned from OperatingSystem endpoint")
            return []

        # Collect basic OS info as a 1-valued metric
        os_info_metric = GaugeMetricFamily(
            "redfish_operating_system_info",
            "Basic information about the operating system",
            labels=["os_id", "os_name", "kernel_name", "hostname", "processor_type"] + list(self.labels.keys())
        )
        os_info_metric.add_sample(
            "redfish_operating_system_info",
            value=1,
            labels={
                "os_id": os_info.get("Id", "unknown"),
                "os_name": os_info.get("OperatingSystemName", "unknown"),
                "kernel_name": os_info.get("KernelName", "unknown"),
                "hostname": os_info.get("Hostname", "unknown"),
                "processor_type": os_info.get("ProcessorType", "unknown"),
                **self.labels
            }
        )

        # Try to follow OperatingSystemMetrics endpoint
        metrics_url = (
            os_info.get("OperatingSystemMetrics", {})
            .get("@odata.id")
        )
        os_metrics = self.connect_server(metrics_url) if metrics_url else {}

        status_metric = GaugeMetricFamily(
            "redfish_operating_system_status",
            "Uptime or other system metrics from OperatingSystemMetrics",
            labels=["metric", "unit"] + list(self.labels.keys())
        )

        # Example: Collect uptime if available
        uptime = os_metrics.get("UptimeSeconds")
        if uptime is not None:
            status_metric.add_sample(
                "redfish_operating_system_status",
                value=float(uptime),
                labels={
                    "metric": "uptime_seconds",
                    "unit": "seconds",
                    **self.labels
                }
            )

        return [os_info_metric, status_metric]
