from kabuto.tests import sample_dockerfile
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
    job_id = json.loads(rv.data.decode('utf-8'))['id']

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

    rv = authenticated_client.post('/pipeline/%s/job' % pipeline_id,
                              data={'image_id': str(image_id),
                                    'command': 'echo hello world',
                                    'attachments': [(open(os.path.join(ROOT_DIR, "data", "file1.txt"), "rb"), 'test1.txt'),
                                                     (open(os.path.join(ROOT_DIR, "data", "file2.txt"), "rb"), 'test2.txt')]})
    assert rv.status_code == 200
    job_id = json.loads(rv.data.decode('utf-8'))['id']
    rv = authenticated_client.get('/pipeline/%s/job/%s' % (pipeline_id, job_id))
    assert rv.status_code == 200
    data = json.loads(rv.data.decode('utf-8'))
    attachments_path = data[str(job_id)][0]
    assert os.path.exists(attachments_path)
    assert len(os.listdir(attachments_path)) == 2
