from kabuto.api import Job, Image, Pipeline, db, app
import json


def test_logs(preloaded_client):
    with app.app_context():
        # deposit
        ac = preloaded_client
        pipeline = Pipeline.query.all()[0]
        image = Image.query.all()[0]
        job = Job(pipeline, image, "", "")
        db.session.add(job)
        db.session.commit()

        log_line_text = "A log line"
        log_line = json.dumps([log_line_text])
        wrong_url = "/execution/%s/log/%s" % (job.id, "wrong_token")
        r = ac.post(wrong_url, data={"log_line": log_line})
        assert r.status_code == 404

        url = "/execution/%s/log/%s" % (999, job.results_token)
        rv = ac.post(url, data={"log_line": log_line})
        data = json.loads(rv.data.decode('utf-8'))
        assert data.get('error', None)
        assert data['error'] == "Job not found"

        url = "/execution/%s/log/%s" % (job.id, job.results_token)
        ac.post(url, data={"log_line": log_line})

        # withdrawal
        url = "/execution/%s/logs" % job.id
        r = ac.get(url)
        data = json.loads(r.data.decode('utf-8'))
        line = data[0]
        assert line['logline'] == log_line_text

        # deposit a new one
        log_line_text = "Another log line"
        log_line = json.dumps([log_line_text])
        url = "/execution/%s/log/%s" % (job.id, job.results_token)
        ac.post(url, data={"log_line": log_line})

        # withdraw only the new one
        url = "/execution/%s/logs/%s" % (job.id, line['id'])
        r = ac.get(url)
        data = json.loads(r.data.decode('utf-8'))
        line = data[0]
        assert line['logline'] == log_line_text
