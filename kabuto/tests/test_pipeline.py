import json
from kabuto.tests.conftest import preload
from kabuto.api import Pipeline, User, Image, Job, db, app
from unittest.mock import patch


def test_create_pipeline(authenticated_client):
    rv = authenticated_client.post('/pipeline',
                                   data={'name': 'my first pipeline'})
    assert rv.status_code == 200
    pipeline_id = json.loads(rv.data.decode('utf-8'))['id']
    assert pipeline_id is not None


def test_update_pipeline(preloaded_client):
    with app.app_context():
        u = User.query.filter_by(login='me').first()
        pipeline = Pipeline("my first pipeline", u)
        image = Image.query.all()[0]
        job1 = Job(pipeline, image, "", "")
        job2 = Job(pipeline, image, "", "")
        job3 = Job(pipeline, image, "", "")
        job1_id = job1.id
        job2_id = job2.id
        job3_id = job3.id
        db.session.add(pipeline)
        db.session.add(job1)
        db.session.add(job2)
        db.session.add(job3)
        db.session.commit()
        pipeline_id = pipeline.id

        assert job1.sequence_number == 0
        assert job2.sequence_number == 1
        assert job3.sequence_number == 2

        rv = preloaded_client.put('/pipeline/999')
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('error')

        # arrange_jobs
        arranged_jobs = [str(job2.id), str(job3.id), str(job1.id)]
        rv = preloaded_client.put('/pipeline/%s' % pipeline_id,
                                  data={'name': 'my edited pipeline',
                                        'rearrange_jobs': ",".join(arranged_jobs)})

        pipeline = Pipeline.query.filter_by(id=pipeline_id).first()
        job1 = Job.query.filter_by(id=job1_id).first()
        job2 = Job.query.filter_by(id=job2_id).first()
        job3 = Job.query.filter_by(id=job3_id).first()
        assert pipeline.name == 'my edited pipeline'
        assert len(pipeline.jobs.all()) == 3
        assert job1.sequence_number == 2
        assert job2.sequence_number == 0
        assert job3.sequence_number == 1
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('rearrange_jobs')
        assert data['rearrange_jobs'] == "Successfully removed jobs"

        # arrange jobs error
        wrong_jobs = [str(job2.id), str(job3.id)]
        rv = preloaded_client.put('/pipeline/%s' % pipeline_id,
                                  data={'name': 'my edited pipeline',
                                        'rearrange_jobs': ",".join(wrong_jobs)})
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('rearrange_jobs')
        error = ("Could not rearrange jobs. rearrange ids are [%s] while" %
                 ", ".join(wrong_jobs))
        assert error in data['rearrange_jobs']

        # remove jobs
        job1 = Job.query.filter_by(id=job1_id).first()
        job3 = Job.query.filter_by(id=job3_id).first()
        rv = preloaded_client.put('/pipeline/%s' % pipeline_id,
                                  data={'name': 'my edited pipeline',
                                        'remove_jobs': ",".join([str(job1.id),
                                                                 str(job3.id)])})
        pipeline = Pipeline.query.filter_by(id=pipeline_id).first()
        assert len(pipeline.jobs.all()) == 1
        assert pipeline.jobs.all()[0].id == job2_id


def test_delete_pipeline(authenticated_client):
    u = User.query.filter_by(login='me').first()
    pipeline = Pipeline("my first pipeline", u)
    db.session.add(pipeline)
    db.session.commit()
    pipeline_id = pipeline.id

    authenticated_client.delete('/pipeline/%s' % pipeline_id)
    assert not Pipeline.query.filter_by(id=pipeline_id).first()

    rv = authenticated_client.delete('/pipeline/999')
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)


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

    rv = client.post('/pipeline/%s/submit' % 999)
    data = json.loads(rv.data.decode('utf-8'))
    assert data.get('error', None)
    assert data['error'] == "Pipeline not found"


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
