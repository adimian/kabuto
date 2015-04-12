from flask import Flask, abort
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
import re
import json


class ProtectedResource(restful.Resource):
    method_decorators = [login_required]


app = Flask(__name__)
api = restful.Api(app)
login_manager = LoginManager(app)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)


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
    docker_id = db.Column(db.String(64))
    name = db.Column(db.String(128))
    dockerfile = db.Column(db.Text)

    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())

    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    owner = db.relationship('User',
                            backref=db.backref('images', lazy='dynamic'))

    def __init__(self, dockerfile, docker_id, name, owner):
        self.dockerfile = dockerfile
        self.docker_id = docker_id
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
    used_cpu = db.Column(db.Float(precision=2), default=0.)
    used_memory = db.Column(db.Float(precision=2), default=0.)
    used_io = db.Column(db.Float(precision=2), default=0.)

    def __init__(self, pipeline, image, attachments, command):
        self.pipeline = pipeline
        self.image = image
        self.attachments = attachments
        self.command = command

    def serialize(self):
        return json.dumps({'image': self.image.docker_id,
                           'command': self.command})


class Execution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'))
    job = db.relationship('Job',
                          backref=db.backref('executions', lazy='dynamic'))
    state = db.Column(db.String(32), default='ready')
    creation_date = db.Column(db.DateTime, default=datetime.datetime.utcnow())

    def __init__(self, job):
        self.job = job


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
            output = client.build(tag=tag, fileobj=dockerfile)

        last_line = list(output)[-1]
        last_stream = json.loads(last_line)['stream'].strip()
        docker_id = re.search(pattern='Successfully built ([a-z0-9]+)',
                              string=last_stream).groups()[0]
        os.remove(filename)

        image = Image(content, docker_id, name, current_user)
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
    def post(self, pipeline_id):
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=unicode)
        parser.add_argument('command', type=unicode)
        # TODO: handle upload
#         parser.add_argument('attachments', type=file)
        args = parser.parse_args()

        pipeline = Pipeline.query.filter_by(id=pipeline_id).one()
        image = Image.query.filter_by(id=args['image_id']).one()

        job = Job(pipeline, image, [], args['command'])

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
            publish_job(message=job.serialize())
        db.session.commit()
        return dict([(ex.id, ex.state) for ex in execs])


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

if __name__ == '__main__':
    app.config.from_object('kabuto.config.Config')
    db.create_all()
    app.run()
