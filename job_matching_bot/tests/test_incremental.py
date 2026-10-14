"""증분 수집 검증 — 파일 입출력, 목록 관측 의미론, 대상 선정.

증분 수집의 핵심 약속은 하나다: **목록에서 보인 공고를 상세를 다시 받지
않았다는 이유로 사라졌다고 판단하지 않는다.** 이게 깨지면 매일 돌릴 때마다
기존 공고가 전부 REMOVED가 된다.
"""

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from job_matching_bot.ingest import ingest
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.ingestion.record_files import append_record, read_records, record_ids
from job_matching_bot.schemas.job_record import STATUS_OPEN, STATUS_REMOVED
from job_matching_bot.tests import AS_OF, saramin_records

from job_matching_bot.crawling.crawl_detail import fresh_raw_ids, plan_targets
from job_matching_bot.crawling.crawl_list import pages_for
from job_matching_bot.crawling.http_session import (
    CLIENT_HINTS,
    SESSION_HEADERS,
    USER_AGENT,
    navigation_headers,
    xhr_headers,
)


class RecordFilesTest(unittest.TestCase):
    def test_reads_json_array_and_jsonl_alike(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a.json").write_text('[{"source_job_id": "1"}]', encoding="utf-8")
            append_record(root / "b.jsonl", {"source_job_id": "2"})
            append_record(root / "b.jsonl", {"source_job_id": "3"})
            self.assertEqual(["1"], [r["source_job_id"] for r in read_records(root / "a.json")])
            self.assertEqual(["2", "3"], [r["source_job_id"] for r in read_records(root / "b.jsonl")])
            self.assertEqual([], read_records(root / "missing.jsonl"))

    def test_unicode_line_separator_inside_a_record_does_not_split_it(self):
        # 사람인 본문에 U+2028(LINE SEPARATOR)이 들어 있는 공고가 실제로 있다.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "u.jsonl"
            append_record(path, {"source_job_id": "1", "description": "앞 뒤끝"})
            append_record(path, {"source_job_id": "2"})
            records = read_records(path)
            self.assertEqual(["1", "2"], [r["source_job_id"] for r in records])
            self.assertIn(" ", records[0]["description"])

    def test_truncated_last_line_is_skipped_not_fatal(self):
        # 크롤러를 Ctrl+C로 끊으면 마지막 줄이 반쯤 써진 채 남는다.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "c.jsonl"
            path.write_text('{"source_job_id": "1"}\n{"source_job_id": "2", "desc": "잘린', encoding="utf-8")
            self.assertEqual(["1"], [r["source_job_id"] for r in read_records(path)])

    def test_ids_are_found_at_top_level_or_inside_list_item(self):
        records = [{"source_job_id": "1"}, {"list_item": {"source_job_id": "2"}}, {}]
        self.assertEqual({"1", "2"}, record_ids(records))


class ObservedSemanticsTest(unittest.TestCase):
    """목록에서 본 공고는 상세 없이도 살아 있다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "store.sqlite")
        self.store.upsert(mock_jobs(as_of=AS_OF), source="MOCK", as_of=AS_OF)

    def tearDown(self):
        # Windows는 열린 SQLite 파일을 못 지운다. 연결을 먼저 닫는다.
        self.store.close()
        self.temp.cleanup()

    def test_observed_but_not_collected_stays_open(self):
        store = self.store
        ids = {record.job.source_job_id for record in store.all_records()}
        later = AS_OF + timedelta(days=1)
        # 상세는 하나도 안 받았지만 목록에서는 전부 봤다.
        report = store.upsert([], source="MOCK", as_of=later, observed_ids=ids)
        # 전부 목록에서 봤으니 미관측은 없고, 만료가 아닌 것은 전부 observed다.
        self.assertEqual(len(ids), len(report.observed) + len(report.expired))
        self.assertEqual([], report.still_missing)
        self.assertEqual([], report.removed)
        for record in store.all_records():
            if record.job.deadline is None or record.status == STATUS_OPEN:
                self.assertEqual(later.isoformat(), record.last_seen_at)
                self.assertEqual(0, record.missing_runs)

    def test_unobserved_jobs_still_go_missing(self):
        store = self.store
        first = store.all_records()[0].job.source_job_id
        later = AS_OF + timedelta(days=1)
        # 목록에서 하나만 봤다. 나머지는 미관측으로 세어야 한다.
        report = store.upsert([], source="MOCK", as_of=later, observed_ids={first})
        self.assertEqual(1, len(report.observed))
        self.assertTrue(report.still_missing or report.expired)

    def test_removed_job_reappearing_in_listing_is_reopened(self):
        store = self.store
        # 마감 전인 공고를 삭제 처리해 두고 목록에 다시 나타나게 한다.
        target = store.all_records()[0]
        store.put(replace(target, status=STATUS_REMOVED))
        report = store.upsert(
            [], source="MOCK", as_of=AS_OF + timedelta(days=1),
            observed_ids={target.job.source_job_id},
        )
        self.assertIn(target.job.job_id, report.observed)
        self.assertEqual(STATUS_OPEN, store.get(target.job.job_id).status)

    def test_without_observed_ids_behaviour_is_unchanged(self):
        # 전량 수집(예전 방식)은 그대로 동작해야 한다.
        report = self.store.upsert([], source="MOCK", as_of=AS_OF + timedelta(days=1))
        self.assertEqual([], report.observed)
        self.assertTrue(report.still_missing or report.expired)

    def test_ingest_adds_collected_ids_to_observed_set(self):
        # 이번에 상세를 받은 공고는 목록 파일에 없어도 관측된 것이다.
        records = saramin_records(3)
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            common = dict(source="SARAMIN_POC", store_path=root / "s.sqlite", raw_root=root / "raw")
            ingest(records, **common)
            report = ingest(records[:1], observed_ids=set(), **common)
            # 첫 건은 다시 받았고(변경없음), 나머지는 목록에 없으니 미관측이다.
            self.assertEqual(1, len(report.unchanged))
            self.assertEqual(len(records) - 1, len(report.still_missing) + len(report.expired))


class BrowserLikeHeadersTest(unittest.TestCase):
    """요청이 실제 Chrome 세션처럼 보이는지. 회피가 아니라 정상 사용자 흐름을 따르는 것이다."""

    def test_user_agent_is_fixed_and_client_hints_match_it(self):
        self.assertIn("Chrome/131", USER_AGENT)
        self.assertIn('v="131"', CLIENT_HINTS["sec-ch-ua"])
        self.assertEqual(USER_AGENT, SESSION_HEADERS["User-Agent"])
        self.assertIn("sec-ch-ua-platform", SESSION_HEADERS)

    def test_document_navigation_headers(self):
        headers = navigation_headers("https://www.saramin.co.kr/zf_user/jobs/list/job-category")
        self.assertEqual("navigate", headers["Sec-Fetch-Mode"])
        self.assertEqual("document", headers["Sec-Fetch-Dest"])
        self.assertEqual("same-origin", headers["Sec-Fetch-Site"])
        self.assertEqual("1", headers["Upgrade-Insecure-Requests"])
        self.assertTrue(headers["Accept"].startswith("text/html"))
        # 첫 진입(리퍼러 없음)은 Sec-Fetch-Site: none 이어야 한다.
        self.assertEqual("none", navigation_headers()["Sec-Fetch-Site"])

    def test_xhr_headers_look_like_in_page_script(self):
        headers = xhr_headers("https://www.saramin.co.kr/zf_user/jobs/list/job-category")
        self.assertEqual("XMLHttpRequest", headers["X-Requested-With"])
        self.assertEqual("cors", headers["Sec-Fetch-Mode"])
        self.assertEqual("empty", headers["Sec-Fetch-Dest"])
        self.assertIn("application/json", headers["Accept"])
        self.assertIn("Referer", headers)


class PlanTargetsTest(unittest.TestCase):
    def _listing(self, *ids, url_suffix=""):
        return [
            {"source_job_id": i, "source_url": f"https://www.saramin.co.kr/zf_user/jobs/relay/view?rec_idx={i}{url_suffix}"}
            for i in ids
        ]

    def test_skips_done_fresh_and_robots_blocked(self):
        listings = self._listing("1", "2", "3", "4") + self._listing(
            "5", url_suffix="&innerCampaign=headhuntingView"
        )
        targets, skipped = plan_targets(
            listings, done_ids={"1"}, fresh_ids={"2"}, limit=None
        )
        self.assertEqual(["3", "4"], [t["source_job_id"] for t in targets])
        self.assertEqual(1, skipped["already_in_output"])
        self.assertEqual(1, skipped["fresh_in_raw"])
        self.assertEqual(1, skipped["robots"])

    def test_limit_and_duplicates(self):
        listings = self._listing("1", "1", "2", "3")
        targets, _ = plan_targets(listings, done_ids=set(), fresh_ids=set(), limit=2)
        self.assertEqual(["1", "2"], [t["source_job_id"] for t in targets])

    def test_pages_for_total_count(self):
        self.assertEqual(1, pages_for(0))
        self.assertEqual(1, pages_for(50))
        self.assertEqual(2, pages_for(51))
        self.assertEqual(238, pages_for(11_880))

    def test_fresh_raw_ids_respects_refresh_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            base = root / "SARAMIN_POC"
            base.mkdir()
            now = AS_OF
            recent = {"source_job_id": "10", "fetched_at": (now - timedelta(days=2)).isoformat()}
            stale = {"source_job_id": "11", "fetched_at": (now - timedelta(days=30)).isoformat()}
            (base / "10.json").write_text(json.dumps(recent), encoding="utf-8")
            (base / "11.json").write_text(json.dumps(stale), encoding="utf-8")
            self.assertEqual({"10"}, fresh_raw_ids(root, refresh_days=7, now=now))
            self.assertEqual(set(), fresh_raw_ids(root / "nope", refresh_days=7, now=now))


if __name__ == "__main__":
    unittest.main()
