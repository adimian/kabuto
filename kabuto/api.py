from io import BytesIO
import datetime
import json
import logging
import os
import tempfile
import uuid
import zipfile

from flask import Flask, abort, send_file, request
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_required, login_user, current_user
from flask_restful import reqparse
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.datastructures import FileStorage
import docker
import flask_restful as restful
import pika

from mailer import send_token
from utils import put_in_message_queue, publish_job

class ProtectedResource(restful.Resource):
    method_decorators = [login_required]


app = Flask(__name__)
api = restful.Api(app)
login_manager = LoginManager(app)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

logger = logging.getLogger(__name__)
logger.level = logging.DEBUG


def get_remote_ip():
    return request.environ.get('HTTP_X_REAL_IP') or \
        request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)



def get_docker_client():
    client = docker.Client(base_url=app.config['DOCKER_CLIENT'])
    if app.config['DOCKER_LOGIN']:
        client.login(app.config['DOCKER_LOGIN'],
                     app.config['DOCKER_PASSWORD'],
                     registry=app.config['DOCKER_REGISTRY'])
    return client


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(64), unique=True)
    _password = db.Column(db.String(128))
    source = db.Column(db.String(32))  # internal/LDAP/...
    email = db.Column(db.String(256), unique=True)
    token = db.Column(db.String(36))

    def __init__(self, login, password, email):
        self.login = login
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

    def __init__(self, pipeline, image, attachments, command):
        self.pipeline = pipeline
        self.image = image
        self.command = command
        self.attachments_path = attachments
        self.attachments_token = str(uuid.uuid4())
        self.results_token = str(uuid.uuid4())
        self.results_path = tempfile.mkdtemp(prefix='kabuto-outbox-')

    def serialize(self):
        return json.dumps({'execution': self.id,
                           'image': self.image.name,
                           'command': self.command,
                           'attachment_token': self.attachments_token,
                           'result_token': self.results_token})


class ExecutionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    job = db.relationship('Job', backref=db.backref('logs', lazy='dynamic'))
    logline = db.Column(db.Text)

    def __init__(self, execution, line):
        self.execution = execution
        self.logline = line


@login_manager.user_loader
def load_user(username):
    try:
        user = User.query.filter_by(login=username).one()
    except NoResultFound:
        return None
    return user


class Login(restful.Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('login', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        args = parser.parse_args()

        user = load_user(args['login'])
        if user:
            if user.is_correct_password(args['password']):
                login_user(user)
                return {'login': 'success'}
        abort(401)


class Images(ProtectedResource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('dockerfile', type=str, required=True)
        parser.add_argument('name', type=str, required=True)

        args = parser.parse_args()
        content = args['dockerfile']
        name = args['name']

        client = get_docker_client()

        # TODO: async all the following

        tag = '/'.join((app.config['DOCKER_REGISTRY_URL'], name))
        client.build(tag=tag, fileobj=BytesIO(content.encode('utf-8')))

        image = Image(content, name, current_user)
        db.session.add(image)
        db.session.commit()

        client.push(repository=tag,
                    insecure_registry=app.config['DOCKER_REGISTRY_INSECURE'])

        return {'id': image.id}


class Pipelines(ProtectedResource):
    def get(self):
        pipelines = Pipeline.query.filter_by(owner=current_user).all()
        return dict([(p.id, p.name) for p in pipelines])

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, required=True)
        args = parser.parse_args()
        name = args['name']
        pipeline = Pipeline(name, current_user)

        db.session.add(pipeline)
        db.session.commit()

        return {'id': pipeline.id}


class Jobs(ProtectedResource):
    def get(self, pipeline_id, job_id):
        jobs = Job.query.filter_by(id=job_id).all()
        re = dict([(p.id, (p.attachments_path,
                           p.results_path, p.state)) for p in jobs])
        return re

    def post(self, pipeline_id):
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=str)
        parser.add_argument('command', type=str)

        parser.add_argument('attachments', type=FileStorage, location='files',
                            action='append', default=[])
        args = parser.parse_args()

        path = tempfile.mkdtemp(prefix='kabuto-inbox-')
        for filestorage in args['attachments']:
            with open(os.path.join(path, filestorage.filename), "wb+") as fh:
                fh.write(filestorage.read())

        pipeline = Pipeline.query.filter_by(id=pipeline_id).one()
        image = Image.query.filter_by(id=args['image_id']).one()

        job = Job(pipeline, image, path, args['command'])

        db.session.add(job)
        db.session.commit()

        return {'id': job.id}


class Submitter(ProtectedResource):
    def post(self, pipeline_id):
        pipeline = Pipeline.query.filter_by(id=pipeline_id).one()
        jobs = []
        for job in pipeline.jobs:
            jobs.append(job)
            publish_job(message=job.serialize())

        return dict([(jb.id, jb.state) for jb in jobs])


class LogDeposit(restful.Resource):
    def post(self, job_id, token):
        job = Job.query.filter_by(id=job_id).one()
        if not job or not job.results_token == token:
            msg = "Unauthorized log deposit from %s with token: %s"
            logging.info(msg % (get_remote_ip(), token))
            abort(404)

        parser = reqparse.RequestParser()
        parser.add_argument('log_line', type=str)
        args = parser.parse_args()

        db.session.add(ExecutionLog(job, args['log_line']))
        db.session.commit()


class LogWithdrawal(ProtectedResource):
    def get(self, job_id, last_id=None):
        logs = ExecutionLog.query.filter_by(job_id=job_id)
        if last_id:
            logs.filter(ExecutionLog.id > last_id)
        return dict([(log.id, log.logline) for log in logs])


class Attachment(restful.Resource):
    def get(self, job_id, token):
        job = Job.query.filter_by(id=job_id).one()
        if not job or not job.attachments_token == token:
            msg = "Unauthorized download request from %s with token: %s"
            logging.info(msg % (get_remote_ip(), token))
            abort(404)
        try:
            zip_file = "%s.zip" % os.path.join(tempfile.mkdtemp(), token)
            zipf = zipfile.ZipFile(zip_file, 'w')
            zipdir(job.attachments_path, zipf,
                   root_folder=job.attachments_path)
            zipf.close()
            return send_file(zip_file,
                             as_attachment=True,
                             attachment_filename=os.path.basename(zip_file))
        except Exception:
            return "Something went wrong, contact your admin"

    def post(self, job_id, token):
        job = Job.query.filter_by(id=job_id).one()

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
        user = User.query.filter_by(login=user).one()
        if user and user.token == token:
            user.active = True
            db.session.add(user)
            db.session.commit()
            return {"registration": "success"}
        return {"registration": "user or token not found"}

    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('username', type=str, required=True)
        parser.add_argument('password', type=str, required=True)
        parser.add_argument('email', type=str, required=True)
        args = parser.parse_args()

        user = User(login=args['username'],
                    password=args['password'],
                    email=args['email'])
        user.token = str(uuid.uuid4())
        db.session.add(user)
        db.session.commit()
        send_token(args['email'], user, user.token,
                   url_root=request.url_root[:-1])


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
api.add_resource(Pipelines,
                 '/pipeline',
                 '/pipeline/<string:pipeline_id>')
api.add_resource(Jobs,
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

if __name__ == '__main__':
    app.config.from_object('config.Config')
    db.create_all()
    app.run(host=app.config['HOST'],
            port=app.config['PORT'])
