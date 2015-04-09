import pytest
from kabuto.api import app


@pytest.fixture(scope='module')
def client():
    app.config['SECRET_KEY'] = 'haha'
    client = app.test_client()
    return client


@pytest.fixture(scope='module')
def authenticated_client(client):
    client.post('/login', data={'username': 'me',
                                'password': 'Secret'})
    return client
