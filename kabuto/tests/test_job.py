from kabuto.tests import sample_dockerfile
from kabuto.tests.conftest import preload
from kabuto.api import Job, Image, Pipeline, db, app, SENDER
import json
import os
import zipfile
from io import BytesIO
from unittest.mock import patch
from kabuto.tests.conftest import MockClient, mock_async_result, poll_for_image_id


ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def broadcast(*args, **kwargs):
    pass

SENDER.broadcast = broadcast


@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_create_job(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']

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


@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_attach_files_post_create_job(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']

    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']

    authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                              data={'image_id': image_id,
                                    'command': 'echo hello world'})
    assert rv.status_code == 200
    job_id = json.loads(rv.data.decode('utf-8'))['id']

    attachments_path = Job.query.filter_by(id=job_id).one().attachments_path
    assert len(os.listdir(attachments_path)) == 0
    attachments = [(open(os.path.join(ROOT_DIR, "data", "file1.txt"), "rb"),
                    'test1.txt'),
                   (open(os.path.join(ROOT_DIR, "data", "file2.txt"), "rb"),
                    'test2.txt')]
    authenticated_client.put('/pipeline/%s/job/%s' % (pipeline_id, job_id),
                             data={'command': 'echo hello world2',
                                   'attachments': attachments})
    assert len(os.listdir(attachments_path)) == 2


@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_create_job_with_attachment(authenticated_client):
    with patch('docker.Client', MockClient):
        rv = authenticated_client.post('/image',
                                       data={'dockerfile': sample_dockerfile,
                                             'name': 'hellozeworld'})
    assert rv.status_code == 200
    build_id = json.loads(rv.data.decode('utf-8'))['build_id']
    build_data = poll_for_image_id(authenticated_client, build_id)
    image_id = build_data['id']

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


@patch('tasks.build_and_push.AsyncResult', mock_async_result)
def test_get_job_details(authenticated_client):
    client = authenticated_client
    data = {'command': 'echo hello world'}
    with patch('docker.Client', MockClient):
        rv = client.post('/image',
                         data={'dockerfile': sample_dockerfile,
                               'name': 'hellozeworld'})
        build_id = json.loads(rv.data.decode('utf-8'))['build_id']
        build_data = poll_for_image_id(authenticated_client, build_id)
        image_id = build_data['id']

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

        rv = client.get("/pipeline/%s/job" % (pipeline_id1))
        keys = list(json.loads(rv.data.decode('utf-8')).keys())
        assert len(keys) == 2

        rv = client.get("/pipeline/%s/job/%s" % (pipeline_id1, jid2))
        keys = list(json.loads(rv.data.decode('utf-8')).keys())
        assert str(jid2) in keys


def test_download_result(authenticated_client):
    pipeline = Pipeline.query.all()[0]
    image = Image.query.all()[0]
    with app.app_context():
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


def test_delete_job(authenticated_client):
    pipeline = Pipeline.query.all()[0]
    image = Image.query.all()[0]
    with app.app_context():
        job = Job(pipeline, image, "", "")
        db.session.add(job)
        job.state = 'in_queue'
        db.session.commit()
        job_id = job.id
    result_url = '/pipeline/%s/job/%s' % (job.pipeline_id, job.id)
    rv = authenticated_client.delete(result_url)
    result = json.loads(rv.data.decode('utf-8'))
    assert result.get('error') == 'Cannot delete jobs in queue, try again later'
    assert rv.status_code == 200

    job.state = 'running'
    db.session.add(job)
    db.session.commit()
    rv = authenticated_client.delete(result_url)
    result = json.loads(rv.data.decode('utf-8'))
    assert result.get('error') == "Job didn't update properly, try again later"

    job.container_id = '1'
    db.session.add(job)
    db.session.commit()
    with patch('kabuto.connection.Sender.broadcast'):
        rv = authenticated_client.delete(result_url)

    job = Job.query.filter_by(id=job_id).all()
    assert not job


def test_kill_job(authenticated_client):
    pipeline = Pipeline.query.all()[0]
    image = Image.query.all()[0]
    with app.app_context():
        job = Job(pipeline, image, "", "")
        db.session.add(job)
        job.state = 'running'
        job.container_id = '1'
        db.session.commit()
        job_id = job.id
    result_url = '/pipeline/%s/job/%s/kill' % (job.pipeline_id, job.id)
    rv = authenticated_client.get(result_url)
    assert rv.status_code == 200
    result = json.loads(rv.data.decode('utf-8'))
    print(result)
    assert result.get('message') == "Success"
