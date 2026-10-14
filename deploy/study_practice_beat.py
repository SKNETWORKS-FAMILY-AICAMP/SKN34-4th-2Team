"""Dedicated production beat: only the existing daily study-practice task.

Start through docker-compose.study-practice.yml after repository access is
verified and schedulers using the same database have been stopped elsewhere.
The existing task also publishes summaries for finished subjects.
"""
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "production_settings")
os.environ["LMS_INLINE_PUBLISH"] = "0"

from django.conf import settings  # noqa: E402

daily = settings.CELERY_BEAT_SCHEDULE["practice-auto-daily"]
if daily["task"] != "lms.tasks.run_practice_auto":
    raise RuntimeError("Unexpected study-practice task; refuse to start")
if settings.CELERY_TIMEZONE != "Asia/Seoul":
    raise RuntimeError("Study-practice schedule requires Asia/Seoul")
settings.CELERY_BEAT_SCHEDULE = {"practice-auto-daily": daily}

from lms_server.celery import app  # noqa: E402

if set(app.conf.beat_schedule) != {"practice-auto-daily"}:
    raise RuntimeError("Unexpected additional schedules; refuse to start")
