from kabuto.tests import sample_dockerfile
import json
from unittest.mock import patch
from kabuto.api import Image
from kabuto.tests.conftest import MockClient, BrokenBuildMockClient

update_file = '''FROM phusion/baseimage:0.9.16
CMD ["echo", "hello world"]
'''


def test_create_image(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
        assert rv.status_code == 200
        image_id = json.loads(rv.data.decode('utf-8'))['id']
        assert image_id is not None

    with patch('docker.Client', BrokenBuildMockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
        assert rv.status_code == 200
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get("error")
        assert data["output"] == ["some output saying your "
                                  "build is unsuccessful"]


def test_update_image(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
        assert rv.status_code == 200
        image_id = json.loads(rv.data.decode('utf-8'))['id']

        new_name = 'some_new_name'
        rv = authenticated_client.put('/image/%s' % image_id,
                                      data={'dockerfile': update_file,
                                            'name': new_name})
        img = Image.query.filter_by(id=image_id).first()
        assert img.name == new_name
        assert img.dockerfile == update_file

        rv = authenticated_client.put('/image/999',
                                      data={'dockerfile': update_file,
                                            'name': new_name})
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('error', None)


def test_delete_image(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
        assert rv.status_code == 200
        image_id = json.loads(rv.data.decode('utf-8'))['id']

        authenticated_client.delete('/image/%s' % image_id)
        assert not Image.query.filter_by(id=image_id).first()

        rv = authenticated_client.delete('/image/999')
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('error', None)


def test_get_details(client):
    with patch('docker.Client', MockClient):
        client.post('/login', data={'login': 'me',
                                    'password': 'Secret'})

        def create_image(name, client):
            rv = client.post('/image',
                             data={'dockerfile': sample_dockerfile,
                                   'name': name})
            return str(json.loads(rv.data.decode('utf-8'))['id']), name

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
        assert images[id2]['name'] == name2

        rv = client.get("/image/%s" % id2)
        images = json.loads(rv.data.decode('utf-8'))

        assert not images.get(id1)
        assert images.get(id2)
        assert sorted(images[id2].keys()) == sorted(["id", "name", "creation_date",
                                                     "dockerfile"])
        assert images[id2]['name'] == name2
