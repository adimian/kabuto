from kabuto.api import db, Job
import zipfile
from StringIO import StringIO
import os

ROOT_DIR = os.path.abspath(os.path.dirname(os.path.abspath(__file__)))


def test_download_attachments(preloaded_client_with_attachments):
    job = Job.query.all()[0]
    url = "/execution/%s/attachments/%s" % (job.id, job.attachments_token)
    rv = preloaded_client_with_attachments.get(url)

    expected_files = ["test1.txt", "test2.txt"]
    zp = zipfile.ZipFile(StringIO(rv.data))
    il = zp.infolist()
    assert len(il) == 2
    for zf in il:
        assert zf.filename in expected_files


def test_upload_attachments(preloaded_client_with_attachments):
    job = Job.query.all()[0]
    url = "/execution/%s/results/%s" % (job.id, job.results_token)
    data = {'results': (open(os.path.join(ROOT_DIR, "data", "results.zip")),
                        'results.zip')}
    preloaded_client_with_attachments.post(url, data=data)
    assert os.path.exists(os.path.join(job.results_path, "file1.txt"))
    assert os.path.exists(os.path.join(job.results_path, "file2.txt"))
