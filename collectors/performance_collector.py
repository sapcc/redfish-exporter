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

        # The legacy /Chassis/{id}/Power resource exposes a chassis-level
        # PowerControl[] aggregate that several vendors (notably HPE iLO 6) keep
        # populated with real-time data even when the modern PowerSubsystem
        # readings are stale or zero. Read it once and pass it to both the
        # chassis-aggregate reader and (if needed) the legacy per-PSU reader.
        legacy_power_data = None
        if self.col.urls['Power']:
            legacy_power_data = self.col.connect_server(self.col.urls['Power'])
            if legacy_power_data:
                if self.get_chassis_power_control(legacy_power_data):
                    no_psu_metrics = False

        # fall back to deprecated per-PSU URL only if neither modern nor chassis
        # aggregate produced anything usable.
        if legacy_power_data and no_psu_metrics:
            if self.get_old_power_metrics(legacy_power_data):
                no_psu_metrics = False

        if no_psu_metrics:
            logging.warning(
                "Target %s, Host %s, Model %s: No power metrics could be collected.",
                self.col.target,
                self.col.host,
                self.col.model
            )

    def get_chassis_power_control(self, power_data):
        """Read the chassis-level PowerControl[] aggregate from a pre-fetched
        legacy Power resource.

        Returns True when at least one reading was emitted.
        """
        if not power_data or 'PowerControl' not in power_data:
            return False

        emitted = False
        # PowerControl is an array — each entry typically represents one chassis
        # or one power-domain. Disambiguate with MemberId/Id.
        for entry in power_data['PowerControl']:
            consumed = entry.get('PowerConsumedWatts')
            if consumed is None:
                continue
            current_labels = {
                'type': 'PowerConsumedWatts',
                'id': entry.get('MemberId') or entry.get('Id') or '0',
            }
            current_labels.update(self.col.labels)
            self.power_metrics.add_sample(
                "redfish_power", value=consumed, labels=current_labels
            )
            emitted = True

        return emitted

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

        # Collect every reading first so we can decide whether the PSU is reporting
        # any non-zero data. A PSU that reports only zeros is either an empty bay or
        # a vendor-broken sensor (HPE iLO 6 publishes 0.0 on populated PSUs). Emitting
        # those clutters dashboards without informing them, so we drop them.
        readings = {}
        for metric in metrics:
            reading = None
            if metric in power_supply_metrics:
                metric_entry = power_supply_metrics[metric]
                if isinstance(metric_entry, dict):
                    reading = metric_entry.get('Reading')
                else:
                    reading = metric_entry
            if reading is None and metric in power_supply_data:
                reading = power_supply_data.get(metric)
            if reading is not None:
                readings[metric] = reading

        if not any(value for value in readings.values()):
            logging.debug(
                "Target %s: PSU %s reports only zero/missing readings, skipping.",
                self.col.target,
                power_supply_labels["id"]
            )
            return no_psu_metrics

        no_psu_metrics = False
        for metric, reading in readings.items():
            current_labels = {'type': metric}
            current_labels.update(power_supply_labels)
            self.power_metrics.add_sample(
                "redfish_power", value=reading, labels=current_labels
            )

        return no_psu_metrics


    def get_old_power_metrics(self, power_data):
        """Get the per-PSU readings from a pre-fetched legacy Power resource.

        Returns True when at least one reading was emitted.
        """
        logging.debug("Target %s: Reading deprecated Power URL.", self.col.target)

        if not power_data or 'PowerSupplies' not in power_data:
            logging.warning(
                "Target %s: Legacy Power resource has no PowerSupplies array.",
                self.col.target
            )
            return False

        # PowerCapacityWatts is included so vendors that publish only the
        # nameplate (e.g. Lenovo XCC, Fujitsu iRMC) still produce some output.
        # The silent-PSU rule below drops bays whose every reading is zero or
        # missing so this doesn't reintroduce dashboard noise.
        metrics = [
            'PowerOutputWatts',
            'EfficiencyPercent',
            'PowerInputWatts',
            'LineInputVoltage',
            'PowerCapacityWatts',
        ]

        emitted = False
        for psu in power_data['PowerSupplies']:
            # Skip absent slots up-front — they would otherwise hand us a
            # capacity reading like 0 for an empty bay.
            psu_state = psu.get('Status', {}).get('State') if isinstance(psu.get('Status'), dict) else None
            if psu_state == 'Absent':
                continue

            psu_name = psu.get('Name') or 'unknown'
            psu_model = psu.get('Model') or 'unknown'
            # MemberId is the unique-within-array key on the legacy Power resource.
            # Falling back to Id covers vendors that publish it instead.
            psu_id = psu.get('MemberId') or psu.get('Id') or 'unknown'
            psu_serial = psu.get('SerialNumber') or 'n/a'

            # Collect first, then drop the PSU entirely if it has nothing useful
            # to report. Same rule as the modern path.
            readings = {
                metric: psu.get(metric)
                for metric in metrics
                if psu.get(metric) is not None
            }
            if not any(value for value in readings.values()):
                continue

            for metric, value in readings.items():
                current_labels = {
                    'device_name': psu_name,
                    'device_model': psu_model,
                    'id': psu_id,
                    'serial': psu_serial,
                    'type': metric,
                }
                current_labels.update(self.col.labels)
                self.power_metrics.add_sample(
                    "redfish_power",
                    value=value,
                    labels=current_labels
                )
                emitted = True

        return emitted

    def get_temp_metrics(self):
        """Get the Thermal data from the Redfish API."""
        logging.info("Target %s: Get the Thermal data.", self.col.target)

        emitted = False
        if self.col.urls['ThermalSubsystem']:
            emitted = self._get_temp_from_thermal_subsystem()

        # Vendors that don't expose the modern ThermalSubsystem (e.g. Fujitsu iRMC,
        # older HPE Gen10) keep their thermal data on the legacy /Chassis/{id}/Thermal
        # resource. Read it whenever it is available so we don't lose temperature
        # coverage on those platforms.
        if not emitted and self.col.urls['Thermal']:
            self._get_temp_from_legacy_thermal()

    def _get_temp_from_thermal_subsystem(self):
        """Read temperatures from the modern ThermalSubsystem resource. Returns True
        if at least one reading was emitted."""
        thermal_subsystem = self.col.connect_server(self.col.urls['ThermalSubsystem'])

        # Check if thermal_subsystem data was received (connect_server returns "" on error)
        if not thermal_subsystem:
            logging.warning(
                "Target %s: No thermal subsystem data received, skipping temperature metrics.",
                self.col.target
            )
            return False

        # Check if ThermalMetrics key exists
        if 'ThermalMetrics' not in thermal_subsystem or '@odata.id' not in thermal_subsystem.get('ThermalMetrics', {}):
            logging.warning(
                "Target %s: ThermalMetrics not found in thermal subsystem data.",
                self.col.target
            )
            return False

        thermal_metrics_url = thermal_subsystem['ThermalMetrics']['@odata.id']
        result = self.col.connect_server(thermal_metrics_url)

        # Check if thermal metrics data was received (connect_server returns "" on error)
        if not result:
            logging.warning(
                "Target %s: No thermal metrics data received.",
                self.col.target
            )
            return False

        thermal_metrics = result.get('TemperatureSummaryCelsius', {})

        emitted = False
        for metric in thermal_metrics:
            current_labels = {'type': metric}
            current_labels.update(self.col.labels)
            entry = thermal_metrics[metric]
            reading = entry.get('Reading') if isinstance(entry, dict) else None
            if reading is None:
                continue
            self.temperature_metrics.add_sample(
                "redfish_temperature", value=reading, labels=current_labels
            )
            emitted = True
        return emitted

    def _get_temp_from_legacy_thermal(self):
        """Fallback to the deprecated /Chassis/{id}/Thermal resource. Reads the
        Temperatures[] array which most pre-PowerSubsystem BMCs expose. Returns
        True if at least one reading was emitted."""
        thermal = self.col.connect_server(self.col.urls['Thermal'])
        if not thermal:
            return False

        temperatures = thermal.get('Temperatures', [])
        if not isinstance(temperatures, list) or not temperatures:
            return False

        emitted = False
        for entry in temperatures:
            reading = entry.get('ReadingCelsius')
            if reading is None:
                continue
            # Skip absent sensors so we don't emit zeros for empty slots.
            state = entry.get('Status', {}).get('State')
            if state == 'Absent':
                continue
            sensor_name = entry.get('Name') or entry.get('MemberId') or 'unknown'
            current_labels = {
                'type': sensor_name,
                'id': entry.get('MemberId') or entry.get('Id') or 'unknown',
            }
            current_labels.update(self.col.labels)
            self.temperature_metrics.add_sample(
                "redfish_temperature", value=reading, labels=current_labels
            )
            emitted = True
        return emitted

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
