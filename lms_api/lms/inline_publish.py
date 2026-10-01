"""Celery beat 없이도 기한 지난 예약 공지를 주기적으로 발행한다 (로컬/폴백).

같은 루프가 자격시험 일정(하루 넘게 묵었을 때)과 복습 문제 자동 출제(오늘 18:30 이 지났는데 아직이면)도 대신 돌린다.
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_started = False
# 자동 출제는 저장소마다 몇 분 — 도는 동안 루프(공지 게시)를 막지 않게 따로 띄우고, 같은 프로세스에서 겹쳐 띄우지 않는다
_practice_running = threading.Event()


def _start_practice_if_due() -> None:
    """복습 문제 자동 출제 — Celery beat 18:30 의 대체(practice_auto.daily_due)"""
    from lms.practice_auto import daily_due, run_daily

    if _practice_running.is_set() or not daily_due():
        return
    _practice_running.set()

    def work() -> None:
        from django.db import connection

        try:
            logger.info("inline practice auto: %s", run_daily())
        except Exception:
            logger.exception("inline practice auto failed")
        finally:
            connection.close()
            _practice_running.clear()

    threading.Thread(target=work, name="lms-inline-practice", daemon=True).start()


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
        next_qual_check = 0.0
        while True:
            try:
                from lms.publish import publish_scheduled_notices

                count = publish_scheduled_notices()
                if count:
                    logger.info("inline publish: %s notice(s)", count)
            except Exception:
                logger.exception("inline publish failed")
            # 시험 일정은 하루 넘게 묵었을 때만 받는다. 확인은 한 시간에 한 번
            if time.monotonic() >= next_qual_check:
                next_qual_check = time.monotonic() + 3600
                try:
                    from lms.external_feeds import sync_qual_exams_if_stale

                    synced = sync_qual_exams_if_stale()
                    if synced:
                        logger.info("inline qual exams synced: %s", synced)
                except Exception as exc:
                    logger.warning("inline qual exams sync failed: %s", type(exc).__name__)
            try:
                _start_practice_if_due()
            except Exception:
                logger.exception("inline practice auto check failed")
            time.sleep(interval_sec)

    thread = threading.Thread(target=_loop, name="lms-inline-publish", daemon=True)
    thread.start()
    logger.info("inline scheduled-notice publisher started (every %ss)", interval_sec)
