"""Ordinary LMS contracts, isolated B database. No production URL changes."""
import os
from django.core.exceptions import ImproperlyConfigured

if os.environ.get('RESUME_REVIEW_ENGINE') != 'v2-local' or os.environ.get('DB_HOST') not in ('127.0.0.1', 'localhost'):
    raise ImproperlyConfigured('Use local_resume_site.py; cloud database prohibited')

from lms_server.settings import *  # noqa: F403

ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
LMS_INLINE_PUBLISH = '0'
CORS_ALLOWED_ORIGINS = ['http://127.0.0.1:5180', 'http://localhost:5180']
DATABASES['default']['OPTIONS'] = {'sslmode': 'disable', 'connect_timeout': 5}  # noqa: F405
