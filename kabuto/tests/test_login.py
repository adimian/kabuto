from kabuto.api import app
import pytest


@pytest.fixture
def client():
    app.config['SECRET_KEY'] = 'haha'
    client = app.test_client()
    return client

def test_login(client):
    rv = client.post('/login', data={'username': 'me',
                                     'password': 'Secret'})
    print rv.data
