"""공부방 노트 — 같은 기수가 나눠 보고, 수업 파일이 바뀌면 다시 만들고, 자동 출제 날짜엔 미리 넣어 둔다.

AI 서버는 부르지 않는다(`_call`을 바꿔 끼운다). DB 는 실제로 쓴다 — 나눠 주기는 SQL 이 전부라서다.
로컬 DB 로 돌린다: `DB_HOST= python manage.py test lms.test_study_note_sharing`
"""

from __future__ import annotations

import json
from unittest import mock

from django.db import connection
from django.test import TestCase

from lms import study_note_service as notes

DATE = "2026-09-11"
FILES_V1 = [{"path": "01_cnn/a.py", "commit": "c1", "blob": "blob-a1"}]
FILES_V2 = [{"path": "01_cnn/a.py", "commit": "c2", "blob": "blob-a2"}]


class FakeAi:
    """/proxy/resolve 와 /proxy/generate. 무엇을 몇 번 불렀는지 남긴다."""

    def __init__(self) -> None:
        self.files = FILES_V1
        self.resolve_status = "ready"
        self.resolve_fails = False
        self.calls: list[str] = []
        self.dates = [DATE]
        self.subject_days: list[str] = []
        self.subject_files = True
        self.previous: list[list[str]] = []  # /proxy/generate 마다 넘긴 이전 노트 날짜

    def __call__(self, path: str, payload: dict, timeout: int) -> dict:
        self.calls.append(path)
        if path == "/proxy/tree":
            return {"dates": self.dates, "entries": []}
        if path == "/proxy/subject-files":
            # 과목 요약은 수업 파일을 직접 읽는다 — 날짜 노트를 모으지 않는다
            if not self.subject_files:
                return {"status": "empty", "message": "아직 수업 파일이 올라오지 않은 저장소예요."}
            self.subject_days = list(self.dates)
            return {"status": "ready", "dates": list(self.dates), "files": [{"path": "01_cnn/a.py", "commit": "h1"}],
                    "reportMarkdown": "## 과목 한눈에 보기\n과목 요약 " + ",".join(self.dates) + "\n## 주제별 핵심 정리\n### 01_cnn"}
        if path == "/proxy/resolve":
            if self.resolve_fails:
                raise notes.StudyNoteError(503, "연결 실패")
            if self.resolve_status == "too_broad":
                return {"status": "too_broad", "message": "파일을 선택하세요.", "files": [{"path": "x.py", "commit": "c1"}]}
            return {"status": "ready", "files": self.files}
        if path == "/proxy/generate":
            self.previous.append([p["date"] for p in payload.get("previous", [])])
            day = payload.get("scopeValue")
            return {"status": "ready", "files": self.files, "reportMarkdown": f"노트 {day} {self.files[0]['blob']}",
                    "reviewMarkdown": ""}
        raise AssertionError(path)

    def generated(self) -> int:
        return self.calls.count("/proxy/generate")


_EMPTY = {"boolean": False, "jsonb": "{}", "ARRAY": "{}", "integer": 0, "bigint": 0, "smallint": 0}


def _insert(cur, table: str, values: dict) -> int:
    """행 하나. 테스트 DB 는 migration 으로 만들어 DB 기본값이 없으므로, 채우지 않은 필수 칸은 빈 값으로."""
    cur.execute(
        """SELECT column_name, data_type FROM information_schema.columns
           WHERE table_schema = 'public' AND table_name = %s AND is_nullable = 'NO' AND column_default IS NULL
             AND is_identity = 'NO' AND column_name <> 'id'""",
        [table],
    )
    row = dict(values)
    for column, data_type in cur.fetchall():
        row.setdefault(column, _EMPTY.get(data_type, ""))
    cols = ", ".join(row)
    marks = ", ".join(["%s"] * len(row))
    cur.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks}) RETURNING id", list(row.values()))
    return cur.fetchone()[0]


class SharingTestCase(TestCase):
    def setUp(self) -> None:
        with connection.cursor() as cur:
            cur.execute("INSERT INTO cohorts (code, name, status, is_active) VALUES ('t34', '34기', 'active', true) RETURNING id")
            self.cohort = cur.fetchone()[0]
            self.users = []
            for name in ("가", "나", "다"):
                uid = _insert(cur, "users", {"display_name": name, "role": "student", "is_active": True,
                                             "cohort_id": self.cohort})
                self.users.append({"id": uid, "role": "student", "is_active": True, "cohort_id": self.cohort})
            # allowed_prefixes 는 운영 DB 에선 text[], migration 으로 만든 테스트 DB 에선 jsonb 다. 여기선 안 쓴다
            self.source_id = _insert(cur, "study_sources", {
                "cohort_id": self.cohort, "title": "멀티모달", "repo_url": "https://github.com/skn34/multimodal",
                "branch": "main", "is_active": True,
            })
        self.ai = FakeAi()
        self.spawned: list = []
        patches = [
            mock.patch.object(notes, "_call", self.ai),
            mock.patch.object(notes, "_spawn", self.spawned.append),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def open(self, who: int, date: str = DATE) -> dict:
        with self.captureOnCommitCallbacks(execute=True):
            out = notes.start_note(self.users[who], str(self.source_id), "date", date)
        # 뒤에서 도는 작업은 스레드용이라 끝에 DB 연결을 닫는다. 테스트는 같은 연결로 돌리므로 닫지 않게 한다
        with mock.patch.object(connection, "close"):
            for work in self.spawned:
                work()
        self.spawned.clear()
        return out

    def row(self, who: int) -> dict:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM study_notes WHERE user_id = %s ORDER BY id DESC LIMIT 1", [self.users[who]["id"]])
            return notes._one(cur)


class PreviousLessonTests(SharingTestCase):
    def test_earlier_day_notes_are_passed_newest_three(self) -> None:
        for day in ("2026-09-08", "2026-09-09", "2026-09-10", DATE):
            self.open(0, day)
        self.assertEqual([], self.ai.previous[0], "첫 수업은 이전 노트가 없다")
        self.assertEqual(["2026-09-10", "2026-09-09", "2026-09-08"], self.ai.previous[-1])

    def test_later_days_are_not_previous(self) -> None:
        self.open(0, DATE)
        self.open(1, "2026-09-01")
        self.assertEqual([], self.ai.previous[-1])


class ShareWithinCohortTests(SharingTestCase):
    def test_first_student_generates_once_and_others_get_a_copy(self) -> None:
        first = self.open(0)
        self.assertEqual("generating", first["status"])
        self.assertEqual("ready", self.row(0)["status"])
        self.assertEqual(1, self.ai.generated())

        second = self.open(1)
        self.assertEqual("ready", second["status"], "기다리지 않고 바로 받는다")
        self.assertEqual("노트 2026-09-11 blob-a1", second["reportMarkdown"])
        self.assertEqual("", second["reviewMarkdown"])
        self.assertEqual(1, self.ai.generated(), "LLM 은 한 번")

    def test_own_note_is_remade_when_lesson_file_changed(self) -> None:
        self.open(0)
        self.ai.files = FILES_V2
        again = self.open(0)
        self.assertEqual("generating", again["status"])
        self.assertEqual("노트 2026-09-11 blob-a2", self.row(0)["report_markdown"])
        self.assertEqual(2, self.ai.generated())

    def test_unchanged_own_note_is_returned_without_llm(self) -> None:
        self.open(0)
        again = self.open(0)
        self.assertEqual("ready", again["status"])
        self.assertEqual(1, self.ai.generated())

    def test_classmate_note_from_old_files_is_not_shared(self) -> None:
        self.open(0)
        self.ai.files = FILES_V2
        second = self.open(1)
        self.assertEqual("generating", second["status"])
        self.assertEqual("노트 2026-09-11 blob-a2", self.row(1)["report_markdown"])

    def test_when_resolve_fails_it_behaves_as_before(self) -> None:
        self.open(0)
        self.ai.resolve_fails = True
        self.assertEqual("ready", self.open(0)["status"], "내 노트는 그대로 준다")
        self.assertEqual("generating", self.open(1)["status"], "나눠 줄 수 없으면 새로 만든다")

    def test_too_broad_is_answered_without_generating(self) -> None:
        self.ai.resolve_status = "too_broad"
        out = self.open(0)
        self.assertEqual("too_broad", out["status"])
        self.assertEqual([{"path": "x.py", "commit": "c1"}], out["files"])
        self.assertEqual(0, self.ai.generated())


class PublishLessonNotesTests(SharingTestCase):
    def source(self) -> dict:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT s.*, c.code AS cohort_code FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id WHERE s.id = %s",
                [self.source_id],
            )
            return notes._one(cur)

    def test_every_student_gets_the_day_note_generated_once(self) -> None:
        out = notes.publish_lesson_notes(self.source(), [DATE])
        self.assertEqual([DATE], out["notes"])
        self.assertEqual(3, out["students"])
        self.assertEqual(1, self.ai.generated())
        for who in range(3):
            row = self.row(who)
            self.assertEqual("ready", row["status"])
            self.assertEqual(DATE, row["scope_key"])
            self.assertEqual(FILES_V1, json.loads(row["files"]) if isinstance(row["files"], str) else row["files"])

        # 다음 날 다시 돌아도 같은 자료면 만들지도 · 덮지도 않는다
        notes.publish_lesson_notes(self.source(), [DATE])
        self.assertEqual(1, self.ai.generated())
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM study_notes")
            self.assertEqual(3, cur.fetchone()[0])

    def test_student_opening_after_publish_gets_it_instantly(self) -> None:
        notes.publish_lesson_notes(self.source(), [DATE])
        self.assertEqual("ready", self.open(2)["status"])
        self.assertEqual(1, self.ai.generated())

    def test_too_broad_day_is_skipped(self) -> None:
        self.ai.resolve_status = "too_broad"
        out = notes.publish_lesson_notes(self.source(), [DATE])
        self.assertEqual([], out["notes"])
        self.assertEqual([DATE], out["skipped"])
        self.assertEqual(0, self.ai.generated())


class SubjectSummaryTests(SharingTestCase):
    def setUp(self) -> None:
        super().setUp()
        # 끝난 과목이라고 본다 — 진행 중인 과목을 막는 것은 test_subject_finished 가 본다
        finished = mock.patch.object(notes, "subject_finished", return_value=True)
        finished.start()
        self.addCleanup(finished.stop)

    def open_subject(self, who: int) -> dict:
        with self.captureOnCommitCallbacks(execute=True):
            out = notes.start_note(self.users[who], str(self.source_id), "subject", "all")
        with mock.patch.object(connection, "close"):
            for work in self.spawned:
                work()
        self.spawned.clear()
        return out

    def subject_row(self, who: int) -> dict:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM study_notes WHERE user_id = %s AND scope_key = 'subject'", [self.users[who]["id"]])
            return notes._one(cur)

    def test_summary_reads_lesson_files_without_day_notes(self) -> None:
        self.ai.dates = [DATE, "2026-09-12"]
        out = self.open_subject(1)
        self.assertEqual("generating", out["status"])
        row = self.subject_row(1)
        self.assertEqual("ready", row["status"])
        self.assertIn("/proxy/subject-files", self.ai.calls)
        self.assertNotIn("/proxy/generate", self.ai.calls, "날짜 노트를 만들지 않는다")
        self.assertEqual([DATE, "2026-09-12"], notes._subject_dates(row))
        self.assertIn(notes.SUBJECT_FORMAT_MARK, row["report_markdown"])

    def test_classmate_gets_the_summary_instantly_until_a_new_lesson_day(self) -> None:
        self.open_subject(0)
        calls = len(self.ai.calls)
        copied = self.open_subject(1)
        self.assertEqual("ready", copied["status"])
        self.assertTrue(copied["reportMarkdown"].startswith("## 과목 한눈에 보기"))
        self.assertEqual(["/proxy/tree"], self.ai.calls[calls:], "날짜만 확인하고 LLM 은 안 부른다")

        self.ai.dates = [DATE, "2026-09-12"]
        self.assertEqual("generating", self.open_subject(1)["status"], "수업 날짜가 늘면 다시 만든다")

    def test_old_format_summary_is_made_again(self) -> None:
        # 예전 방식(날짜 노트를 모아 다시 요약) 요약 — 수업 날짜가 같아도 새 형식으로 다시 만든다
        with connection.cursor() as cur:
            notes._put(cur, None, self.users[0]["id"], self.source_id, "subject", [DATE], "subject", status="ready",
                       message="", report="## 과목 한눈에 보기\n예전 요약\n## 핵심 개념 정리\n…", review="", files=[])
        self.assertEqual("generating", self.open_subject(0)["status"])
        self.assertIn(notes.SUBJECT_FORMAT_MARK, self.subject_row(0)["report_markdown"])

    def test_repo_without_lesson_files_says_so(self) -> None:
        self.ai.dates = []
        self.ai.subject_files = False
        self.open_subject(0)
        row = self.subject_row(0)
        self.assertEqual("failed", row["status"])
        self.assertIn("수업 파일", row["error_message"])

    def test_finished_subject_is_published_to_every_student_once(self) -> None:
        source = {**self.source_row(), "cohort_code": "t34"}
        self.assertEqual("made", notes.publish_subject_note(source))
        for i in range(3):
            self.assertIn(notes.SUBJECT_FORMAT_MARK, self.subject_row(i)["report_markdown"])
        calls = self.ai.calls.count("/proxy/subject-files")
        self.assertEqual("copied", notes.publish_subject_note(source), "두 번째는 LLM 없이")
        self.assertEqual(calls, self.ai.calls.count("/proxy/subject-files"))

    def test_running_subject_is_not_published(self) -> None:
        source = {**self.source_row(), "cohort_code": "t34"}
        with mock.patch.object(notes, "subject_finished", return_value=False):
            self.assertEqual("running", notes.publish_subject_note(source))
        self.assertNotIn("/proxy/subject-files", self.ai.calls)

    def source_row(self) -> dict:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM study_sources WHERE id = %s", [self.source_id])
            return notes._one(cur)


class AllowedPrefixesTests(TestCase):
    """허용 폴더 — jsonb '[]' 를 「[]」라는 폴더로 읽으면 저장소가 통째로 비어 보인다."""

    def test_every_stored_shape(self) -> None:
        cases = [
            ("[]", []), ("{}", []), ('["01_cnn", "02_rag"]', ["01_cnn", "02_rag"]),
            ("{01_cnn,02_rag}", ["01_cnn", "02_rag"]), (["01_cnn"], ["01_cnn"]), ({}, []), (None, []),
        ]
        for raw, expected in cases:
            self.assertEqual(expected, notes._prefixes(raw), raw)
