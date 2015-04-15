import pytest
from kabuto.api import app, db
from kabuto.tests import sample_dockerfile
import json
import os


ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))

@pytest.fixture
def client():
    app.config.from_object('kabuto.config.TestingConfig')
    db.create_all()
    client = app.test_client()
    return client


@pytest.fixture
def authenticated_client(client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})
    return client


@pytest.fixture
def preloaded_client(authenticated_client):
    data = {'command': 'echo hello world'}
    preload(authenticated_client, data)
    return authenticated_client


@pytest.fixture
def preloaded_client_with_attachments(authenticated_client):
    data = {'command': 'cat /inbox/file1.txt > /outbox/output1.txt',
            'attachments': [(open(os.path.join(ROOT_DIR, "data", "file1.txt"), "rb"), 'test1.txt'),
                            (open(os.path.join(ROOT_DIR, "data", "file2.txt"), "rb"), 'test2.txt')]}
    preload(authenticated_client, data)
    return authenticated_client


def preload(client, data):
    rv = client.post('/image',
                     data={'dockerfile': sample_dockerfile,
                           'name': 'hellozeworld'})
    image_id = json.loads(rv.data)['id']

    rv = client.post('/pipeline',
                     data={'name': 'my first pipeline'})
    pipeline_id = json.loads(rv.data)['id']

    data['image_id'] = image_id
    rv = client.post('/pipeline/%s/job' % pipeline_id,
                              data=data)
    job_id = json.loads(rv.data)['id']
    assert job_id is not None
