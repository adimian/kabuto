from kabuto.tests import sample_dockerfile
from kabuto.tests.conftest import preload
from kabuto.api import Job, Image, Pipeline, db
import json
import os
import zipfile
from io import BytesIO
from unittest.mock import patch


ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def test_create_job(authenticated_client):
    with patch('docker.Client'):
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

    rv = authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                                   data={'image_id': 999,
                                         'command': 'echo hello world'})
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)
    assert data['error'] == "Image not found"

    rv = authenticated_client.post('/pipeline/%s/job' % 999,
                                   data={'image_id': 999,
                                         'command': 'echo hello world'})
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)
    assert data['error'] == "Pipeline not found"


def test_create_job_with_attachment(authenticated_client):
    with patch('docker.Client'):
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


def test_get_job_details(authenticated_client):
    client = authenticated_client
    data = {'command': 'echo hello world'}
    with patch('docker.Client'):
        rv = client.post('/image',
                         data={'dockerfile': sample_dockerfile,
                               'name': 'hellozeworld'})
        image_id = json.loads(rv.data.decode('utf-8'))['id']

        rv = client.post('/pipeline',
                         data={'name': 'my first pipeline'})
        pipeline_id1 = json.loads(rv.data.decode('utf-8'))['id']
        rv = client.post('/pipeline',
                         data={'name': 'my first pipeline'})
        pipeline_id2 = json.loads(rv.data.decode('utf-8'))['id']

        data['image_id'] = str(image_id)
        client.post('/pipeline/%s/job' % pipeline_id2,
                    data=data)
        rv = client.post('/pipeline/%s/job' % pipeline_id1,
                         data=data)
        client.post('/pipeline/%s/job' % pipeline_id1,
                    data=data)

        jid2 = json.loads(rv.data.decode('utf-8'))['id']

        rv = client.get("/pipeline/%s/job/%s" % (pipeline_id1, jid2))
        keys = list(json.loads(rv.data.decode('utf-8')).keys())
        assert str(jid2) in keys


def test_download_result(authenticated_client):
    pipeline = Pipeline.query.all()[0]
    image = Image.query.all()[0]
    job = Job(pipeline, image, "", "")
    db.session.add(job)
    db.session.commit()
    with open(os.path.join(job.results_path, "results.txt"), "w") as fh:
        fh.write("some results")

    result_url = '/pipeline/%s/job/%s?result' % (job.pipeline_id, job.id)
    rv = authenticated_client.get(result_url)
    assert rv.status_code == 200
    result = json.loads(rv.data.decode('utf-8'))
    assert list(result.keys()) == ["error"]

    job.state = "done"
    db.session.add(job)
    db.session.commit()
    result_url = '/pipeline/%s/job/%s?result' % (job.pipeline_id, job.id)
    rv = authenticated_client.get(result_url)
    assert rv.status_code == 200
    expected_file = "results.txt"
    zp = zipfile.ZipFile(BytesIO(rv.data))
    il = zp.infolist()
    assert len(il) == 1
    for zf in il:
        assert zf.filename in expected_file

    job.results_path = os.path.join(job.results_path, "does_not_exist")
    db.session.add(job)
    db.session.commit()
    rv = authenticated_client.get(result_url)
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get("error", None)

    rv = authenticated_client.get("/pipeline/%s/job/%s?result" % (0, 999))
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)
    assert data['error'] == "Job not found"
