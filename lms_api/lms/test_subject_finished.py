"""과목 전체 요약은 끝난 과목만 — 다음 과목이 시작했거나 수료일이 지났을 때(화면 lessonDays.subjectFinished 와 같은 규칙)."""

from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from lms import study_note_service
from lms.study_note_service import StudyNoteError, subject_finished

SOURCE = {"id": 12, "cohort_id": 1, "repo_url": "https://github.com/skn-ai34-260616/web_client.git", "is_active": True}


class FakeCursor:
    """subject_finished 가 묻는 차례대로 답한다 — 마지막 수업일 · 수료일 · 뒤에 시작한 다른 과목"""

    def __init__(self, last, end, later):
        self.answers = [(last,), (end,) if end is not None else None, (1,) if later else None]
        self.sql: list[tuple[str, list]] = []

    def execute(self, sql, params):
        self.sql.append((sql, params))

    def fetchone(self):
        return self.answers[len(self.sql) - 1]


class SubjectFinishedTests(SimpleTestCase):
    def test_next_subject_started_after_last_lesson(self):
        cur = FakeCursor("2026-09-29", date(2026, 12, 7), later=True)
        self.assertTrue(subject_finished(cur, SOURCE))
        # 세트의 과목 이름은 저장소 이름 소문자, 다른 과목은 첫 수업일로 견준다
        self.assertEqual(cur.sql[0][1], [1, "web_client"])
        self.assertIn("HAVING min(lesson_date) >", cur.sql[2][0])
        self.assertEqual(cur.sql[2][1], [1, "web_client", "2026-09-29"])

    def test_running_subject_is_not_finished(self):
        self.assertFalse(subject_finished(FakeCursor("2026-09-30", date(2026, 12, 7), later=False), SOURCE))

    def test_repo_dates_count_as_lessons_too(self):
        # 세트가 없어도 저장소에 수업 날짜가 있으면 그 마지막 날로 본다
        cur = FakeCursor(None, None, later=True)
        self.assertTrue(subject_finished(cur, SOURCE, ["2026-09-23", "2026-09-29"]))
        self.assertEqual(cur.sql[-1][1][-1], "2026-09-29")

    def test_cohort_end_passed_finishes_the_last_subject(self):
        with mock.patch.object(study_note_service.timezone, "localdate", return_value=date(2026, 12, 8)):
            self.assertTrue(subject_finished(FakeCursor("2026-12-01", date(2026, 12, 7), later=False), SOURCE))

    def test_no_lessons_is_not_finished(self):
        self.assertFalse(subject_finished(FakeCursor(None, None, later=True), SOURCE))

    def test_start_subject_note_refuses_running_subject(self):
        with mock.patch.object(study_note_service, "_load_source", return_value={**SOURCE, "cohort_code": "cohort_34"}), \
             mock.patch.object(study_note_service, "_lesson_dates", return_value=["2026-09-30"]), \
             mock.patch.object(study_note_service, "subject_finished", return_value=False), \
             mock.patch.object(study_note_service, "connection"):
            with self.assertRaises(StudyNoteError) as ctx:
                study_note_service.start_subject_note({"id": 1, "role": "student"}, "12")
        self.assertEqual(ctx.exception.status, 409)
