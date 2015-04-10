import pytest
from kabuto.api import app
from kabuto.tests import sample_dockerfile
import json


@pytest.fixture
def client():
    app.config['SECRET_KEY'] = 'haha'
    client = app.test_client()
    return client


@pytest.fixture
def authenticated_client(client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})
    return client


@pytest.fixture
def preloaded_client(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    image_id = json.loads(rv.data)['id']

    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    pipeline_id = json.loads(rv.data)['id']

    authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                              data={'image_id': image_id,
                                    'command': 'echo hello world'})
    job_id = json.loads(rv.data)['id']
    assert job_id is not None
    return authenticated_client
