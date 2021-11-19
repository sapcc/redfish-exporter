from handler import metricsHandler
from handler import welcomePage
import argparse
import yaml
import logging
import sys
import falcon
from wsgiref.simple_server import make_server, WSGIServer, WSGIRequestHandler
import socket
import os
import warnings
from socketserver import ThreadingMixIn

class _SilentHandler(WSGIRequestHandler):
    """WSGI handler that does not log requests."""

    def log_message(self, format, *args):
        """Log nothing."""

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Thread per request HTTP server."""
    # Make worker threads "fire and forget". Beginning with Python 3.7 this
    # prevents a memory leak because ``ThreadingMixIn`` starts to gather all
    # non-daemon threads in a list in order to join on them at server close.
    daemon_threads = True

def falcon_app():
    port = int(os.getenv('LISTEN_PORT', config['listen_port']))
    addr = '0.0.0.0'
    logging.info("Starting Redfish Prometheus Server on Port %s", port)
    ip = socket.gethostbyname(socket.gethostname())
    logging.info("Listening on IP %s", ip)
    api = falcon.API()
    api.add_route('/redfish', metricsHandler(config, health = True))
    api.add_route('/firmware', metricsHandler(config, firmware = True))
    api.add_route('/', welcomePage())

    try:
        httpd = make_server(addr, port, api, ThreadingWSGIServer)
    except Exception as excptn:
        logging.error("Couldn't start Server: %s", excptn)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("Stopping Redfish Prometheus Server")

def enable_logging():
    # enable logging
    logger = logging.getLogger()
    if args.debug:
        logger.setLevel('DEBUG')
    else:
        logger.setLevel('INFO')
    format = '%(asctime)-15s %(process)d %(levelname)s %(filename)s:%(lineno)d %(message)s'
    if args.logging:
        logging.basicConfig(filename=args.logging, format=format)
    else:
        logging.basicConfig(stream=sys.stdout, format=format)

if __name__ == '__main__':
    # command line options
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c", "--config", help="Specify config yaml file", metavar="FILE", required=False, default="config.yml")
    parser.add_argument(
        "-l", "--logging", help="Log all messages to a file", metavar="FILE", required=False)
    parser.add_argument(
        "-d", "--debug", help="Debugging mode", action="store_true", required=False)
    args = parser.parse_args()

    warnings.filterwarnings("ignore")

    enable_logging()

    # get the config
    try:
        with open(args.config, 'r') as config_file:
            config =  yaml.load(config_file.read(), Loader=yaml.FullLoader)
    except FileNotFoundError as e:
        print("Config File not found: {0}".format(e))
        exit(1)

    falcon_app()
