from flask import Flask
import flask_restful as restful
from flask_restful import reqparse
from flask_login import LoginManager, login_required, login_user


app = Flask(__name__)
api = restful.Api(app)
login_manager = LoginManager(app)

login_parser = reqparse.RequestParser()
login_parser.add_argument('login', type=unicode, help='your login')
login_parser.add_argument('password', type=unicode, help='your password')


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
        args = login_parser.parse_args()
        user = load_user(args['login'])
        login_user(user)
        return {'login': 'success'}



class Job(restful.Resource):
    def get(self, job_id):
        pass


class HelloWorld(restful.Resource):
    @login_required
    def get(self):
        return {'hello': 'world'}

api.add_resource(HelloWorld, '/')
api.add_resource(Login, '/login')

if __name__ == '__main__':
    app.config['SECRET_KEY'] = 'haha'
    app.run(debug=True)
