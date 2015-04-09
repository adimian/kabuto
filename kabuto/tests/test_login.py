from kabuto.api import app
import pytest


@pytest.fixture
def client():
    app.config['SECRET_KEY'] = 'haha'
    client = app.test_client()
    return client


def test_login(client):
    # not yet logged in
    rv = client.get('/')
    assert rv.status_code == 401

    # logging in
    rv = client.post('/login', data={'username': 'me',
                                     'password': 'Secret'})
    assert rv.status_code == 200

    # logged in, yay
    rv = client.get('/')
    assert rv.status_code == 200
