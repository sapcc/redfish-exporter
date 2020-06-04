#!/bin/bash

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3
apt-get install -y python3-pip

pip3 install --no-cache-dir -r requirements.txt

PYTHONPATH=. python3 main.py "$@"

