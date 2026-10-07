"""폴더 올리기(GitHub 없이) — 권한 · 기수 달력 · 과목 만들기 · S3 보관 · 보관본으로 되살리기.

AI 서버는 부르지 않는다(_post 를 바꿔 끼운다). DB 는 실제로 쓴다(과목 행 · 권한).
로컬 DB 로 돌린다: `DB_HOST= python manage.py test lms.test_folder_upload`
"""

from __future__ import annotations

import base64
import json
from datetime import date
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import SimpleTestCase, TestCase

from lms import folder_upload, study_note_service
from lms.study_source_service import StudySourceError
from lms.test_study_note_sharing import _insert


class FakeAi:
    """/proxy/upload/* — 무엇을 보냈는지 남긴다. head 가 None 이면 서버 안 저장소가 없는 것"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.head: str | None = None  # 서버 안 저장소 — None 이면 없다
        self.fail_commit = False
        self.restore_fails = False

    def __call__(self, path: str, payload: dict, timeout: int) -> dict:
        self.calls.append((path, payload))
        if path == "/proxy/upload/head":
            return {"head": self.head}
        if path == "/proxy/upload/restore":
            if self.restore_fails:
                raise study_note_service.StudyNoteError(422, "보관본으로 되살리지 못했어요")
            self.head = "restored"
            return {"head": "restored"}
        if path == "/proxy/upload/plan":
            return {"what": "subject", "subjects": []}
        if path == "/proxy/upload/commit":
            if self.fail_commit:
                raise study_note_service.StudyNoteError(400, "올리지 못했어요")
            if self.head is None and not payload.get("create"):
                raise study_note_service.StudyNoteError(409, "서버 안 저장소가 없어요")
            self.head = "s1"
            return {"commits": [{"date": d["date"], "sha": "s1", "changed": [f["path"] for f in d["files"]], "skipped": []}
                                for d in payload["days"]],
                    "head": "s1", "bundle": base64.b64encode(b"BUNDLE").decode()}
        if path == "/proxy/upload/schedule":
            return {"issues": [{"kind": "schedule_drift", "subject": "python_basic"}], "topics": []}
        raise AssertionError(path)

    def paths(self) -> list[str]:
        return [p for p, _ in self.calls]


class UploadTestCase(TestCase):
    def setUp(self) -> None:
        with connection.cursor() as cur:
            cur.execute(
                """INSERT INTO cohorts (code, name, status, is_active, start_date, end_date)
                   VALUES ('t34', '34기', 'active', true, '2026-06-15', '2026-12-07') RETURNING id"""
            )
            self.cohort = cur.fetchone()[0]
            self.github = _insert(cur, "study_sources", {
                "cohort_id": self.cohort, "title": "웹 클라이언트", "repo_url": "https://github.com/skn34/web_client",
                "branch": "main", "is_active": True,
            })
        self.instructor = {"id": 1, "role": "instructor", "cohort_code": "t34"}
        self.ai = FakeAi()
        self.saved: dict[str, bytes] = {}
        patches = [
            mock.patch.object(folder_upload, "_post", self.ai),
            mock.patch.object(folder_upload.storage, "put_object", lambda k, d, _t: self.saved.__setitem__(k, d)),
            mock.patch.object(folder_upload.storage, "get_object", lambda k: self.saved.get(k)),
            mock.patch.object(folder_upload, "holidays_of", lambda y: {f"{y}-10-09": "한글날"}),
            mock.patch.object(folder_upload, "_curriculum_rows", lambda cur, cid: [
                {"date_label": "2026년 6월 16일 화요일", "subject": "기초", "topic": "Python", "detail": ""},
                {"date_label": "6/17 수", "subject": "기초", "topic": "Python", "detail": ""},
                {"date_label": "", "subject": "", "topic": "", "detail": ""},
            ]),
            mock.patch.object(folder_upload.timezone, "localdate", return_value=date(2026, 10, 1)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        folder_upload._checked.clear()

    def commit(self, files: dict[str, bytes], *, days=None, past=None, name="python_basic", source=""):
        uploads = [SimpleUploadedFile(f"f{i}", body) for i, body in enumerate(files.values())]
        manifest = json.dumps({"paths": list(files), "days": days or [], "past": past or []})
        return folder_upload.commit(self.instructor, cohort_code="t34", source_key=source, name=name,
                                    manifest=manifest, files=uploads)


class PlanTests(UploadTestCase):
    def test_calendar_and_sources_go_with_the_plan(self) -> None:
        folder_upload.plan(self.instructor, {"cohortId": "t34", "mode": "import", "files": [{"path": "a/b.py"}],
                                             "extraDays": ["2026-10-09", "bad"]})
        path, payload = self.ai.calls[-1]
        self.assertEqual("/proxy/upload/plan", path)
        cal = payload["calendar"]
        self.assertEqual(("2026-06-15", "2026-12-07", "2026-10-01"), (cal["start"], cal["end"], cal["today"]))
        self.assertEqual("한글날", cal["holidays"]["2026-10-09"])
        # 날짜를 읽은 줄만 — 못 읽은 줄은 수만 센다(빈 줄은 세지 않는다)
        self.assertEqual([{"date": "2026-06-16", "topic": "Python", "unit": "기초"}], cal["curriculum"])
        self.assertEqual(1, cal["unreadable"])
        self.assertEqual(["2026-10-09"], cal["extraDays"])
        # GitHub 과목은 화면 제목이 아니라 저장소 이름으로 견준다
        self.assertEqual([("web_client", "github")], [(s["title"], s["kind"]) for s in payload["sources"]])

    def test_only_staff_of_the_cohort(self) -> None:
        for user in ({"id": 2, "role": "student", "cohort_code": "t34"}, {"id": 3, "role": "instructor", "cohort_code": "t35"}):
            with self.assertRaises(StudySourceError) as ctx:
                folder_upload.plan(user, {"cohortId": "t34", "mode": "import", "files": [{"path": "a.py"}]})
            self.assertEqual(403, ctx.exception.status)

    def test_daily_needs_an_uploaded_subject(self) -> None:
        with self.assertRaises(StudySourceError) as ctx:
            folder_upload.plan(self.instructor, {"cohortId": "t34", "mode": "daily", "target": str(self.github),
                                                 "files": [{"path": "a.py"}]})
        self.assertEqual(404, ctx.exception.status)


class CommitTests(UploadTestCase):
    def test_new_subject_is_created_committed_and_backed_up(self) -> None:
        out = self.commit({"01_variable/a.py": b"x = 1", "04_function/f.py": b"def f(): pass"},
                          days=[{"date": "2026-06-18", "files": [0]}], past=[1])
        self.assertTrue(out["source"]["created"])
        self.assertEqual("upload://t34/python_basic", out["source"]["repoUrl"])
        path, payload = self.ai.calls[-1]
        self.assertEqual("/proxy/upload/commit", path)
        self.assertEqual(["01_variable/a.py"], [f["path"] for f in payload["days"][0]["files"]])
        self.assertEqual(b"def f(): pass", base64.b64decode(payload["past"][0]["content"]))
        self.assertEqual(b"BUNDLE", self.saved[f"study-uploads/t34/{out['source']['id']}.bundle"])
        # 같은 이름으로 다시 올리면 새 과목을 만들지 않는다
        again = self.commit({"01_variable/a.py": b"x = 2"}, days=[{"date": "2026-06-19", "files": [0]}])
        self.assertFalse(again["source"]["created"])
        self.assertEqual(out["source"]["id"], again["source"]["id"])

    def test_same_name_as_github_subject_is_refused(self) -> None:
        with self.assertRaises(StudySourceError) as ctx:
            self.commit({"a.py": b"x"}, days=[{"date": "2026-06-18", "files": [0]}], name="Web_Client")
        self.assertEqual(409, ctx.exception.status)

    def test_failed_commit_removes_the_new_subject(self) -> None:
        self.ai.fail_commit = True
        with self.assertRaises(StudySourceError):
            self.commit({"a.py": b"x"}, days=[{"date": "2026-06-18", "files": [0]}])
        with connection.cursor() as cur:
            cur.execute("SELECT count(*) FROM study_sources WHERE repo_url LIKE 'upload://%%'")
            self.assertEqual(0, cur.fetchone()[0])

    def test_lost_repo_is_restored_before_committing_even_if_checked_recently(self) -> None:
        first = self.commit({"a.py": b"x"}, days=[{"date": "2026-06-18", "files": [0]}])
        sid = first["source"]["id"]
        self.ai.head = None  # AI 서버를 새로 띄웠다 — 10분 안에 확인했다고 넘어가면 빈 저장소에 커밋된다
        self.commit({"a.py": b"y"}, days=[{"date": "2026-06-19", "files": [0]}], source=sid)
        self.assertEqual(["/proxy/upload/head", "/proxy/upload/restore", "/proxy/upload/commit"], self.ai.paths()[-3:])
        self.assertFalse(self.ai.calls[-1][1]["create"])

    def test_restore_failure_stops_instead_of_overwriting_the_backup(self) -> None:
        sid = self.commit({"a.py": b"x"}, days=[{"date": "2026-06-18", "files": [0]}])["source"]["id"]
        backup = self.saved[f"study-uploads/t34/{sid}.bundle"]
        self.ai.head, self.ai.restore_fails = None, True
        with self.assertRaises(StudySourceError) as ctx:
            self.commit({"a.py": b"y"}, days=[{"date": "2026-06-19", "files": [0]}], source=sid)
        self.assertEqual(503, ctx.exception.status)
        self.assertEqual(backup, self.saved[f"study-uploads/t34/{sid}.bundle"])
        self.assertNotIn(True, [p.get("create") for path, p in self.ai.calls if path == "/proxy/upload/commit"][1:])

    def test_no_backup_at_all_starts_over(self) -> None:
        sid = self.commit({"a.py": b"x"}, days=[{"date": "2026-06-18", "files": [0]}])["source"]["id"]
        self.saved.clear()  # 첫 보관이 실패했던 과목 — 잃을 기록이 없다
        self.ai.head = None
        self.commit({"a.py": b"y"}, days=[{"date": "2026-06-19", "files": [0]}], source=sid)
        self.assertTrue(self.ai.calls[-1][1]["create"])

    def test_bad_input(self) -> None:
        cases = [
            ({"a.py": b"x"}, {"days": [{"date": "2026-10-02", "files": [0]}]}, 400),  # 앞으로 올 날짜
            ({"a.py": b"x"}, {"days": [{"date": "2026-06-18", "files": [3]}]}, 422),  # 없는 파일 번호
            ({"a.py": b"x"}, {"name": "../etc", "days": [{"date": "2026-06-18", "files": [0]}]}, 422),
            ({"a.py": b"x"}, {"source": str(self.github), "days": [{"date": "2026-06-18", "files": [0]}]}, 400),
        ]
        for files, kw, status in cases:
            with self.assertRaises(StudySourceError, msg=kw) as ctx:
                self.commit(files, **kw)
            self.assertEqual(status, ctx.exception.status, kw)


class RestoreTests(UploadTestCase):
    SOURCE = {"id": "77", "repoUrl": "upload://t34/python_basic", "title": "python_basic", "branch": "main"}

    def test_missing_repo_is_restored_from_the_backup_once(self) -> None:
        self.saved["study-uploads/t34/77.bundle"] = b"OLD"
        self.ai.head = None
        folder_upload.ensure_repo("t34", self.SOURCE)
        self.assertEqual(["/proxy/upload/head", "/proxy/upload/restore"], self.ai.paths())
        self.assertEqual(b"OLD", base64.b64decode(self.ai.calls[-1][1]["bundle"]))
        folder_upload.ensure_repo("t34", self.SOURCE)  # 10분 안엔 다시 묻지 않는다
        self.assertEqual(2, len(self.ai.calls))

    def test_existing_repo_and_github_are_left_alone(self) -> None:
        self.ai.head = "abc123"
        folder_upload.ensure_repo("t34", self.SOURCE)
        folder_upload.ensure_repo("t34", {**self.SOURCE, "id": "1", "repoUrl": "https://github.com/a/b"})
        self.assertEqual(["/proxy/upload/head"], self.ai.paths())

    def test_every_ai_call_for_an_uploaded_subject_checks_first(self) -> None:
        self.ai.head = "abc123"
        with mock.patch.object(study_note_service, "_post", return_value={"ok": True}) as post:
            study_note_service._call("/proxy/tree", {"cohortId": "t34", "source": self.SOURCE}, 10)
        self.assertEqual(["/proxy/upload/head"], self.ai.paths())
        post.assert_called_once()


class ScheduleTests(UploadTestCase):
    def test_actual_lesson_dates_come_from_practice_sets(self) -> None:
        with connection.cursor() as cur:
            for day in ("2026-06-18", "2026-06-25"):
                _insert(cur, "practice_sets", {"cohort_id": self.cohort, "source_title": "python_basic", "lesson_date": day, "legacy_id": f"t-{day}",
                                               "origin": "lesson", "title": "", "day_label": "",
                                               "created_at": "2026-10-01T00:00:00+00:00"})
        out = folder_upload.schedule(self.instructor, "t34")
        _path, payload = self.ai.calls[-1]
        self.assertEqual({"python_basic": {"dates": ["2026-06-18", "2026-06-25"]}}, payload["subjects"])
        self.assertEqual("schedule_drift", out["issues"][0]["kind"])


class SubjectNameTests(SimpleTestCase):
    def test_names(self) -> None:
        self.assertEqual("python basic", folder_upload._subject_name({"repo_url": "upload://t34/python basic"}))
        self.assertEqual("web_client", folder_upload._subject_name({"repo_url": "https://github.com/x/Web_Client.git"}))


class HttpTests(UploadTestCase):
    """실제 요청 — 로그인 토큰 · 라우팅 · multipart(파일 여러 개 + 폼 칸) 해석까지"""

    def setUp(self) -> None:
        super().setUp()
        from lms.jwt_auth import issue_tokens

        self.tokens = {}
        with connection.cursor() as cur:
            for role in ("instructor", "student"):
                uid = _insert(cur, "users", {"display_name": role, "role": role, "is_active": True, "cohort_id": self.cohort,
                                             "firebase_uid": f"fb-{role}", "email": f"{role}@t.kr",
                                             "must_change_password": False})
                self.tokens[role] = issue_tokens({"id": uid, "firebase_uid": f"fb-{role}", "role": role})["access"]

    def auth(self, role: str = "instructor") -> dict:
        return {"HTTP_AUTHORIZATION": f"Bearer {self.tokens[role]}"}

    def post_commit(self, count: int, role: str = "instructor"):
        files = [SimpleUploadedFile(f"f{i}.py", f"x = {i}".encode()) for i in range(count)]
        manifest = json.dumps({"paths": [f"01_variable/f{i}.py" for i in range(count)],
                               "days": [{"date": "2026-06-18", "files": list(range(count))}]})
        return self.client.post("/api/study-sources/upload/commit",
                                {"cohortId": "t34", "name": "python_basic", "manifest": manifest, "files": files},
                                **self.auth(role))

    def test_plan_commit_schedule_over_http(self) -> None:
        plan = self.client.post("/api/study-sources/upload/plan",
                                json.dumps({"cohortId": "t34", "mode": "import", "files": [{"path": "p/a.py", "blob": "0" * 40}]}),
                                content_type="application/json", **self.auth())
        self.assertEqual(200, plan.status_code, plan.content)
        made = self.post_commit(3)
        self.assertEqual(200, made.status_code, made.content)
        body = made.json()
        self.assertEqual("upload://t34/python_basic", body["source"]["repoUrl"])
        sent = self.ai.calls[-1][1]["days"][0]["files"]
        self.assertEqual(["01_variable/f0.py", "01_variable/f1.py", "01_variable/f2.py"], [f["path"] for f in sent])
        self.assertEqual(b"x = 2", base64.b64decode(sent[2]["content"]))
        sched = self.client.get("/api/study-sources/schedule?cohortId=t34", **self.auth())
        self.assertEqual(200, sched.status_code, sched.content)

    def test_students_and_strangers_cannot_upload(self) -> None:
        self.assertEqual(403, self.post_commit(1, role="student").status_code)
        anon = self.client.post("/api/study-sources/upload/plan", "{}", content_type="application/json")
        self.assertEqual(401, anon.status_code)

    def test_more_than_a_hundred_files_is_refused_before_reading(self) -> None:
        # Django 가 한 요청에 받는 파일은 100개(DATA_UPLOAD_MAX_NUMBER_FILES) — 화면은 100개씩 나눠 보낸다
        self.assertEqual(400, self.post_commit(101).status_code)
        self.assertEqual(200, self.post_commit(100).status_code)
