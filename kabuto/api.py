from flask import Flask
import flask_restful as restful
from flask_restful import reqparse
from flask_login import LoginManager, login_required, login_user
import subprocess
import StringIO
import tempfile


app = Flask(__name__)
api = restful.Api(app)
login_manager = LoginManager(app)

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


class Login(restful.Resource):
    def post(self):
        login_parser = reqparse.RequestParser()
        login_parser.add_argument('login', type=unicode)
        login_parser.add_argument('password', type=unicode)

        args = login_parser.parse_args()
        user = load_user(args['login'])
        login_user(user)
        return {'login': 'success'}


class Image(restful.Resource):
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
            image_id = subprocess.check_output(command, shell=True)
            return {'id': image_id}


class HelloWorld(restful.Resource):
    @login_required
    def get(self):
        return {'hello': 'world'}

api.add_resource(HelloWorld, '/')
api.add_resource(Login, '/login')
api.add_resource(Image, '/image')

if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'haha'
    app.run(debug=True)
