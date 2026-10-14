"""닫힌 지 오래된 공고 지우기 — 무엇을 지우고 무엇을 남기나.

1. 닫힌 지 15일이 지난 것만. EXPIRED 는 마감일, REMOVED · CLOSED 는 마지막으로 본 날로 센다.
2. 열린 공고 · 15일 안쪽은 남긴다.
3. 첨삭 중인 공고(맞춤 이력서가 가리키는 공고)는 닫혀도 남긴다.
4. 아직 Pinecone 에 올라가 있는 공고는 남긴다 — 밤 인덱스가 벡터를 먼저 지운다.
5. 잡코리아 누적 상세에서 지운 공고 줄만 뺀다. --apply 가 아니면 파일을 건드리지 않는다.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot import prune
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.retrieval.store_search import KST

NOW = datetime(2026, 10, 6, 17, 0, tzinfo=KST)


def day(n: int) -> str:
    return (NOW - timedelta(days=n)).isoformat()


class CandidatesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        base = mock_jobs()[0]
        rows = {
            "OLD-EXPIRED": ("EXPIRED", day(20)[:10], day(25), None),
            "NEW-EXPIRED": ("EXPIRED", day(10)[:10], day(12), None),
            "OLD-REMOVED": ("REMOVED", None, day(16), None),
            "NEW-REMOVED": ("REMOVED", None, day(3), None),
            "OLD-OPEN": ("OPEN", None, day(40), None),
            "LINKED": ("EXPIRED", day(30)[:10], day(30), None),
            "STILL-INDEXED": ("CLOSED", None, day(20), "sha256:x"),
        }
        jobs = [replace(base, job_id=k, source_job_id=k, deadline=v[1], status=v[0]) for k, v in rows.items()]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")
            with store.conn:
                for k, (status, deadline, seen, indexed) in rows.items():
                    store.conn.execute(
                        "UPDATE jobs SET status = %s, deadline = %s, last_seen_at = %s, indexed_embed_hash = %s WHERE job_id = %s",
                        (status, deadline, seen, indexed, k),
                    )

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_closed_for_more_than_15_days(self):
        with SqliteJobStore(self.path) as store:
            found = prune.job_candidates(store.conn, NOW, 15, protect={"LINKED"})
        self.assertEqual({"OLD-EXPIRED", "OLD-REMOVED"}, {row["job_id"] for row in found})

    def test_linked_jobs_are_kept_only_while_protected(self):
        with SqliteJobStore(self.path) as store:
            found = prune.job_candidates(store.conn, NOW, 15, protect=set())
        self.assertIn("LINKED", {row["job_id"] for row in found})

    def test_rows_still_in_the_index_are_kept(self):
        with SqliteJobStore(self.path) as store:
            found = prune.job_candidates(store.conn, NOW, 15, protect=set())
        self.assertNotIn("STILL-INDEXED", {row["job_id"] for row in found})


class ListingCandidatesTest(unittest.TestCase):
    def test_unseen_or_long_past_deadline(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "store.sqlite"
        with SqliteJobStore(path) as store:
            store.record_list_jobs(
                [{"source_job_id": i, "company": "가", "title": "영업", "support_text": "", "condition_text": ""}
                 for i in ("SEEN", "UNSEEN", "PAST")],
                NOW, source="MOCK",
            )
            with store.conn:
                store.conn.execute("UPDATE list_jobs SET seen_at = %s WHERE source_job_id = 'UNSEEN'", (day(20),))
                store.conn.execute("UPDATE list_jobs SET deadline = %s WHERE source_job_id = 'PAST'", (day(16),))
            found = prune.listing_candidates(store.conn, NOW, 15)
        self.assertEqual({"UNSEEN", "PAST"}, {row["source_job_id"] for row in found})


class JobkoreaFileTest(unittest.TestCase):
    def test_drops_only_removed_lines_and_only_on_apply(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "details.jsonl"
        path.write_text("".join(json.dumps({"source_job_id": i}) + "\n" for i in ("1", "2", "3")), encoding="utf-8")
        backup = Path(tmp.name) / "backup.jsonl"

        self.assertEqual((3, 1), prune.prune_jobkorea_file(path, {"2"}, backup, apply=False))
        self.assertEqual(3, len(path.read_text(encoding="utf-8").splitlines()), "세기만 할 때는 파일을 안 바꾼다")

        self.assertEqual((3, 1), prune.prune_jobkorea_file(path, {"2"}, backup, apply=True))
        left = [json.loads(line)["source_job_id"] for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["1", "3"], left)
        self.assertEqual([{"source_job_id": "2"}], [json.loads(line) for line in backup.read_text(encoding="utf-8").splitlines()], "뺀 줄만 백업한다")


if __name__ == "__main__":
    unittest.main()
