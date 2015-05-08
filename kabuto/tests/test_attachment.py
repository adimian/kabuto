from kabuto.api import db, Job
import zipfile
from io import BytesIO
import os

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def test_download_attachments(preloaded_client_with_attachments):
    job = Job.query.all()[0]
    url = "/execution/%s/attachments/%s" % (job.id, job.attachments_token)
    rv = preloaded_client_with_attachments.get(url)
    assert rv.status_code == 200
    expected_files = ["test1.txt", "test2.txt"]
    zp = zipfile.ZipFile(BytesIO(rv.data))
    il = zp.infolist()
    assert len(il) == 2
    for zf in il:
        assert zf.filename in expected_files

    job = Job.query.all()[0]
    url = "/execution/%s/attachments/%s" % (job.id, "invalid_token")
    rv = preloaded_client_with_attachments.get(url)
    assert rv.status_code == 404

    job = Job.query.all()[0]
    job.attachments_path = os.path.join(job.attachments_path, "does_not_exist")
    db.session.add(job)
    db.session.commit()
    url = "/execution/%s/attachments/%s" % (job.id, job.attachments_token)
    rv = preloaded_client_with_attachments.get(url)
    assert "Something went wrong, contact your admin" in rv.data.decode('utf-8')


def test_upload_attachments(preloaded_client_with_attachments):
    job = Job.query.all()[0]
    result_path = job.results_path
    url = "/execution/%s/results/%s" % (job.id, job.results_token)
    data = {'results': (open(os.path.join(ROOT_DIR, "data", "results.zip"),
                             'rb'),
                        'results.zip'),
            "state": "done",
            "response": "done",
            "cpu": '0',
            "memory": '0',
            "io": '0',
    }
    rv = preloaded_client_with_attachments.post(url, data=data)
    assert rv.status_code == 200
    assert os.path.exists(os.path.join(result_path, "file1.txt"))
    assert os.path.exists(os.path.join(result_path, "file2.txt"))

    job = Job.query.all()[0]
    url = "/execution/%s/results/%s" % (job.id, "invalid_token")
    data['results'] = (open(os.path.join(ROOT_DIR, "data", "results.zip"),
                            'rb'),
                       'results.zip')
    rv = preloaded_client_with_attachments.post(url, data=data)
    assert rv.status_code == 404
