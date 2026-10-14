"""Small regression checks for the scheduled-notice HTTP route and publisher."""

from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from lms.publish import publish_scheduled_notices
from lms.services import SCHEDULED_ATTENDANCE_TITLE


class ScheduledRouteTests(SimpleTestCase):
    def test_publish_post_reaches_auth_instead_of_dynamic_pk_route(self):
        response = Client(HTTP_HOST="127.0.0.1").post(
            "/api/scheduled-notices/publish",
            data="{}",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)


class _ScheduleCursor:
    def __init__(self):
        self.active = True
        self.notices = 0
        self.description = None
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        if "SELECT * FROM scheduled_notices" in sql:
            self.description = [(name,) for name in ("id", "cohort_id", "repeat_type", "author_id", "title", "content", "is_favorite")]
            self.rows = [(7, 34, "once", None, "Test", "Test content", False)] if self.active else []
        elif "SELECT code FROM cohorts" in sql:
            self.rows = [("cohort_34",)]
        elif "INSERT INTO notices" in sql:
            self.notices += 1
            self.rows = [(self.notices,)]
        elif "UPDATE scheduled_notices" in sql:
            self.active = False
            self.rows = []
        else:
            raise AssertionError(f"Unexpected query: {sql}")

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class ScheduledPublisherTests(TestCase):
    def test_attendance_schedule_reuses_notice_across_days(self):
        cursor = _AttendanceCursor()
        with patch("lms.publish.connection.cursor", return_value=cursor), \
             patch("lms.publish.transaction.atomic", return_value=nullcontext()), \
             patch("lms.publish.schedule_notice_vector"), \
             patch("lms.publish.notify_new_notice"):
            self.assertEqual(publish_scheduled_notices(ids=[7]), 1)
            self.assertEqual(publish_scheduled_notices(ids=[7]), 1)
        self.assertEqual(cursor.notices, 1)
        self.assertEqual(cursor.updates, 1)
        self.assertEqual(cursor.locks, 2)

    def test_once_schedule_cannot_be_published_twice(self):
        cursor = _ScheduleCursor()
        with patch("lms.publish.connection.cursor", return_value=cursor), \
             patch("lms.publish.transaction.atomic", return_value=nullcontext()), \
             patch("lms.publish.schedule_notice_vector"), \
             patch("lms.publish.notify_new_notice") as notify:
            self.assertEqual(publish_scheduled_notices(ids=[7]), 1)
            self.assertEqual(publish_scheduled_notices(ids=[7]), 0)
        self.assertEqual(cursor.notices, 1)
        notify.assert_called_once()


class _AttendanceCursor(_ScheduleCursor):
    def __init__(self):
        super().__init__()
        self.updates = 0
        self.locks = 0

    def execute(self, sql, params=None):
        if "pg_advisory_xact_lock" in sql:
            self.locks += 1
            self.rows = []
        elif "SELECT id, vector_chunk_count FROM notices" in sql:
            assert params == [34, SCHEDULED_ATTENDANCE_TITLE]
            assert "source = 'scheduled'" in sql
            self.rows = [(1, 0)] if self.notices else []
        elif "UPDATE notices" in sql:
            self.updates += 1
            assert params[-1] == 1
            self.rows = []
        elif "UPDATE scheduled_notices" in sql:
            self.rows = []
        else:
            super().execute(sql, params)
            if "SELECT * FROM scheduled_notices" in sql:
                self.rows = [(7, 34, "daily", None, SCHEDULED_ATTENDANCE_TITLE, "내용", True)]
