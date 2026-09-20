"""야간 배치 — 네트워크 없이 검증하는 판정 규칙.

핵심 약속 둘:
1. **끝까지 훑은 대분류에서 안 보인 공고만 사라진 것으로 센다.** 주 1회 훑는 대분류의
   공고를 평일에 "오늘 안 보였다"고 지우면 안 된다.
2. **sweep이 끊기면 그날은 아무것도 지우지 않는다.**
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

from job_matching_bot.crawling.http_session import BlockedByTargetSiteError
from job_matching_bot.crawling.nightly import (
    DAILY_CATEGORIES,
    SKIPPED_CATEGORIES,
    SweepResult,
    categories_for,
    is_closed_page,
    link_check,
    link_check_budget,
    prioritize,
    prune,
    run_stamp,
    sweep,
    sweep_category,
)
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.schemas.job_record import STATUS_OPEN, STATUS_REMOVED

KST = timezone(timedelta(hours=9))
DAY1 = datetime(2026, 9, 6, 23, 0, tzinfo=KST)  # 일요일


class CategoriesTest(unittest.TestCase):
    def test_weekday_is_daily_set_and_sunday_is_everything_but_skipped(self):
        self.assertEqual(list(DAILY_CATEGORIES), categories_for(date(2026, 9, 7)))  # 월
        sunday = categories_for(date(2026, 9, 6))
        self.assertEqual(14, len(sunday))
        for cat in SKIPPED_CATEGORIES:
            self.assertNotIn(cat, sunday)
        self.assertEqual(sunday, categories_for(date(2026, 9, 7), full=True))


class RunStampTest(unittest.TestCase):
    """같은 날 두 번 돌아도 파일을 덮어쓰지 않는다.

    09-13 00:55에 다시 돌린 배치와 같은 날 23:00 정기 배치가 둘 다 `2026-09-13`이라
    뒤엣것이 요약·적재 리포트·목록 원본을 덮어썼다.
    """

    def test_two_runs_on_the_same_day_get_different_names(self):
        rerun = datetime(2026, 9, 13, 0, 55, tzinfo=KST)
        nightly = datetime(2026, 9, 13, 23, 0, tzinfo=KST)
        self.assertNotEqual(run_stamp(rerun), run_stamp(nightly))
        self.assertEqual("2026-09-13-2300", run_stamp(nightly))

    def test_prune_still_reads_the_date(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            old = folder / f"{run_stamp(datetime(2026, 8, 1, 23, 0, tzinfo=KST))}.json"
            new = folder / f"{run_stamp(datetime(2026, 9, 13, 23, 0, tzinfo=KST))}.json"
            old.write_text("[]")
            new.write_text("[]")
            self.assertEqual(1, prune(folder, 14, date(2026, 9, 14)))
            self.assertTrue(new.exists())


def _rows(cat: str, start: int, n: int) -> list[dict]:
    return [{"source_job_id": f"{cat}-{i}", "job_sectors": [], "badge": "", "support_text": ""} for i in range(start, start + n)]


class SweepTest(unittest.TestCase):
    def test_reads_every_page_and_marks_complete(self):
        def fetch(cat, page):
            return 250, _rows(cat, (page - 1) * 100, 100 if page < 3 else 50)

        records, total, read, last, blocked = sweep_category(fetch, "2", min_delay=0, max_delay=0)
        self.assertEqual((250, 3, 3, False), (total, read, last, blocked))
        self.assertEqual(250, len(records))
        self.assertEqual([1, 250], [records[0]["list_rank"], records[-1]["list_rank"]])

    def test_block_stops_and_marks_incomplete(self):
        def fetch(cat, page):
            if page == 2:
                raise BlockedByTargetSiteError("429")
            return 250, _rows(cat, 0, 100)

        result = sweep(["2", "15"], fetch, min_delay=0, max_delay=0)
        self.assertTrue(result.blocked)
        self.assertEqual(set(), result.complete)
        self.assertEqual((1, 3), result.pages["2"])
        self.assertNotIn("15", result.pages)  # 차단 뒤에는 더 요청하지 않는다
        self.assertFalse(result.authoritative(["2", "15"]))

    def test_one_transient_error_is_retried_then_complete(self):
        calls = []

        def fetch(cat, page):
            calls.append(page)
            if page == 2 and calls.count(2) == 1:
                raise requests.ConnectionError("reset")
            return 150, _rows(cat, (page - 1) * 100, 100 if page == 1 else 50)

        import job_matching_bot.crawling.nightly as nightly

        original = nightly.polite_delay
        nightly.polite_delay = lambda *a: None
        try:
            result = sweep(["2"], fetch, min_delay=0, max_delay=0)
        finally:
            nightly.polite_delay = original
        self.assertEqual({"2"}, result.complete)
        self.assertEqual(150, len(result.seen["2"]))


class ObservedTest(unittest.TestCase):
    """저장소의 목록 관측 기록으로 무엇을 살아 있다고 보는지."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "s.sqlite")
        base = mock_jobs()[0]
        self.jobs = [
            replace(base, source="SARAMIN_POC", source_job_id=sid, job_id=f"SARAMIN-{sid}", deadline=None)
            for sid in ("it-1", "sales-1", "unknown-1")
        ]
        self.store.upsert(self.jobs, source="SARAMIN_POC", as_of=DAY1)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _observed(self, seen_today, at, authoritative):
        return self.store.list_observed(
            "SARAMIN_POC", seen_today=seen_today, as_of=at, within_days=15, authoritative=authoritative
        )

    def test_full_sweep_is_authoritative(self):
        # 일요일: 전 대분류 완전. it-1은 IT에서, sales-1은 영업에서 봤고 unknown-1은 어디에도 없다.
        self.store.record_list_seen({"2": {"it-1"}, "8": {"sales-1"}}, {"2": 1, "8": 1}, DAY1, source="SARAMIN_POC")
        observed = self._observed({"it-1", "sales-1"}, DAY1, authoritative=True)
        self.assertEqual({"it-1", "sales-1"}, observed)

    def test_weekday_keeps_weekly_category_jobs_and_unknown_ones(self):
        self.store.record_list_seen({"2": {"it-1"}, "8": {"sales-1"}}, {"2": 1, "8": 1}, DAY1, source="SARAMIN_POC")
        monday = DAY1 + timedelta(days=1)
        # 월요일: IT만 완전히 훑었는데 it-1이 없다 → 사라짐. sales-1은 영업을 안 훑었으니 살아 있음.
        # unknown-1은 기록이 없고 전 대분류를 훑은 것도 아니니 모름 → 살아 있음.
        self.store.record_list_seen({"2": set()}, {"2": 0}, monday, source="SARAMIN_POC")
        observed = self._observed(set(), monday, authoritative=False)
        self.assertEqual({"sales-1", "unknown-1"}, observed)

    def test_weekly_evidence_expires_after_window(self):
        self.store.record_list_seen({"8": {"sales-1"}}, {"8": 1}, DAY1, source="SARAMIN_POC")
        later = DAY1 + timedelta(days=16)
        self.store.record_list_seen({"2": set()}, {"2": 0}, later, source="SARAMIN_POC")
        self.assertNotIn("sales-1", self._observed(set(), later, authoritative=False))

    def test_incomplete_sweep_does_not_invalidate_earlier_sighting(self):
        self.store.record_list_seen({"2": {"it-1"}}, {"2": 1}, DAY1, source="SARAMIN_POC")
        monday = DAY1 + timedelta(days=1)
        # IT를 훑다 끊겼다(complete에 없음). it-1을 못 봤어도 어제 기록이 살아 있다.
        self.store.record_list_seen({"2": set()}, {}, monday, source="SARAMIN_POC")
        self.assertIn("it-1", self._observed(set(), monday, authoritative=False))

    def test_removal_candidates_are_those_about_to_hit_the_limit(self):
        # 한 번 안 보인 뒤(missing_runs=1) 오늘도 안 보이면 REMOVED가 된다.
        later = DAY1 + timedelta(days=1)
        self.store.upsert([], source="SARAMIN_POC", as_of=later, observed_ids={"sales-1", "unknown-1"})
        self.assertEqual(1, self.store.get("SARAMIN-it-1").missing_runs)
        self.assertEqual(["it-1"], self.store.removal_candidates("SARAMIN_POC", observed=set()))
        self.assertEqual([], self.store.removal_candidates("SARAMIN_POC", observed={"it-1"}))
        # 링크 확인에서 살아 있다고 나오면 observed에 넣어 삭제를 막는다.
        self.store.upsert([], source="SARAMIN_POC", as_of=later + timedelta(days=1), observed_ids={"it-1", "sales-1", "unknown-1"})
        self.assertEqual(STATUS_OPEN, self.store.get("SARAMIN-it-1").status)

    def test_source_job_ids_by_status(self):
        later = DAY1 + timedelta(days=1)
        self.store.upsert([], source="SARAMIN_POC", as_of=later, observed_ids={"it-1"}, missing_run_limit=1)
        self.assertEqual({"it-1"}, self.store.source_job_ids("SARAMIN_POC", statuses=[STATUS_OPEN]))
        self.assertEqual({"sales-1", "unknown-1"}, self.store.source_job_ids("SARAMIN_POC", statuses=[STATUS_REMOVED]))


class LinkCheckTest(unittest.TestCase):
    def test_closed_page_detection(self):
        self.assertTrue(is_closed_page("<html><body><p>마감된 공고입니다</p></body></html>"))
        self.assertTrue(is_closed_page("<html><body><div class='wrap'>다른 페이지</div></body></html>"))
        self.assertFalse(is_closed_page("<html><body><div class='jv_cont'><h2>상세요강</h2></div></body></html>"))

    def test_unknown_and_unchecked_are_kept(self):
        class Response:
            def __init__(self, status, text=""):
                self.status_code, self.text = status, text

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise requests.HTTPError(response=self)

        pages = {
            "1": Response(200, "<div class='jv_cont'>x</div>"),  # 살아 있음
            "2": Response(404),                                    # 내려감
            "3": Response(500),                                    # 모름
        }

        class Session:
            def get(self, url, **kwargs):
                rec = url.rsplit("=", 1)[1]
                if rec == "4":
                    raise requests.ConnectionError("timeout")
                return pages[rec]

        import job_matching_bot.crawling.nightly as nightly

        original = nightly.polite_delay
        nightly.polite_delay = lambda *a: None
        try:
            alive, counts = link_check(Session(), ["1", "2", "3", "4", "5"], limit=4, min_delay=0, max_delay=0)
        finally:
            nightly.polite_delay = original
        self.assertEqual({"1", "3", "4", "5"}, alive)  # 2만 지운다. 5는 상한 밖이라 확인 안 함
        self.assertEqual({"alive": 1, "closed": 1, "unknown": 2, "unchecked": 1}, dict(counts))


class PriorityTest(unittest.TestCase):
    def test_it_category_comes_first_and_inner_order_is_kept(self):
        queue = [
            {"source_job_id": "p1", "cat_mcls": "16"},
            {"source_job_id": "it1", "cat_mcls": "2"},
            {"source_job_id": "p2", "cat_mcls": "16"},
            {"source_job_id": "it2", "cat_mcls": "2"},
        ]
        self.assertEqual(["it1", "it2", "p1", "p2"], [r["source_job_id"] for r in prioritize(queue)])


class SweepResultTest(unittest.TestCase):
    def test_seen_today_unions_categories(self):
        result = SweepResult(seen={"2": {"a", "b"}, "15": {"b", "c"}}, complete={"2", "15"})
        self.assertEqual({"a", "b", "c"}, result.seen_today)
        self.assertTrue(result.authoritative(["2", "15"]))
        self.assertFalse(result.authoritative(["2", "15", "9"]))


if __name__ == "__main__":
    unittest.main()


class LinkCheckBudgetTest(unittest.TestCase):
    """남은 시간을 전부 링크 확인에 쓴다. 미리 떼어 둔 몫 아래로는 내려가지 않는다."""

    def test_uses_remaining_minutes(self) -> None:
        # 60분, 한 건 6초(응답 1초 + 쉬는 시간 5초) → 600건
        self.assertEqual(link_check_budget(60, max_delay=5.0), 600)

    def test_floor_when_time_ran_out(self) -> None:
        self.assertEqual(link_check_budget(-10, max_delay=5.0, floor=200), 200)
        self.assertEqual(link_check_budget(0, max_delay=5.0), 0)

    def test_more_than_floor_when_time_allows(self) -> None:
        self.assertEqual(link_check_budget(200, max_delay=5.0, floor=200), 2000)
