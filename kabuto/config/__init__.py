class Config(object):
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = True
    TESTING = True
    BCRYPT_LOG_ROUNDS = 12
    CSRF_ENABLED = True
    SECRET_KEY = 'you-will-never-get-me'
    AMQP_HOSTNAME = 'localhost'
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/test.db'
    DOCKER_CLIENT = 'unix://var/run/docker.sock'


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///'
