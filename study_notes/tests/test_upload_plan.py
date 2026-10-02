"""폴더 올리기 계획 — 날짜 근거(시안 규칙) · 커리큘럼 · 공휴일은 힌트(틀릴 수 있다) · 지난번과 같은 파일 · 넣을 폴더."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from study_notes import upload_plan, upload_repo
from study_notes.git_tools import SEOUL, RepoCache, _remove_tree, parse_repo_url, run_git
from study_notes.upload_plan import Calendar, CurriculumDay, file_row

HOLIDAYS = {"2026-09-24": "추석", "2026-09-25": "추석", "2026-09-26": "추석", "2026-10-03": "개천절",
            "2026-10-05": "대체공휴일(개천절)", "2026-10-09": "한글날"}


def curriculum() -> list[CurriculumDay]:
    """34기 커리큘럼 일부(실제 표에서) — 추석 · 대체공휴일은 이미 빠져 있다"""
    rows = [
        ("프로그래밍과 데이터 기초", "Python", ["06-16", "06-17", "06-18", "06-19", "06-22", "06-23", "06-24"]),
        ("프로그래밍과 데이터 기초", "Database", ["06-25", "06-26", "06-29"]),
        ("데이터 분석과 머신러닝", "딥러닝", ["07-06", "07-07", "07-08"]),
        ("AI 활용 애플리케이션 개발", "화면 구현", ["09-23", "09-28", "09-29"]),
        ("AI 활용 애플리케이션 개발", "Django Framework", ["09-30", "10-01", "10-02", "10-06", "10-07"]),
    ]
    return [CurriculumDay(f"2026-{d}", topic, unit) for unit, topic, days in rows for d in days]


def calendar(**kw) -> Calendar:
    return Calendar(today="2026-10-01", start="2026-06-16", end="2026-12-08", holidays=dict(HOLIDAYS),
                    curriculum=kw.pop("curriculum", curriculum()), **kw)


def ms(day: str) -> int:
    return int(datetime.fromisoformat(f"{day}T12:00:00").replace(tzinfo=SEOUL).timestamp() * 1000)


def row(path: str, body: str = "", day: str = "2026-10-01", **extra) -> dict:
    out = file_row(path, (body or path).encode(), ms(day))
    out.update(extra)
    return out


PYTHON_BASIC = [
    "01_variable/exercise.ipynb", "01_variable/question.ipynb", "02_data-type/exercise.ipynb", "03_control/exercise.ipynb",
    "04_function/exercise.ipynb", "04_function/question.ipynb", "05_class/exercise.ipynb", "06_module/alias.py",
    "06_module/math_test.py", "07_package/team_management/developers.py", "07_package/team_management/manager.py",
    "08_file-io/exercise.ipynb", "09_exception/exercise.ipynb", "10_streamlit/app.py",
]


class CalendarTests(unittest.TestCase):
    def test_holiday_written_in_curriculum_is_dropped_but_asked(self) -> None:
        # 커리큘럼을 잘못 만들어 추석(9/24)에 수업이 잡혔다
        cal = calendar(curriculum=[*curriculum(), CurriculumDay("2026-09-24", "화면 구현", "AI 활용 애플리케이션 개발")])
        topic = "AI 활용 애플리케이션 개발|화면 구현"
        self.assertNotIn("2026-09-24", cal.class_days(topic))
        kinds = [w["kind"] for w in cal.warnings()]
        self.assertIn("holiday_in_curriculum", kinds)
        # 강사가 「수업 있었음」 하면 되돌린다 — 공휴일 표도 틀릴 수 있다
        cal.extra_days.add("2026-09-24")
        self.assertIn("2026-09-24", cal.class_days(topic))
        self.assertNotIn("holiday_in_curriculum", [w["kind"] for w in cal.warnings()])

    def test_weekend_in_curriculum_is_kept_and_asked_as_makeup(self) -> None:
        cal = calendar(curriculum=[*curriculum(), CurriculumDay("2026-06-20", "Python", "프로그래밍과 데이터 기초")])
        self.assertIn("2026-06-20", cal.class_days("프로그래밍과 데이터 기초|Python"))
        self.assertEqual(["weekend_in_curriculum"], [w["kind"] for w in cal.warnings()])

    def test_without_curriculum_counts_weekdays_minus_holidays(self) -> None:
        cal = calendar(curriculum=[])
        days = cal.class_days()
        self.assertNotIn("2026-09-24", days)
        self.assertNotIn("2026-09-26", days)
        self.assertIn("2026-09-23", days)
        self.assertEqual("2026-09-29", upload_plan.nth_class_day(cal, 3, topic=None, start="2026-09-23"))

    def test_round_counts_curriculum_days_of_the_subject(self) -> None:
        cal = calendar()
        self.assertEqual("2026-06-18", upload_plan.nth_class_day(cal, 3, topic="프로그래밍과 데이터 기초|Python", start=""))
        # 커리큘럼 기간보다 길게 이어진 과목 — 그 뒤 평일로 센다
        self.assertEqual("2026-06-25", upload_plan.nth_class_day(cal, 8, topic="프로그래밍과 데이터 기초|Python", start=""))


class MatchTopicTests(unittest.TestCase):
    def test_by_name_by_alias_and_by_dates(self) -> None:
        cal = calendar()
        self.assertEqual("프로그래밍과 데이터 기초|Python", upload_plan.match_topic("python_basic", [], cal)["id"])
        self.assertEqual("데이터 분석과 머신러닝|딥러닝", upload_plan.match_topic("DL", [], cal)["id"])
        # 이름으로는 못 맞추는 과목 — 실제 수업 날짜로 맞춘다
        self.assertIsNone(upload_plan.match_topic("web_server", [], cal)["id"])
        self.assertEqual(
            {"id": "AI 활용 애플리케이션 개발|Django Framework", "by": "dates"},
            upload_plan.match_topic("web_server", ["2026-09-30", "2026-10-01"], cal),
        )

    def test_unclear_is_left_for_the_instructor(self) -> None:
        cal = calendar()
        self.assertIsNone(upload_plan.match_topic("web_client", [], cal)["id"])
        self.assertIsNone(upload_plan.match_topic("anything", [], calendar(curriculum=[]))["id"])


class PlanImportTests(unittest.TestCase):
    def test_cohort_folder_dates_from_names_rounds_and_lesson_lines(self) -> None:
        heads = {"cells": [{"type": "markdown", "source": h} for h in ("# JS 심화", "## 배열", "## 콜백", "## 객체")]}
        files = [
            row("34기/frontend/0923_HTML_CSS/index.html", day="2026-09-23"),
            row("34기/frontend/0928_JavaScript/01_변수.js", day="2026-09-28"),
            row("34기/frontend/0928_0929_JS심화.ipynb", **heads),
            row("34기/frontend/DOM실습/dom_basic.html", "<!-- 2026-09-29 DOM 수업 -->\n<html>"),
            row("34기/frontend/예제/data.py", "rows = [('2024-01-15', '회의')]\nprice = 1500"),
            row("34기/web_server/2026-09-30_Django/views.py"),
            row("34기/web_server/2일차_ORM/models.py"),
            row("34기/web_server/.DS_Store"),
        ]
        plan = upload_plan.plan_import(files, calendar())
        self.assertEqual("cohort", plan["what"])
        self.assertEqual(1, plan["skipped"])
        by = {x["path"]: x for s in plan["subjects"] for x in s["files"]}
        self.assertEqual(("name", "2026-09-23"), (by["0923_HTML_CSS/index.html"]["basis"], by["0923_HTML_CSS/index.html"]["date"]))
        self.assertEqual(["2026-09-28", "2026-09-29"], by["0928_0929_JS심화.ipynb"]["dates"])
        self.assertEqual(("content", "2026-09-29"), (by["DOM실습/dom_basic.html"]["basis"], by["DOM실습/dom_basic.html"]["date"]))
        # 예제 데이터의 날짜(2024-01-15)는 수업 날짜가 아니다 — 수정 시각으로
        self.assertEqual("time", by["예제/data.py"]["basis"])
        web = next(s for s in plan["subjects"] if s["name"] == "web_server")
        self.assertEqual("AI 활용 애플리케이션 개발|Django Framework", web["topic"])
        self.assertEqual("dates", web["topicBy"])
        # 2일차 = Django Framework 둘째 수업일
        self.assertEqual("2026-10-01", by["2일차_ORM/models.py"]["date"])

    def test_copied_subject_folder_becomes_past_material_with_curriculum_estimate(self) -> None:
        # 압축 풀기로 수정 시각이 전부 오늘 — 날짜 단서가 없다
        files = [row(f"python_basic/{p}", f"# {p}") for p in PYTHON_BASIC]
        plan = upload_plan.plan_import(files, calendar())
        self.assertEqual("subject", plan["what"])
        subject = plan["subjects"][0]
        self.assertEqual("프로그래밍과 데이터 기초|Python", subject["topic"])
        self.assertTrue(all(x["basis"] == "pick" and x["date"] is None for x in subject["files"]))
        self.assertEqual(len(PYTHON_BASIC), subject["counts"]["past"])
        # 추정은 따로(노란 줄) — 큰 주제 번호 순서대로 Python 수업일(6/16~6/24)에 나뉜다
        est = {x["path"].split("/")[0]: x["estimate"] for x in subject["files"]}
        self.assertEqual("2026-06-16", est["01_variable"])
        self.assertEqual(sorted(est.values()), [est[k] for k in sorted(est, key=upload_plan._natural)])
        self.assertLessEqual(est["10_streamlit"], "2026-06-24")
        self.assertGreaterEqual(len(set(est.values())), 6)

    def test_dates_on_off_days_and_other_subjects_are_asked_not_blocked(self) -> None:
        files = [
            row("python_basic/2026-10-09_extra/a.py"),  # 한글날
            row("python_basic/0930_more/b.py"),  # 커리큘럼은 Django Framework 날
            row("python_basic/0622_func/c.py"),
        ]
        subject = upload_plan.plan_import(files, calendar(), what="subject")["subjects"][0]
        kinds = {w["date"]: w["kind"] for w in subject["warnings"]}
        self.assertEqual({"2026-10-09": "off_day", "2026-09-30": "other_topic"}, kinds)

    def test_existing_subject_marks_same_update_new(self) -> None:
        a, b = row("python_basic/01_variable/a.py", "x = 1"), row("python_basic/01_variable/b.py", "y = 2")
        new = row("python_basic/02_data-type/c.py", "z = 3")
        existing = {"python_basic": {"kind": "upload", "id": "7", "tree": {"01_variable/a.py": a["blob"], "01_variable/b.py": "0" * 40}, "dates": []}}
        subject = upload_plan.plan_import([a, b, new], calendar(), what="subject", existing=existing)["subjects"][0]
        self.assertEqual({"01_variable/a.py": "same", "01_variable/b.py": "update", "02_data-type/c.py": "new"},
                         {x["path"]: x["status"] for x in subject["files"]})
        github = upload_plan.plan_import([a], calendar(), what="subject",
                                         existing={"python_basic": {"kind": "github", "id": "3"}})["subjects"][0]
        self.assertEqual("github_same_name", github["warnings"][0]["kind"])


class PlanDailyTests(unittest.TestCase):
    TREE_TEXT = {
        "04_function/exercise.ipynb": "add = lambda x, y: x + y\nfor a, b in zip(xs, ys): pass\nsorted(p, key=f)",
        "05_class/exercise.ipynb": "class Person:\n  def __init__(self): super().__init__()",
        "06_module/math_test.py": "import ohgiraffers_module as og\nif __name__ == '__main__': og.gorilla()",
        "06_module/alias.py": "import ohgiraffers_module as og",
        "07_package/team_management/developers.py": "class Dev: pass",
        "08_file-io/exercise.ipynb": "with open('a.txt') as f:\n  import csv, json",
        "09_exception/exercise.ipynb": "try:\n  1 / 0\nexcept ZeroDivisionError as e:\n  raise\nfinally:\n  pass",
        "01_variable/exercise.ipynb": "x = 10",
    }

    def plan(self, files: list[dict], day: str = "2026-10-01", topic: str | None = "AI 활용 애플리케이션 개발|Django Framework"):
        tree = {p: upload_plan.blob_id(t.encode()) for p, t in self.TREE_TEXT.items()}
        return upload_plan.plan_daily(files, calendar(), day=day, tree=tree, texts=self.TREE_TEXT, topic=topic)

    def test_same_update_pick_and_folder_suggestions(self) -> None:
        plan = self.plan([
            file_row("06_module/alias.py", b"import ohgiraffers_module as og  # changed"),
            file_row("math_test.py", self.TREE_TEXT["06_module/math_test.py"].encode()),
            file_row("exercise.ipynb", b"{}"),
            file_row("practice.py", b"add = lambda x, y: x + y\nfor a, b in zip(xs, ys):\n  print(add(a, b))\nsorted(pairs, key=lambda p: p[1])"),
            file_row("try_test.py", b"try:\n  int('x')\nexcept ValueError as e:\n  print(e)\nfinally:\n  print('end')"),
            file_row("team_management/leader.py", b"class Leader: pass"),
            file_row("summary.py", b"class Shape:\n  def __init__(self): pass\nwith open('a.txt') as f:\n  import json\ntry:\n  pass\nexcept Exception:\n  raise"),
            file_row("notes.txt", b"not a lesson file"),
        ])
        by = {x["path"]: x for x in plan["files"]}
        self.assertEqual(("update", "06_module/alias.py"), (by["06_module/alias.py"]["status"], by["06_module/alias.py"]["target"]))
        self.assertEqual("same", by["math_test.py"]["status"])
        self.assertEqual("pick", by["exercise.ipynb"]["status"])
        self.assertEqual(5, len(by["exercise.ipynb"]["options"]))
        self.assertEqual("04_function", by["practice.py"]["folder"])
        self.assertEqual("09_exception", by["try_test.py"]["folder"])
        self.assertEqual("07_package/team_management", by["team_management/leader.py"]["folder"])
        # 여러 주제를 섞은 정리 파일 — 한 주제에 넣지 않고 날짜 폴더
        self.assertEqual("2026-10-01/", by["summary.py"]["folder"])
        self.assertNotIn("notes.txt", by)
        self.assertEqual([], plan["warnings"])

    def test_day_checks(self) -> None:
        one = [file_row("a.py", b"x = 1")]
        self.assertEqual("off_day", self.plan(one, day="2026-09-24")["warnings"][0]["kind"])
        self.assertEqual("other_topic", self.plan(one, day="2026-06-22")["warnings"][0]["kind"])
        self.assertEqual("future", self.plan(one, day="2026-10-02")["warnings"][0]["kind"])


class ScheduleCheckTests(unittest.TestCase):
    def test_subject_running_into_the_next_unit_is_reported(self) -> None:
        issues = upload_plan.schedule_check(calendar(), {
            "python_basic": {"dates": ["2026-06-18", "2026-06-23", "2026-06-25", "2026-07-06", "2026-07-07"]},
            "web_server": {"dates": ["2026-09-30", "2026-10-01"]},
        })
        drift = [i for i in issues if i["kind"] == "schedule_drift"]
        # 6/25(Database)는 같은 단원이라 그대로, 7/6 · 7/7(딥러닝 — 다음 단원)만
        self.assertEqual([("python_basic", ["2026-07-06", "2026-07-07"])], [(i["subject"], i["dates"]) for i in drift])
        self.assertIn("다음 단원 「데이터 분석과 머신러닝」", drift[0]["text"])

    def test_curriculum_subjects_are_not_one_to_one_with_repos(self) -> None:
        # 「딥러닝」 한 칸에 저장소 여럿, LLM 저장소 하나에 과목 여럿 — 같은 단원이면 어긋남이 아니다(34기 실측)
        cal = calendar(curriculum=[
            *curriculum(),
            CurriculumDay("2026-08-21", "LLM", "LLM"), CurriculumDay("2026-08-27", "프롬프트 엔지니어링", "LLM"),
            CurriculumDay("2026-09-02", "파인튜닝", "LLM"),
        ])
        issues = upload_plan.schedule_check(cal, {
            "llm": {"dates": ["2026-08-21", "2026-08-27", "2026-09-02"]},
            "data_analysis": {"dates": ["2026-07-06", "2026-07-07"]},
            "dl": {"dates": ["2026-07-08"]},
        })
        self.assertEqual([], issues)

    def test_lesson_on_a_day_without_curriculum_class(self) -> None:
        issues = upload_plan.schedule_check(calendar(), {"web_client": {"dates": ["2026-09-23", "2026-09-24", "2026-09-28"]}})
        self.assertEqual(["off_curriculum"], [i["kind"] for i in issues])
        self.assertIn("9/24(추석)", issues[0]["text"])


class UploadRepoPlanTests(unittest.TestCase):
    """서버 안 저장소 — 지문이 화면과 같고, 지난 자료는 수업 날짜가 아니다"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.dict("os.environ", {"STUDY_NOTES_CACHE_DIR": self.tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.cache = RepoCache("cohort_34", "99", parse_repo_url("upload://cohort_34/python_basic"), "main")

    def test_fingerprint_matches_git_and_keeps_crlf(self) -> None:
        body = b"x = 1\r\nprint(x)\r\n"
        upload_repo.commit_day(self.cache, "2026-06-18", {"01_variable/a.py": body})
        tree = upload_repo.tree_blobs(self.cache.dir)
        self.assertEqual(upload_plan.blob_id(body), tree["01_variable/a.py"])
        again = upload_repo.commit_day(self.cache, "2026-06-19", {"01_variable/a.py": body})
        self.assertEqual(["01_variable/a.py"], again.skipped)

    def test_korean_file_names_read_back(self) -> None:
        upload_repo.commit_day(self.cache, "2026-09-28", {"0928_JavaScript/01_변수.js": b"let a = 1;"})
        _shas, files = self.cache.changed_files_on("2026-09-28", [])
        self.assertEqual(["0928_JavaScript/01_변수.js"], [f.path for f in files])
        self.assertIn("0928_JavaScript/01_변수.js", upload_repo.tree_blobs(self.cache.dir))

    def test_past_material_is_not_a_lesson_day_until_updated(self) -> None:
        notebook = json.dumps({"cells": [{"cell_type": "code", "source": ["def f(): pass"]}]}).encode()
        out = upload_repo.import_all(
            self.cache,
            {"2026-06-22": {"08_file-io/exercise.ipynb": b"open('a')"}},
            past={"04_function/exercise.ipynb": notebook, "01_variable/a.py": b"x = 1"},
        )
        self.assertEqual(["", "2026-06-22"], [c.date for c in out])
        today = datetime.now(SEOUL).strftime("%Y-%m-%d")
        self.assertEqual(["2026-06-22"], self.cache.recent_lesson_dates([]))
        self.assertEqual([], self.cache.changed_files_on(today, [])[1])
        # 폴더 노트 · 과목 요약은 최신 파일 전체를 본다 — 지난 자료도 있다
        self.assertEqual(
            ["01_variable/a.py", "04_function/exercise.ipynb", "08_file-io/exercise.ipynb"], self.cache.list_tree([]),
        )
        # 지난 자료 노트북을 오늘 이어 쓰면 오늘 수업이 된다
        grown = json.dumps({"cells": [{"cell_type": "code", "source": ["def f(): pass"]},
                                      {"cell_type": "code", "source": ["lambda x: x"]}]}).encode()
        upload_repo.commit_day(self.cache, "2026-06-23", {"04_function/exercise.ipynb": grown})
        _shas, files = self.cache.changed_files_on("2026-06-23", [])
        self.assertEqual(["04_function/exercise.ipynb"], [f.path for f in files])
        snap = upload_repo.snapshot(self.cache)
        self.assertEqual(["2026-06-23", "2026-06-22"], snap["dates"])
        self.assertIn("lambda x: x", snap["texts"]["04_function/exercise.ipynb"])
        log = run_git(["log", "--format=%ae %s"], cwd=self.cache.dir)
        self.assertIn("past@lms.local 지난 자료 2개(날짜 없음)", log)

    def test_bundle_restores_dates_files_and_past_mark(self) -> None:
        upload_repo.import_all(
            self.cache,
            {"2026-06-18": {"01_variable/a.py": b"x = 1\r\n"}, "2026-06-19": {"04_function/f.py": b"def f(): pass"}},
            past={"09_exception/e.py": b"try: pass\nexcept: pass"},
        )
        data = upload_repo.bundle(self.cache)
        before = upload_repo.head(self.cache)
        # 서버를 새로 띄워 캐시 폴더가 사라졌다
        _remove_tree(self.cache.dir)
        self.assertIsNone(upload_repo.head(self.cache))
        self.assertEqual(before, upload_repo.restore(self.cache, data))
        self.assertEqual(["2026-06-19", "2026-06-18"], self.cache.recent_lesson_dates([]))
        self.assertEqual(upload_plan.blob_id(b"x = 1\r\n"), upload_repo.tree_blobs(self.cache.dir)["01_variable/a.py"])
        # 되살린 뒤에도 이어서 올린다 — 원격(origin)은 남기지 않는다
        upload_repo.commit_day(self.cache, "2026-06-22", {"04_function/f.py": b"def f(): pass\nlambda: 1"})
        self.assertEqual(["2026-06-22", "2026-06-19", "2026-06-18"], self.cache.recent_lesson_dates([]))
        self.assertEqual("", run_git(["remote"], cwd=self.cache.dir).strip())
        # 이미 있으면 보관본으로 덮지 않는다
        self.assertEqual(upload_repo.head(self.cache), upload_repo.restore(self.cache, data))

    def test_restore_keeps_line_endings_in_the_work_folder(self) -> None:
        # 시스템 git 설정이 autocrlf=true 인 PC 에서 되살린 작업 폴더가 CRLF 로 바뀌었다
        lf, crlf = b"x = 1\ny = 2\n", b"z = 3\r\n"
        upload_repo.commit_day(self.cache, "2026-06-18", {"a.py": lf, "b.py": crlf})
        data = upload_repo.bundle(self.cache)
        _remove_tree(self.cache.dir)
        upload_repo.restore(self.cache, data)
        self.assertEqual(lf, (self.cache.dir / "a.py").read_bytes())
        self.assertEqual(crlf, (self.cache.dir / "b.py").read_bytes())

    def test_commit_endpoint_refuses_a_missing_repo_unless_new(self) -> None:
        import base64
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from study_notes.api import router

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        source = {"id": "99", "title": "python_basic", "repoUrl": "upload://cohort_34/python_basic", "branch": "main"}
        body = {"cohortId": "cohort_34", "source": source,
                "days": [{"date": "2026-06-18", "files": [{"path": "a.py", "content": base64.b64encode(b"x = 1").decode()}]}]}
        with mock.patch.dict("os.environ", {"LMS_AI_SHARED_TOKEN": ""}):
            refused = client.post("/api/v1/study-notes/proxy/upload/commit", json=body)
            self.assertEqual(409, refused.status_code)
            self.assertIsNone(upload_repo.head(self.cache))
            made = client.post("/api/v1/study-notes/proxy/upload/commit", json={**body, "create": True})
            self.assertEqual(200, made.status_code)
            self.assertTrue(made.json()["bundle"])
            again = client.post("/api/v1/study-notes/proxy/upload/commit",
                                json={**body, "days": [{"date": "2026-06-19", "files": [{"path": "a.py", "content": base64.b64encode(b"x = 2").decode()}]}]})
            self.assertEqual(200, again.status_code)
        self.assertEqual(["2026-06-19", "2026-06-18"], self.cache.recent_lesson_dates([]))

    def test_snapshot_of_missing_subject_is_empty(self) -> None:
        self.assertEqual({"tree": {}, "dates": [], "texts": {}}, upload_repo.snapshot(self.cache))
        self.assertFalse(Path(self.cache.dir, ".git").exists())


if __name__ == "__main__":
    unittest.main()
