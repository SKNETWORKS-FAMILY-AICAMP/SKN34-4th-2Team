"""Only the isolated localhost PostgreSQL cluster used for v2 verification.

Unlike the SQLite test settings this runs the full historical migration graph.
Never use inherited DB_HOST/DB_NAME or production credentials here.
"""

from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'HOST': '127.0.0.1',
        'PORT': '55439',
        'NAME': 'resume_review_v2_test',
        'USER': 'resume_v2_test_admin',
        'PASSWORD': '',
        'OPTIONS': {'sslmode': 'disable', 'connect_timeout': 5},
        'TEST': {'NAME': 'test_resume_review_v2'},
    },
}
MIGRATION_MODULES = {}
CONN_MAX_AGE = 0
