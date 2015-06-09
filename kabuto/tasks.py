import shutil
import os
import tempfile
from io import BytesIO
from hgapi import hg_clone
import docker
from utils import make_app
from celery import Celery
import json


def make_celery(config=None):
    app, _, _, _, _, _ = make_app(config)
    celery = Celery(app.import_name,
                    broker=app.config['CELERY_BROKER_URL'])
    celery.conf.update(app.config)
    TaskBase = celery.Task

    class ContextTask(TaskBase):
        abstract = True

        def __call__(self, *args, **kwargs):
            with app.app_context():
                return TaskBase.__call__(self, *args, **kwargs)
    celery.Task = ContextTask
    return celery, app

celery, app = make_celery()


def get_docker_client():
    client = docker.Client(base_url=app.config['DOCKER_CLIENT'])
    if app.config['DOCKER_LOGIN']:
        client.login(app.config['DOCKER_LOGIN'],
                     app.config['DOCKER_PASSWORD'],
                     registry=app.config['DOCKER_REGISTRY'])
    return client


@celery.task(name='tasks.build_and_push')
def build_and_push(name, content=None, url=None):
    error = None
    output = []
    folder = None

    client = get_docker_client()

    # TODO: async all the following

    kwargs = {}
    if content:
        fileobj = BytesIO(content.encode('utf-8'))
        kwargs['fileobj'] = fileobj
    elif url:
        folder = tempfile.mkdtemp()
        hg_clone(url, folder)
        dockerfile = os.path.join(folder, "Dockerfile")
        if not os.path.exists(dockerfile):
            error = "Repository has no file named 'Dockerfile'"
        kwargs['path'] = folder
    else:
        error = "Must provide a dockerfile or a repository"
    if error:
        return None, None, error, None

    error = "Build failed"
    tag = '/'.join((app.config['DOCKER_REGISTRY_URL'], name))
    result = client.build(tag=tag,
                          **kwargs)
    for line in result:
        output.append(json.loads(line.decode()))
        if "Successfully built" in str(line):
            error = None
    if not error:
        client.push(repository=tag,
                    insecure_registry=app.config['DOCKER_REGISTRY_INSECURE'])

    if folder:
        shutil.rmtree(folder)

    return name, content, error, output
