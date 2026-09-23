"""복습 문제 자동 출제 — 어느 날짜를 출제할지, 기록을 어떻게 이어 가는지.

저장소 · LLM · 검증기는 가짜다. build_practice_set 만 바꿔 끼워 계획과 기록만 본다.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from study_notes.git_tools import ChangedFile
from study_notes.practice import auto
from study_notes.practice.build import BuildResult
from study_notes.practice.generate import Usage
from study_notes.practice.models import PracticeProblem

LONG = "x = 1\n" * 60


def notebook(*codes: str) -> str:
    return json.dumps({"cells": [{"cell_type": "code", "source": c} for c in codes]})


class FakeRepo:
    """날짜별로 바뀐 파일과 그 시점 내용"""

    def __init__(self, days: dict[str, dict[str, str]]) -> None:
        self.days = days
        self.synced = 0

    def sync(self) -> str:
        self.synced += 1
        return "head"

    def recent_lesson_dates(self, prefixes: list[str]) -> list[str]:
        return sorted(self.days, reverse=True)

    def changed_files_on(self, date: str, prefixes: list[str]):
        return [f"c-{date}"], [ChangedFile(path=p, commit=f"c-{date}") for p in sorted(self.days.get(date, {}))]

    def read_file(self, commit: str, path: str) -> str:
        return self.days[commit[2:]][path]


def problem(topic: str) -> PracticeProblem:
    return PracticeProblem(kind="concept", prompt=topic, topic=topic, choices=["a", "b", "c"], answer_index=0)


def built(*topics: str) -> BuildResult:
    return BuildResult(problems=[problem(t) for t in topics], stats={}, usage=Usage())


class DatesToRunTests(unittest.TestCase):
    def test_first_run_only_recent_days(self) -> None:
        lessons = ["2026-07-22", "2026-09-21", "2026-09-22", "2026-09-23"]
        self.assertEqual(auto.dates_to_run(lessons, {}, "2026-09-23"), ["2026-09-21", "2026-09-22", "2026-09-23"])

    def test_next_runs_start_from_last_done_day_again(self) -> None:
        lessons = ["2026-09-18", "2026-09-21", "2026-09-22", "2026-09-24"]
        days = {"2026-09-18": 12, "2026-09-21": 8}
        self.assertEqual(auto.dates_to_run(lessons, days, "2026-09-24"), ["2026-09-21", "2026-09-22", "2026-09-24"])

    def test_never_future(self) -> None:
        self.assertEqual(auto.dates_to_run(["2026-09-25"], {}, "2026-09-24"), [])


class RunSourceTests(unittest.TestCase):
    def run_source(self, repo: FakeRepo, coverage=None, today="2026-09-23", results=None):
        effect = results or [built("합성곱", "풀링", "합성곱", "stride")]
        with mock.patch.object(auto, "build_practice_set", side_effect=effect) as fake:
            out = auto.run_source(repo, source_title="멀티모달", prefixes=[], coverage=coverage, today=today, runner=object())
        return out, fake

    def test_makes_a_set_per_lesson_day_with_label_and_title(self) -> None:
        repo = FakeRepo({
            "2026-09-11": {"01_cnn.ipynb": notebook(LONG)},
            "2026-09-22": {"02_vit.ipynb": notebook(LONG + "y = 2\n" * 40)},
        })
        out, fake = self.run_source(repo)
        self.assertEqual(repo.synced, 1)
        self.assertEqual(fake.call_count, 1)  # 9/11 은 첫 실행 범위(최근 3일) 밖
        [s] = out["sets"]
        self.assertEqual(s["lessonDate"], "2026-09-22")
        self.assertEqual(s["dayLabel"], "멀티모달 2일차")  # 커밋이 있던 날 중 두 번째
        self.assertEqual(s["title"], "합성곱 · 풀링 · stride")
        self.assertEqual(s["files"], ["02_vit.ipynb"])
        self.assertEqual(len(s["problems"]), 4)
        self.assertEqual(out["coverage"]["days"], {"2026-09-22": 4})
        self.assertEqual(out["error"], "")

    def test_second_run_with_same_content_makes_nothing(self) -> None:
        repo = FakeRepo({"2026-09-22": {"02_vit.ipynb": notebook(LONG)}})
        first, _ = self.run_source(repo)
        again, fake = self.run_source(repo, coverage=first["coverage"], today="2026-09-24")
        self.assertEqual(again["sets"], [])
        fake.assert_not_called()  # 새 셀이 없으면 LLM 을 부르지 않는다
        self.assertEqual(again["coverage"]["days"], {"2026-09-22": 4})

    def test_late_commit_on_same_day_adds_only_new_cells(self) -> None:
        repo = FakeRepo({"2026-09-22": {"02_vit.ipynb": notebook(LONG)}})
        first, _ = self.run_source(repo)
        # 저녁에 셀을 더 올렸다
        repo.days["2026-09-22"]["02_vit.ipynb"] = notebook(LONG, "z = 3\n" * 60)
        again, fake = self.run_source(repo, coverage=first["coverage"], today="2026-09-23", results=[built("위치 임베딩")])
        self.assertEqual(fake.call_count, 1)
        # 새로 붙은 셀만 새 부분으로 넘긴다 — 앞 셀은 이미 출제했다
        content = fake.call_args.kwargs["materials"][0]["content"]
        self.assertIn("[새로 진행한 부분]", content)
        self.assertIn("z = 3", content)
        self.assertNotIn("x = 1\nx = 1", content.split("[새로 진행한 부분]")[1])
        self.assertEqual([s["lessonDate"] for s in again["sets"]], ["2026-09-22"])
        self.assertEqual(again["coverage"]["days"]["2026-09-22"], 5)

    def test_failure_stops_and_keeps_earlier_days(self) -> None:
        repo = FakeRepo({
            "2026-09-21": {"a.ipynb": notebook(LONG)},
            "2026-09-22": {"b.ipynb": notebook(LONG + "q = 1\n" * 30)},
        })
        out, _ = self.run_source(repo, results=[built("A"), RuntimeError("LLM 시간 초과")])
        self.assertEqual([s["lessonDate"] for s in out["sets"]], ["2026-09-21"])
        self.assertIn("2026-09-22 출제 실패", out["error"])
        self.assertEqual(out["coverage"]["days"], {"2026-09-21": 1})  # 실패한 날은 기록하지 않는다 — 다음에 다시


if __name__ == "__main__":
    unittest.main()
