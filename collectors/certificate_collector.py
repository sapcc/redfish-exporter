"""Collects certificate information from the Redfish API."""

import logging
import ssl
import datetime
from cryptography import x509 as crypto_x509
from cryptography.x509.oid import NameOID
from prometheus_client.core import GaugeMetricFamily

class CertificateCollector:
    """Collects certificate information from the Redfish API."""

    def __init__(self, host, target, labels):
        self.host = host
        self.target = target
        self.timeout = 10
        self.labels = labels
        self.port = 443

        self.cert_metrics_isvalid = GaugeMetricFamily(
                name = "redfish_certificate_isvalid",
                documentation = "Redfish Server Monitoring certificate is valid",
                labels = self.labels,
        )

        self.cert_metrics_valid_hostname = GaugeMetricFamily(
                name = "redfish_certificate_valid_hostname",
                documentation = "Redfish Server Monitoring certificate has valid hostname",
                labels = self.labels,
        )

        self.cert_metrics_valid_days = GaugeMetricFamily(
                name = "redfish_certificate_valid_days",
                documentation = "Redfish Server Monitoring certificate valid for days",
                labels = self.labels,
        )

        self.cert_metrics_selfsigned = GaugeMetricFamily(
                name = "redfish_certificate_selfsigned",
                documentation = "Redfish Server Monitoring certificate is self-signed",
                labels = self.labels,
        )

    def collect(self):
        '''Collect Certificate data'''
        logging.info("Target %s: Collecting certificate data ...", self.target)

        cert = None
        cert_obj = None
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
            cert = ssl.get_server_certificate((self.host, self.port))
            cert_obj = crypto_x509.load_pem_x509_certificate(cert.encode('utf-8'))

        except (ssl.SSLError, OSError) as e:
            logging.debug("Target %s: Certificate Validation Error!", self.target)
            logging.debug("Target %s: %s", self.target, e)

        if cert and cert_obj:
            subject_attrs = cert_obj.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
            subject = subject_attrs[0].value if subject_attrs else 'n/a'

            issuer_attrs = cert_obj.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)
            issuer = issuer_attrs[0].value if issuer_attrs else 'n/a'

            cert_expiry_date = cert_obj.not_valid_after_utc.replace(tzinfo=None)

            cert_days_left = (cert_expiry_date - datetime.datetime.now()).days

            current_labels.update(
                {
                    "issuer": issuer,
                    "subject": subject,
                    "not_after": cert_expiry_date.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            if issuer == subject:
                logging.warning(
                    "Target %s: Certificate is self-signed. Issuer: %s, Subject: %s",
                    self.target, issuer, subject
                )
                cert_selfsigned = 1
            else:
                logging.info(
                    "Target %s: Certificate not self-signed. Issuer: %s, Subject: %s",
                    self.target, issuer, subject
                )

            if subject == self.host:
                logging.info("Target %s: Certificate has right hostname.", self.target)
                cert_has_right_hostname = 1
            else:
                logging.warning(
                    "Target %s: Certificate has wrong hostname. Hostname: %s, Subject: %s",
                    self.target, self.host, subject
                )

            if cert_days_left > 0:
                logging.info(
                    "Target %s: Certificate still valid. Days left: %d",
                    self.target, cert_days_left
                )
                if cert_has_right_hostname:
                    cert_valid = 1
            else:
                logging.warning(
                    "Target %s: Certificate not valid. Days left: %d",
                    self.target, cert_days_left
                )

        current_labels.update(self.labels)

        self.cert_metrics_isvalid.add_sample(
            "redfish_certificate_isvalid",
            value = cert_valid,
            labels = current_labels,
        )

        self.cert_metrics_valid_hostname.add_sample(
            "redfish_certificate_valid_hostname",
            value = cert_has_right_hostname,
            labels = current_labels,
        )

        self.cert_metrics_valid_days.add_sample(
            "redfish_certificate_valid_days",
            value = cert_days_left,
            labels = current_labels,
        )

        self.cert_metrics_selfsigned.add_sample(
            "redfish_certificate_selfsigned",
            value = cert_selfsigned,
            labels = current_labels,
        )
