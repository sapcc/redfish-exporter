import logging

from prometheus_client.metrics_core import GaugeMetricFamily, CounterMetricFamily


class SensorsCollector:

    def __init__(self, redfish_metrics_collector):
        self.collector = redfish_metrics_collector

        self.sensor_labels = {
            "id": "Id",
            "name": "Name",
            "type": "ReadingType",
            "unit": "ReadingUnits",
            "physical_context": "PhysicalContext",
            "electrical_context": "ElectricalContext",
        }

        self.labels = list(self.collector.labels.keys()) + list(self.sensor_labels.keys())

        self.gauge_metrics = GaugeMetricFamily(
            "redfish_sensors",
            "Redfish Server Monitoring Sensors Data",
            labels=self.labels,
        )
        self.counter_metrics = CounterMetricFamily(
            "redfish_sensors_total",
            "Redfish Server Monitoring Sensors Data Total",
            labels=self.labels,
        )

    def collect(self):
        logging.info("Target %s: Get the Sensor data.", self.collector.target)
        url = self.collector.urls['Sensors']
        sensors = self.collector.connect_server(url)

        for sensor_ref in sensors.get('Members', []):
            metric = self.collector.connect_server(sensor_ref['@odata.id'])

            status = metric.get('Status', {})
            state = status.get('State')
            reading = metric.get('Reading')

            if state != 'Enabled' or reading is None:
                continue

            labels = ([self.collector.labels[key] for key in self.collector.labels.keys()]
                      + [str(metric.get(k, "unknown")) for k in self.sensor_labels.values()])

            units = metric.get('ReadingUnits')
            is_counter = units in ["kW.h", "kWh", "Joules"]

            if is_counter:
                self.counter_metrics.add_metric(labels=labels, value=float(reading))
            else:
                self.gauge_metrics.add_metric(labels=labels, value=float(reading))

        return [self.gauge_metrics, self.counter_metrics]
