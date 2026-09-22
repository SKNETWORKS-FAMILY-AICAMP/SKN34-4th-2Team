"""Celery beat 없이도 기한 지난 예약 공지를 주기적으로 발행한다 (로컬/폴백)."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False


def start_inline_publisher(*, interval_sec: float = 60.0) -> None:
    global _started
    if _started:
        return
    flag = os.environ.get("LMS_INLINE_PUBLISH", "").strip().lower()
    if flag in ("0", "false", "off", "no"):
        return
    # 기본: DEBUG 또는 LMS_INLINE_PUBLISH=1
    from django.conf import settings

    if flag not in ("1", "true", "on", "yes") and not settings.DEBUG:
        return

    _started = True

    def _loop() -> None:
        # runserver 기동 직후 DB 준비 대기
        time.sleep(5)
        while True:
            try:
                from lms.publish import publish_scheduled_notices

                count = publish_scheduled_notices()
                if count:
                    logger.info("inline publish: %s notice(s)", count)
            except Exception:
                logger.exception("inline publish failed")
            time.sleep(interval_sec)

    thread = threading.Thread(target=_loop, name="lms-inline-publish", daemon=True)
    thread.start()
    logger.info("inline scheduled-notice publisher started (every %ss)", interval_sec)
