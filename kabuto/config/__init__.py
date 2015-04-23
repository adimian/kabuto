class Config(object):
    HOST = '0.0.0.0'
    PORT = 5000
    DEBUG = True
    TESTING = False
    BCRYPT_LOG_ROUNDS = 12
    CSRF_ENABLED = True
    SECRET_KEY = 'you-will-never-get-me'
    AMQP_HOSTNAME = 'localhost'
    AMQP_USER = 'kabuto'
    AMQP_PASSWORD = 'kabuto'
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/kabuto.db'
    DOCKER_CLIENT = 'unix://var/run/docker.sock'
    DOCKER_REGISTRY_URL = 'localhost:7900'
    DOCKER_REGISTRY_INSECURE = True
    DOCKER_LOGIN = ""
    DOCKER_PASSWORD = ""
    # python -m smtpd -c DebuggingServer -n localhost:2525
    SMTP_SERVER = 'localhost'
    SMTP_PORT = 2525
    MAIL_AUTHOR = ''
    MAIL_SENDER_ADDRESS = ''
    MAIL_SENDER_PW = ''


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///'
