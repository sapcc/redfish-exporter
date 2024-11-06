"""
This module contains the handler classes for the Falcon web server.
"""

import logging
import socket
import re
import os
import traceback
import falcon

from prometheus_client.exposition import CONTENT_TYPE_LATEST
from prometheus_client.exposition import generate_latest

from collector import RedfishMetricsCollector

# pylint: disable=no-member

class WelcomePage:
    """
    Create the Welcome page for the API.
    """

    def on_get(self, resp):
        """
        Define the GET method for the API.
        """

        resp.status = falcon.HTTP_200
        resp.content_type = 'text/html'
        resp.text = """
        <h1>Redfish Exporter</h1>
        <h2>Prometheus Exporter for redfish API based servers monitoring</h2>
        <ul>
            <li>Use <a href="/redfish">/redfish</a> to retrieve health metrics.</li>
            <li>Use <a href="/firmware">/firmware</a> to retrieve firmware version metrics.</li>
        </ul>
        """

class MetricsHandler:
    """
    Metrics Handler for the Falcon API.
    """

    def __init__(self, config, metrics_type):
        self._config = config
        self.metrics_type = metrics_type

    def on_get(self, req, resp):
        """
        Define the GET method for the API.
        """
        target = req.get_param("target")
        if not target:
            logging.error("No target parameter provided!")
            raise falcon.HTTPMissingParam("target")

        job = req.get_param("job")
        if not job:
            logging.error("Target %s: No job provided!", target)
            raise falcon.HTTPMissingParam("job")

        logging.debug("Received Target %s with Job %s", target, job)

        ip_re = re.compile(
            r"^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}"
            r"([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$"
        )

        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)

        host = None
        if ip_re.match(target):
            logging.debug("Target %s: Target is an IP Address.", target)
            try:
                host = socket.gethostbyaddr(target)[0]
            except socket.herror as err:
                msg = f"Target {target}: Reverse DNS lookup failed: {err}"
                logging.error(msg)
                raise falcon.HTTPInvalidParam(msg, "target")
        else:
            logging.debug("Target %s: Target is a hostname.", target)
            host = target
            try:
                target = socket.gethostbyname(host)
            except socket.gaierror as err:
                msg = f"Target {target}: DNS lookup failed: {err}"
                logging.error(msg)
                raise falcon.HTTPInvalidParam(msg, "target")

        usr_env_var = job.replace("-", "_").upper() + "_USERNAME"
        pwd_env_var = job.replace("-", "_").upper() + "_PASSWORD"
        usr = os.getenv(usr_env_var, self._config.get("username"))
        pwd = os.getenv(pwd_env_var, self._config.get("password"))

        if not usr or not pwd:
            msg = (
                f"Target {target}: "
                "Unknown job provided or "
                f"no user/password found in environment and config file: {job}"
            )
            logging.error(msg)
            raise falcon.HTTPInvalidParam(msg, "job")

        logging.debug("Target %s: Using user %s", target, usr)

        with RedfishMetricsCollector(
            self._config,
            target = target,
            host = host,
            usr = usr,
            pwd = pwd,
            metrics_type = self.metrics_type
        ) as registry:

            # open a session with the remote board
            registry.get_session()

            try:
                # collect the actual metrics
                resp.text = generate_latest(registry)
                resp.status = falcon.HTTP_200

            except Exception as err:
                message = f"Exception: {traceback.format_exc()}"
                logging.error("Target %s: %s", target, message)
                raise falcon.HTTPBadRequest(description=message)
