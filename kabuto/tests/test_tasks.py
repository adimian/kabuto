from kabuto.tasks import build_and_push, LogHandler, app
from mock import patch
from kabuto.tests.conftest import MockClient, ROOT_DIR
import os
import shutil
import hgapi
import json


def rm_hg(url):
    hg_path = os.path.join(url, ".hg")
    if os.path.exists(hg_path):
        shutil.rmtree(hg_path)


@patch('docker.Client', MockClient)
def test_build_and_push(authenticated_client):
    repo_template_path = os.path.join(ROOT_DIR, "data", "repo")
    repo_path = os.path.join(ROOT_DIR, "data", "repo_test")
    shutil.copytree(repo_template_path, repo_path)
    result = build_and_push({"nocache": False,
                             "url": None,
                             "path": repo_path,
                             "user": "user",
                             "name": "name",
                             "content": "some_content"})
    reg_url = app.config['DOCKER_REGISTRY_URL']
    expected = {'tag': '%s_user/name' % reg_url,
                'output': ['Successfully built'],
                'content': 'some_content',
                'error': None, 'name': 'name'}
    assert expected == result

    rm_hg(repo_template_path)
    repo = hgapi.hgapi.Repo(repo_template_path)
    repo.hg_init()
    repo.hg_add()
    repo.hg_commit("init", user='me')
    result = build_and_push({"nocache": False,
                             "url": repo_template_path,
                             "path": None,
                             "user": "user",
                             "name": "name",
                             "content": "some_content"})
    rm_hg(repo_template_path)
    assert expected == result

    result = build_and_push({"nocache": False,
                             "url": None,
                             "path": None,
                             "user": "user",
                             "name": "name",
                             "content": "some_content"})
    assert result['error'] == "Must provide a dockerfile or a repository"


class mockCh(object):
    def basic_ack(self, *args, **kwargs):
        pass


class mockMethod(object):
    delivery_tag = None


def test_log_handler():
    handler = LogHandler()
    log_dir = os.path.join(ROOT_DIR, "data", "logs")
    os.mkdir(log_dir)
    app.config['JOB_LOGS_DIR'] = log_dir
    recipe = {'job_id': 1,
              'log_lines': ["log line 1\n", "log line 2\n"]}
    handler(mockCh(), mockMethod(), None, bytes(json.dumps(recipe), "utf-8"))

    expected = """log line 1
log line 2
"""
    with open(os.path.join(log_dir, "job_1.log")) as fh:
        assert expected == fh.read()
    shutil.rmtree(log_dir)
