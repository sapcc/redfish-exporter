"""Prometheus Exporter for collecting baremetal server Redfish metrics."""
import logging
import os
import time
import sys
import re
import requests
from prometheus_client.core import GaugeMetricFamily
from collectors.performance_collector import PerformanceCollector
from collectors.firmware_collector import FirmwareCollector
from collectors.health_collector import HealthCollector
from collectors.certificate_collector import CertificateCollector

class RedfishMetricsCollector:
    """Class for collecting Redfish metrics."""
    def __enter__(self):
        return self

    def __init__(self, config, target, host, usr, pwd, metrics_type):
        self.target = target
        self.host = host

        self._username = usr
        self._password = pwd

        self.metrics_type = metrics_type

        self._timeout = int(os.getenv("TIMEOUT", config.get('timeout', 10)))
        self.labels = {"host": self.host}
        self._redfish_up = 0
        self._response_time = 0
        self._last_http_code = 0
        self.powerstate = 0

        self.urls = {
            "Systems": "",
            "SessionService": "",
            "Memory": "",
            "ManagedBy": "",
            "Processors": "",
            "Storage": "",
            "Chassis": "",
            "Power": "",
            "Thermal": "",
            "PowerSubsystem": "",
            "ThermalSubsystem": "",
            "NetworkInterfaces": "",
        }

        self.server_health = 0

        self.manufacturer = ""
        self.model = ""
        self.serial = ""
        self.status = {
            "ok": 0,
            "operable": 0,
            "enabled": 0,
            "good": 0,
            "critical": 1,
            "error": 1,
            "warning": 2,
            "absent": 0
        }
        self._start_time = time.time()

        self._session_url = ""
        self._auth_token = ""
        self._basic_auth = False
        self._session = ""
        self.redfish_version = "not available"

    def get_session(self):
        """Get the url for the server info and messure the response time"""
        logging.info("Target %s: Connecting to server %s", self.target, self.host)
        start_time = time.time()
        server_response = self.connect_server("/redfish/v1", noauth=True)

        self._response_time = round(time.time() - start_time, 2)
        logging.info("Target %s: Response time: %s seconds.", self.target, self._response_time)

        if not server_response:
            logging.warning("Target %s: No data received from server %s!", self.target, self.host)
            return

        logging.debug("Target %s: data received from server %s.", self.target, self.host)

        if "RedfishVersion" in server_response:
            self.redfish_version = server_response['RedfishVersion']

        for key in ["Systems", "SessionService"]:
            if key in server_response:
                self.urls[key] = server_response[key]['@odata.id']
            else:
                logging.warning(
                    "Target %s: No %s URL found on server %s!",
                    self.target,
                    key,
                    self.host
                )
                return

        session_service = self.connect_server(
            self.urls['SessionService'],
            basic_auth=True
        )

        if self._last_http_code != 200:
            logging.warning(
                "Target %s: Failed to get a session from server %s!",
                self.target,
                self.host
            )
            self._basic_auth = True
            return

        sessions_url = f"https://{self.target}{session_service['Sessions']['@odata.id']}"
        session_data = {"UserName": self._username, "Password": self._password}
        self._session.auth = None
        result = ""

        # Try to get a session
        try:
            result = self._session.post(
                sessions_url, json=session_data, verify=False, timeout=self._timeout
            )
            result.raise_for_status()

        except requests.exceptions.ConnectionError:
            logging.warning(
                "Target %s: Failed to get an auth token from server %s. Retrying ...",
                self.target, self.host
            )
            try:
                result = self._session.post(
                    sessions_url, json=session_data, verify=False, timeout=self._timeout
                )
                result.raise_for_status()

            except requests.exceptions.ConnectionError as e:
                logging.error(
                    "Target %s: Error getting an auth token from server %s: %s",
                    self.target, self.host, e
                )
                self._basic_auth = True

        except requests.exceptions.HTTPError as err:
            logging.warning(
                "Target %s: No session received from server %s: %s",
                self.target, self.host, err
            )
            logging.warning("Target %s: Switching to basic authentication.",
                    self.target
            )
            self._basic_auth = True

        except requests.exceptions.ReadTimeout as err:
            logging.warning(
                "Target %s: No session received from server %s: %s",
                self.target, self.host, err
            )
            logging.warning("Target %s: Switching to basic authentication.",
                    self.target
            )
            self._basic_auth = True

        if result:
            if result.status_code in [200, 201]:
                self._auth_token = result.headers['X-Auth-Token']
                self._session_url = result.json()['@odata.id']
                logging.info("Target %s: Got an auth token from server %s!", self.target, self.host)
                self._redfish_up = 1

    def connect_server(self, command, noauth=False, basic_auth=False):
        """Connect to the server and get the data."""
        logging.captureWarnings(True)

        req = ""
        req_text = ""
        server_response = ""
        self._last_http_code = 200
        request_duration = 0
        request_start = time.time()

        url = f"https://{self.target}{command}"

        # check if we already established a session with the server
        if not self._session:
            self._session = requests.Session()
        else:
            logging.debug("Target %s: Using existing session.", self.target)

        self._session.verify = False
        self._session.headers.update({"charset": "utf-8"})
        self._session.headers.update({"content-type": "application/json"})

        if noauth:
            logging.debug("Target %s: Using no auth", self.target)
        elif basic_auth or self._basic_auth:
            self._session.auth = (self._username, self._password)
            logging.debug("Target %s: Using basic auth with user %s", self.target, self._username)
        else:
            logging.debug("Target %s: Using auth token", self.target)
            self._session.auth = None
            self._session.headers.update({"X-Auth-Token": self._auth_token})

        logging.debug("Target %s: Using URL %s", self.target, url)
        try:
            req = self._session.get(url, stream=True, timeout=self._timeout)
            req.raise_for_status()

        except requests.exceptions.HTTPError as err:
            self._last_http_code = err.response.status_code
            if err.response.status_code == 401:
                logging.error(
                    "Target %s: Authorization Error: "
                    "Wrong job provided or user/password set wrong on server %s: %s",
                    self.target, self.host, err
                )
            else:
                logging.error("Target %s: HTTP Error on server %s: %s", self.target, self.host, err)

        except requests.exceptions.ConnectTimeout:
            logging.error("Target %s: Timeout while connecting to %s", self.target, self.host)
            self._last_http_code = 408

        except requests.exceptions.ReadTimeout:
            logging.error("Target %s: Timeout while reading data from %s", self.target, self.host)
            self._last_http_code = 408

        except requests.exceptions.ConnectionError as err:
            logging.error("Target %s: Unable to connect to %s: %s", self.target, self.host, err)
            self._last_http_code = 444
        except requests.exceptions.RequestException:
            logging.error("Target %s: Unexpected error: %s", self.target, sys.exc_info()[0])
            self._last_http_code = 500

        if req != "":
            self._last_http_code = req.status_code
            try:
                req_text = req.json()

            except requests.JSONDecodeError:
                logging.debug("Target %s: No json data received.", self.target)

            # req will evaluate to True if the status code was between 200 and 400
            # and False otherwise.
            if req:
                server_response = req_text

            # if the request fails the server might give a hint in the ExtendedInfo field
            else:
                if req_text:
                    logging.debug(
                        "Target %s: %s: %s",
                        self.target,
                        req_text['error']['code'],
                        req_text['error']['message']
                    )

                    if "@Message.ExtendedInfo" in req_text['error']:

                        if isinstance(req_text['error']['@Message.ExtendedInfo'], list):
                            if "Message" in req_text['error']['@Message.ExtendedInfo'][0]:
                                logging.debug(
                                    "Target %s: %s",
                                    self.target,
                                    req_text['error']['@Message.ExtendedInfo'][0]['Message']
                                )

                        elif isinstance(req_text['error']['@Message.ExtendedInfo'], dict):

                            if "Message" in req_text['error']['@Message.ExtendedInfo']:
                                logging.debug(
                                    "Target %s: %s",
                                    self.target,
                                    req_text['error']['@Message.ExtendedInfo']['Message']
                                )
                        else:
                            pass

        request_duration = round(time.time() - request_start, 2)
        logging.debug("Target %s: Request duration: %s", self.target, request_duration)
        return server_response

    def get_base_labels(self):
        """Get the basic labels for the metrics."""
        systems = self.connect_server(self.urls['Systems'])

        if not systems:
            return

        power_states = {"off": 0, "on": 1}
        # Get the server info for the labels
        server_info = {}
        for member in systems['Members']:
            self._systems_url = member['@odata.id']
            info = self.connect_server(self._systems_url)
            if info:
                server_info.update(info)

        if not server_info:
            return
        self.manufacturer = server_info['Manufacturer']
        self.model = server_info['Model']
        self.powerstate = power_states[server_info['PowerState'].lower()]
        # Dell has the Serial# in the SKU field, others in the SerialNumber field.
        if "SKU" in server_info and re.match(r'^[Dd]ell.*', server_info['Manufacturer']):
            self.serial = server_info['SKU']
        else:
            self.serial = server_info['SerialNumber']

        self.labels.update(
            {
                "host": self.host,
                "server_manufacturer": self.manufacturer,
                "server_model": self.model,
                "server_serial": self.serial
            }
        )

        self.server_health = self.status[server_info['Status']['Health'].lower()]

        # get the links of the parts for later
        for url in self.urls:
            if url in server_info:
                self.urls[url] = server_info[url]['@odata.id']

        # standard is a list but there are exceptions
        if isinstance(server_info['Links']['Chassis'][0], str):
            self.urls['Chassis'] = server_info['Links']['Chassis'][0]
            self.urls['ManagedBy'] = server_info['Links']['ManagedBy'][0]
        else:
            self.urls['Chassis'] = server_info['Links']['Chassis'][0]['@odata.id']
            self.urls['ManagedBy'] = server_info['Links']['ManagedBy'][0]['@odata.id']

        self.get_chassis_urls()

    def get_chassis_urls(self):
        """Get the urls for the chassis parts."""
        chassis_data = self.connect_server(self.urls['Chassis'])
        if not chassis_data:
            return None

        urls = ['PowerSubsystem', 'Power', 'ThermalSubsystem', 'Thermal']

        for url in urls:
            if url in chassis_data:
                self.urls[url] = chassis_data[url]['@odata.id']

        return chassis_data

    def collect(self):
        """Collect the metrics."""
        if self.metrics_type == 'health':
            up_metrics = GaugeMetricFamily(
                "redfish_up",
                "Redfish Server Monitoring availability",
                labels = self.labels,
            )
            up_metrics.add_sample(
                "redfish_up", 
                value = self._redfish_up,
                labels = self.labels
            )
            yield up_metrics

            version_metrics = GaugeMetricFamily(
                "redfish_version",
                "Redfish Server Monitoring redfish version",
                labels = self.labels,
            )
            version_labels = {'version': self.redfish_version}
            version_labels.update(self.labels)
            version_metrics.add_sample(
                "redfish_version",
                value = 1,
                labels = version_labels
            )
            yield version_metrics

            response_metrics = GaugeMetricFamily(
                "redfish_response_duration_seconds",
                "Redfish Server Monitoring response time",
                labels = self.labels,
            )
            response_metrics.add_sample(
                "redfish_response_duration_seconds",
                value = self._response_time,
                labels = self.labels,
            )
            yield response_metrics

        if self._redfish_up == 0:
            return

        self.get_base_labels()

        if self.metrics_type == 'health':

            cert_metrics = CertificateCollector(self.host, self.target, self.labels)
            cert_metrics.collect()

            yield cert_metrics.cert_metrics_isvalid
            yield cert_metrics.cert_metrics_valid_hostname
            yield cert_metrics.cert_metrics_valid_days
            yield cert_metrics.cert_metrics_selfsigned

            powerstate_metrics = GaugeMetricFamily(
                "redfish_powerstate",
                "Redfish Server Monitoring Power State Data",
                labels = self.labels,
            )
            powerstate_metrics.add_sample(
                "redfish_powerstate", value = self.powerstate, labels = self.labels
            )
            yield powerstate_metrics

            metrics = HealthCollector(self)
            metrics.collect()

            yield metrics.mem_metrics_correctable
            yield metrics.mem_metrics_uncorrectable
            yield metrics.health_metrics

        # Get the firmware information
        if self.metrics_type == 'firmware':
            metrics = FirmwareCollector(self)
            metrics.collect()

            yield metrics.fw_metrics

        # Get the performance information
        if self.metrics_type == 'performance':
            metrics = PerformanceCollector(self)
            metrics.collect()

            yield metrics.power_metrics
            yield metrics.temperature_metrics

        # Finish with calculating the scrape duration
        duration = round(time.time() - self._start_time, 2)
        logging.info(
            "Target %s: %s scrape duration: %s seconds",
            self.target, self.metrics_type, duration
        )

        scrape_metrics = GaugeMetricFamily(
            f"redfish_{self.metrics_type}_scrape_duration_seconds",
            f"Redfish Server Monitoring redfish {self.metrics_type} scrabe duration in seconds",
            labels = self.labels,
        )

        scrape_metrics.add_sample(
            f"redfish_{self.metrics_type}_scrape_duration_seconds",
            value = duration,
            labels = self.labels,
        )
        yield scrape_metrics

    def __exit__(self, exc_type, exc_val, exc_tb):
        logging.debug("Target %s: Deleting Redfish session with server %s", self.target, self.host)

        response = None

        if self._auth_token:
            session_url = f"https://{self.target}{self._session_url}"
            headers = {"x-auth-token": self._auth_token}

            logging.debug("Target %s: Using URL %s", self.target, session_url)

            try:
                response = requests.delete(
                    session_url, verify=False, timeout=self._timeout, headers=headers
                )
                response.close()

            except requests.exceptions.RequestException as e:
                logging.error(
                    "Target %s: Error deleting session with server %s: %s",
                    self.target, self.host, e
                )

            if response:
                logging.info("Target %s: Redfish Session deleted successfully.", self.target)
            else:
                logging.warning(
                    "Target %s: Failed to delete session with server %s",
                    self.target,
                    self.host
                )
                logging.warning("Target %s: Token: %s", self.target, self._auth_token)

        else:
            logging.debug(
                "Target %s: No Redfish session existing with server %s",
                self.target,
                self.host
            )

        if self._session:
            logging.info("Target %s: Closing requests session.", self.target)
            self._session.close()
