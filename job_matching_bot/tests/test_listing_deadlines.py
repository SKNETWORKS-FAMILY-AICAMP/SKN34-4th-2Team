"""회사가 늘린 마감일을 목록에서 읽어 되살린다.

상세는 한 번 받으면 다시 받지 않는다. 회사가 마감일을 늘리면 저장소는 처음 마감일로 공고를
마감(EXPIRED)했고, 목록에 계속 보여도 되살리지 않았다(2026-10-06 최근 사흘 목록에 보인 마감 공고
2,010건). 목록 문구(`~10.31` · `D-7` · `상시채용`)가 새 마감일을 알려 준다.

1. 판정: OPEN · EXPIRED만, 못 읽으면 두고, 같은 날이면 저장값을 지키고, 상시면 비운다.
2. 저장소: 늘린 공고는 OPEN으로 · 마감일과 근거를 고친다. CLOSED · REMOVED · 다른 출처는 그대로.
3. 사람인 목록 줄 → (마감일, 상시인가, 문구). 상세 적재와 같은 파서.
4. 잡코리아는 적재 입력(누적 상세)의 마감일을 고친다 — 저장소만 고치면 적재가 되돌린다.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from job_matching_bot.crawling.nightly import jobkorea_listing_deadline, listing_deadlines
from job_matching_bot.ingestion.job_store import listing_deadline_change
from job_matching_bot.ingestion.listing_conditions import deadline_from_listing, deadline_is_open
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.schemas.job_record import STATUS_CLOSED, STATUS_EXPIRED, STATUS_OPEN, STATUS_REMOVED

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 5, 23, 0, tzinfo=KST)
PAST = "2026-09-30T23:59:59+09:00"
LATER = "2026-10-31T23:59:59+09:00"


class ChangeRuleTest(unittest.TestCase):
    def test_extended_expired_job_reopens(self) -> None:
        self.assertEqual(listing_deadline_change(PAST, STATUS_EXPIRED, LATER, False, NOW), (LATER, STATUS_OPEN))

    def test_open_ended_clears_deadline_and_reopens(self) -> None:
        self.assertEqual(listing_deadline_change(PAST, STATUS_EXPIRED, None, True, NOW), (None, STATUS_OPEN))

    def test_shortened_deadline_that_passed_expires(self) -> None:
        self.assertEqual(listing_deadline_change(LATER, STATUS_OPEN, PAST, False, NOW), (PAST, STATUS_EXPIRED))

    def test_unreadable_listing_leaves_it(self) -> None:
        self.assertIsNone(listing_deadline_change(PAST, STATUS_EXPIRED, None, False, NOW))

    def test_same_day_keeps_stored_time(self) -> None:
        # 상세 페이지의 18:00 마감이 목록의 23:59 보다 정확하다
        self.assertIsNone(listing_deadline_change("2026-10-31T18:00:00+09:00", STATUS_OPEN, LATER, False, NOW))

    def test_one_day_off_relative_text_is_no_change(self) -> None:
        # 자정 넘어 받은 `D-6` 은 하루 늦게 읽힌다 — 같은 마감이다
        self.assertIsNone(
            listing_deadline_change("2026-10-11T23:59:59+09:00", STATUS_OPEN, "2026-10-12T00:30:00+09:00", False, NOW)
        )

    def test_open_ended_with_no_deadline_is_no_change(self) -> None:
        self.assertIsNone(listing_deadline_change(None, STATUS_OPEN, None, True, NOW))

    def test_closed_and_removed_are_left(self) -> None:
        for status in (STATUS_CLOSED, STATUS_REMOVED):
            self.assertIsNone(listing_deadline_change(PAST, status, LATER, False, NOW))


class StoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        store = SqliteJobStore(self.path)
        store.upsert(mock_jobs(), source="MOCK")
        self.ids = sorted(r.job.source_job_id for r in store.all_records())[:3]
        with store.conn:
            for job_id, status in zip(self.ids, (STATUS_EXPIRED, STATUS_EXPIRED, STATUS_CLOSED)):
                store.conn.execute(
                    "UPDATE jobs SET status = %s, deadline = %s, missing_runs = 1 WHERE source_job_id = %s",
                    (status, PAST, job_id),
                )
        store.close()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def row(self, job_id: str) -> dict:
        store = SqliteJobStore(self.path)
        row = store.conn.execute(
            "SELECT status, deadline, missing_runs, field_provenance FROM jobs WHERE source_job_id = %s", (job_id,)
        ).fetchone()
        store.close()
        return dict(row)

    def test_extended_jobs_reopen_and_others_stay(self) -> None:
        extended, unreadable, closed = self.ids
        store = SqliteJobStore(self.path)
        counts = store.refresh_listing_deadlines(
            {
                extended: (LATER, False, "입사지원 ~10.31(토)"),
                unreadable: (None, False, "입사지원"),
                closed: (LATER, False, "입사지원 ~10.31(토)"),
                "없는공고": (LATER, False, "입사지원 ~10.31(토)"),
            },
            NOW,
            source="MOCK",
        )
        store.close()
        self.assertEqual(counts, {"reopened": 1, "changed": 0, "expired": 0})
        row = self.row(extended)
        self.assertEqual((row["status"], row["deadline"], row["missing_runs"]), (STATUS_OPEN, LATER, 0))
        self.assertEqual(row["field_provenance"]["deadline"], {"method": "listing", "evidence": "입사지원 ~10.31(토)"})
        self.assertEqual(self.row(unreadable)["status"], STATUS_EXPIRED)
        self.assertEqual(self.row(closed)["status"], STATUS_CLOSED)

    def test_other_source_is_not_touched(self) -> None:
        store = SqliteJobStore(self.path)
        counts = store.refresh_listing_deadlines({self.ids[0]: (LATER, False, "~10.31")}, NOW, source="SARAMIN_POC")
        store.close()
        self.assertEqual(sum(counts.values()), 0)
        self.assertEqual(self.row(self.ids[0])["status"], STATUS_EXPIRED)


class SaraminListingTest(unittest.TestCase):
    def test_reads_date_days_left_and_open_ended(self) -> None:
        listed = listing_deadlines(
            [
                {"source_job_id": "1", "support_text": "입사지원 ~10.31(토) 31일 전 등록"},
                {"source_job_id": "2", "support_text": "입사지원 D-7 26일 전 등록"},
                {"source_job_id": "3", "support_text": "입사지원 상시채용 47일 전 등록"},
                {"source_job_id": "4", "support_text": ""},
                {"source_job_id": "1", "support_text": "다른 대분류에서 본 같은 공고"},
            ],
            NOW,
        )
        self.assertEqual(listed["1"][:2], ("2026-10-31T23:59:59+09:00", False))
        self.assertEqual(listed["2"][0][:10], "2026-10-12")
        self.assertEqual(listed["3"][:2], (None, True))
        self.assertEqual(listed["4"][:2], (None, False))
        self.assertEqual(listed["1"][2], "입사지원 ~10.31(토) 31일 전 등록")


class JobkoreaInputTest(unittest.TestCase):
    def test_extended_deadline_replaces_stored(self) -> None:
        self.assertEqual(jobkorea_listing_deadline("2026-09-30T23:59", "~10/31 (토)", NOW), LATER)

    def test_same_day_and_unreadable_keep_stored(self) -> None:
        self.assertIsNone(jobkorea_listing_deadline("2026-10-31T23:59", "~10/31 (토)", NOW))
        self.assertIsNone(jobkorea_listing_deadline("2026-09-30T23:59", "", NOW))

    def test_open_ended_clears(self) -> None:
        self.assertEqual(jobkorea_listing_deadline("2026-09-30T23:59", "상시채용", NOW), "")


class ListingParserTest(unittest.TestCase):
    def test_days_left(self) -> None:
        self.assertEqual(deadline_from_listing("입사지원 D-7", date(2026, 10, 5)), "2026-10-12T23:59:59+09:00")

    def test_date_wins_over_days_left(self) -> None:
        self.assertEqual(deadline_from_listing("~10.31(토) D-26", date(2026, 10, 5)), LATER)

    def test_open_ended(self) -> None:
        self.assertTrue(deadline_is_open("상시채용"))
        self.assertFalse(deadline_is_open("~10.31"))
        self.assertFalse(deadline_is_open(""))


if __name__ == "__main__":
    unittest.main()
