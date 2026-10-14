"""Standalone local settings: deliberately never import production settings/.env."""
import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured


def require_loopback(host):
    if host not in {'localhost', '127.0.0.1'}:
        raise ImproperlyConfigured('Local E2E requires localhost or 127.0.0.1; RDS is prohibited')
    return host


BASE_DIR = Path(__file__).resolve().parent
SECRET_KEY = 'fictional-local-e2e-signing-key-not-for-production'
DEBUG = True
LOCAL_RESUME_E2E = True
LOCAL_AI_MODE = os.environ.get('LOCAL_AI_MODE', 'mock')
if LOCAL_AI_MODE not in {'mock', 'live'}:
    raise ImproperlyConfigured('LOCAL_AI_MODE must be mock or live')
ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'testserver']
INSTALLED_APPS = ['django.contrib.auth', 'django.contrib.contenttypes', 'django.contrib.sessions',
                  'django.contrib.messages', 'django.contrib.staticfiles', 'lms.apps.LmsConfig']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware', 'django.middleware.common.CommonMiddleware',
              'lms.middleware.LmsUserMiddleware']
ROOT_URLCONF = 'local_resume_e2e_urls'
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': require_loopback(os.environ.get('LOCAL_DB_HOST', '127.0.0.1')),
    'PORT': os.environ.get('LOCAL_DB_PORT', '55439'),
    'NAME': os.environ.get('LOCAL_DB_NAME', 'resume_review_v2_test'),
    'USER': os.environ.get('LOCAL_DB_USER', 'resume_v2_test_admin'),
    'PASSWORD': os.environ.get('LOCAL_DB_PASSWORD', ''),
    'OPTIONS': {'sslmode': 'disable', 'connect_timeout': 5},
    'TEST': {'NAME': 'test_resume_review_v2'},
}}
SIMPLE_JWT = {'SIGNING_KEY': SECRET_KEY, 'ALGORITHM': 'HS256',
              'ACCESS_TOKEN_LIFETIME': timedelta(hours=4)}
LANGUAGE_CODE = 'ko-kr'
TIME_ZONE = 'Asia/Seoul'
USE_TZ = True
STATIC_URL = 'static/'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LMS_INLINE_PUBLISH = '0'
os.environ['LMS_INLINE_PUBLISH'] = '0'
SESSION_ENGINE = 'django.contrib.sessions.backends.signed_cookies'
print(f"DB MODE: LOCAL E2E | DB HOST: {DATABASES['default']['HOST']} | DB NAME: {DATABASES['default']['NAME']} | AI: {LOCAL_AI_MODE}")
