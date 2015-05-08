import json
from unittest.mock import patch


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
