DEBUG = False
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name

SITE_ID = 1

USE_I18N = False
LANGUAGE_CODE = 'en-us'
USE_L10N = False
USE_TZ = True
TIME_ZONE = 'America/Los_Angeles'

TEST_RUNNER = 'django_nose.NoseTestSuiteRunner'
NOSE_ARGS = ['-s']

INSTALLED_APPS = (
    'listener.bitcoind',
)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {
            'format': '%(levelname)s %(message)s'
        },
    },
    'filters': {
        'require_debug_false': {
            '()': 'django.utils.log.RequireDebugFalse'
        }
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'propagate': True,
            'level': 'INFO'
        },
        'django.db': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
}

import os

SECRET_KEY = os.environ['SECRET_KEY']

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.environ['DB_NAME'],
        'USER': os.environ['DB_USER'],
        'PASSWORD': os.environ['DB_PASS'],
        'HOST': os.environ['DB_HOST'],
        'PORT': os.environ['DB_PORT'],
        'ATOMIC_REQUESTS': True
    }
}

BITCOIN_RPC_USER = os.environ['BITCOIN_RPC_USER']
BITCOIN_RPC_PASSWORD = os.environ['BITCOIN_RPC_PASSWORD']

from bitcoin import SelectParams
SelectParams(os.environ['BITCOIN_NETWORK'])
