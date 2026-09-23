"""Small API-contract checks that do not require a database connection."""

import os
from collections import namedtuple

from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from lms.api import ChatIn, _data, api, chat
from lms.bootstrap_service import _dicts
from lms.commands import (
    _validate_record_submission_write, _validate_resume_write, op_add_todo,
    op_delete_todo, op_toggle_todo, op_upsert_sql,
)


class JsonBodyContractTests(SimpleTestCase):
    def test_arbitrary_json_fields_survive(self):
        payload = {"title": "Notice", "cohortId": "cohort_34", "isActive": False}
        self.assertEqual(_data(payload), payload)
        self.assertEqual(_data(None), {})

    def test_write_routes_accept_json_request_bodies(self):
        paths = api.get_openapi_schema()["paths"]
        for path, method in (
            ("/api/notices", "post"),
            ("/api/notices/{pk}", "patch"),
            ("/api/scheduled-notices", "post"),
            ("/api/scheduled-notices/{pk}", "patch"),
            ("/api/alert-popups", "post"),
            ("/api/alert-popups/{pk}", "patch"),
        ):
            with self.subTest(path=path, method=method):
                operation = paths[path][method]
                self.assertIn("requestBody", operation)
                self.assertFalse(any(p["name"] == "body" for p in operation.get("parameters", [])))


class AiProxyContractTests(SimpleTestCase):
    def test_missing_internal_token_does_not_call_ai_service(self):
        request = Mock(auth={"role": "student", "firebase_uid": "student-a"})
        with patch.dict(os.environ, {"CHATBOT_URL": "http://ai:8001", "LMS_AI_SHARED_TOKEN": ""}), \
             patch("lms.api.urllib.request.urlopen") as urlopen:
            response = chat(request, ChatIn(message="hello"))
        self.assertEqual(response.status_code, 503)
        urlopen.assert_not_called()

    def test_internal_token_is_sent_in_header_not_body(self):
        request = Mock(auth={"role": "student", "firebase_uid": "student-a"})
        with patch.dict(os.environ, {"CHATBOT_URL": "http://ai:8001", "LMS_AI_SHARED_TOKEN": "private-test-token"}), \
             patch("lms.api.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.read.return_value = b'{"answer":"ok"}'
            response = chat(request, ChatIn(message="hello"))
            sent = urlopen.call_args.args[0]
        self.assertEqual(response["answer"], "ok")
        self.assertEqual(sent.get_header("X-lms-ai-token"), "private-test-token")
        self.assertNotIn(b"private-test-token", sent.data)


class ResumeWriteValidationTests(SimpleTestCase):
    def setUp(self):
        self.actor = {"id": 1, "role": "student", "cohort_id": 34}

    def test_cannot_edit_another_users_resume(self):
        with self.assertRaises(PermissionError):
            _validate_resume_write(Mock(), self.actor, {"title": "changed"}, {"id": 5, "user_id": 2, "cohort_id": 34, "base_resume_id": None, "is_base_resume": True})

    @patch("lms.commands.resolve_row")
    def test_parent_must_be_own_base_resume(self, resolve):
        resolve.return_value = {"id": 7, "user_id": 2, "is_base_resume": True}
        with self.assertRaises(ValueError):
            _validate_resume_write(Mock(), self.actor, {"base_resume_id": 7}, None)

    def test_linked_job_must_exist(self):
        cur = Mock()
        cur.fetchone.return_value = None
        with self.assertRaises(ValueError):
            _validate_resume_write(cur, self.actor, {"linked_job_id": "missing"}, None)

    @patch("lms.commands.resolve_row")
    def test_own_base_resume_is_accepted(self, resolve):
        resolve.return_value = {"id": 7, "user_id": 1, "is_base_resume": True}
        data = {"base_resume_id": 7}
        _validate_resume_write(Mock(), self.actor, data, None)
        self.assertEqual(data["user_id"], 1)
        self.assertEqual(data["base_resume_id"], 7)


class UpsertRoleTests(SimpleTestCase):
    def test_student_cannot_mutate_administrative_tables(self):
        student = {"id": 1, "role": "student"}
        for table in ("cohorts", "mileage_products", "assessments", "cohort_seating"):
            with self.subTest(table=table), self.assertRaises(PermissionError):
                op_upsert_sql(Mock(), student, {"table": table, "action": "insert"})

    def test_instructor_cannot_mutate_cohorts(self):
        with self.assertRaises(PermissionError):
            op_upsert_sql(Mock(), {"id": 2, "role": "instructor"}, {"table": "cohorts", "action": "insert"})

    def test_student_cannot_write_unvalidated_scores_or_purchase_state(self):
        student = {"id": 1, "role": "student"}
        for table in (
            "assessment_submissions", "submission_responses", "purchase_requests",
            "mileage_cart_items", "mission_progress", "recommendation_events",
        ):
            with self.subTest(table=table), self.assertRaises(PermissionError):
                op_upsert_sql(Mock(), student, {"table": table, "action": "insert", "userId": 2})


class RecordSubmissionValidationTests(SimpleTestCase):
    def setUp(self):
        self.actor = {"id": 1, "role": "student", "cohort_id": 34, "is_active": True}

    def test_student_cannot_edit_another_users_submission(self):
        with self.assertRaises(PermissionError):
            _validate_record_submission_write(
                self.actor, {"title": "changed"}, {"user_id": 2, "cohort_id": 34}
            )

    def test_student_cannot_set_review_status(self):
        with self.assertRaises(PermissionError):
            _validate_record_submission_write(self.actor, {"status": "approved"}, None)

    def test_student_cannot_forge_review_comment(self):
        with self.assertRaises(PermissionError):
            _validate_record_submission_write(self.actor, {"review_comment": "approved"}, None)

    def test_student_insert_uses_own_identity(self):
        data = {"status": "submitted"}
        _validate_record_submission_write(self.actor, data, None)
        self.assertEqual(data["user_id"], 1)
        self.assertEqual(data["cohort_id"], 34)


class TodoAuthorizationTests(SimpleTestCase):
    def setUp(self):
        self.actor = {"id": 1, "role": "student", "firebase_uid": "student-a"}

    @patch("lms.commands.resolve_user")
    def test_student_cannot_add_todo_for_another_user(self, resolve):
        with self.assertRaises(PermissionError):
            op_add_todo(Mock(), self.actor, {"uid": "student-b", "title": "wrong"})
        resolve.assert_not_called()

    @patch("lms.commands.resolve_row", return_value={"id": 3, "user_id": 2})
    def test_student_cannot_toggle_another_users_todo(self, _resolve):
        cur = Mock()
        with self.assertRaises(PermissionError):
            op_toggle_todo(cur, self.actor, {"todoId": "3"})
        cur.execute.assert_not_called()

    @patch("lms.commands.resolve_row", return_value={"id": 3, "user_id": 2})
    def test_student_cannot_delete_another_users_todo(self, _resolve):
        cur = Mock()
        with self.assertRaises(PermissionError):
            op_delete_todo(cur, self.actor, {"todoId": "3"})
        cur.execute.assert_not_called()

    @patch("lms.commands.resolve_row", return_value={"id": 3, "user_id": 1})
    def test_student_can_toggle_own_todo(self, _resolve):
        cur = Mock()
        op_toggle_todo(cur, self.actor, {"todoId": "3"})
        cur.execute.assert_called_once()


class BootstrapJsonTests(SimpleTestCase):
    def test_jsonb_is_an_object_not_a_json_string(self):
        cur = Mock()
        column = namedtuple("Column", "name type_code")
        cur.description = [column("content", 3802), column("title", 1043)]
        cur.fetchall.return_value = [('{"section_status":{"intro":true}}', "Resume")]
        rows = _dicts(cur)
        self.assertEqual(rows[0]["content"]["section_status"], {"intro": True})
        self.assertEqual(rows[0]["title"], "Resume")
