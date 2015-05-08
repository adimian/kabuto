from kabuto.api import Job, Image, Pipeline, db
import json


def test_logs(preloaded_client):
    # deposit
    ac = preloaded_client
    pipeline = Pipeline.query.all()[0]
    image = Image.query.all()[0]
    job = Job(pipeline, image, "", "")
    db.session.add(job)
    db.session.commit()

    log_line = "A log line"
    wrong_url = "/execution/%s/log/%s" % (job.id, "wrong_token")
    r = ac.post(wrong_url, data={"log_line": log_line})
    assert r.status_code == 404

    url = "/execution/%s/log/%s" % (job.id, job.results_token)
    ac.post(url, data={"log_line": log_line})

    # withdrawal
    url = "/execution/%s/logs" % job.id
    r = ac.get(url)
    data = json.loads(r.data.decode('utf-8'))
    print(data)
    line = data[0]
    assert line['logline'] == log_line

    # deposit a new one
    log_line = "Another log line"
    url = "/execution/%s/log/%s" % (job.id, job.results_token)
    ac.post(url, data={"log_line": log_line})

    # withdraw only the new one
    url = "/execution/%s/logs/%s" % (job.id, line['id'])
    r = ac.get(url)
    data = json.loads(r.data.decode('utf-8'))
    line = data[0]
    assert line['logline'] == log_line
