#!/bin/bash
export PYTHONPATH=kabuto
virtualenv -p python3 .ve
source .ve/bin/activate
pip install -r requirements.txt
service rabbitmq-server start
rabbitmqctl add_user kabuto kabuto
rabbitmqctl add_vhost celery
rabbitmqctl set_permissions -p celery kabuto ".*" ".*" ".*"
find . -name "*.pyc" -delete && py.test $@
