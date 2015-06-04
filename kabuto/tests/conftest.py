import pytest
from kabuto.api import app, db, User
from kabuto.tasks import celery
from kabuto.tests import sample_dockerfile
from sqlalchemy.orm.exc import NoResultFound
import json
import os
from unittest.mock import patch
import time

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


def mock_async_result(build_id):
    class MockResult(object):
        @property
        def id(self):
            return "some_id"

        @property
        def state(self):
            return "SUCCESS"

        def get(self):
            return "hellozeworld", sample_dockerfile, "", ""
    return MockResult()


def mock_broken_async_result(build_id):
    class MockResult(object):
        @property
        def id(self):
            return "some_id"

        @property
        def state(self):
            return "SUCCESS"

        def get(self):
            return ("hellozeworld",
                    sample_dockerfile,
                    "Build failed",
                    ["some output saying your build is unsuccessful"])
    return MockResult()


@pytest.fixture
def client():
    app.config.from_object('config.TestingConfig')
    celery.conf.update({"CELERY_ALWAYS_EAGER": True,
                        "CELERY_EAGER_PROPAGATES_EXCEPTIONS": True,
                        "BROKER_BACKEND": 'memory'})
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


@patch('docker.Client', MockClient)
@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def preload(client, data):
    rv = client.post('/image',
                     data={'dockerfile': sample_dockerfile,
                           'name': 'hellozeworld'})
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']

    image_id = poll_for_image_id(client, build_id)['id']

    rv = client.post('/pipeline',
                     data={'name': 'my first pipeline'})
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']

    data['image_id'] = str(image_id)
    rv = client.post('/pipeline/%s/job' % pipeline_id,
                     data=data)
    job_id = json.loads(rv.data.decode('utf-8'))['id']
    assert job_id is not None
    return image_id, pipeline_id, job_id


def poll_for_image_id(client, build_id):
    def wait_for_image():
        rv = client.get('image/build/%s' % build_id)
        build_data = json.loads(rv.data.decode('utf-8'))
        return build_data

    build_data = wait_for_image()
    state = build_data['state']
    while state == 'PENDING':
        time.sleep(1)
        build_data = wait_for_image()
        state = build_data['state']

    return build_data
