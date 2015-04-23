from kabuto.tests import sample_dockerfile
from kabuto.tests.conftest import preload
from kabuto.api import Job
import json
import os


ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def test_create_job(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    image_id = json.loads(rv.data.decode('utf-8'))['id']

    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']

    authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                              data={'image_id': image_id,
                                    'command': 'echo hello world'})
    assert rv.status_code == 200
    json.loads(rv.data.decode('utf-8'))['id']


def test_create_job_with_attachment(authenticated_client):
    rv = authenticated_client.post('/image',
                                   data={'dockerfile': sample_dockerfile,
                                         'name': 'hellozeworld'})
    assert rv.status_code == 200
    image_id = json.loads(rv.data.decode('utf-8'))['id']

    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my not so first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']

    attachments = [(open(os.path.join(ROOT_DIR, "data", "file1.txt"), "rb"),
                    'test1.txt'),
                   (open(os.path.join(ROOT_DIR, "data", "file2.txt"), "rb"),
                    'test2.txt')]
    rv = authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                                   data={'image_id': str(image_id),
                                         'command': 'echo hello world',
                                         'attachments': attachments})
    assert rv.status_code == 200
    job_id = json.loads(rv.data.decode('utf-8'))['id']
    attachments_path = Job.query.filter_by(id=job_id).one().attachments_path
    assert os.path.exists(attachments_path)
    assert len(os.listdir(attachments_path)) == 2


def test_get_details(client):
    client.post('/login', data={'login': 'me',
                                'password': 'Secret'})
    _, _, jid1 = preload(client, {'command': 'echo hello world'})
    client.post('/login', data={'login': 'me1',
                                'password': 'Secret'})
    iid2, pid2, jid2 = preload(client, {'command': 'echo hello world'})

    rv = client.get("/jobs")
    jobs = json.loads(rv.data.decode('utf-8'))
    assert not jobs.get(str(jid1))
    assert jobs.get(str(jid2))
    assert jobs[str(jid2)]["image"]["id"] == iid2
    assert jobs[str(jid2)]["pipeline"]["id"] == pid2

    rv = client.get("/pipeline/%s/job/%s" % (pid2, jid2))
    jobs = json.loads(rv.data.decode('utf-8'))
    assert not jobs.get(str(jid1))
    assert jobs.get(str(jid2))
    assert jobs[str(jid2)]["image"]["id"] == iid2
    assert jobs[str(jid2)]["pipeline"]["id"] == pid2
