FROM docker.io/ubuntu:20.04

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y python3 \
    && apt-get install -y python3-pip

ARG FOLDERNAME=redfish_exporter

RUN mkdir /${FOLDERNAME}

WORKDIR /${FOLDERNAME}

COPY requirements.txt /${FOLDERNAME}
RUN pip3 install --no-cache-dir -r requirements.txt

COPY *.py /${FOLDERNAME}/
COPY config.yml /${FOLDERNAME}/

ENTRYPOINT [ "python3", "-u", "./main.py"]

LABEL source_repository="https://github.com/sapcc/redfish-exporter"