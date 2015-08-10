from contextlib import contextmanager
from flask import Flask, current_app
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_ldap3_login import LDAP3LoginManager
from flask_login import LoginManager
from raven.contrib.flask import Sentry
import flask_restful as restful
import pika
import os
import tempfile

OVERRIDES = ('SECRET_KEY',
             'SQLALCHEMY_DATABASE_URI',
             'SENTRY_DSN',
             'KABUTO_WORKING_DIR')


def read_config(config, key):
    config[key] = os.environ.get(key, config[key])


def make_app(config=None):
    if not config:
        config = 'config.Config'
    app = Flask(__name__)
    app.config.from_object(config)
    app.config.from_envvar('KABUTO_CONFIG', silent=True)
    for key in OVERRIDES:
        read_config(app.config, key)

    api = restful.Api(app)
    login_manager = LoginManager(app)
    ldap_manager = None
    if app.config['LDAP_HOST']:
        ldap_manager = LDAP3LoginManager(app)
    db = SQLAlchemy(app)
    bcrypt = Bcrypt(app)
    if app.config['SENTRY_DSN']:
        Sentry(app)
    else:
        print("sentry not enabled !")
    return app, api, login_manager, ldap_manager, db, bcrypt


def get_working_dir(prefix=''):
    if current_app.config.get("KABUTO_WORKING_DIR", None):
        return current_app.config["KABUTO_WORKING_DIR"]
    return tempfile.mkdtemp(prefix=prefix)


@contextmanager
def open_channel(config):
    login = config['AMQP_USER']
    password = config['AMQP_PASSWORD']
    if login and password:
        credentials = pika.PlainCredentials(login, password)
    else:
        credentials = None

    host = config['AMQP_HOSTNAME']
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host=host,
            credentials=credentials,
        ))
    channel = connection.channel()
    yield channel
    connection.close()


def put_in_message_queue(queue, message, config):
    with open_channel(config) as channel:
        channel.queue_declare(queue=queue, durable=True)
        properties = pika.BasicProperties(delivery_mode=2,)
        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=message,
                              properties=properties)


def publish_job(message, config):
    put_in_message_queue('jobs', message, config)
