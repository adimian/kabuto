import pytest
from kabuto.api import app, db, User
from kabuto.tests import sample_dockerfile
from sqlalchemy.orm.exc import NoResultFound
import json
import os
from unittest.mock import patch

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


class MockClient(object):
    def __init__(self, *args, **kwargs):
        pass

    def build(self, *args, **kwargs):
        return ["Successfully built"]

    def push(self, *args, **kwargs):
        pass

    def remove_image(self, *args, **kwargs):
        pass


class BrokenBuildMockClient(object):
    def __init__(self, *args, **kwargs):
        pass

    def build(self, *args, **kwargs):
        return ["some output saying your build is unsuccessful"]


@pytest.fixture
def client():
    app.config.from_object('kabuto.config.TestingConfig')
    db.create_all()
    try:
        User.query.filter_by(login='me').one()
    except NoResultFound:
        db.session.add(User('me', 'Secret', 'test@test.com'))
        db.session.add(User('me1', 'Secret', 'test1@test.com'))
        db.session.commit()
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
            'attachments': [(open(os.path.join(ROOT_DIR, "data",
                                               "file1.txt"), "rb"),
                             'test1.txt'),
                            (open(os.path.join(ROOT_DIR, "data",
                                               "file2.txt"), "rb"),
                             'test2.txt')]}
    preload(authenticated_client, data)
    return authenticated_client


def preload(client, data):
    with patch('docker.Client', MockClient):
        rv = client.post('/image',
                         data={'dockerfile': sample_dockerfile,
                               'name': 'hellozeworld'})
        image_id = json.loads(rv.data.decode('utf-8'))['id']

        rv = client.post('/pipeline',
                         data={'name': 'my first pipeline'})
        pipeline_id = json.loads(rv.data.decode('utf-8'))['id']

        data['image_id'] = str(image_id)
        rv = client.post('/pipeline/%s/job' % pipeline_id,
                         data=data)
        job_id = json.loads(rv.data.decode('utf-8'))['id']
        assert job_id is not None
        return image_id, pipeline_id, job_id
