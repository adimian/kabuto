import json


def test_create_pipeline(authenticated_client):
    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data)['id']
    assert pipeline_id is not None


def test_submit_pipeline(preloaded_client):
    rv = preloaded_client.get('/pipeline')
    assert rv.status_code == 200
    pipelines = json.loads(rv.data)

    first_pipeline = pipelines.keys()[0]

    rv = preloaded_client.post('/pipeline/%s/submit' % first_pipeline)
    assert rv.status_code == 200

    submit_id = json.loads(rv.data).keys()[0]
    assert submit_id is not None
