import json
import time
from kabuto.tests.conftest import preload


def test_create_pipeline(authenticated_client):
    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']
    assert pipeline_id is not None


def test_submit_pipeline(preloaded_client):
    rv = preloaded_client.get('/pipeline')
    assert rv.status_code == 200
    pipelines = json.loads(rv.data.decode('utf-8'))

    first_pipeline = list(pipelines)[0]

    rv = preloaded_client.post('/pipeline/%s/submit' % first_pipeline)
    assert rv.status_code == 200

    submit_id = list(json.loads(rv.data.decode('utf-8')))[0]
    assert submit_id is not None


def test_get_details(client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})
    _, pid1, _ = preload(client, {'command': 'echo hello world'})
    client.post('/login', data={'login': 'me1',
                                'password': 'Secret'})
    _, pid2, jid2 = preload(client, {'command': 'echo hello world'})

    rv = client.get("/pipeline")
    pipe = json.loads(rv.data.decode('utf-8'))
    assert not pipe.get(str(pid1))
    assert pipe.get(str(pid2))
    assert pipe[str(pid2)]["jobs"] == [{"id": jid2}]

    rv = client.get("/pipeline/%s" % pid2)
    pipe = json.loads(rv.data.decode('utf-8'))
    assert not pipe.get(str(pid1))
    assert pipe.get(str(pid2))
    assert pipe[str(pid2)]["jobs"] == [{"id": jid2}]
