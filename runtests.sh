#!/bin/bash
export PYTHONPATH=kabuto
virtualenv -p python3 .ve
source .ve/bin/activate
pip install -r requirements.txt
sudo service rabbitmq-server start
sudo rabbitmqctl add_user kabuto kabuto
sudo rabbitmqctl add_vhost celery
sudo rabbitmqctl set_permissions -p celery kabuto ".*" ".*" ".*"
find . -name "*.pyc" -delete && py.test $@
