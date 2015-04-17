from flask import Flask, abort, send_file, request
from werkzeug.datastructures import FileStorage
import flask_restful as restful
from flask_restful import reqparse
from flask_login import LoginManager, login_required, login_user, current_user
from flask_sqlalchemy import SQLAlchemy
import os
import tempfile
import pika
from sqlalchemy.ext.hybrid import hybrid_property
from flask_bcrypt import Bcrypt
from sqlalchemy.orm.exc import NoResultFound
import datetime
import docker
import zipfile
import json
import uuid
import logging
import sys


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


def put_in_message_queue(queue, message):
    connection = pika.BlockingConnection(pika.ConnectionParameters(
        host=app.config['AMQP_HOSTNAME']))
    channel = connection.channel()
    channel.queue_declare(queue=queue, durable=True)

    properties = pika.BasicProperties(delivery_mode=2,)
    channel.basic_publish(exchange='',
                          routing_key=queue,
                          body=message,
                          properties=properties)
    connection.close()


def publish_job(message):
    put_in_message_queue(queue='jobs', message=message)


def get_docker_client():
    client = docker.Client(base_url=app.config['DOCKER_CLIENT'])
    if app.config['DOCKER_LOGIN']:
        client.login(app.config['DOCKER_LOGIN'], app.config['DOCKER_PASSWORD'])
    return client


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(64), unique=True)
    _password = db.Column(db.String(128))
    source = db.Column(db.String(32))  # internal/LDAP/...
    active = db.Column(db.Boolean, default=False)
    email = db.Column(db.String(256), unique=True)

    def __init__(self, login):
        self.login = login

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
        return self.id


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

    attachments_token = db.Column(db.String(36))
    attachments_path = db.Column(db.String(128))
    results_token = db.Column(db.String(36))
    results_path = db.Column(db.String(128))

    def __init__(self, pipeline, image, attachments, command):
        self.pipeline = pipeline
        self.image = image
        self.command = command
        self.attachments_token = unicode(uuid.uuid4())
        self.attachments_path = attachments
        self.results_token = unicode(uuid.uuid4())
        self.results_path = tempfile.mkdtemp(prefix='kabuto-outbox-')


class Execution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    job = db.relationship('Job',
                          backref=db.backref('executions', lazy='dynamic'))
    state = db.Column(db.String(32), default='ready')
    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())

    used_cpu = db.Column(db.Float(precision=2), default=0.)
    used_memory = db.Column(db.Float(precision=2), default=0.)
    used_io = db.Column(db.Float(precision=2), default=0.)

    def __init__(self, job):
        self.job = job

    def serialize(self):
        return json.dumps({'execution': self.id,
                           'image': self.job.image.name,
                           'command': self.job.command,
                           'attachment_token': self.job.attachments_token,
                           'result_token': self.job.results_token})

class ExecutionLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    execution_id = db.Column(db.Integer, db.ForeignKey('execution.id'))
    execution = db.relationship('Execution',
                            backref=db.backref('logs', lazy='dynamic'))
    logline = db.Column(db.Text)

    def __init__(self, execution, line):
        self.execution = execution
        self.logline = line


@login_manager.user_loader
def load_user(username):
    try:
        user = User.query.filter_by(login=username).one()
    except NoResultFound:
        user = User(login=username)
        db.session.add(user)
        db.session.commit()
    return user


class Login(restful.Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('login', type=unicode, required=True)
        parser.add_argument('password', type=unicode, required=True)
        args = parser.parse_args()

        if args['login'] and args['password']:
            user = load_user(args['login'])
            login_user(user)
            return {'login': 'success'}

        abort(401)


class Images(ProtectedResource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('dockerfile', type=unicode, required=True)
        parser.add_argument('name', type=unicode, required=True)

        args = parser.parse_args()
        content = args['dockerfile']

        name = args['name']

        client = get_docker_client()

        # TODO: async all the following

        fd, filename = tempfile.mkstemp()
        os.close(fd)

        with open(filename, 'w') as f:
            f.write(content)

        with open(filename, 'r') as dockerfile:
            tag = '/'.join((app.config['DOCKER_REGISTRY_URL'], name))
            client.build(tag=tag, fileobj=dockerfile)

        os.remove(filename)

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
        parser.add_argument('name', type=unicode, required=True)
        args = parser.parse_args()
        name = args['name']

        pipeline = Pipeline(name, current_user)

        db.session.add(pipeline)
        db.session.commit()

        return {'id': pipeline.id}


class Jobs(ProtectedResource):
    def get(self, pipeline_id, job_id):
        jobs = Job.query.filter_by(id=job_id).all()
        return dict([(p.id, (p.attachments_path, p.results_path)) for p in jobs])

    def post(self, pipeline_id):
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=unicode)
        parser.add_argument('command', type=unicode)

        parser.add_argument('attachments', type=FileStorage, location='files', action='append', default=[])
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
        execs = []
        for job in pipeline.jobs:
            ex = Execution(job)
            db.session.add(ex)
            execs.append(ex)

        # we need this before publish, to get the ID
        db.session.commit()

        for ex in execs:
            publish_job(message=ex.serialize())

        return dict([(ex.id, ex.state) for ex in execs])


class Executions(ProtectedResource):
    def get(self, execution_id):
        ex = Execution.query.filter_by(id=execution_id).one()
        return {ex.id: ex.state}


class LogDeposit(restful.Resource):
    def post(self, execution_id, token):
        ex = Execution.query.filter_by(id=execution_id).one()
        if not ex or not ex.job.results_token == token:
            logging.info("Unauthorized log deposit from %s with token: %s" % (get_remote_ip(), token))
            abort(404)

        parser = reqparse.RequestParser()
        parser.add_argument('log_line', type=unicode)
        args = parser.parse_args()

        db.session.add(ExecutionLog(ex, args['log_line']))
        db.session.commit()


class LogWithdrawal(ProtectedResource):
    def get(self, execution_id, last_id=None):
        logs = ExecutionLog.query.filter_by(execution_id=execution_id)
        if last_id:
            logs.filter(ExecutionLog.id > last_id)
        return dict([(log.id, log.logline) for log in logs])


class Attachment(restful.Resource):
    def get(self, execution_id, token):
        ex = Execution.query.filter_by(id=execution_id).one()
        if not ex or not ex.job.attachments_token == token:
            logging.info("Unauthorized download request from %s with token: %s" % (get_remote_ip(), token))
            abort(404)
        try:
            zip_file = "%s.zip" % os.path.join("/tmp", token)
            zipf = zipfile.ZipFile(zip_file, 'w')
            zipdir(ex.job.attachments_path, zipf, root_folder=ex.job.attachments_path)
            zipf.close()
            filename = zip_file
            return send_file(filename,
                             as_attachment=True,
                             attachment_filename=os.path.basename(filename))
        except Exception, e:
            return "Something went wrong, contact your admin"

    def post(self, execution_id, token):
        ex = Execution.query.filter_by(id=execution_id).one()
        if not ex.job.results_token == token:
            logging.info("Unauthorized upload request from %s with token: %s" % (get_remote_ip(), token))
            abort(404)

        parser = reqparse.RequestParser()
        parser.add_argument('results', type=FileStorage, location='files', default=None)
        parser.add_argument('state', type=unicode, required=True)
        parser.add_argument('response')
        parser.add_argument('cpu', type=int, required=True)
        parser.add_argument('memory', type=int, required=True)
        parser.add_argument('io', type=int, required=True)
        args = parser.parse_args()

        zip_dir = os.path.join(ex.job.results_path, '%s.zip' % token)
        if args['results']:
            with open(zip_dir, "wb+") as fh:
                fh.write(args['results'].read())

        with zipfile.ZipFile(zip_dir) as zf:
            zf.extractall(ex.job.results_path)

        os.remove(zip_dir)
        ex.state = args['state']
        ex.used_cpu = args['cpu']
        ex.used_memory = args['memory']
        ex.used_io = args['io']
        db.session.add(ex)
        db.session.commit()


def zipdir(path, zipf, root_folder):
    # Still need to find a clean way to write empty folders, as this is not being done
    for root, dirs, files in os.walk(path):
        for fh in files:
            file_path = os.path.join(root, fh)
            zipf.write(file_path, os.path.relpath(file_path, root_folder))


class HelloWorld(ProtectedResource):
    def get(self):
        return {'hello': 'world'}

api.add_resource(HelloWorld, '/')
api.add_resource(Login, '/login')
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
                 '/pipeline/<string:pipeline_id>/submit',)
api.add_resource(Executions,
                 '/execution/<string:execution_id>')
api.add_resource(Attachment,
                 '/execution/<string:execution_id>/attachments/<string:token>',
                 '/execution/<string:execution_id>/results/<string:token>')
api.add_resource(LogDeposit,
                 '/execution/<string:execution_id>/log/<string:token>')
api.add_resource(LogWithdrawal,
                 '/execution/<string:execution_id>/logs',
                 '/execution/<string:execution_id>/logs/<string:last_id>')

if __name__ == '__main__':
    app.config.from_object('kabuto.config.Config')
    db.create_all()
    app.run(host=app.config['HOST'],
            port=app.config['PORT'])
