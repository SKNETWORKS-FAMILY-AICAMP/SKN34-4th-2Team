"""Small regression checks for the scheduled-notice HTTP route and publisher."""

from contextlib import nullcontext
from unittest import TestCase
from unittest.mock import patch

from django.test import Client, SimpleTestCase

from lms.publish import publish_scheduled_notices


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
    def test_once_schedule_cannot_be_published_twice(self):
        cursor = _ScheduleCursor()
        with patch("lms.publish.connection.cursor", return_value=cursor), \
             patch("lms.publish.transaction.atomic", return_value=nullcontext()), \
             patch("lms.publish.schedule_notice_vector"):
            self.assertEqual(publish_scheduled_notices(ids=[7]), 1)
            self.assertEqual(publish_scheduled_notices(ids=[7]), 0)
        self.assertEqual(cursor.notices, 1)
