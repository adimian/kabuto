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
    DOCKER_REGISTRY_URL = 'localhost:7900'
    DOCKER_REGISTRY_INSECURE = True
    DOCKER_LOGIN = ""
    DOCKER_PASSWORD = ""
    MAIL_SERVER = 'smtp-adimian.alwaysdata.net'
    MAIL_AUTHOR = 'Adimian'
    MAIL_SENDER_ADDRESS = 'kabuto'
    MAIL_SENDER_PW = '4yhLx1ZmUYonchhOTQEq'


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///'
