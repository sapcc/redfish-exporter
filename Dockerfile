FROM keppel.eu-de-1.cloud.sap/ccloud-dockerhub-mirror/library/ubuntu:latest

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt update \
    && apt upgrade -y \
    && apt install -y python3.11 \
    && apt install -y python3-pip

ARG FOLDERNAME=redfish_exporter

RUN mkdir /${FOLDERNAME}
RUN mkdir /${FOLDERNAME}/collectors

WORKDIR /${FOLDERNAME}

RUN pip3 install --upgrade pip
COPY requirements.txt /${FOLDERNAME}
RUN pip3 install --no-cache-dir -r requirements.txt

COPY *.py /${FOLDERNAME}/
COPY collectors/ /${FOLDERNAME}/collectors/
COPY config.yml /${FOLDERNAME}/

LABEL source_repository="https://github.com/sapcc/redfish-exporter"