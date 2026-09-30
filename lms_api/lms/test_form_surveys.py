from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from lms import form_surveys as fs

QUESTIONS = [
    {"id": "name", "type": "short", "title": "이름", "required": True},
    {"id": "track", "type": "single", "title": "관심 분야", "required": True, "options": ["AI", "웹"]},
    {"id": "tools", "type": "multi", "title": "써 본 도구", "required": False, "options": ["git", "docker", "k8s"]},
    {"id": "score", "type": "scale", "title": "만족도", "required": False, "scaleMax": 5},
    {"id": "day", "type": "date", "title": "면담 희망일", "required": False},
]


class CleanQuestionsTests(SimpleTestCase):
    def test_trims_dedupes_options_and_fills_missing_id(self):
        out = fs.clean_questions([
            {"type": "single", "title": "  분야 ", "options": ["AI", " AI ", "", "웹"], "required": 1},
        ])
        self.assertEqual(out[0]["title"], "분야")
        self.assertEqual(out[0]["options"], ["AI", "웹"])
        self.assertTrue(out[0]["required"])
        self.assertRegex(out[0]["id"], r"^[0-9a-f]{8}$")

    def test_choice_needs_two_options(self):
        with self.assertRaisesMessage(ValueError, "1번 질문에 보기를 두 개 이상"):
            fs.clean_questions([{"type": "multi", "title": "도구", "options": ["git"]}])

    def test_rejects_unknown_type_and_empty_title(self):
        with self.assertRaises(ValueError):
            fs.clean_questions([{"type": "file", "title": "파일"}])
        with self.assertRaisesMessage(ValueError, "2번 질문 내용"):
            fs.clean_questions([{"type": "short", "title": "a"}, {"type": "long", "title": " "}])

    def test_duplicate_ids_are_replaced_and_scale_is_clamped(self):
        out = fs.clean_questions([
            {"id": "q", "type": "short", "title": "a"},
            {"id": "q", "type": "scale", "title": "b", "scaleMax": 99},
        ])
        self.assertNotEqual(out[0]["id"], out[1]["id"])
        self.assertEqual(out[1]["scaleMax"], 10)


class ValidateAnswersTests(SimpleTestCase):
    def test_keeps_valid_answers_and_drops_unknown_keys(self):
        out = fs.validate_answers(QUESTIONS, {
            "name": " 홍길동 ", "track": "AI", "tools": ["docker", "git"], "score": "4",
            "day": "2026-10-02", "hack": "x",
        })
        self.assertEqual(out, {"name": "홍길동", "track": "AI", "tools": ["git", "docker"], "score": 4, "day": "2026-10-02"})

    def test_required_missing(self):
        with self.assertRaisesMessage(ValueError, "「관심 분야」에 답해 주세요."):
            fs.validate_answers(QUESTIONS, {"name": "a"})

    def test_rejects_values_outside_the_question(self):
        base = {"name": "a", "track": "AI"}
        for bad in ({"track": "게임"}, {"tools": ["svn"]}, {"score": 6}, {"day": "2026-13-01"}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fs.validate_answers(QUESTIONS, {**base, **bad})

    def test_optional_empty_answers_are_skipped(self):
        out = fs.validate_answers(QUESTIONS, {"name": "a", "track": "웹", "tools": [], "day": ""})
        self.assertEqual(out, {"name": "a", "track": "웹"})


class _Cursor:
    def __init__(self):
        self.sql = []

    def execute(self, sql, args=None):
        self.sql.append((sql, args))

    def fetchall(self):
        return [(1,)]


def _task(**kw):
    task = {
        "id": 7, "legacy_id": None, "submission_type": "builtin", "published": True,
        "due_at": datetime.now(timezone.utc) + timedelta(days=1), "questions": QUESTIONS,
    }
    task.update(kw)
    return task


STUDENT = {"id": 3, "role": "student", "cohort_id": 1}


class SubmitResponseTests(SimpleTestCase):
    def _submit(self, task, answers, user=STUDENT):
        cur = _Cursor()
        with mock.patch("lms.commands.resolve_row", return_value=task), \
             mock.patch("lms.commands.can_access_cohort", return_value=True):
            result = fs.op_submit_form_response(cur, user, {"taskId": "7", "answers": answers})
        return cur, result

    def test_saves_cleaned_answers(self):
        cur, result = self._submit(_task(), {"name": "a", "track": "AI"})
        self.assertEqual(result["answers"], {"name": "a", "track": "AI"})
        sql, args = cur.sql[-1]
        self.assertIn("INSERT INTO submission_responses", sql)
        self.assertEqual(args[:2], [7, 3])

    def test_blocks_after_due_and_external_forms(self):
        with self.assertRaisesMessage(ValueError, "마감이 지나"):
            self._submit(_task(due_at=datetime.now(timezone.utc) - timedelta(minutes=1)), {"name": "a", "track": "AI"})
        with self.assertRaisesMessage(ValueError, "외부 폼"):
            self._submit(_task(submission_type="external_form"), {})

    def test_questions_stored_as_json_text_are_read(self):
        import json

        _, result = self._submit(_task(questions=json.dumps(QUESTIONS)), {"name": "a", "track": "웹"})
        self.assertEqual(result["answers"]["track"], "웹")

    def test_staff_cannot_submit(self):
        with self.assertRaises(PermissionError):
            self._submit(_task(), {}, user={"id": 1, "role": "admin"})
