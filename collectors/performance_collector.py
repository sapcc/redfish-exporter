from prometheus_client.core import GaugeMetricFamily

import logging

class PerformanceCollector(object):

    def __enter__(self):
        return self

    def __init__(self, redfish_metrics_collector):

        self.col = redfish_metrics_collector

        self.performance_metrics = GaugeMetricFamily(
            "redfish_performance",
            "Server Monitoring Performance Data",
            labels=self.col.labels,
        )
        self.power_metrics = GaugeMetricFamily(
            "redfish_power",
            "Server Monitoring Power Data",
            labels=self.col.labels,
        )
        self.temperature_metrics = GaugeMetricFamily(
            "redfish_temperature",
            "Server Monitoring Temperature Data",
            labels=self.col.labels,
            unit="Celsius"
        )

    def get_power_metrics(self):
        logging.debug(f"Target {self.col.target}: Get the PDU Power data.")

        if self.col.urls['PowerSubsystem']:

            power_subsystem = self.col.connect_server(self.col.urls['PowerSubsystem'])
            metrics = ['CapacityWatts', 'Allocation']

            for metric in metrics:
                if metric in power_subsystem:
                    if isinstance(power_subsystem[metric], dict):
                        for submetric in power_subsystem[metric]:
                            current_labels = {'type': submetric}
                            current_labels.update(self.col.labels)
                            self.power_metrics.add_sample(
                                "redfish_power", value=power_subsystem[metric][submetric], labels=current_labels
                            )
                    else:
                        current_labels = {'type': metric}
                        current_labels.update(self.col.labels)
                        self.power_metrics.add_sample(
                            "redfish_power", value=power_subsystem[metric], labels=current_labels
                        )

            power_supplies_url = power_subsystem['PowerSupplies']['@odata.id']
            power_supplies = self.col.connect_server(power_supplies_url)['Members']

            fields = ['Name', 'Model', 'SerialNumber', 'Id']
            metrics = ['InputVoltage', 'InputCurrentAmps', 'InputPowerWatts', 'OutputPowerWatts']

            for power_supply in power_supplies:
                power_supply_labels = {}
                power_supply_data = self.col.connect_server(power_supply['@odata.id'])
                for field in fields:
                    power_supply_labels.update({field: power_supply_data.get(field, 'unknown')})

                power_supply_labels.update(self.col.labels)

                power_supply_metrics_url = power_supply_data['Metrics']['@odata.id']
                power_supply_metrics = self.col.connect_server(power_supply_metrics_url)
                for metric in metrics:
                    current_labels = {'type': metric}
                    current_labels.update(power_supply_labels)
                    if metric in power_supply_metrics:
                        self.power_metrics.add_sample(
                            "redfish_power", value=power_supply_metrics[metric]['Reading'], labels=current_labels
                        )

        # fall back to deprecated URL
        elif self.col.urls['Power']:
            power_data = self.col.connect_server(self.col.urls['Power'])
            if not power_data:
                return
    
            values = ['PowerOutputWatts', 'EfficiencyPercent', 'PowerInputWatts', 'LineInputVoltage']
            for psu in power_data['PowerSupplies']:
                psu_name = psu.get('Name', 'unknown')
                psu_model = psu.get('Model', 'unknown')
                current_labels = {'type': 'powersupply', 'name': psu_name, 'model': psu_model}
                current_labels.update(self.col.labels)

                for value in values:
                    if value in psu:
                        self.power_metrics.add_sample(
                            f"redfish_power_{value}", value=psu[value], labels=current_labels
                        )
        else:
            logging.warning(f"Target {self.col.target}, Host {self.col.host}, Model {self.col.model}: No power url found.")


    def get_temp_metrics(self):
        logging.debug(f"Target {self.col.target}: Get the Thermal data.")

        if self.col.urls['ThermalSubsystem']:
            thermal_subsystem = self.col.connect_server(self.col.urls['ThermalSubsystem'])
            thermal_metrics_url = thermal_subsystem['ThermalMetrics']['@odata.id']
            thermal_metrics = self.col.connect_server(thermal_metrics_url)['TemperatureSummaryCelsius']

            for metric in thermal_metrics:
                current_labels = {'type': metric}
                current_labels.update(self.col.labels)
                self.temperature_metrics.add_sample(
                    "redfish_temperature", value=thermal_metrics[metric]['Reading'], labels=current_labels
                )

    def collect(self):

        logging.info(f"Target {self.col.target}: Get the firmware information.")
        self.get_power_metrics()
        self.get_temp_metrics()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logging.exception(f"Target {self.target}: An exception occured in {sys.exc_info()[-1].tb_frame.f_code.co_filename}:{sys.exc_info()[-1].tb_lineno}")
            logging.exception(f"Target {self.target}: Exception type: {exc_type}")
            logging.exception(f"Target {self.target}: Exception value: {exc_val}")
            logging.exception(f"Target {self.target}: Traceback: {exc_tb}")
