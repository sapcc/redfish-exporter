import logging
from prometheus_client.core import GaugeMetricFamily

class EthernetCollector:
    def __init__(self, host, target, labels, urls, connect_fn):
        self.host = host
        self.target = target
        self.labels = labels
        self.urls = urls
        self.connect_server = connect_fn  # Redfish API connection method

        self.ethernet_metrics = GaugeMetricFamily(
            "redfish_ethernet_interface",
            "Redfish Server Monitoring Ethernet Interface Status",
            labels=["interface_name", "mac_address", "ipv4", "ipv6", "speed_mbps"] + list(self.labels.keys())
        )

        self.link_status_metric = GaugeMetricFamily(
            "redfish_ethernet_link_status",
            "Link status of the Ethernet interface (1=Up, 0=Down/Unknown)",
            labels=["interface_name"] + list(self.labels.keys())
        )

        self.duplex_metric = GaugeMetricFamily(
            "redfish_ethernet_full_duplex",
            "Whether the Ethernet interface is in full duplex mode",
            labels=["interface_name"] + list(self.labels.keys())
        )

        self.dhcp_metric = GaugeMetricFamily(
            "redfish_ethernet_dhcp_enabled",
            "Whether DHCPv4 is enabled on the Ethernet interface",
            labels=["interface_name"] + list(self.labels.keys())
        )

    def collect(self):
        eth_url = self.urls.get("NetworkInterfaces") or self.urls.get("EthernetInterfaces")
        if not eth_url:
            logging.warning("Target %s: No Ethernet interface URL found.", self.target)
            return

        iface_list = self.connect_server(eth_url)
        if not iface_list or "Members" not in iface_list:
            logging.warning("Target %s: EthernetInterfaces returned no members.", self.target)
            return

        for iface in iface_list["Members"]:
            iface_url = iface.get("@odata.id")
            if not iface_url:
                continue

            iface_data = self.connect_server(iface_url)
            if not iface_data:
                continue

            interface_name = iface_data.get("Name", "unknown")
            mac = iface_data.get("MACAddress", "")
            speed = str(iface_data.get("SpeedMbps", 0))
            ipv4 = "unknown"
            ipv6 = "unknown"

            ipv4_list = iface_data.get("IPv4Addresses", [])
            if ipv4_list and isinstance(ipv4_list, list) and "Address" in ipv4_list[0]:
                ipv4 = ipv4_list[0]["Address"]

            ipv6_list = iface_data.get("IPv6Addresses", [])
            if ipv6_list and isinstance(ipv6_list, list) and "Address" in ipv6_list[0]:
                ipv6 = ipv6_list[0]["Address"]

            metric_labels = {
                "interface_name": interface_name,
                "mac_address": mac,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "speed_mbps": speed
            }
            metric_labels.update(self.labels)

            self.ethernet_metrics.add_sample(
                "redfish_ethernet_interface", value=1, labels=metric_labels
            )

            # LinkStatus
            link_status = iface_data.get("LinkStatus", "Unknown")
            self.link_status_metric.add_sample(
                "redfish_ethernet_link_status",
                value=1 if link_status.lower() == "up" else 0,
                labels={"interface_name": interface_name, **self.labels}
            )

            # FullDuplex
            full_duplex = iface_data.get("FullDuplex", False)
            self.duplex_metric.add_sample(
                "redfish_ethernet_full_duplex",
                value=1 if full_duplex else 0,
                labels={"interface_name": interface_name, **self.labels}
            )

            # DHCPv4 Enabled
            dhcp_enabled = iface_data.get("DHCPv4", {}).get("DHCPEnabled", False)
            self.dhcp_metric.add_sample(
                "redfish_ethernet_dhcp_enabled",
                value=1 if dhcp_enabled else 0,
                labels={"interface_name": interface_name, **self.labels}
            )

        return [
            self.ethernet_metrics,
            self.link_status_metric,
            self.duplex_metric,
            self.dhcp_metric
        ]
