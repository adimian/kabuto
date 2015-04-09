from kabuto.api import app
import pytest
import json


@pytest.fixture
def client():
    app.config['SECRET_KEY'] = 'haha'
    client = app.test_client()
    return client


@pytest.fixture
def authenticated_client(client):
    client.post('/login', data={'username': 'me',
                                'password': 'Secret'})
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


def test_create_image(authenticated_client):
    dockerfile = '''FROM busybox
    CMD ["echo", "hello world"]
    '''
    rv = authenticated_client.post('/image', data={'dockerfile': dockerfile,
                                                   'name': 'hellozeworld'})
    assert rv.status_code == 200
    image_id = json.loads(rv.data)['id']
    assert image_id is not None
