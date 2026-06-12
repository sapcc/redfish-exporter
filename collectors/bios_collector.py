"""
The collector for BIOS settings is implemented in the BiosCollector class.
The collect method retrieves the BIOS settings from the Redfish API and adds them to the BIOS metrics.
The collect method is called by the collect method of the RedfishMetricsCollector class.
The __enter__ and __exit__ methods are used to manage the lifecycle of the BiosCollector class.
"""

import logging
import re

from prometheus_client.core import GaugeMetricFamily

def camel_to_snake(name):
    """
    Convert a Redfish BIOS attribute name to a Prometheus-compatible snake_case
    metric suffix.

    Handles vendor noise such as parentheses, slashes, dashes, hyphens, and
    trailing colons (Fujitsu publishes attributes like ``ConsoleRedirection:``,
    ``PCIe10-bitTagSupport``, ``(CPU1-RP1VMD)Bus20``).

    The output is guaranteed to:
    - contain only ``[a-z0-9_]`` characters
    - have no leading or trailing underscores
    - have no consecutive underscores

    Examples:
        AcPwrRcvry              -> ac_pwr_rcvry
        BootMode                -> boot_mode
        ConsoleRedirection:     -> console_redirection
        PCIe10-bitTagSupport    -> pcie10_bit_tag_support
        (CPU1-RP1VMD)Bus20      -> cpu1_rp1_vmd_bus20
        TME-MT/TDXkeysplit      -> tme_mt_tdxkeysplit
    """
    # Insert underscore before uppercase letters that follow lowercase letters or numbers
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    # Insert underscore before uppercase letters that follow lowercase letters
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    # Replace any remaining non-alphanumeric character with an underscore,
    # collapse runs of underscores, and trim.
    s3 = re.sub(r'[^a-zA-Z0-9]+', '_', s2)
    return s3.strip('_').lower()

class BiosCollector:
    """
    Collects BIOS settings from the Redfish API.
    """

    def __enter__(self):
        return self

    def __init__(self, redfish_metrics_collector):

        self.col = redfish_metrics_collector
        self.bios_metrics = {}
        self.pending_changes_metric = GaugeMetricFamily(
            "redfish_bios_pending_changes",
            "Indicates if there are pending BIOS changes awaiting reboot",
            labels=self.col.labels,
        )

    def collect(self):
        """
        Collects BIOS settings from the Redfish API.
        """

        logging.info("Target %s: Get the BIOS settings.", self.col.target)

        # Get BIOS data from Systems endpoint
        systems = self.col.connect_server("/redfish/v1/Systems")
        if not systems or 'Members' not in systems:
            logging.warning("Target %s: Cannot get Systems data!", self.col.target)
            return

        # Iterate through each system
        for system_member in systems['Members']:
            system_url = system_member['@odata.id']
            
            # First get the system object to find the BIOS URL
            system_data = self.col.connect_server(system_url)
            if not system_data:
                logging.warning("Target %s: Cannot get System data from %s", 
                              self.col.target, system_url)
                continue
            
            # Get BIOS URL from the system object (proper Redfish way)
            if 'Bios' not in system_data:
                logging.warning("Target %s: System %s does not have Bios property", 
                              self.col.target, system_url)
                continue
            
            bios_url = system_data['Bios']['@odata.id']
            bios_data = self.col.connect_server(bios_url)
            
            if not bios_data:
                logging.warning("Target %s: Cannot get BIOS data from %s", 
                              self.col.target, bios_url)
                continue

            # Check for pending BIOS changes
            has_pending_changes = 1 if '@Redfish.Settings' in bios_data else 0
            self.pending_changes_metric.add_sample(
                "redfish_bios_pending_changes",
                value=has_pending_changes,
                labels=self.col.labels
            )

            # Get BIOS attributes
            if 'Attributes' in bios_data:
                attributes = bios_data['Attributes']
                logging.info("Target %s: Received %d BIOS attributes.", 
                           self.col.target, len(attributes))
                
                # Export each BIOS setting as a separate metric
                for attr_name, attr_value in attributes.items():
                    # Skip vendor-specific device configuration attributes
                    # e.g., Broadcom* attributes that are having complex names
                    # and create metric names longer than 80 characters
                    # Seen on Lenovo ThinkSystem SR675 V3
                    if attr_name.startswith('Broadcom'):
                        continue

                    # Resolve the value first. Sequence/object-typed BIOS
                    # attributes (e.g. Fujitsu BootSources, PersistentBootConfigOrder)
                    # are skipped — emitting them would create an empty metric
                    # family with HELP/TYPE lines and zero samples.
                    current_labels = self.col.labels.copy()
                    current_labels["setting_name"] = attr_name

                    # bool first: Python `bool` is a subclass of `int`, so the
                    # int/float branch would otherwise swallow True/False.
                    if isinstance(attr_value, bool):
                        numeric_value = 1 if attr_value else 0
                    elif isinstance(attr_value, (int, float)):
                        numeric_value = float(attr_value)
                    elif isinstance(attr_value, str):
                        # Check if string is a boolean-like value
                        lowered = attr_value.strip().lower()
                        if lowered == 'enabled':
                            numeric_value = 1
                        elif lowered == 'disabled':
                            numeric_value = 0
                        else:
                            # For other string values, store as info metric with value 1
                            current_labels["setting_value"] = str(attr_value)
                            numeric_value = 1
                    else:
                        # Skip unsupported types (lists, dicts, None, ...) entirely.
                        continue

                    # Build the metric name only after we know we have a sample
                    # to add. camel_to_snake guarantees Prometheus-safe output.
                    metric_name = f"redfish_bios_{camel_to_snake(attr_name)}"
                    if not metric_name or metric_name == "redfish_bios_":
                        # Defensive: an attribute name like "::" would normalise
                        # to nothing. Drop it rather than emit an invalid metric.
                        continue

                    if metric_name not in self.bios_metrics:
                        self.bios_metrics[metric_name] = GaugeMetricFamily(
                            metric_name,
                            f"Redfish BIOS Setting: {attr_name}",
                            labels=self.col.labels,
                        )

                    self.bios_metrics[metric_name].add_sample(
                        metric_name,
                        value=numeric_value,
                        labels=current_labels
                    )
        
        # Yield all collected metrics
        logging.info("Target %s: Collected %d BIOS metrics.", 
                   self.col.target, len(self.bios_metrics))
        yield self.pending_changes_metric
        for metric in self.bios_metrics.values():
            yield metric

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb is not None:
            logging.exception(
                "Target %s: An exception occured in {exc_tb.f_code.co_filename}:{exc_tb.tb_lineno}",
                self.col.target
            )
