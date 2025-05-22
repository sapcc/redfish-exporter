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

    def on_get(self, req, resp):
        """
        Define the GET method for the API.
        """

        resp.status = falcon.HTTP_200
        resp.content_type = 'text/html'
        resp.text = """
        <h1>Redfish Exporter</h1>
        <h2>Prometheus Exporter for redfish API based servers monitoring</h2>
        <ul>
            <li><strong>Health Metrics:</strong> Use <code>/health</code> to retrieve health-related metrics, such as system status, memory errors, and power state.</li>
            <li><strong>Firmware Metrics:</strong> Use <code>/firmware</code> to retrieve firmware version information for the server components.</li>
            <li><strong>Performance Metrics:</strong> Use <code>/performance</code> to retrieve performance-related metrics like power consumption and temperature data.</li>
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

        resp.set_header("Content-Type", CONTENT_TYPE_LATEST)

        if not self._config["targets"].get(target,{}):
            logging.error("Target parameter provided not found in config: %s", target)
            raise falcon.HTTPMissingParam("target")

        usr_env_var = job.replace("-", "_").upper() + target.replace("-", "_").upper() + "_USERNAME"
        pwd_env_var = job.replace("-", "_").upper() + target.replace("-", "_").upper() + "_PASSWORD"

        target_config = self._config["targets"][target]
        usr = os.getenv(usr_env_var, target_config.get("username"))
        pwd = os.getenv(pwd_env_var, target_config.get("password"))
        port = target_config.get("port")
        host = target_config.get("host")

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
            target_config,
            target = target,
            host = host,
            usr = usr,
            pwd = pwd,
            port = port,
            metrics_type = self.metrics_type
        ) as registry:

            # open a session with the remote board
            registry.get_session()

            try:
                # collect the actual metrics
                resp.text = generate_latest(registry)
                resp.status = falcon.HTTP_200

            except Exception:
                message = f"Exception: {traceback.format_exc()}"
                logging.error("Target %s: %s", target, message)
                raise falcon.HTTPBadRequest(description=message)
