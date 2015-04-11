from flask import Flask, abort
import flask_restful as restful
from flask_restful import reqparse
from flask_login import LoginManager, login_required, login_user, current_user
from flask_sqlalchemy import SQLAlchemy
import os
import tempfile
import uuid
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


def get_docker_client():
    client = docker.Client(base_url=app.config['DOCKER_CLIENT'])
    return client


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(64), unique=True)
    _password = db.Column(db.String(128))
    source = db.Column(db.String(32))  # internal/LDAP/...
    active = db.Column(db.Boolean, default=False)

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


class Job(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    image = db.Column(db.Integer)

    def __init__(self, uid, image, attachments, command):
        self.uid = uid
        self.image = image
        self.attachments = attachments
        self.command = command

    def __repr__(self):
        return str(self.__dict__)


class Execution(object):
    def __init__(self, uid, job):
        self.uid = uid
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


# TODO: plug to a database
PIPELINES = {}
EXECUTION_QUEUE = []


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
            output = client.build(tag=name, fileobj=dockerfile)

        last_line = list(output)[-1]
        last_stream = json.loads(last_line)['stream'].strip()
        docker_id = re.search(pattern='Successfully built ([a-z0-9]+)',
                              string=last_stream).groups()[0]
        os.remove(filename)

        image = Image(content, docker_id, name, current_user)
        db.session.add(image)
        db.session.commit()

        return {'id': image.id}


class Pipelines(ProtectedResource):
    def get(self):
        global PIPELINES
        res = []
        for pipeline_id, details in PIPELINES.iteritems():
            res.append({'id': pipeline_id,
                        'name': details['name'],
                        'jobs': len(details['jobs'])})
        return res

    def post(self):
        global PIPELINES
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=unicode)
        args = parser.parse_args()
        name = args['name']
        uid = str(uuid.uuid4())
        PIPELINES[uid] = {'name': name,
                          'jobs': []}
        return {'id': uid}


class Jobs(ProtectedResource):
    def post(self, pipeline_id):
        global PIPELINES

        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=unicode)
        parser.add_argument('command', type=unicode)
        # TODO: handle upload
#         parser.add_argument('attachments', type=file)
        args = parser.parse_args()

        pipeline = PIPELINES[pipeline_id]
        uid = str(uuid.uuid4())

        job = Job(uid, args['image_id'], [], args['command'])

        pipeline['jobs'].append(job)

        return {'id': uid}


class Submitter(ProtectedResource):
    def post(self, pipeline_id):
        global PIPELINES
        pipeline = PIPELINES[pipeline_id]
        jobs = pipeline['jobs']
        status = {}
        for job in jobs:
            uid = str(uuid.uuid4())
            EXECUTION_QUEUE.append(Execution(uid, job))
            status[uid] = job.uid
        return status


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
    app.config['DOCKER_CLIENT'] = 'unix://var/run/docker.sock'
    app.config['BCRYPT_LOG_ROUNDS'] = 12
    app.config['SECRET_KEY'] = 'haha'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'

    db.create_all()
    app.run(host='0.0.0.0', port=5000, debug=True)
