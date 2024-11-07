"""Collects health information from the Redfish API."""
import logging
import math

from prometheus_client.core import GaugeMetricFamily

class HealthCollector():
    """Collects health information from the Redfish API."""
    def __enter__(self):
        return self

    def __init__(self, redfish_metrics_collector):
        self.col = redfish_metrics_collector

        self.health_metrics = GaugeMetricFamily(
            "redfish_health",
            "Redfish Server Monitoring Health Data",
            labels=self.col.labels,
        )
        self.mem_metrics_correctable = GaugeMetricFamily(
            "redfish_memory_correctable",
            "Redfish Server Monitoring Memory Data for correctable errors",
            labels=self.col.labels,
        )
        self.mem_metrics_uncorrectable = GaugeMetricFamily(
            "redfish_memory_uncorrectable",
            "Redfish Server Monitoring Memory Data for uncorrectable errors",
            labels=self.col.labels,
        )

    def get_processors_health(self):
        """Get the Processor data from the Redfish API."""
        logging.debug("Target %s: Get the CPU health data.", self.col.target)
        processor_collection = self.col.connect_server(self.col.urls["Processors"])

        if not processor_collection:
            return
        for processor in processor_collection["Members"]:
            processor_data = self.col.connect_server(processor["@odata.id"])
            if not processor_data:
                continue

            proc_status = self.extract_health_status(
                processor_data, "Processor", processor_data.get("Socket", "unknown")
            )
            current_labels = {
                "device_type": "processor",
                "device_name": processor_data.get("Socket", "unknown"),
                "device_manufacturer": processor_data.get("Manufacturer", "unknown"),
                "cpu_type": processor_data.get("ProcessorType", "unknown"),
                "cpu_model": processor_data.get("Model", "unknown"),
                "cpu_cores": str(processor_data.get("TotalCores", "unknown")),
                "cpu_threads": str(processor_data.get("TotalThreads", "unknown")),
            }
            current_labels.update(self.col.labels)

            self.add_metric_sample(
                "redfish_health",
                {"Health": proc_status},
                "Health",
                current_labels
            )

    def get_storage_health(self):
        """Get the Storage data from the Redfish API."""
        logging.debug("Target %s: Get the storage health data.", self.col.target)
        storage_collection = self.col.connect_server(self.col.urls["Storage"])

        if not storage_collection:
            return

        for controller in storage_collection["Members"]:
            controller_data = self.col.connect_server(controller["@odata.id"])
            if not controller_data:
                continue

            controller_details = self.get_controller_details(controller_data)
            controller_name = self.get_controller_name(controller_details, controller_data)
            controller_status = self.extract_health_status(
                controller_details, "Controller", controller_name
            )

            current_labels = self.get_controller_labels(controller_details, controller_name)
            self.add_metric_sample(
                "redfish_health",
                {"Health": controller_status},
                "Health",
                current_labels
            )

            for disk in controller_data["Drives"]:
                disk_data = self.col.connect_server(disk["@odata.id"])
                if not disk_data:
                    continue

                disk_status = self.extract_health_status(
                    disk_data,
                    "Disk",
                    disk_data.get("Name", "unknown")
                )
                current_labels = self.get_disk_labels(disk_data)
                self.add_metric_sample(
                    "redfish_health",
                    {"Health": disk_status},
                    "Health",
                    current_labels
                )

    def get_controller_details(self, controller_data):
        """Get controller details from controller data."""
        if controller_data.get("StorageControllers"):
            if isinstance(controller_data["StorageControllers"], list):
                return controller_data["StorageControllers"][0]
            return list(controller_data["StorageControllers"].values())[0]
        return controller_data

    def get_controller_name(self, controller_details, controller_data):
        """Get controller name from controller details or data."""
        return controller_details.get("Name") or controller_data.get("Name", "unknown")

    def extract_health_status(self, data, device_type, device_name):
        """Extract health status from data."""
        if "Status" not in data:
            return math.nan

        status = data["Status"]
        if isinstance(status, str):
            return self.col.status[status.lower()]

        status = {k.lower(): v for k, v in status.items()}
        state = status.get("state")
        if state is None or state.lower() == "absent":
            logging.debug(
                "Target %s: Host %s, Model %s, %s %s: absent.",
                self.col.target,
                self.col.host,
                self.col.model,
                device_type,
                device_name
            )
            return math.nan

        health = status.get("health", "")
        if not health:
            logging.warning(
                "Target %s: No %s health data provided for %s!",
                self.col.target,
                device_type,
                device_name
            )
            return math.nan

        return self.col.status[health.lower()]

    def get_controller_labels(self, controller_details, controller_name):
        """Generate labels for Controller."""
        labels = {
            "device_type": "storage",
            "device_name": controller_name,
            "device_manufacturer": controller_details.get("Manufacturer", "unknown"),
            "controller_model": controller_details.get("Model", "unknown"),
        }
        labels.update(self.col.labels)
        return labels

    def get_disk_labels(self, disk_data):
        """Generate labels for Disk."""
        disk_attributes = {
            "Name": "device_name",
            "MediaType": "disk_type",
            "Manufacturer": "device_manufacturer",
            "Model": "disk_model",
            "CapacityBytes": "disk_capacity",
            "Protocol": "disk_protocol",
        }
        labels = {"device_type": "disk"}
        for disk_attribute, label_name in disk_attributes.items():
            if disk_attribute in disk_data:
                labels[label_name] = str(disk_data[disk_attribute])
        labels.update(self.col.labels)
        return labels

    def get_chassis_health(self):
        """Get the Chassis data from the Redfish API."""
        logging.debug("Target %s: Get the Chassis health data.", self.col.target)
        chassis_data = self.col.connect_server(self.col.urls["Chassis"])
        if not chassis_data:
            return

        current_labels = {
            "device_type": "chassis",
            "device_name": chassis_data["Name"]
        }
        current_labels.update(self.col.labels)
        chassis_health = self.extract_health_status(chassis_data, "Chassis", chassis_data["Name"])
        self.add_metric_sample(
            "redfish_health",
            {"Health": chassis_health},
            "Health",
            current_labels
        )

    def get_power_health(self):
        """Get the Power data from the Redfish API."""
        logging.debug("Target %s: Get the PDU health data.", self.col.target)
        power_data = self.col.connect_server(self.col.urls["Power"])
        if not power_data:
            return

        for psu in power_data["PowerSupplies"]:
            psu_name = psu["Name"] if "Name" in psu and psu["Name"] is not None else "unknown"
            psu_model = psu["Model"] if "Model" in psu and psu["Model"] is not None else "unknown"

            current_labels = {
                "device_type": "powersupply",
                "device_name": psu_name,
                "device_model": psu_model
            }
            current_labels.update(self.col.labels)
            psu_health = self.extract_health_status(psu, "PSU", psu_name)
            self.add_metric_sample(
                "redfish_health",
                {"Health": psu_health},
                "Health",
                current_labels
            )

    def get_thermal_health(self):
        """Get the Thermal data from the Redfish API."""
        logging.debug("Target %s: Get the thermal health data.", self.col.target)
        thermal_data = self.col.connect_server(self.col.urls["Thermal"])
        if not thermal_data:
            return

        for fan in thermal_data["Fans"]:
            fan_name = fan.get("Name", "unknown")
            current_labels = {
                "device_type": "fan",
                "device_name": fan_name
            }
            current_labels.update(self.col.labels)
            fan_health = self.extract_health_status(fan, "Fan", fan_name)
            self.add_metric_sample(
                "redfish_health",
                {"Health": fan_health},
                "Health",
                current_labels
            )

    def get_memory_health(self):
        """Get the Memory data from the Redfish API."""
        logging.debug("Target %s: Get the Memory data.", self.col.target)

        memory_collection = self.col.connect_server(self.col.urls["Memory"])
        if not memory_collection:
            return

        for dimm_url in memory_collection["Members"]:
            dimm_info = self.col.connect_server(dimm_url["@odata.id"])
            if not dimm_info:
                continue

            dimm_health = self.extract_health_status(
                dimm_info,
                "Dimm",
                dimm_info.get("Name", "unknown")
            )
            if dimm_health is math.nan:
                logging.debug(
                    "Target %s: Host %s, Model %s, Dimm %s: No health data found.",
                    self.col.target,
                    self.col.host,
                    self.col.model,
                    dimm_info['Name']
                )
                continue

            current_labels = self.get_dimm_labels(dimm_info)
            self.add_metric_sample(
                "redfish_health",
                {"Health": dimm_health},
                "Health",
                current_labels
            )

            if "Metrics" in dimm_info:
                self.process_dimm_metrics(dimm_info, current_labels)

    def get_dimm_labels(self, dimm_info):
        """Generate labels for DIMM."""
        labels = {
            "device_type": "memory",
            "device_name": dimm_info["Name"],
            "dimm_capacity": str(dimm_info["CapacityMiB"]),
            "dimm_speed": str(dimm_info.get("OperatingSpeedMhz", "unknown")),
            "dimm_type": dimm_info["MemoryDeviceType"],
            "device_manufacturer": dimm_info.get("Manufacturer", "N/A")
        }

        if "Oem" in dimm_info and "Hpe" in dimm_info["Oem"]:
            labels["device_manufacturer"] = dimm_info["Oem"]["Hpe"].get("VendorName", "unknown")

        labels.update(self.col.labels)
        return labels

    def process_dimm_metrics(self, dimm_info, current_labels):
        """Process DIMM metrics."""
        dimm_metrics = self.col.connect_server(dimm_info["Metrics"]["@odata.id"])
        if not dimm_metrics:
            return

        health_data = dimm_metrics.get("HealthData", {}).get("AlarmTrips", {})
        self.add_metric_sample(
            "redfish_memory_correctable",
            health_data,
            "CorrectableECCError",
            current_labels
        )

        self.add_metric_sample(
            "redfish_memory_uncorrectable",
            health_data,
            "UncorrectableECCError",
            current_labels
        )

    def add_metric_sample(self, metric_name, data, key, labels):
        """Add a sample to the specified metric."""
        try:
            value = int(data[key]) if data.get(key) is not None else math.nan
        except (ValueError, TypeError):
            value = math.nan

        if math.isnan(value):
            logging.debug(
                "Target %s: Host %s, Model %s, Name %s: No %s Metrics found.",
                self.col.target,
                self.col.host,
                self.col.model,
                labels["device_name"],
                key
            )
        else:
            if metric_name == "redfish_health":
                metric_family = self.health_metrics
            else:
                metric_family = getattr(self, f"mem_metrics_{metric_name.split('_')[-1]}")
            metric_family.add_sample(metric_name, value=value, labels=labels)

    def collect_health_data(self, url_key):
        """Helper method to collect health data."""
        health_function_name = f"get_{url_key.lower()}_health"
        health_function = getattr(self, health_function_name, None)
        if health_function and self.col.urls[url_key]:
            health_function()
        else:
            warning_message = f"No {url_key} URL provided! Cannot get {url_key} data!"
            logging.warning("Target %s: %s", self.col.target, warning_message)

    def collect(self):
        """Collect the health data."""
        logging.info("Target %s: Collecting health data ...", self.col.target)

        current_labels = {"device_type": "system", "device_name": "summary"}
        current_labels.update(self.col.labels)
        self.add_metric_sample(
            "redfish_health",
            {"Health": self.col.server_health},
            "Health",
            current_labels
        )

        for url_key in ["Processors", "Storage", "Chassis", "Power", "Thermal", "Memory"]:
            self.collect_health_data(url_key)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb is not None:
            logging.exception(
                "Target %s: An exception occured in %s:%s",
                self.col.target,
                exc_tb.tb_frame.f_code.co_filename,
                exc_tb.tb_lineno
            )
