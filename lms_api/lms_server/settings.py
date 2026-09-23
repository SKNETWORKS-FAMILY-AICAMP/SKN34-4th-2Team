import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

_env = REPO_DIR / ".env"
if _env.exists():
    for raw in _env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "lms-api-dev")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("ALLOWED_HOSTS", "*").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "lms.apps.LmsConfig",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "lms.middleware.LmsUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "lms_server.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": [
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
        ]},
    }
]
WSGI_APPLICATION = "lms_server.wsgi.application"

_url = urlparse(os.environ.get("DATABASE_URL", "postgresql://postgres@127.0.0.1:5432/lms"))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (_url.path or "/lms").lstrip("/"),
        "USER": _url.username or "postgres",
        "PASSWORD": _url.password or "",
        "HOST": _url.hostname or "127.0.0.1",
        "PORT": str(_url.port or 5432),
    }
}

AUTH_PASSWORD_VALIDATORS = []
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

from datetime import timedelta

from corsheaders.defaults import default_headers

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_HEADERS = (*default_headers, "authorization", "x-csrftoken")

# SimpleJWT 토큰 발급/검증만 사용 (HTTP 레이어는 Django Ninja)
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
# redis-py 5+/8 + 구형 Redis: HELLO(RESP3) 실패 → protocol 2
CELERY_BROKER_TRANSPORT_OPTIONS = {"protocol": 2, "health_check_interval": 30}
CELERY_RESULT_BACKEND_TRANSPORT_OPTIONS = {"protocol": 2, "health_check_interval": 30}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "publish-scheduled-notices": {
        "task": "lms.tasks.publish_due_notices",
        "schedule": 60.0,
    },
    # 공부방 — 연결한 GitHub 조직·계정의 새 수업 저장소를 올린다(lms/study_source_service.py)
    "sync-study-sources": {
        "task": "lms.tasks.sync_study_sources",
        "schedule": 3600.0,
    },
}
# DEBUG면 Celery 없이도 60초마다 예약 공지 발행. 끄려면 LMS_INLINE_PUBLISH=0
LMS_INLINE_PUBLISH = os.environ.get("LMS_INLINE_PUBLISH", "1" if DEBUG else "0")

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:5173", "http://localhost:5173"]
