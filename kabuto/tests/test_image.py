from kabuto.tests import sample_dockerfile
import json
from unittest.mock import patch
from kabuto.api import Image
from kabuto.tests.conftest import (MockClient, ROOT_DIR, poll_for_image_id,
                                   mock_async_result, mock_broken_async_result)
import os
import hgapi
import shutil

update_file = '''FROM phusion/baseimage:0.9.16
CMD ["echo", "hello world"]
'''


def rm_hg(url):
    hg_path = os.path.join(url, ".hg")
    if os.path.exists(hg_path):
        shutil.rmtree(hg_path)


@patch('docker.Client', MockClient)
@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_create_image(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']
    assert image_id is not None

    with patch('tasks.build_and_push.AsyncResult',
               mock_broken_async_result):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
        assert rv.status_code == 200
        build_id = json.loads(rv.data.decode('utf-8'))['build_id']
        data = poll_for_image_id(authenticated_client, build_id)
        assert data.get("error")
        assert data["output"] == ["some output saying your "
                                  "build is unsuccessful"]

    url = os.path.join(ROOT_DIR, "data", "repo")
    rm_hg(url)
    repo = hgapi.hgapi.Repo(url)
    repo.hg_init()
    repo.hg_add()
    repo.hg_commit("init", user='me')
    data = {"repo_url": url, "name": "some_image"}
    rv = authenticated_client.post('/image', data=data)
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']
    assert image_id is not None
    rm_hg(url)


@patch('docker.Client', MockClient)
@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_update_image(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': update_file,
                                         'name': 'some_name'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']

    new_name = 'hellozeworld'
    rv = authenticated_client.put('/image/%s' % image_id,
                                  data={'dockerfile': sample_dockerfile,
                                        'name': new_name})
    img = Image.query.filter_by(id=image_id).first()
    assert img.name == new_name
    assert img.dockerfile == sample_dockerfile

    rv = authenticated_client.put('/image/999',
                                  data={'dockerfile': sample_dockerfile,
                                        'name': new_name})
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)


@patch('docker.Client', MockClient)
@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_delete_image(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']

    authenticated_client.delete('/image/%s' % image_id)
    assert not Image.query.filter_by(id=image_id).first()

    rv = authenticated_client.delete('/image/999')
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)


@patch('docker.Client', MockClient)
@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_get_details(client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})

    def create_image(name, client):
        rv = client.post('/image',
                         data={'dockerfile': sample_dockerfile,
                               'name': name})
        build_id = json.loads(rv.data.decode('utf-8'))['build_id']
        build_data = poll_for_image_id(client, build_id)
        image_id = build_data['id']
        return str(image_id), name

    id1, _ = create_image("image1", client)
    client.post('/login', data={'login': 'me1',
                                'password': 'Secret'})
    id2, name2 = create_image("image2", client)

    rv = client.get("/image")
    images = json.loads(rv.data.decode('utf-8'))

    assert not images.get(id1)
    assert images.get(id2)
    assert sorted(images[id2].keys()) == sorted(["id", "name", "creation_date",
                                                 "dockerfile"])

    rv = client.get("/image/%s" % id2)
    images = json.loads(rv.data.decode('utf-8'))

    assert not images.get(id1)
    assert images.get(id2)
    assert sorted(images[id2].keys()) == sorted(["id", "name", "creation_date",
                                                 "dockerfile"])
