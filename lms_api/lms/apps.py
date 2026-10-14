import os

from django.apps import AppConfig


class LmsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "lms"

    def ready(self) -> None:
        # runserver 부모 프로세스에서는 스레드를 두지 않는다.
        if os.environ.get("RUN_MAIN") == "true" or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            from lms.inline_publish import start_inline_publisher

            start_inline_publisher()
        elif os.environ.get("RUN_MAIN") is None and os.environ.get("WERKZEUG_RUN_MAIN") is None:
            # gunicorn / manage.py 직접 실행
            from django.conf import settings

            if not settings.DEBUG:
                from lms.inline_publish import start_inline_publisher

                start_inline_publisher()

