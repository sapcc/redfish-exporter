from prometheus_client.core import GaugeMetricFamily

import logging
import ssl
import socket
import datetime

class CertificateCollector(object):

    def __init__(self, host, target, labels):
        self.host = host
        self.target = target
        self.timeout = 10

        self.labels = labels
        self.cert_metrics_valid = GaugeMetricFamily(
            f"redfish_certificate_valid",
            "Redfish Server Monitoring certificate is valid",
            labels = self.labels,
        )
        self.cert_metrics_valid_hostname = GaugeMetricFamily(
            f"redfish_certificate_valid_hostname",
            "Redfish Server Monitoring certificate has valid hostname",
            labels = self.labels,
        )
        self.cert_metrics_valid_days = GaugeMetricFamily(
            f"redfish_certificate_valid_days",
            "Redfish Server Monitoring certificate valid for days",
            labels = self.labels,
        )
        self.cert_metrics_selfsigned = GaugeMetricFamily(
            f"redfish_certificate_selfsigned",
            "Redfish Server Monitoring certificate is self-signed",
            labels = self.labels,
        )


    def collect(self):
        port = 443
        context = ssl.create_default_context()
        context.check_hostname = False
        # context.verify_mode = ssl.CERT_NONE
        cert_days_left = 0
        cert_valid = 0
        cert_has_right_hostname = 0
        cert_selfsigned = 0
        current_labels = {
            "issuer": "n/a",
            "subject": "n/a",
            "not_after": "n/a",
        }

        try:
            sock = socket.socket(socket.AF_INET)
            sock.settimeout(self.timeout)
            conn = context.wrap_socket(sock, server_hostname=self.host)
            conn.connect((self.host, port))
            cert = conn.getpeercert()
            cert_expiry_date = datetime.datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z') if 'notAfter' in cert else datetime.datetime.now()
            cert_days_left = (cert_expiry_date - datetime.datetime.now()).days
            issuer = dict(x[0] for x in cert['issuer'])
            subject = dict(x[0] for x in cert['subject'])
            current_labels.update(
                {
                    "issuer": issuer['commonName'],
                    "subject": subject['commonName'],
                    "not_after": cert_expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
            if issuer['commonName'] == subject['commonName'] or subject['commonName'] == "www.example.org":
                cert_selfsigned = 1

            if subject['commonName'] == self.host:
                cert_has_right_hostname = 1

            if cert_days_left > 0 and cert_has_right_hostname:
                cert_valid = 1


        except ssl.SSLCertVerificationError as e:
            if e.verify_message == 'self-signed certificate':
                cert_selfsigned = 1
                current_labels.update({"issuer": "self-signed"})
            else:
                logging.debug(f"Target {self.target}: Certificate Validation Error: {e}")
                logging.debug(f"Target {self.target}: Verify Message: {e.verify_message}")
                return
        except TimeoutError:
            logging.debug(f"Target {self.target}: Timeout occured!")
            return
        
        finally:
            conn.close()
            sock.close()

        current_labels.update(self.labels)

        self.cert_metrics_valid.add_sample(
            f"redfish_certificate_valid",
            value = cert_valid,
            labels = current_labels,
        )

        self.cert_metrics_valid_hostname.add_sample(
            f"redfish_certificate_valid_hostname",
            value = cert_has_right_hostname,
            labels = current_labels,
        )

        self.cert_metrics_valid_days.add_sample(
            f"redfish_certificate_valid_days",
            value = cert_days_left,
            labels = current_labels,
        )

        self.cert_metrics_selfsigned.add_sample(
            f"redfish_certificate_selfsigned",
            value = cert_selfsigned,
            labels = current_labels,
        )
     
