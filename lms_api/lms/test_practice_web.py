"""웹 실습(web_task) — DB 에는 code_write + ["web"] 로 적고, 화면에는 검사문을 보내지 않고, 채점은 DB 의 검사문으로.

DB 없이 돈다: `DB_HOST= python manage.py test lms.test_practice_web`
"""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from lms import practice_web
from lms.practice_service import _problem_json, _stored, stored_kind
from lms.study_source_service import StudySourceError

WEB = {"kind": "web_task", "topic": "flex", "prompt": "가로로", "starterCode": "<ul></ul>", "referenceSolution": "<ul></ul>",
       "hiddenTests": "check(has('ul'), '목록');"}


def db_row(problem: dict) -> dict:
    return {"kind": problem["kind"], "topic": "", "prompt": "", "source_files": "[]", "explanation": "", "choices": "[]",
            "answer_index": None, "starter_code": problem.get("starterCode", ""), "expected_stdout": "", "blank_answers": "[]",
            "reference_solution": "", "hidden_tests": problem.get("hiddenTests", ""), "packages": '["web"]' if problem.get("packages") == ["web"] else "[]"}


class StorageTests(SimpleTestCase):
    def test_web_task_is_stored_as_code_write_and_comes_back(self) -> None:
        stored = _stored(WEB)
        self.assertEqual((stored["kind"], stored["packages"]), ("code_write", ["web"]))
        self.assertEqual(stored["hiddenTests"], WEB["hiddenTests"], "검사문은 DB 에 남는다")
        back = _problem_json(db_row(stored))
        self.assertEqual(back["kind"], "web_task")
        self.assertEqual(back["hiddenTests"], "", "화면에는 검사문을 보내지 않는다")

    def test_plain_code_write_stays(self) -> None:
        self.assertEqual(stored_kind({"kind": "code_write", "packages": "[]"}), "code_write")


class GradeTests(SimpleTestCase):
    def grade(self, row: dict | None, **kw):
        cursor = mock.MagicMock()
        with mock.patch.object(practice_web, "connection") as conn, \
                mock.patch.object(practice_web, "_problem_id", return_value=7), \
                mock.patch.object(practice_web, "_one", return_value=row), \
                mock.patch.object(practice_web, "_call", return_value={"passed": True, "checks": [], "error": ""}) as call:
            conn.cursor.return_value.__enter__.return_value = cursor
            out = practice_web.grade({"id": 1, "role": "student"}, "ps-1", 0, kw.get("html", "<ul></ul>"))
        return out, call

    def test_checks_come_from_db_not_the_browser(self) -> None:
        out, call = self.grade({"kind": "code_write", "packages": '["web"]', "hidden_tests": "check(has('ul'), '목록');"})
        self.assertTrue(out["passed"])
        self.assertEqual(call.call_args.args[1], {"html": "<ul></ul>", "checks": "check(has('ul'), '목록');"})

    def test_other_kinds_are_refused(self) -> None:
        with self.assertRaises(StudySourceError) as caught:
            self.grade({"kind": "code_write", "packages": "[]", "hidden_tests": "assert True"})
        self.assertEqual(caught.exception.status, 422)

    def test_too_long_html_is_refused(self) -> None:
        with self.assertRaises(StudySourceError) as caught:
            practice_web.grade({"id": 1}, "ps-1", 0, "x" * (practice_web.MAX_HTML_CHARS + 1))
        self.assertEqual(caught.exception.status, 413)
