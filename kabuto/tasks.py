import shutil
import os
from io import BytesIO
from hgapi import hg_clone
from hgapi.hgapi import HgException
import docker
from utils import make_app, get_working_dir
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


class BuildResult(object):
    def __init__(self, name=None, content=None, error=None, output=None):
        self.name = name
        self.content = content
        self.error = error
        self.output = output


@celery.task(name='tasks.build_and_push')
def build_and_push(args):
    error = None
    output = []
    folder = None

    client = get_docker_client()

    # TODO: async all the following

    kwargs = {"nocache": args["nocache"]}
    if args["url"]:
        folder = get_working_dir()
        try:
            hg_clone(args["url"], folder)
            dockerfile = os.path.join(folder, "Dockerfile")
            if not os.path.exists(dockerfile):
                error = "Repository has no file named 'Dockerfile'"
            kwargs['path'] = folder
        except HgException as e:
            error = "Could not clone repository: %s" % e
    elif args["path"]:
        kwargs['path'] = args["path"]
    else:
        error = "Must provide a dockerfile or a repository"
    if error:
        return {"error": error}

    error = "Build failed"
    tag = '/'.join((app.config['DOCKER_REGISTRY_URL'], args["name"]))
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
    if args["path"]:
        shutil.rmtree(args["path"])

    return {"name": args["name"], "content": args["content"],
            "error": error, "output": output}
