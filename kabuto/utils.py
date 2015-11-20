from contextlib import contextmanager
from flask import Flask, current_app
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_ldap3_login import LDAP3LoginManager
from flask_login import LoginManager
from raven.contrib.flask import Sentry
import uuid
import flask_restful as restful
import pika
import os
import json
import tempfile
import logging

OVERRIDES = ('SECRET_KEY',
             'SQLALCHEMY_DATABASE_URI',
             'SENTRY_DSN',
             'KABUTO_WORKING_DIR')

logger = logging.getLogger("kabuto")
logger.level = logging.DEBUG


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
        base = current_app.config["KABUTO_WORKING_DIR"]
        folder_name = '%s%s' % (prefix, uuid.uuid4())
        path = os.path.join(base, folder_name)
        os.mkdir(path)
        return path
    return tempfile.mkdtemp(prefix=prefix)
