# Redfish-Exporter

This is a Prometheus Exporter for extracting metrics from a server using the Redfish API.
The hostname of the server has to be passed as **target parameter** in the http call.

It has been tested with the following server models:

Cisco UCS C480M5, working properly since BMC FW 4.1(1d)  
Cisco UCS C240M4  
Cisco UCS C240M5  
Cisco UCS C220M4  
Cisco UCS C220M5

Cisco BMC FW below 4.x has its flaws regarding redfish API. Hence, I recommend updating at least to 4.0(1c).

Dell PowerEdge R640  
Dell PowerEdge R730  
Dell PowerEdge R740  
Dell PowerEdge R640  
Dell PowerEdge R840

Lenovo ThinkSystem SR950

HPE DL360 Gen10   
HPE DL560 Gen10

## Example Call

If you are logged into the POD running the exporter, you can retrieve metrics from a server, make an HTTP call to the exporter with the `target` and `job` parameters. The exporter supports the following endpoints:

### `/health`
Retrieves health-related metrics (e.g., system status, memory errors, power state).

```bash
curl "http://localhost:9220/health?target=server1.example.com&job=redfish-myjob"
```

### `/firmware`
Retrieves firmware version information for the server components.

```bash
curl "http://localhost:9220/firmware?target=server1.example.com&job=redfish-myjob"
```

### `/performance`
Retrieves performance-related metrics (e.g., power consumption, temperature).

```bash
curl "http://localhost:9220/performance?target=server1.example.com&job=redfish-myjob"
```

### `/sensors`
Retrieves sensor-related metrics (e.g. energy, voltage, current, temperature, ...).

```bash
curl "http://localhost:9220/sensors?target=server1.example.com&job=redfish-myjob"
```

**Notes**:
- Replace `server1.example.com` with the hostname or IP address of your Redfish server.
- Replace `redfish-myjob` with the name of your job (used to map credentials).
- The exporter listens on port 9220 by default.

## Prerequisites and Installation

The exporter was written for Python 3.6 or newer. To install all modules needed you have to run the following command:

```bash
pip3 install --no-cache-dir -r requirements.txt
```

Alternatively, you can use the provided Dockerfile to build and run the exporter in a container.

## Running with Docker

To build the container, the following command can be used:

```bash
docker build -t your-path/redfish-exporter:v0.1.0 .
```

This will have the default configuration stored in config.yml. It is recommended that if you need to change the configuration, you make a copy of the file and mount it to the container when it is executed. Once this is done, run the exporter in a Docker container using the following command:

```bash
docker run -d -p 9220:9220  -v ${PWD}/myconfig.yml:/redfish_exporter/config.yml  your-path/redfish-exporter:v0.1.0
```

## Parameters

`-l <logfile>` - all output is written to a logfile.

`-d` - switches on debugging mode

`-c <config file>` - you can specify the path to the config file, default is config.yml.

## The config.yml file

* The **listen_port** is providing the port on which the exporter is waiting to receive calls. It is overwritten by the environment variable **LISTEN_PORT**.

* The credentials for login to the switches can either be added to the config.yaml file or passed via environment variables. The environment variables are taking precedence over the entries in config.yaml file.

    The mapping of job names to environment variables follows a schema: `REDFISH_JOB1_USERNAME` and `REDFISH_JOB1_PASSWORD` would be the variables for example of the first job called `redfish/job1`.
    A slash gets replaced by underscore and everything gets converted to uppercase.

* The **timeout** parameter specifies the amount of time to wait for an answer from the server. Again this can alos be provided via TIMEOUT environment variable.

* The **job** parameter specifies the Prometheus job that will be passed as label if no job was handed over during the API call.

### Example of a config file

```yaml
listen_port: 9200
username: <your username>
password: <your password>
timeout: 40
job: 'redfish-myjob'
```

## Exported Metrics

All metrics returned by the redfish exporter are gauges, except energy measurements from sensors.

### redfish_up

Indicating if the redfish API was giving useful data back (== 1) or not (== 0).

### redfish_health

Show the health information of the hardware parts like processor, memory, storage controllers, disks, fans, power and chassis if available.

### redfish_memory_correctable

### redfish_memory_uncorrectable

Showing the count of errors per dimm.

Cisco servers do not seem to provide this kind of information via redfish. Dell PowerEdge servers only with certain DIMM manufacturers (Samsung not, Micron Technology and Hynix Semiconductor do).

### redfish_powerstate

Showing the powerstate of the server

### redfish_response_duration_seconds

The duration of the first response of the server to a call to /redfish/v1

### redfish_up

Metric indicating if there was a valid redfish response while calling /redfish/v1

### redfish_scrape_duration_seconds

Total duration of scarping all data from the server

### redfish_firmware

A collection of firmware version data stored in the labels. The value is always 1.
