import os
from pathlib import Path

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lms_server.settings")

_repo = Path(__file__).resolve().parents[2]
_env = _repo / ".env"
if _env.exists():
    for raw in _env.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))

# Windows/구형 Redis: RESP3 HELLO 미지원 → Celery 연결 전에 RESP2 강제
from lms.redis_compat import force_redis_resp2

force_redis_resp2()

app = Celery("lms_server")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
