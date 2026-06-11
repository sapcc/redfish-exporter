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
                "Target %s, Host %s, Model %s: No power metrics could be collected.",
                self.col.target,
                self.col.host,
                self.col.model
            )

    def get_power_subsystem_metrics(self):
        '''Get the PowerSubsystem data from the Redfish API.'''
        no_psu_metrics = True
        power_supplies_url = None

        logging.debug("Target %s: Checking PowerSubsystem ...", self.col.target)
        power_subsystem = self.col.connect_server(self.col.urls['PowerSubsystem'])
        
        # Check if power_subsystem data was received (connect_server returns "" on error)
        if not power_subsystem:
            logging.warning(
                "Target %s: No power subsystem data received, skipping power metrics.",
                self.col.target
            )
            return no_psu_metrics
        
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
        
        # Check if power_supplies data was received (connect_server returns "" on error)
        if not power_supplies:
            logging.warning(
                "Target %s: No power supplies data received.",
                self.col.target
            )
            return no_psu_metrics

        if 'Members' in power_supplies:
            power_supplies = power_supplies['Members']

        for power_supply in power_supplies:
            psu_failed = self.get_power_supply_metrics(power_supply)
            # Track success across all PSUs: fallback to legacy path only when NO PSU produced metrics.
            if not psu_failed:
                no_psu_metrics = False

        return no_psu_metrics

    def get_power_supply_metrics(self, power_supply):
        """Get power supply metrics and update labels."""
        fields = ["Name", "Manufacturer", "Model"]
        metrics = ["PowerInputWatts", "PowerOutputWatts", "PowerCapacityWatts", "InputPowerWatts", "OutputPowerWatts"]
        no_psu_metrics = True


        power_supply_labels = {}
        power_supply_data = self.col.connect_server(power_supply['@odata.id'])

        # Check if power_supply data was received (connect_server returns "" on error)
        if not power_supply_data:
            logging.warning(
                "Target %s: No power supply data received.",
                self.col.target
            )
            return no_psu_metrics

        # NOTE: We intentionally do NOT skip PSUs reporting Status.State == "Absent" here.
        # HPE iLO 6 marks every populated PSU bay as "Absent" on the modern
        # /PowerSubsystem/PowerSupplies/{id} resource even when the PSU is physically
        # present and operational. Filtering on Absent dropped all bays and forced the
        # legacy fallback path. We let the per-metric loop below decide whether each
        # individual reading is reportable instead.

        if 'Metrics' not in power_supply_data:
            logging.debug(
                "Target %s: No Metrics URL on PSU %s — emitting parent-resource "
                "values only.",
                self.col.target,
                power_supply_data.get('Id', 'unknown')
            )
            power_supply_metrics = {}
        else:
            power_supply_metrics_url = power_supply_data['Metrics']['@odata.id']
            fetched = self.col.connect_server(power_supply_metrics_url)
            power_supply_metrics = fetched if fetched else {}

        for field in fields:
            field_value = power_supply_data.get(field, 'unknown')
            # Ensure None values are replaced with 'unknown' for Prometheus label compatibility
            power_supply_labels.update({field: field_value if field_value is not None else 'unknown'})

        # id is the only label Redfish guarantees to be unique per PSU collection;
        # serial may be absent on some vendors. Both are needed to keep series distinct.
        power_supply_labels["id"] = power_supply_data.get('Id') or 'unknown'
        power_supply_labels["serial"] = power_supply_data.get('SerialNumber') or 'n/a'

        power_supply_labels.update(self.col.labels)

        for metric in metrics:
            current_labels = {'type': metric}
            current_labels.update(power_supply_labels)

            # Prefer the dedicated Metrics sub-resource. If it doesn't expose this metric,
            # fall back to the same-named field on the parent PowerSupply resource
            # (some vendors put readings on the parent rather than under Metrics).
            # A real value of 0 is a valid reading (idle PSU) and is NOT treated as missing.
            reading = None
            if metric in power_supply_metrics:
                metric_entry = power_supply_metrics[metric]
                if isinstance(metric_entry, dict):
                    reading = metric_entry.get('Reading')
                else:
                    reading = metric_entry
            if reading is None and metric in power_supply_data:
                reading = power_supply_data.get(metric)

            if reading is None:
                # Neither resource reported this measurement for this PSU.
                continue

            no_psu_metrics = False
            self.power_metrics.add_sample(
                "redfish_power", value=reading, labels=current_labels
            )

        return no_psu_metrics


    def get_old_power_metrics(self):
        """Get the Power data from the Redfish API."""
        logging.debug("Target %s: Fallback to deprecated Power URL.", self.col.target)

        no_psu_metrics = True

        power_data = self.col.connect_server(self.col.urls['Power'])
        
        # Check if power_data was received and has PowerSupplies (connect_server returns "" on error)
        if not power_data or 'PowerSupplies' not in power_data:
            logging.warning(
                "Target %s: No power data received or PowerSupplies not found.",
                self.col.target
            )
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
            # MemberId is the unique-within-array key on the legacy Power resource.
            # Falling back to Id covers vendors that publish it instead.
            psu_id = psu.get('MemberId') or psu.get('Id') or 'unknown'
            psu_serial = psu.get('SerialNumber') or 'n/a'

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
                    'id': psu_id,
                    'serial': psu_serial,
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
            
            # Check if thermal_subsystem data was received (connect_server returns "" on error)
            if not thermal_subsystem:
                logging.warning(
                    "Target %s: No thermal subsystem data received, skipping temperature metrics.",
                    self.col.target
                )
                return
            
            # Check if ThermalMetrics key exists
            if 'ThermalMetrics' not in thermal_subsystem or '@odata.id' not in thermal_subsystem.get('ThermalMetrics', {}):
                logging.warning(
                    "Target %s: ThermalMetrics not found in thermal subsystem data.",
                    self.col.target
                )
                return
            
            thermal_metrics_url = thermal_subsystem['ThermalMetrics']['@odata.id']
            result = self.col.connect_server(thermal_metrics_url)
            
            # Check if thermal metrics data was received (connect_server returns "" on error)
            if not result:
                logging.warning(
                    "Target %s: No thermal metrics data received.",
                    self.col.target
                )
                return
            
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
