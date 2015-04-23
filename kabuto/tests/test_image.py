from kabuto.tests import sample_dockerfile
import json


def test_create_image(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    image_id = json.loads(rv.data.decode('utf-8'))['id']
    assert image_id is not None


def test_get_details(client):
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
