"""Collects performance, thermal and power information from the Redfish API like."""
import logging
import math
from prometheus_client.core import GaugeMetricFamily

class PerformanceCollector:
    """Collects performance information from the Redfish API."""
    def __enter__(self):
        return self

    def __init__(self, redfish_metrics_collector):

        self.col = redfish_metrics_collector

        self.performance_metrics = GaugeMetricFamily(
            "redfish_performance",
            "Redfish Server Monitoring Performance Data",
            labels=self.col.labels,
        )
        self.power_metrics = GaugeMetricFamily(
            "redfish_power",
            "Redfish Server Monitoring Power Data",
            labels=self.col.labels,
        )
        self.temperature_metrics = GaugeMetricFamily(
            "redfish_temperature",
            "Redfish Server Monitoring Temperature Data",
            labels=self.col.labels,
            unit="Celsius"
        )

    def get_power_metrics(self):
        """Get the Power data from the Redfish API."""
        logging.info("Target %s: Get the PDU Power data.", self.col.target)
        no_psu_metrics = True

        if self.col.urls['PowerSubsystem']:
            no_psu_metrics = self.get_power_subsystem_metrics()

        # fall back to deprecated URL
        if self.col.urls['Power'] and no_psu_metrics:
            self.get_old_power_metrics()

        if no_psu_metrics:
            logging.warning(
                "Target %s, Host %s, Model %s: No power url found.",
                self.col.target,
                self.col.host,
                self.col.model
            )

    def get_power_subsystem_metrics(self):
        '''Get the PowerSubsystem data from the Redfish API.'''
        no_psu_metrics = True
        power_supplies_url = None

        logging.debug("Target %s:Checking PowerSubsystem ...", self.col.target)
        power_subsystem = self.col.connect_server(self.col.urls['PowerSubsystem'])
        metrics = ['CapacityWatts', 'Allocation']

        for metric in metrics:
            if metric not in power_subsystem:
                continue

            if isinstance(power_subsystem[metric], dict):
                for submetric in power_subsystem[metric]:
                    current_labels = {'type': submetric}
                    current_labels.update(self.col.labels)
                    power_metric_value = (
                        math.nan
                        if power_subsystem[metric][submetric] is None
                        else power_subsystem[metric][submetric]
                    )
                    self.power_metrics.add_sample(
                        "redfish_power",
                        value=power_metric_value,
                        labels=current_labels
                    )
            else:
                current_labels = {'type': metric}
                current_labels.update(self.col.labels)
                power_metric_value = (
                    math.nan
                    if power_subsystem[metric] is None
                    else power_subsystem[metric]
                )
                self.power_metrics.add_sample(
                    "redfish_power",
                    value=power_metric_value,
                    labels=current_labels
                )

        power_supplies_url = power_subsystem.get('PowerSupplies', {}).get('@odata.id')

        if not power_supplies_url:
            logging.warning(
                "Target %s, Host %s, Model %s: No power supplies url found.",
                self.col.target,
                self.col.host,
                self.col.model
            )
            return no_psu_metrics

        power_supplies = self.col.connect_server(power_supplies_url)

        if 'Members' in power_supplies:
            power_supplies = power_supplies['Members']

        for power_supply in power_supplies:
            no_psu_metrics = self.get_power_supply_metrics(power_supply)

        return no_psu_metrics

    def get_power_supply_metrics(self, power_supply):
        """Get power supply metrics and update labels."""
        fields = ["Name", "Manufacturer", "Model"]
        metrics = ["PowerInputWatts", "PowerOutputWatts", "PowerCapacityWatts", "InputPowerWatts", "OutputPowerWatts"]
        no_psu_metrics = True


        power_supply_labels = {}
        power_supply_data = self.col.connect_server(power_supply['@odata.id'])

        if 'Metrics' not in power_supply_data:
            logging.warning(
                "Target %s, Host %s, Model %s: No power supply metrics url found for %s.",
                self.col.target,
                self.col.host,
                self.col.model,
                power_supply_data.get('Name', 'unknown')
            )
            return no_psu_metrics

        for field in fields:
            power_supply_labels.update({field: power_supply_data.get(field, 'unknown')})

        power_supply_labels.update(self.col.labels)

        power_supply_metrics_url = power_supply_data['Metrics']['@odata.id']
        power_supply_metrics = self.col.connect_server(power_supply_metrics_url)

        no_psu_metrics = False
        for metric in metrics:
            current_labels = {'type': metric}
            current_labels.update(power_supply_labels)
            if metric not in power_supply_metrics:
                continue

            power_metric_value = (
                math.nan
                if power_supply_metrics[metric]['Reading'] is None
                else power_supply_metrics[metric]['Reading']
            )
            self.power_metrics.add_sample(
                "redfish_power", value=power_metric_value, labels=current_labels
            )

        return no_psu_metrics


    def get_old_power_metrics(self):
        """Get the Power data from the Redfish API."""
        logging.debug("Target %s: Fallback to deprecated Power URL.", self.col.target)

        no_psu_metrics = True

        power_data = self.col.connect_server(self.col.urls['Power'])
        if not power_data:
            return no_psu_metrics

        metrics = [
            'PowerOutputWatts',
            'EfficiencyPercent',
            'PowerInputWatts',
            'LineInputVoltage'
        ]

        for psu in power_data['PowerSupplies']:
            psu_name = (
                'unknown' 
                if psu.get('Name', 'unknown') is None
                else psu.get('Name', 'unknown')
            )
            psu_model = (
                'unknown' 
                if psu.get('Model', 'unknown') is None
                else psu.get('Model', 'unknown')
            )

            for metric in metrics:
                if metric not in psu:
                    continue

                no_psu_metrics = False
                power_metric_value = (
                    math.nan
                    if psu[metric] is None
                    else psu[metric]
                )

                current_labels = {
                    'device_name': psu_name,
                    'device_model': psu_model,
                    'type': metric
                }
                current_labels.update(self.col.labels)
                self.power_metrics.add_sample(
                    "redfish_power",
                    value=power_metric_value,
                    labels=current_labels
                )

        return no_psu_metrics

    def get_temp_metrics(self):
        """Get the Thermal data from the Redfish API."""
        logging.info("Target %s: Get the Thermal data.", self.col.target)

        if self.col.urls['ThermalSubsystem']:
            thermal_subsystem = self.col.connect_server(self.col.urls['ThermalSubsystem'])
            thermal_metrics_url = thermal_subsystem['ThermalMetrics']['@odata.id']
            result = self.col.connect_server(thermal_metrics_url)
            thermal_metrics = result.get('TemperatureSummaryCelsius', {})

            for metric in thermal_metrics:
                current_labels = {'type': metric}
                current_labels.update(self.col.labels)
                thermal_metric_value = (
                    math.nan
                    if thermal_metrics[metric]['Reading'] is None
                    else thermal_metrics[metric]['Reading']
                )
                self.temperature_metrics.add_sample(
                    "redfish_temperature", value=thermal_metric_value, labels=current_labels
                )

    def collect(self):
        """Collects performance information from the Redfish API."""
        logging.info("Target %s: Collecting performance data ...",self.col.target)
        self.get_power_metrics()
        self.get_temp_metrics()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_tb is not None:
            logging.exception(
                "Target %s: An exception occured in %s:%s",
                self.col.target,
                exc_tb.tb_frame.f_code.co_filename,
                exc_tb.tb_lineno
            )
