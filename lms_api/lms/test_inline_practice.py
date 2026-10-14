"""Celery 없이 도는 대체 스레드의 복습 문제 자동 출제 — 18:30 뒤 오늘 일정 출제가 없을 때 한 번만."""

from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from lms import inline_publish, practice_auto

KST = ZoneInfo("Asia/Seoul")


class FakeCursor:
    def __init__(self, ready=True, ran_today=False):
        self.answers = [(ready,), (1,) if ran_today else None]
        self.calls = 0

    def execute(self, sql, params=None):
        self.calls += 1

    def fetchone(self):
        return self.answers[self.calls - 1]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def due(at: datetime, **cursor) -> bool:
    cur = FakeCursor(**cursor)
    with mock.patch.object(practice_auto, "connection") as conn:
        conn.cursor.return_value = cur
        return practice_auto.daily_due(at)


class DailyDueTests(SimpleTestCase):
    def test_after_1830_without_schedule_run(self):
        self.assertTrue(due(datetime(2026, 10, 1, 18, 30, tzinfo=KST)))
        # 서버가 18:30 에 꺼져 있었어도 그날 늦게 뜨면 돈다
        self.assertTrue(due(datetime(2026, 10, 1, 23, 5, tzinfo=KST)))

    def test_before_1830_or_already_ran(self):
        self.assertFalse(due(datetime(2026, 10, 1, 18, 29, tzinfo=KST)))
        self.assertFalse(due(datetime(2026, 10, 1, 19, 0, tzinfo=KST), ran_today=True))

    def test_without_practice_tables(self):
        self.assertFalse(due(datetime(2026, 10, 1, 19, 0, tzinfo=KST), ready=False))


class InlineStartTests(SimpleTestCase):
    def tearDown(self):
        inline_publish._practice_running.clear()

    def test_starts_once_while_running(self):
        started = []
        with mock.patch.object(practice_auto, "daily_due", return_value=True), \
             mock.patch.object(inline_publish.threading, "Thread") as thread:
            thread.return_value.start.side_effect = lambda: started.append(1)
            inline_publish._start_practice_if_due()
            inline_publish._start_practice_if_due()  # 아직 도는 중 — 다시 띄우지 않는다
        self.assertEqual(len(started), 1)

    def test_not_due_does_nothing(self):
        with mock.patch.object(practice_auto, "daily_due", return_value=False), \
             mock.patch.object(inline_publish.threading, "Thread") as thread:
            inline_publish._start_practice_if_due()
        thread.assert_not_called()
