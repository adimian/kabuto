from flask import Flask
import flask_restful as restful
from flask_restful import reqparse
from flask_login import LoginManager, login_required, login_user
import subprocess
import tempfile
import uuid


class ProtectedResource(restful.Resource):
    method_decorators = [login_required]


app = Flask(__name__)
api = restful.Api(app)
login_manager = LoginManager(app)


class Job(object):
    def __init__(self, uid, pipeline, image, attachments, command):
        self.uid = uid
        self.pipeline = pipeline
        self.image = image
        self.attachments = attachments
        self.command = command


class User(object):
    def is_active(self):
        return True

    def is_authenticated(self):
        return True

    def get_id(self):
        return 'test'


@login_manager.user_loader
def load_user(username):
    return User()


# TODO: plug to a database
PIPELINES = {}


class Login(restful.Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('login', type=unicode)
        parser.add_argument('password', type=unicode)

        args = parser.parse_args()
        user = load_user(args['login'])
        login_user(user)
        return {'login': 'success'}


class Images(ProtectedResource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument('dockerfile', type=unicode)
        parser.add_argument('name', type=unicode)

        args = parser.parse_args()
        content = args['dockerfile']

        name = args['name']

        # TODO: async
        with tempfile.NamedTemporaryFile('w') as dockerfile:
            dockerfile.write(content)
            dockerfile.flush()
            dockerfile.seek(0)
            subprocess.call(['docker', 'build', '-t', name, '-'],
                            stdin=dockerfile)
            # TODO: (security) do not use shell with constructed args (grep)
            command = "docker images --no-trunc | grep %s | awk '{print $3}'" % name
            image_id = subprocess.check_output(command, shell=True).strip()
            return {'id': image_id}


class Pipelines(ProtectedResource):
    def post(self):
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
        parser = reqparse.RequestParser()
        parser.add_argument('image_id', type=unicode)
        parser.add_argument('command', type=unicode)
        # TODO: handle upload
#         parser.add_argument('attachments', type=file)
        args = parser.parse_args()

        print args
        pipeline = PIPELINES[pipeline_id]
        uid = str(uuid.uuid4())

        job = Job(uid, pipeline, args['image_id'], None, args['command'])

        pipeline['jobs'].append(job)

        print pipeline

        return {'id': uid}


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

if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'haha'
    app.run(debug=True)
