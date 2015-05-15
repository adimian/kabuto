import json
from unittest.mock import patch
from flask_ldap3_login import AuthenticationResponse, AuthenticationResponseStatus as ars


def test_login(client):
    # not yet logged in
    rv = client.get('/')
    assert rv.status_code == 401

    # logging in
    rv = client.post('/login', data={'login': 'me',
                                     'password': 'Secret'})
    assert rv.status_code == 200

    # logged in, yay
    rv = client.get('/')
    assert rv.status_code == 200


def test_empty_login(client):
    # not yet logged in
    rv = client.get('/')
    assert rv.status_code == 401

    # logging in
    rv = client.post('/login', data={})
    assert rv.status_code == 400


def test_wrong_login(client):
    rv = client.post('/login', data={'login': 'nonexistant',
                                     'password': 'Secret'})
    assert rv.status_code == 401

    rv = client.post('/login', data={'login': 'me',
                                     'password': 'Wrong'})
    assert rv.status_code == 401


def test_register(client):
    with patch('smtplib.SMTP'):
        rv = client.post('/register', data={'login': 'new_user',
                                            'password': 'some_pw',
                                            'email': 'new_user@test.com'})
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('status', None) == 'success'

        token = data['token']

        rv = client.get('/register/confirm/new_user/%s' % token)
        data = json.loads(rv.data.decode('utf-8'))
        assert data['registration'] == "success"

        rv = client.get('/register/confirm/new_user/%s' % "invalid_token")
        data = json.loads(rv.data.decode('utf-8'))
        assert data['registration'] == "user or token not found"


# This test has to be solved way better but requires a refactoring session
# of the api to be able to get apps initialized in different ways
class MockLdapManager(object):

    def authenticate(self, login, pw):
        if login == "me" and pw == "Secret":
            return AuthenticationResponse(status=ars.success)
        return AuthenticationResponse(status=ars.fail)

from flask import Flask
from flask_bcrypt import Bcrypt
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
import flask_restful as restful
from kabuto.api import Login
ldap_app = Flask(__name__)
ldap_app.config.from_object('kabuto.config.TestingConfig')
ldap_app.config.update(LDAP_HOST='some_host',
                       LDAP_BASE_DN='',
                       LDAP_USER_DN='ou=people',
                       LDAP_GROUP_DN='ou=groups',
                       LDAP_USER_RDN_ATTR='uid',
                       LDAP_USER_LOGIN_ATTR='uid',
                       LDAP_BIND_USER_DN='',
                       LDAP_BIND_USER_PASSWORD='')
ldap_api = restful.Api(ldap_app)
ldap_api.add_resource(Login, '/login')
ldap_login_manager = LoginManager(ldap_app)
ldap_ldap_manager = MockLdapManager()
ldap_db = SQLAlchemy(ldap_app)
ldap_bcrypt = Bcrypt(ldap_app)


@patch('kabuto.api.api', ldap_api)
@patch('kabuto.api.login_manager', ldap_login_manager)
@patch('kabuto.api.ldap_manager', ldap_ldap_manager)
@patch('kabuto.api.db', ldap_db)
@patch('kabuto.api.bcrypt', ldap_bcrypt)
def test_ldap_login():
    ldap_client = ldap_app.test_client()
    rv = ldap_client.post('/login', data={'login': 'me',
                                          'password': 'Secret'})
    assert rv.status_code == 200

    rv = ldap_client.post('/login', data={'login': 'nonexistant',
                                          'password': 'Secret'})
    assert rv.status_code == 401
