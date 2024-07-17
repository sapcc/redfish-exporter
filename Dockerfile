FROM keppel.eu-de-1.cloud.sap/ccloud-dockerhub-mirror/library/ubuntu:latest

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get upgrade -y \
    && apt-get install -y python3 \
    && apt-get install -y python3-pip \
    && apt-get install -y curl \
    && apt-get autoremove -y \
    && apt-get clean -y \
    && rm -rf /var/lib/apt/lists/*

ARG FOLDERNAME=redfish_exporter

RUN mkdir /${FOLDERNAME}
RUN mkdir /${FOLDERNAME}/collectors

WORKDIR /${FOLDERNAME}

RUN pip3 install --break-system-packages --upgrade pip --ignore-install
COPY requirements.txt /${FOLDERNAME}
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt

COPY *.py /${FOLDERNAME}/
COPY collectors/ /${FOLDERNAME}/collectors/
COPY config.yml /${FOLDERNAME}/

RUN curl -ks 'https://aia.pki.co.sap.com/aia/SAPNetCA_G2.crt' -o '/usr/lib/ssl/certs/SAPNetCA_G2.crt'
RUN curl -ks 'https://cacerts.digicert.com/DigiCertGlobalRootG2.crt.pem' -o '/usr/lib/ssl/certs/DigiCertGlobalRootCA.crt'
RUN /usr/sbin/update-ca-certificates

LABEL source_repository="https://github.com/sapcc/redfish-exporter"
LABEL maintainer="Bernd Kuespert <bernd.kuespert@sap.com>"
