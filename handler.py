import falcon
import logging
import socket
import re

from wsgiref import simple_server
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from prometheus_client.exposition import generate_latest

from collector import RedfishMetricsCollector

class welcomePage:

    def on_get(self, req, resp):
        resp.body = '{"message": "This is the redfish exporter. Use /redfish to retrieve metrics."}'

class metricHandler:
    def __init__(self, config):
        self._config = config

    def on_get(self, req, resp):

        self._target = req.get_param("target")
        if not self._target:
            msg = "No target parameter provided!"
            logging.error(msg)
            raise falcon.HTTPMissingParam('target')

        self._job = req.get_param("job")
        if not self._job:
            self._job = self._config['job']

        logging.debug("Received Target: %s", self._target)

        ip_re = re.compile(r"^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$")

        resp.set_header('Content-Type', CONTENT_TYPE_LATEST)

        self._host = self._target
        if ip_re.match(self._target):
            try:
                self._host = socket.gethostbyaddr(self._target)[0]

            except socket.herror as excptn:
                msg = "Target {0}: Reverse DNS lookup failed: {1}".format(self._target,excptn)
                logging.error(msg)
        else:
            try:
                self._target = socket.gethostbyname(self._host)

            except socket.gaierror as excptn:
                msg = "Target {0}: DNS lookup failed: {1}".format(self._target,excptn)
                logging.error(msg)

        try:
            userprefix = self._config['job2user_mapping'][self._job]

        except KeyError:
            msg = "Target {0}: Unknown job provided: {1}".format(self._target, self._job)
            logging.error(msg)
            raise falcon.HTTPInvalidParam(msg, 'job')

        usr = userprefix + "_USERNAME"
        pwd = userprefix + "_PASSWORD"
        logging.debug("Target {0}: Search for User in Environment Variable {1}".format(self._target, usr))

        registry = RedfishMetricsCollector(
            self._config,
            target = self._target,
            host = self._host,
            usr = usr,
            pwd = pwd
        )

        collected_metric = generate_latest(registry)

        resp.body = collected_metric