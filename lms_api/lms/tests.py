"""Small API-contract checks that do not require a database connection."""

from collections import namedtuple

from django.test import SimpleTestCase
from unittest.mock import Mock, patch

from lms.api import _data, api
from lms.bootstrap_service import _dicts
from lms.commands import _validate_record_submission_write, _validate_resume_write, op_upsert_sql


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

    def test_student_insert_uses_own_identity(self):
        data = {"status": "submitted"}
        _validate_record_submission_write(self.actor, data, None)
        self.assertEqual(data["user_id"], 1)
        self.assertEqual(data["cohort_id"], 34)


class BootstrapJsonTests(SimpleTestCase):
    def test_jsonb_is_an_object_not_a_json_string(self):
        cur = Mock()
        column = namedtuple("Column", "name type_code")
        cur.description = [column("content", 3802), column("title", 1043)]
        cur.fetchall.return_value = [('{"section_status":{"intro":true}}', "Resume")]
        rows = _dicts(cur)
        self.assertEqual(rows[0]["content"]["section_status"], {"intro": True})
        self.assertEqual(rows[0]["title"], "Resume")
