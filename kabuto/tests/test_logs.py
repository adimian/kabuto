from kabuto.api import app
from kabuto.tests.conftest import ROOT_DIR
import os
import json


def test_logs(preloaded_client):
    ac = preloaded_client
    with app.app_context():
        app.config["JOB_LOGS_DIR"] = os.path.join(ROOT_DIR, "data")

        url = "/execution/1/logs"
        r = ac.get(url)
        data = json.loads(r.data.decode('utf-8'))

        assert data['size'] == 30
        assert data['filename'] == 'job_1_logs.txt'

        r = ac.post(url)
        expected = """Some log line
Another log line"""
        assert r.data.decode('utf-8') == expected

        r = ac.post(url, data={"start_byte": 5, "size": 20})
        expected = """log line
Another log"""
        assert r.data.decode('utf-8') == expected
