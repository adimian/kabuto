from kabuto.tests import sample_dockerfile
from kabuto.tests.conftest import preload
from kabuto.api import Job, Image, Pipeline, db
import json
import os
import zipfile
from io import BytesIO


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
    print(rv.data)
    result = json.loads(rv.data.decode('utf-8'))
    assert list(result.keys()) == ["error"]

    job.state = "done"
    db.session.add(job)
    db.session.commit()
    result_url = '/pipeline/%s/job/%s?result' % (job.pipeline_id, job.id)
    rv = authenticated_client.get(result_url)
    assert rv.status_code == 200
    expected_file = "results.txt"
    print(rv.data)
    zp = zipfile.ZipFile(BytesIO(rv.data))
    il = zp.infolist()
    assert len(il) == 1
    for zf in il:
        assert zf.filename in expected_file
