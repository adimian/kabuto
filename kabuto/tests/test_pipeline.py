import json


def test_create_pipeline(authenticated_client):
    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data)['id']
    assert pipeline_id is not None

