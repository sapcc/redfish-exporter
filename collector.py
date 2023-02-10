from prometheus_client.core import GaugeMetricFamily

import requests
import logging
import os
import time
import sys
import math
from re import search

class RedfishMetricsCollector(object):
    def __init__(self, config, target, host, usr, pwd, firmware=False, health=False):

        self._target = target
        self._host = host

        self._username = usr
        self._password = pwd

        self._timeout = int(os.getenv('TIMEOUT', config['timeout']))
        self._labels = {'host': self._host}
        self._redfish_up = 0
        self._response_time = 0
        self._last_http_code = 0
        self._powerstate = 0

        self._firmware = firmware
        self._health = health

        self._systems_url = ""
        self._urls = {
            'Memory': "",
            'ManagedBy': "",
            'Processors': "",
            'Storage': "",
            'SimpleStorage': "",
            'Chassis': "",
            'Power': "",
            'Thermal': "",
            'NetworkInterfaces': ""
        }

        self._server_health = 0
        self._health_metrics = None
        self._mem_metrics_correctable = None
        self._mem_metrics_unorrectable = None
        self._manufacturer = ""
        self._model = ""
        self._status = {"ok": 0, "operable": 0, "enabled": 0, "good": 0, "critical": 1, "error": 1, "warning": 2}
        self._start_time = time.time()
        
        self._session_url = ""
        self._auth_token = ""
        self._basic_auth = False
        self._session = ""
       
    def get_session(self):
        # Get the url for the server info and messure the response time
        logging.info("Target {0}: Connecting to server {1}".format(self._target, self._host))
        start_time = time.time()
        server_response = self.connect_server("/redfish/v1", noauth=True)
        self._response_time = round(time.time() - start_time,2)
        logging.info("Target {0}: Response time: {1} seconds.".format(self._target, self._response_time))

        if not server_response:
            logging.warning("Target {0}: No data received from server {1}!".format(self._target, self._host))
            return

        logging.debug("Target {0}: data received from server {1}.".format(self._target, self._host))
        if not server_response.get('SessionService'):
            logging.warning("Target {0}: No session service registered on server {1}!".format(self._target, self._host))
            return

        session_service = self.connect_server(server_response['SessionService']['@odata.id'], basic_auth=True)
        if self._last_http_code != 200:
            logging.warning("Target {0}: Failed to get a session from server {1}!".format(self._target, self._host))
            self._basic_auth = True
            return

        sessions_url = "https://{0}{1}".format(self._target, session_service['Sessions']['@odata.id'])
        session_data = {"UserName": self._username, "Password": self._password}
        self._session.auth = None
        result = ""

        # Try to get a session
        try:
            result = self._session.post(sessions_url, json=session_data, verify=False, timeout=self._timeout)
            result.raise_for_status()

        except requests.exceptions.ConnectionError as err:
            logging.error("Target {0}: Error getting an auth token from server {1}: {2}".format(self._target, self._host, err))
            self._basic_auth = True

        except requests.exceptions.HTTPError as err:
            logging.warning("Target {0}: No session received from server {1}: {2}".format(self._target, self._host, err))
            logging.warning("Target {0}: Switching to basic authentication.".format(self._target))
            self._basic_auth = True

        if result:
            if result.status_code in [200,201]:
                self._auth_token = result.headers['X-Auth-Token']
                self._session_url = result.json()['@odata.id']
                logging.info("Target {0}: Got an auth token from server {1}!".format(self._target, self._host))
                self._redfish_up = 1
    
    def connect_server(self, command, noauth = False, basic_auth = False):
        logging.captureWarnings(True)
        
        req = ""
        req_text = ""
        server_response = ""
        self._last_http_code = 200
        request_duration = 0
        request_start = time.time()

        url = "https://{0}{1}".format(self._target, command)

        # check if we already established a session with the server
        if not self._session:
            self._session = requests.Session()
        else:
            logging.debug("Target {0}: Using existing session.".format(self._target))
        self._session.verify = False
        self._session.headers.update({'charset': 'utf-8'})
        self._session.headers.update({'content-type': 'application/json'})

        if noauth:
            logging.debug("Target {0}: Using no auth".format(self._target))
        elif basic_auth or self._basic_auth:
            self._session.auth = (self._username, self._password)
            logging.debug("Target {0}: Using basic auth with user {1}".format(self._target, self._username))
        else:
            logging.debug("Target {0}: Using auth token".format(self._target))
            self._session.auth = None
            self._session.headers.update({'X-Auth-Token': self._auth_token})

        logging.debug("Target {0}: Using URL {1}".format(self._target, url))
        try:
            req = self._session.get(url, timeout = self._timeout)
            req.raise_for_status()

        except requests.exceptions.HTTPError as err:
            self._last_http_code = err.response.status_code
            if err.response.status_code == 401:
                logging.error("Target {0}: Authorization Error: Wrong job provided or user/password set wrong on server {1}: {2}".format(self._target, self._host, err))
            else:
                logging.error("Target {0}: HTTP Error on server {1}: {2}".format(self._target, self._host, err))

        except requests.exceptions.ConnectTimeout:
            logging.error("Target {0}: Timeout while connecting to {1}".format(self._target, self._host))
            self._last_http_code = 408

        except requests.exceptions.ReadTimeout:
            logging.error("Target {0}: Timeout while reading data from {1}".format(self._target, self._host))
            self._last_http_code = 408

        except requests.exceptions.ConnectionError as excptn:
            logging.error("Target {0}: Unable to connect to {1}: {2}".format(self._target, self._host, excptn))
            self._last_http_code = 444

        except:
            logging.error("Target {0}: Unexpected error: {1}".format(self._target, sys.exc_info()[0]))
            self._last_http_code = 500

        else:
            self._last_http_code = req.status_code

        if req != "":
            try: 
                req_text = req.json()

            except:
                logging.debug("Target {0}: No json data received.".format(self._target))

            # req will evaluate to True if the status code was between 200 and 400 and False otherwise.
            if req:
                server_response = req_text

            # if the request fails the server might give a hint in the ExtendedInfo field
            else:
                if req_text:
                    logging.debug("Target {0}: {1}: {2}".format(self._target, req_text['error']['code'], req_text['error']['message']))
                    if '@Message.ExtendedInfo' in req_text['error']:
                        if type(req_text['error']['@Message.ExtendedInfo']) == list:
                            if 'Message' in req_text['error']['@Message.ExtendedInfo'][0]:
                                logging.debug("Target {0}: {1}".format(self._target, req_text['error']['@Message.ExtendedInfo'][0]['Message']))
                        elif type(req_text['error']['@Message.ExtendedInfo']) == dict:
                            if 'Message' in req_text['error']['@Message.ExtendedInfo']:
                                logging.debug("Target {0}: {1}".format(self._target, req_text['error']['@Message.ExtendedInfo']['Message']))
                        else:
                            pass

        request_duration = round(time.time() - request_start,2)
        logging.debug("Target {0}: Request duration: {1}".format(self._target, request_duration))
        return server_response


    def _get_labels(self):

        systems = self.connect_server("/redfish/v1/Systems")

        if not systems:
            return

        powerstates = {'off': 0, 'on': 1}
        # Get the server info for the labels
        self._systems_url = systems['Members'][0]['@odata.id']
        server_info = self.connect_server(self._systems_url)
        if not server_info:
            return
        self._manufacturer = server_info['Manufacturer']
        self._model = server_info['Model']
        self._powerstate = powerstates[server_info['PowerState'].lower()]
        if 'SKU' in server_info:
            serial = server_info['SKU']
        else:
            serial = server_info['SerialNumber']
        self._labels.update({'host': self._host, 'server_manufacturer': self._manufacturer, 'server_model': self._model, 'server_serial': serial})

        self._server_health = self._status[server_info['Status']['Health'].lower()]

        # get the links of the parts for later
        if type(server_info['Links']['Chassis'][0]) == str:
            self._urls['Chassis'] = server_info['Links']['Chassis'][0]
            self._urls['ManagedBy'] = server_info['Links']['ManagedBy'][0]
        else:
            self._urls['Chassis'] = server_info['Links']['Chassis'][0]['@odata.id']
            self._urls['ManagedBy'] = server_info['Links']['ManagedBy'][0]['@odata.id']
        if 'Memory' in server_info:
            self._urls['Memory'] = server_info['Memory']['@odata.id']
        if 'NetworkInterfaces' in server_info:
            self._urls['NetworkInterfaces'] = server_info['NetworkInterfaces']['@odata.id']
        if 'Processors' in server_info:
            self._urls['Processors'] = server_info['Processors']['@odata.id']
        if 'Storage' in server_info:
            self._urls['Storage'] = server_info['Storage']['@odata.id']
        if 'SimpleStorage' in server_info:
            self._urls['SimpleStorage'] = server_info['SimpleStorage']['@odata.id']

    def get_proc_health(self):
        logging.debug("Target {0}: Get the CPU health data.".format(self._target))
        processor_collection = self.connect_server(self._urls['Processors'])

        if not processor_collection:
            return
        for processor in processor_collection['Members']:
            processor_data = self.connect_server(processor['@odata.id'])
            if not processor_data:
                continue
            current_labels = {'type': 'processor', 'name': processor_data.get('Socket', "unknown"), 'cpu_type': processor_data.get('ProcessorType', "unknown"), 'cpu_model': processor_data.get('Model', "unknown"), 'cpu_cores': str(processor_data.get('TotalCores', "unknown")), 'cpu_threads': str(processor_data.get('TotalThreads', "unknown"))}
            current_labels.update(self._labels)
            if processor_data['Status']['Health']:
                self._health_metrics.add_sample('redfish_health', value=self._status[processor_data['Status']['Health'].lower()], labels=current_labels)
            else:
                logging.warning("Target {0}: No Processor health data provided ({1})!".format(self._target, processor['@odata.id']))
                self._health_metrics.add_sample('redfish_health', value=math.nan, labels=current_labels)

    def get_storage_health(self):
        logging.debug("Target {0}: Get the storage health data.".format(self._target))
        storage_collection = self.connect_server(self._urls['Storage'])

        if not storage_collection:
            return
        for controller in storage_collection['Members']:
            controller_data = self.connect_server(controller['@odata.id'])
            if not controller_data:
                continue
            if controller_data.get('StorageControllers'):
                # Cisco sometimes uses a list or a dict
                if type(controller_data['StorageControllers']) == list:
                    controller_details = controller_data['StorageControllers'][0]
                else:
                    controller_details = controller_data['StorageControllers']
            else:
                controller_details = controller_data

            # HPE ILO5 is missing the Name in the details of the controllers
            if 'Name' in controller_details:
                controller_name = controller_details['Name']
            elif 'Name' in controller_data:
                controller_name = controller_data['Name']
            else:
                controller_name = 'unknown'

            if 'Health' in controller_details['Status']:
                # Cisco sometimes uses None as status for onboard controllers
                controller_status = math.nan if controller_details['Status']['Health'] is None else self._status[controller_details['Status']['Health'].lower()]
            else:
                logging.warning("Target {0}, Host {1}, Model {2}, Controller {3}: No health data found.".format(self._target, self._host,self._model, controller_name))

            current_labels = {'type': 'storage', 'name': controller_name, 'controller_model': controller_details.get('Model', 'unknown'), 'controller_manufacturer': controller_details.get('Manufacturer', 'unknown')}
            current_labels.update(self._labels)
            self._health_metrics.add_sample('redfish_health', value=controller_status, labels=current_labels)
            
            # Sometimes not all attributes are implemented. Checking if existing one by one.
            disk_attributes = {'Name': 'name', 'MediaType': 'disk_type', 'Model': 'disk_model', 'Manufacturer': 'disk_manufacturer', 'CapacityBytes': 'disk_capacity', 'Protocol': 'disk_protocol'}
            for disk in controller_data['Drives']:
                current_labels = {'type': 'disk'}
                disk_data = self.connect_server(disk['@odata.id'])
                if disk_data == '':
                    continue

                for disk_attribute in disk_attributes:
                    if disk_attribute in disk_data:
                        current_labels.update({disk_attributes[disk_attribute]: str(disk_data[disk_attribute])})

                current_labels.update(self._labels)
                if 'Health' in disk_data['Status']:
                    disk_status = math.nan if disk_data['Status']['Health'] is None else self._status[disk_data['Status']['Health'].lower()]
                    self._health_metrics.add_sample('redfish_health', value=disk_status, labels=current_labels)
                else:
                    logging.warning("Target {0}, Host {1}, Model {2}, Disk {3}: No health data found.".format(self._target, self._host,self._model, disk_data['name']))

    def get_simple_storage_health(self):
        storage_collection = self.connect_server(self._urls['SimpleStorage'])
        if not storage_collection:
            return
        for controller in storage_collection['Members']:
            controller_data = self.connect_server(controller['@odata.id'])
            if not controller_data:
                continue
            controller_name = controller_data['Name']
            controller_status = math.nan if controller_data['Status']['Health'] is None else self._status[controller_data['Status']['Health'].lower()]

            current_labels = {'type': 'storage', 'name': controller_name}
            current_labels.update(self._labels)
            self._health_metrics.add_sample('redfish_health', value=controller_status, labels=current_labels)
            # Sometimes not all attributes are implemented. Checking if existing one by one.
            disk_attributes = {'Name': 'name', 'Model': 'disk_model', 'Manufacturer': 'disk_manufacturer'}
            for disk in controller_data['Devices']:
                current_labels = {'type': 'disk'}
                if disk['Status']['State'] != 'Absent':
                    for disk_attribute in disk_attributes:
                        if disk_attribute in disk:
                            current_labels.update({disk_attributes[disk_attribute]: disk[disk_attribute]})

                    current_labels.update(self._labels)
                    self._health_metrics.add_sample('redfish_health', value=self._status[disk['Status']['Health'].lower()], labels=current_labels)

    def get_chassis_health(self):
        logging.debug("Target {0}: Get the Chassis health data.".format(self._target))
        chassis_data = self.connect_server(self._urls['Chassis'])
        if not chassis_data:
            return

        current_labels = {'type': 'chassis', 'name': chassis_data['Name']}
        current_labels.update(self._labels)
        self._health_metrics.add_sample('redfish_health', value=self._status[chassis_data['Status']['Health'].lower()], labels=current_labels)
        if 'Power' in chassis_data:
            self._urls['Power'] = chassis_data['Power']['@odata.id']
        if 'Thermal' in chassis_data:
            self._urls['Thermal'] = chassis_data['Thermal']['@odata.id']

    def get_power_health(self):
        logging.debug("Target {0}: Get the PDU health data.".format(self._target))
        power_data = self.connect_server(self._urls['Power'])
        if not power_data:
            return

        for psu in power_data['PowerSupplies']:
            psu_name = psu.get('Name', 'unknown')
            current_labels = {'type': 'powersupply', 'name': psu_name}
            current_labels.update(self._labels)
            psu_health = math.nan
            psu_status = dict((k.lower(),v) for k,v in psu['Status'].items()) # convert to lower case because there are differences per vendor
            if 'state' in psu_status:
                if psu_status['state'] != 'absent':
                    if 'health' in psu_status:
                        psu_health = math.nan if psu_status['health'] is None else self._status[psu_status['health'].lower()]
                    elif 'state' in psu_status:
                        psu_health = math.nan if psu_status['state'] is None else self._status[psu_status['state'].lower()]
            
            if psu_health is math.nan: 
                logging.warning("Target {0}, Host {1}, Model {2}, PSU {3}: No health data found.".format(self._target, self._host,self._model, psu_name))

            self._health_metrics.add_sample('redfish_health', value=psu_health, labels=current_labels)

    def get_thermal_health(self):
        logging.debug("Target {0}: Get the thermal health data.".format(self._target))
        thermal_data = self.connect_server(self._urls['Thermal'])
        if not thermal_data:
            return

        for fan in thermal_data['Fans']:
            fan_name = fan.get('Name', 'unknown')
            current_labels = {'type': 'fan', 'name': fan_name}
            current_labels.update(self._labels)
            fan_health = math.nan
            fan_status = dict((k.lower(),v) for k,v in fan['Status'].items()) # convert to lower case because there are differences per vendor
            if 'state' in fan_status:
                if fan_status['state'] != 'absent':
                    if 'health' in fan_status:
                        fan_health = math.nan if fan_status['health'] is None or fan_status['health'] == '' else self._status[fan_status['health'].lower()]
                    elif 'state' in fan_status:
                        fan_health = math.nan if fan_status['state'] is None else self._status[fan_status['state'].lower()]

            if fan_health is math.nan: 
                logging.warning("Target {0}, Host {1}, Model {2}, Fan {3}: No health data found.".format(self._target, self._host,self._model, fan['Name']))

            self._health_metrics.add_sample('redfish_health', value=fan_health, labels=current_labels)

    def get_memory_health(self):
        logging.debug("Target {0}: Get the Memory data.".format(self._target))

        memory_collection = self.connect_server(self._urls['Memory'])
        if not memory_collection:
            return

        for dimm_url in memory_collection['Members']:
            dimm_info = self.connect_server(dimm_url['@odata.id'])
            if not dimm_info:
                continue
            current_labels = {'type': 'memory', 'name': dimm_info['Name']}
            current_labels.update(self._labels)
            if type(dimm_info['Status']) == str:
                dimm_health = self._status[dimm_info['Status'].lower()]
            else:
                dimm_health = math.nan
                dimm_status = dict((k.lower(),v) for k,v in dimm_info['Status'].items()) # convert to lower case because there are differences per vendor
                if 'state' in dimm_status:
                    if dimm_status['state'] is not None:
                        if dimm_status['state'].lower() == 'absent':
                            logging.warning("Target {0}, Host {1}, Model {2}, Dimm {3}: absent.".format(self._target, self._host,self._model, dimm_info['Name']))
                            continue
                    if 'Manufacturer' in dimm_info:
                        manufacturer = dimm_info['Manufacturer']
                    if 'Oem' in dimm_info:
                        if 'Hpe' in dimm_info['Oem']:
                            manufacturer = dimm_info['Oem']['Hpe']['VendorName']
                    current_labels.update({'dimm_capacity': str(dimm_info['CapacityMiB']), 'dimm_speed': str(dimm_info['OperatingSpeedMhz']), 'dimm_type': dimm_info['MemoryDeviceType'], 'dimm_manufacturer': manufacturer})
                    if 'health' in dimm_status:
                        dimm_health = math.nan if dimm_info['Status']['Health'] is None else self._status[dimm_info['Status']['Health'].lower()]
                    elif 'state' in dimm_status:
                        dimm_health = math.nan if dimm_info['Status']['State'] is None else self._status[dimm_info['Status']['State'].lower()]

            if dimm_health is math.nan:
                logging.warning("Target {0}, Host {1}, Model {2}, Dimm {3}: No health data found.".format(self._target, self._host,self._model, dimm_info['Name']))
            
            self._health_metrics.add_sample('redfish_health', value=dimm_health, labels=current_labels)

            if 'Metrics' in dimm_info:
                dimm_metrics = self.connect_server(dimm_info['Metrics']['@odata.id'])
                if not dimm_metrics:
                    continue
                correctable_ecc_error = math.nan if dimm_metrics['HealthData']['AlarmTrips']['CorrectableECCError'] is None else int(dimm_metrics['HealthData']['AlarmTrips']['CorrectableECCError'])
                uncorrectable_ecc_error = math.nan if dimm_metrics['HealthData']['AlarmTrips']['UncorrectableECCError'] is None else int(dimm_metrics['HealthData']['AlarmTrips']['UncorrectableECCError'])
                self._mem_metrics_correctable.add_sample('redfish_memory_correctable', value=correctable_ecc_error, labels=current_labels)
                self._mem_metrics_unorrectable.add_sample('redfish_memory_uncorrectable', value=uncorrectable_ecc_error, labels=current_labels)
            else:
                logging.warning("Target {0}, Host {1}, Model {2}: Dimm {3}: No Dimm Metrics found.".format(self._target, self._host,self._model, dimm_info['Name']))
            
    def collect(self):

        try:
            # Export the up and response metrics
            up_metrics = GaugeMetricFamily('redfish_up','Server Monitoring for redfish availability',labels=self._labels)
            response_metrics = GaugeMetricFamily('redfish_response_duration_seconds','Server Monitoring for redfish response time',labels=self._labels)

            up_metrics.add_sample('redfish_up', value=self._redfish_up, labels=self._labels)
            response_metrics.add_sample('redfish_response_duration_seconds', value=self._response_time , labels=self._labels)
            yield up_metrics
            yield response_metrics

            if self._redfish_up == 0:
                return

            self._get_labels()
            powerstate_metrics = GaugeMetricFamily('redfish_powerstate','Server Monitoring Power State Data',labels=self._labels)
            powerstate_metrics.add_sample('redfish_powerstate', value=self._powerstate , labels=self._labels)
            yield powerstate_metrics
            
            logging.info("Target {0}: Collecting data ...".format(self._target))
            if self._health:
                self._health_metrics = GaugeMetricFamily('redfish_health','Server Monitoring Health Data',labels=self._labels)

                current_labels = {'type': 'system', 'name': 'summary'}
                current_labels.update(self._labels)
                self._health_metrics.add_sample('redfish_health', value=self._server_health, labels=current_labels)

                # Get the processor health data
                if self._urls['Processors']:
                    self.get_proc_health()
                else:
                    logging.warning("Target {0}: No Processors URL provided! Cannot get Processors data!".format(self._target))

                # Get the storage health data
                if self._urls['Storage']:
                    self.get_storage_health()
                elif self._urls['SimpleStorage']:
                    self.get_simple_storage_health()
                else:
                    logging.warning("Target {0}: No Storage URL provided! Cannot get Storage data!".format(self._target))


                # Get the chassis health data
                if self._urls['Chassis']:
                    self.get_chassis_health()
                else:
                    logging.warning("Target {0}: No Chassis URL provided! Cannot get Chassis data!".format(self._target))

                # Get the powersupply health data
                if self._urls['Power']:
                    self.get_power_health()
                else:
                    logging.warning("Target {0}: No Power URL provided! Cannot get PSU data!".format(self._target))

                # Get the thermal health data
                if self._urls['Thermal']:
                    self.get_thermal_health()
                else:
                    logging.warning("Target {0}: No Thermal URL provided! Cannot get thermal data!".format(self._target))

                # Export the memory data
                if self._urls['Memory']:
                    self._mem_metrics_correctable = GaugeMetricFamily('redfish_memory_correctable','Server Monitoring Memory Data for correctable errors',labels=self._labels)
                    self._mem_metrics_unorrectable = GaugeMetricFamily('redfish_memory_uncorrectable','Server Monitoring Memory Data for uncorrectable errors',labels=self._labels)
                    self.get_memory_health()
                    yield self._mem_metrics_correctable
                    yield self._mem_metrics_unorrectable
                else:
                    logging.warning("Target {0}: No Memory URL provided! Cannot get memory data!".format(self._target))

                yield self._health_metrics

                duration = round(time.time() - self._start_time,2)
                logging.info("Target {0}: Scrape duration: {1} seconds".format(self._target, duration))
                scrape_metrics = GaugeMetricFamily('redfish_scrape_duration_seconds','Server Monitoring redfish scrabe duration in seconds',labels=self._labels)
                scrape_metrics.add_sample('redfish_scrape_duration_seconds', value=duration, labels=self._labels)
                yield scrape_metrics

            # Get the firmware information
            if self._firmware:
                logging.debug("Target {0}: Get the firmware information.".format(self._target))

                fw_collection = self.connect_server("/redfish/v1/UpdateService/FirmwareInventory")
                if not fw_collection:
                    logging.warning("Target {0}: Cannot get Firmware data!".format(self._target))
                    return
                fw_metrics = GaugeMetricFamily('server_monitoring_fwdata','Server Monitoring Firmware Data',labels=self._labels)
                for fw_member in fw_collection['Members']:
                    fw_member_url = fw_member['@odata.id']
                    if (search(".*Dell.*", self._manufacturer) and ("Installed" in fw_member_url)) or not search(".*Dell.*", self._manufacturer):
                        server_response = self.connect_server(fw_member_url)
                        if not server_response:
                            continue
                        name = server_response['Name'].split(",",1)[0]
                        if 'Version' in server_response:
                            version = server_response['Version']
                            if version != "N/A":
                                current_labels = {'name': name, 'version': version}
                                current_labels.update(self._labels)
                                fw_metrics.add_sample('redfish_version', value=1, labels=current_labels)

                yield fw_metrics

        except Exception as err:
            logging.error("Target {0}: An exception occured: {1}".format(self._target, err))
        

        finally:
            logging.debug("Target {0}: Deleting Redfish session with server {1}".format(self._target, self._host))

            if self._auth_token:
                session_url = "https://{0}{1}".format(self._target, self._session_url)
                headers = {'x-auth-token': self._auth_token}

                logging.debug("Target {0}: Using URL {1}".format(self._target, session_url))

                response = requests.delete(session_url, verify=False, timeout=self._timeout, headers=headers)
                response.close()

                if response:
                    logging.info("Target {0}: Redfish Session deleted successfully.".format(self._target))
                else:
                    logging.warning("Target {0}: Failed to delete session with server {1}".format(self._target, self._host))
                    logging.warning("Target {0}: Token: {1}".format(self._target, self._auth_token))

            else:
                logging.debug("Target {0}: No Redfish session existing with server {1}".format(self._target, self._host))

            if self._session:
                logging.info("Target {0}: Closing requests session.".format(self._target))
                self._session.close()
