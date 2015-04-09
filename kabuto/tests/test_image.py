from kabuto.tests import sample_dockerfile
import json


def test_create_image(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    image_id = json.loads(rv.data)['id']
    assert image_id is not None
