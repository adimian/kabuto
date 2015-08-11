import datetime
import json
import logging
import os
import uuid
import zipfile

from flask import abort, send_file, request
from flask_login import (login_required, login_user,
                         current_user)
from flask_restful import reqparse
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import OperationalError
from werkzeug.datastructures import FileStorage
import flask_restful as restful
from flask_ldap3_login import AuthenticationResponseStatus as ars
import time

from mailer import send_token
from utils import publish_job, make_app, get_working_dir
from tasks import build_and_push, get_docker_client


app, api, login_manager, ldap_manager, db, bcrypt = make_app()


class ProtectedResource(restful.Resource):
    method_decorators = [login_required]

logger = logging.getLogger(__name__)
logger.level = logging.DEBUG

DATE_FORMAT = "%Y-%m-%d"


def get_remote_ip():
    return request.environ.get('HTTP_X_REAL_IP') or \
        request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(64), unique=True)
    _password = db.Column(db.String(128))
    source = db.Column(db.String(32))  # internal/LDAP/...
    email = db.Column(db.String(256), unique=True)
    token = db.Column(db.String(36))

    def __init__(self, login, password, email):
        self.login = login
        if not ldap_manager:
            self.password = password
            self.email = email

    @hybrid_property
    def password(self):
        return self._password

    @password.setter
    def _set_password(self, plaintext):
        self._password = bcrypt.generate_password_hash(plaintext)

    def is_correct_password(self, plaintext):
        if bcrypt.check_password_hash(self._password, plaintext):
            return True
        return False

    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.login


class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    dockerfile = db.Column(db.Text)

    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner = db.relationship('User',
                            backref=db.backref('images', lazy='dynamic'))

    def __init__(self, dockerfile, name, owner):
        self.dockerfile = dockerfile
        self.name = name
        self.owner = owner

    def as_dict(self):
        return {"id": self.id,
                "name": self.name,
                "dockerfile": self.dockerfile,
                "creation_date": self.creation_date.strftime(DATE_FORMAT)}


class Pipeline(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128))
    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner = db.relationship('User',
                            backref=db.backref('pipelines', lazy='dynamic'))

    def __init__(self, name, owner):
        self.name = name
        self.owner = owner

    def as_dict(self):
        jobs = [{"id": j.id} for j in Job.query.filter_by(pipeline=self)]
        return {"id": self.id,
                "name": self.name,
                "creation_date": self.creation_date.strftime(DATE_FORMAT),
                "jobs": jobs}


class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_id = db.Column(db.Integer, db.ForeignKey('image.id'))
    image = db.relationship('Image',
                            backref=db.backref('jobs', lazy='dynamic'))

    pipeline_id = db.Column(db.Integer, db.ForeignKey('pipeline.id'))
    pipeline = db.relationship('Pipeline',
                               backref=db.backref('jobs', lazy='dynamic'))

    command = db.Column(db.Text)
    state = db.Column(db.String(32), default='ready')
    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())
    used_cpu = db.Column(db.Float(precision=2), default=0.)
    used_memory = db.Column(db.Float(precision=2), default=0.)
    used_io = db.Column(db.Float(precision=2), default=0.)

    attachments_path = db.Column(db.String(128))
    attachments_token = db.Column(db.String(36))
    results_token = db.Column(db.String(36))
    results_path = db.Column(db.String(128))

    sequence_number = db.Column(db.Integer)

    def __init__(self, pipeline, image, attachments, command, sequence=None):
        self.pipeline = pipeline
        self.image = image
        self.command = command
        self.attachments_path = attachments
        self.attachments_token = str(uuid.uuid4())
        self.results_token = str(uuid.uuid4())
        self.results_path = get_working_dir(prefix='kabuto-outbox-')
        if not sequence:
            self.sequence_number = len(pipeline.jobs.all()) - 1
        else:
            self.sequence_number = sequence

    def serialize(self):
        return json.dumps({'execution': self.id,
                           'image': self.image.name,
                           'command': self.command,
                           'attachment_token': self.attachments_token,
                           'result_token': self.results_token})

    def as_dict(self):
        return {"id": self.id,
                "command": self.command,
                "state": self.state,
                "creation_date": self.creation_date.strftime(DATE_FORMAT),
                "used_cpu": self.used_cpu,
                "used_memory": self.used_memory,
                "used_io": self.used_io,
                "attachment_token": self.attachments_token,
                "results_path": self.results_path,
                "image": {"id": self.image_id},
                "pipeline": {"id": self.pipeline_id}}

    @property
    def owner(self):
        return self.pipeline.owner


class ExecutionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    job = db.relationship('Job', backref=db.backref('logs', lazy='dynamic'))
    logline = db.Column(db.Text)

    def __init__(self, job, line):
        self.job = job
        self.logline = line

    def as_dict(self):
        return {"id": self.id,
                "job": self.job_id,
                "logline": self.logline}


@login_manager.user_loader
def load_user(login):
    try:
        user = User.query.filter_by(login=login).one()
    except NoResultFound:
        return None
    return user


def prepare_entity_dict(entity, entity_id, **kwargs):
    entity_list = get_entities(entity, entity_id, **kwargs)
    entity_dict = {}
    for entity in entity_list:
        entity_dict[entity.id] = entity.as_dict()
    return entity_dict


def get_folder_as_zip(zip_name, folder_to_zip):
    zip_file = "%s.zip" % os.path.join(get_working_dir(),
                                       zip_name)
    zipf = zipfile.ZipFile(zip_file, 'w')
    if not os.path.isdir(folder_to_zip):
        raise Exception("%s is not a folder" % folder_to_zip)
    zipdir(folder_to_zip, zipf,
           root_folder=folder_to_zip)
    zipf.close()
    return zip_file


def get_entities(entity, entity_id, **kwargs):
    kwargs["owner"] = current_user
    if entity_id:
        kwargs["id"] = entity_id
    if isinstance(entity, list):
        base_class, join_class = entity
        query = db.session.query(base_class).join(join_class)
        query = query.filter(join_class.owner == current_user)
        base_id, join_id = entity_id
        if base_id:
            query = query.filter(base_class.id == base_id)
        if join_id:
            query = query.filter(join_class.id == join_id)
        entity_list = query.all()
    else:
        entity_list = entity.query.filter_by(**kwargs).all()
    return entity_list


class Login(restful.Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('login', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        args = parser.parse_args()

        user = load_user(args['login'])
        can_login = False

        if ldap_manager:
            response = ldap_manager.authenticate(args['login'],
                                                 args['password'])
            if ars.success == response.status:
                if not user:
                    user = User(args['login'], None, None)
                can_login = True
        elif user:
            if user.is_correct_password(args['password']):
                can_login = True
        if can_login:
            login_user(user)
            return {'login': 'success'}
        abort(401)


class ImageBuild(ProtectedResource):
    def get(self, build_id, image_id=None):
        if image_id:
            image = get_entities(Image, image_id)
            if not image:
                return {'error': 'could not find image with id %s' % image_id}
            image = image[0]

        res = build_and_push.AsyncResult(build_id)
        if res and res.state == 'FAILURE':
            return {'state': res.state, 'error': res.traceback}
        elif res and res.state == 'SUCCESS':
            result = res.get()
            if result.get("error"):
                return {'state': 'FAILED',
                        'error': result["error"],
                        'output': result.get("output")}
            if image_id:
                if result.get("name") and not image.name == result["name"]:
                    image.name = result["name"]
                if result.get("content"):
                    image.dockerfile = result["content"]
                db.session.add(image)
                db.session.commit()
            else:
                image = Image(result["content"], result["name"], current_user)
                db.session.add(image)
                db.session.commit()
            return {'state': res.state,
                    'id': image.id,
                    'output': result["output"]}
        else:
            return {'state': res.state}


class Images(ProtectedResource):
    def get(self, image_id=None):
        return prepare_entity_dict(Image, image_id)

    def post(self):
        return self.process()

    def put(self, image_id):
        image = get_entities(Image, image_id)
        if not image:
            return {'error': ('You either don\'t have the rights to update '
                              'this image, or it does not exist')}
        return self.process()

    def process(self):
        res = build_and_push.delay(self.parse_request())

        return {'status': 'Your image is being built', 'build_id': res.id}

    def delete(self, image_id):
        image = get_entities(Image, image_id)
        if not image:
            return {'error': ('You either don\'t have the rights to update '
                              'this image, or it does not exist')}
        image = image[0]
        client = get_docker_client()
        client.remove_image(image.name)
        db.session.delete(image)
        db.session.commit()
        return {"status": "Successfully deleted the image"}

    def parse_request(self):
        parser = reqparse.RequestParser()
        parser.add_argument('dockerfile', type=str, default=None)
        parser.add_argument('name', type=str, required=True)
        parser.add_argument('repo_url', type=str, default=None)
        parser.add_argument('nocache', type=str, default="false")
        parser.add_argument('attachments', type=FileStorage, location='files',
                            action='append', default=[])
        args = parser.parse_args()

        path = get_working_dir()
        for filestorage in args['attachments']:
            with open(os.path.join(path, filestorage.filename), "wb+") as fh:
                fh.write(filestorage.read())

        content = args['dockerfile']
        if content:
            with open(os.path.join(path, "Dockerfile"), "wb+") as fh:
                fh.write(bytes(content, 'UTF-8'))
        name = args['name']
        url = args['repo_url']
        nocache = str(args['nocache']).lower() == 'true'

        return {"path": path, "name": name, "content": content,
                "url": url, "nocache": nocache}


class Pipelines(ProtectedResource):
    def get(self, pipeline_id=None):
        return prepare_entity_dict(Pipeline, pipeline_id)

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True)
        args = parser.parse_args()
        name = args['name']
        pipeline = Pipeline(name, current_user)

        db.session.add(pipeline)
        db.session.commit()

        return {'id': pipeline.id}

    def put(self, pipeline_id):
        pl = get_entities(Pipeline, pipeline_id)
        if not pl:
            return {'error': ('You either don\'t have the rights to update '
                              'this image, or it does not exist')}
        pl = pl[0]

        parser = reqparse.RequestParser()
        parser.add_argument('name')
        parser.add_argument('remove_jobs')
        parser.add_argument('rearrange_jobs')
        args = parser.parse_args()

        return_dict = {}

        if args['name']:
            pl.name = args['name']
            return_dict['name'] = "Successfully updated name"
        if args.get('remove_jobs'):
            remove_jobs = args['remove_jobs'].split(",")
            pl.jobs.all()
            jobs = []
            for job in pl.jobs.all():
                if str(job.id) not in remove_jobs:
                    jobs.append(job)
            pl.jobs = jobs
            return_dict['remove_jobs'] = "Successfully removed jobs"
        if args.get('rearrange_jobs'):
            rearrange_jobs = args['rearrange_jobs'].split(",")
            current_jobs = dict([(str(j.id), j) for j in pl.jobs.all()])
            if not sorted(list(current_jobs.keys())) == sorted(rearrange_jobs):
                rearrange_ids = ", ".join(sorted(rearrange_jobs))
                current_ids = ", ".join(sorted(current_jobs))
                return_dict['rearrange_jobs'] = ("Could not rearrange jobs. "
                                                 "rearrange ids are [%s] while"
                                                 " current ids are [%s]" %
                                                 (rearrange_ids, current_ids))
            else:
                for idx, job in enumerate(rearrange_jobs):
                    current_jobs[job].sequence_number = idx
                    db.session.add(current_jobs[job])
                return_dict['rearrange_jobs'] = "Successfully removed jobs"

        db.session.add(pl)
        db.session.commit()
        return return_dict

    def delete(self, pipeline_id):
        pipeline = get_entities(Pipeline, pipeline_id)
        if not pipeline:
            return {'error': ('You either don\'t have the rights to update '
                              'this pipeline, or it does not exist')}
        pipeline = pipeline[0]
        db.session.delete(pipeline)
        db.session.commit()
        return {"status": "Successfully deleted the pipeline"}


class Jobs(ProtectedResource):
    def get(self, pipeline_id=None, job_id=None):
        parser = reqparse.RequestParser()
        parser.add_argument('result', default=False)
        args = parser.parse_args()
        if (not args['result'] is False) and job_id:
            try:
                job = Job.query.filter_by(id=job_id).one()
            except NoResultFound:
                return {"error": "Job not found"}

            if not job.state == "done":
                return {"error": "Job has not finished running, or has failed"}
            try:
                z_file = get_folder_as_zip("results", job.results_path)
                return send_file(z_file,
                                 as_attachment=True,
                                 attachment_filename=os.path.basename(z_file))
            except Exception:
                return {"error": "Something went wrong, contact your admin"}
        return prepare_entity_dict([Job, Pipeline], [job_id, pipeline_id])

    def post(self, pipeline_id):
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=str)
        parser.add_argument('command', type=str)

        parser.add_argument('attachments', type=FileStorage, location='files',
                            action='append', default=[])
        args = parser.parse_args()

        path = get_working_dir(prefix='kabuto-inbox-')
        for filestorage in args['attachments']:
            with open(os.path.join(path, filestorage.filename), "wb+") as fh:
                fh.write(filestorage.read())

        try:
            pipeline = Pipeline.query.filter_by(id=pipeline_id).one()
        except NoResultFound:
            return {"error": "Pipeline not found"}

        try:
            image = Image.query.filter_by(id=args['image_id']).one()
        except NoResultFound:
            return {"error": "Image not found"}

        job = Job(pipeline, image, path, args['command'])

        db.session.add(job)
        db.session.commit()

        return {'id': job.id}

    def put(self, pipeline_id, job_id):
        job = get_entities([Job, Pipeline], [job_id, pipeline_id])
        if not job:
            return {'error': ('You either don\'t have the rights to update '
                              'this image, or it does not exist')}
        job = job[0]
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=str)
        parser.add_argument('command', type=str)

        parser.add_argument('attachments', type=FileStorage, location='files',
                            action='append', default=[])
        args = parser.parse_args()

        path = job.attachments_path
        for filestorage in args['attachments']:
            with open(os.path.join(path, filestorage.filename), "wb+") as fh:
                fh.write(filestorage.read())

        if args.get('image_id'):
            try:
                image = Image.query.filter_by(id=args['image_id']).one()
            except NoResultFound:
                return {"error": "Image not found"}
            if not image.id == job.image.id:
                job.image = image

        command = args.get('command')
        if command:
            if not command == job.command:
                job.command = command

        db.session.add(job)
        db.session.commit()

        return {'id': job.id}


class Submitter(ProtectedResource):
    def post(self, pipeline_id):
        try:
            pipeline = Pipeline.query.filter_by(id=pipeline_id).one()
        except NoResultFound:
            return {"error": "Pipeline not found"}

        jobs = []
        for job in pipeline.jobs:
            jobs.append(job)
            publish_job(job.serialize(), app.config)
            job.state = "in_queue"
            db.session.add(job)
            db.session.commit()

        return dict([(jb.id, jb.state) for jb in jobs])


class LogDeposit(restful.Resource):
    def post(self, job_id, token):
        try:
            job = Job.query.filter_by(id=job_id).one()
        except NoResultFound:
            return {"error": "Job not found"}

        if not job or not job.results_token == token:
            msg = "Unauthorized log deposit from %s with token: %s"
            logging.info(msg % (get_remote_ip(), token))
            abort(404)

        parser = reqparse.RequestParser()
        parser.add_argument('log_line')
        args = parser.parse_args()

        lines = json.loads(args['log_line'])
        for line in lines:
            db.session.add(ExecutionLog(job, line))
        db.session.commit()


class LogWithdrawal(ProtectedResource):
    def get(self, job_id, last_id=None):
        logs = ExecutionLog.query.filter_by(job_id=job_id)
        if last_id:
            logs = logs.filter(ExecutionLog.id > last_id).all()
        return [log.as_dict() for log in logs]


class Attachment(restful.Resource):
    def get(self, job_id, token):
        try:
            job = Job.query.filter_by(id=job_id).one()
        except NoResultFound:
            return {"error": "Job not found"}

        if not job or not job.attachments_token == token:
            msg = "Unauthorized download request from %s with token: %s"
            logging.info(msg % (get_remote_ip(), token))
            abort(404)
        try:
            zip_file = get_folder_as_zip(token, job.attachments_path)
            # We'll assume that the job started running
            # when the attachments are downloaded
            job.state = "running"
            db.session.add(job)
            db.session.commit()
            return send_file(zip_file,
                             as_attachment=True,
                             attachment_filename=os.path.basename(zip_file))
        except Exception as error:
            return "Something went wrong, contact your admin: %s" % error

    def post(self, job_id, token):
        try:
            job = Job.query.filter_by(id=job_id).one()
        except NoResultFound:
            return {"error": "Job not found"}

        if not job.results_token == token:
            msg = "Unauthorized upload request from %s with token: %s"
            logging.info(msg % (get_remote_ip(), token))
            abort(404)

        parser = reqparse.RequestParser()
        parser.add_argument('results', type=FileStorage,
                            location='files', default=None)
        parser.add_argument('state', type=str, required=True)
        parser.add_argument('response')
        parser.add_argument('cpu', type=int, required=True)
        parser.add_argument('memory', type=int, required=True)
        parser.add_argument('io', type=int, required=True)
        args = parser.parse_args()

        zip_dir = os.path.join(job.results_path, '%s.zip' % token)
        if args['results']:
            with open(zip_dir, "wb+") as fh:
                fh.write(args['results'].read())

        if os.path.exists(zip_dir):
            with zipfile.ZipFile(zip_dir) as zf:
                zf.extractall(job.results_path)
                os.remove(zip_dir)

        job.state = args['state']
        job.used_cpu = args['cpu']
        job.used_memory = args['memory']
        job.used_io = args['io']
        db.session.add(job)
        db.session.commit()


def zipdir(path, zipf, root_folder):
    # Still need to find a clean way to write empty folders,
    # as this is not being done
    for root, _, files in os.walk(path):
        for fh in files:
            file_path = os.path.join(root, fh)
            zipf.write(file_path, os.path.relpath(file_path, root_folder))


class Register(restful.Resource):
    def get(self, user, token):
        user = load_user(user)
        if user and user.token == token:
            user.active = True
            db.session.add(user)
            db.session.commit()
            return {"registration": "success"}
        return {"registration": "user or token not found"}

    def post(self):
        if ldap_manager:
            return {"status": "fail",
                    "error": "Working with ldap context, cannot register"}
        parser = reqparse.RequestParser()
        parser.add_argument('login', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        parser.add_argument('email', type=str, required=True)
        args = parser.parse_args()

        user = User(login=args['login'],
                    password=args['password'],
                    email=args['email'])
        user.token = str(uuid.uuid4())
        db.session.add(user)
        db.session.commit()
#         send_token(args['email'], user, user.token,
#                    url_root=request.url_root[:-1])
        return {"status": "success",
                "token": user.token}


class HelloWorld(ProtectedResource):
    def get(self):
        return {'hello': 'world'}

api.add_resource(HelloWorld, '/')
api.add_resource(Login, '/login')
api.add_resource(Register,
                 '/register',
                 '/register/confirm/<string:user>/<string:token>')
api.add_resource(Images,
                 '/image',
                 '/image/<string:image_id>')
api.add_resource(ImageBuild,
                 '/image/build/<string:build_id>',
                 '/image/build/<string:build_id>/<string:image_id>')
api.add_resource(Pipelines,
                 '/pipeline',
                 '/pipeline/<string:pipeline_id>')
api.add_resource(Jobs,
                 '/jobs',
                 '/pipeline/<string:pipeline_id>/job',
                 '/pipeline/<string:pipeline_id>/job/<string:job_id>')
api.add_resource(Submitter,
                 '/pipeline/<string:pipeline_id>/submit')
api.add_resource(Attachment,
                 '/execution/<string:job_id>/attachments/<string:token>',
                 '/execution/<string:job_id>/results/<string:token>')
api.add_resource(LogDeposit,
                 '/execution/<string:job_id>/log/<string:token>')
api.add_resource(LogWithdrawal,
                 '/execution/<string:job_id>/logs',
                 '/execution/<string:job_id>/logs/<string:last_id>')


def init_db():
    def create_db(timeout):
        try:
            db.create_all()
        except OperationalError as error:
            app.logger.error("Could not connect. Retrying in %ss" % timeout)
            time.sleep(timeout)
            return error
        return None

    timeout = 1
    while timeout <= 8:
        error = create_db(timeout)
        if error:
            timeout = timeout * 2
        else:
            break

    if error:
        raise error


if __name__ == '__main__':
    init_db()
    app.run(host=app.config['HOST'],
            port=app.config['PORT'])
else:
    # for gunicorn
    init_db()
