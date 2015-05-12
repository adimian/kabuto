import json
from kabuto.tests.conftest import preload
from unittest.mock import patch


def test_create_pipeline(authenticated_client):
    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']
    assert pipeline_id is not None


@patch('pika.PlainCredentials')
@patch('pika.ConnectionParameters')
@patch('pika.BlockingConnection')
@patch('pika.BasicProperties')
def test_submit_pipeline(mpc, mcp, mbc, mbp, client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})
    _, pid1, _ = preload(client, {'command': 'echo hello world'})

    rv = client.post('/pipeline/%s/submit' % pid1)
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
