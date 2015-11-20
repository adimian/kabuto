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
    KABUTO_WORKING_DIR = ''
    JOB_LOGS_DIR = '/tmp'
    CELERY_BROKER_URL = 'amqp://%s:%s@%s:5672/celery' % (AMQP_USER,
                                                         AMQP_PASSWORD,
                                                         AMQP_HOSTNAME)
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
    SQLALCHEMY_DATABASE_URI = 'sqlite:////tmp/kabuto.db'
    DOCKER_CLIENT = 'unix://var/run/docker.sock'
    DOCKER_REGISTRY_URL = 'localhost:7900'
    DOCKER_REGISTRY_URL = 'localhost:7900/kabuto'
    DOCKER_REGISTRY_INSECURE = True
    DOCKER_LOGIN = ""
    DOCKER_PASSWORD = ""
    # python -m smtpd -c DebuggingServer -n localhost:2525
    SMTP_SERVER = 'localhost'
    SMTP_PORT = 2525
    MAIL_AUTHOR = ''
    MAIL_SENDER_ADDRESS = ''
    MAIL_SENDER_PW = ''

    LDAP_HOST = ''  # Hostname of your LDAP Server
    LDAP_BASE_DN = ''  # Base DN of your directory
    LDAP_USER_DN = 'ou=people'  # Users DN to be prepended to the Base DN
    LDAP_GROUP_DN = 'ou=groups'  # Groups DN to be prepended to the Base DN

    LDAP_USER_RDN_ATTR = 'uid'  # The RDN attribute for your user schema on LDAP
    LDAP_USER_LOGIN_ATTR = 'uid'  # The Attribute you want users to authenticate to LDAP with.
    LDAP_BIND_USER_DN = ''  # The Username to bind to LDAP with
    LDAP_BIND_USER_PASSWORD = ''

    SENTRY_DSN = ''


class TestingConfig(Config):
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///'
    MAIL_SENDER_PW = 'test'
    MAIL_SENDER_ADDRESS = 'test'
