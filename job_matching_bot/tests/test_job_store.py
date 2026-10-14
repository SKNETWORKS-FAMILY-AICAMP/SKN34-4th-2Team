"""수집 저장소의 upsert와 상태 전이 검증.

핵심은 "관측되지 않았다"와 "사라졌다"를 구분하는 것이다. 수집이 한 번
실패했다고 저장된 공고 전체가 삭제 처리되면 안 된다.
"""

import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from job_matching_bot.ingestion.record_files import latest_by_id, read_records
from job_matching_bot.config import DEFAULT_SARAMIN_INPUT
from job_matching_bot.ingest import ingest
from job_matching_bot.ingestion import raw_store
from job_matching_bot.ingestion.job_store import reconcile, resolve_status
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.saramin import normalize_saramin
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.schemas.job_record import (
    STATUS_EXPIRED,
    STATUS_OPEN,
    STATUS_REMOVED,
    JobRecord,
)
from job_matching_bot.tests import AS_OF, saramin_records


def _store_from(jobs, source="MOCK", as_of=AS_OF):
    records, _ = reconcile({}, jobs, source=source, as_of=as_of)
    return records


class UpsertTest(unittest.TestCase):
    def setUp(self):
        self.jobs = mock_jobs()

    def test_first_collection_registers_every_job(self):
        records, report = reconcile({}, self.jobs, source="MOCK")
        self.assertEqual(len(self.jobs), len(records))
        self.assertEqual(len(self.jobs), len(report.new))
        self.assertEqual([], report.updated)

    def test_recollecting_same_content_does_not_count_as_update(self):
        first = _store_from(self.jobs)
        later = AS_OF + timedelta(days=1)
        second, report = reconcile(first, self.jobs, source="MOCK", as_of=later)

        self.assertEqual([], report.new)
        self.assertEqual([], report.updated)
        self.assertEqual(len(self.jobs), len(report.unchanged))
        # 처음 본 시각은 유지되고 마지막 확인 시각만 움직인다.
        record = second[("MOCK", "MOCK-BE-001")]
        self.assertEqual(AS_OF.isoformat(), record.first_seen_at)
        self.assertEqual(later.isoformat(), record.last_seen_at)
        self.assertEqual(0, record.revisions)

    def test_changed_content_is_recorded_as_revision(self):
        first = _store_from(self.jobs)
        changed = [
            replace(job, content_hash="sha256:changed", title=f"{job.title} (수정)")
            if job.job_id == "MOCK-BE-001"
            else job
            for job in self.jobs
        ]
        second, report = reconcile(first, changed, source="MOCK")

        self.assertEqual(["MOCK-BE-001"], report.updated)
        record = second[("MOCK", "MOCK-BE-001")]
        self.assertEqual(1, record.revisions)
        self.assertIn("(수정)", record.job.title)


class StatusTransitionTest(unittest.TestCase):
    def setUp(self):
        self.jobs = mock_jobs()
        self.kept = [job for job in self.jobs if job.job_id != "MOCK-BE-001"]

    def test_single_miss_keeps_status_and_is_reported(self):
        first = _store_from(self.jobs)
        second, report = reconcile(first, self.kept, source="MOCK")

        # 수집 실패일 수 있으므로 한 번 안 보였다고 삭제하지 않는다.
        self.assertEqual(["MOCK-BE-001"], report.still_missing)
        self.assertEqual([], report.removed)
        record = second[("MOCK", "MOCK-BE-001")]
        self.assertEqual(STATUS_OPEN, record.status)
        self.assertEqual(1, record.missing_runs)

    def test_repeated_miss_marks_removed(self):
        store = _store_from(self.jobs)
        store, _ = reconcile(store, self.kept, source="MOCK")
        store, report = reconcile(store, self.kept, source="MOCK")

        self.assertEqual(["MOCK-BE-001"], report.removed)
        record = store[("MOCK", "MOCK-BE-001")]
        self.assertEqual(STATUS_REMOVED, record.status)
        # 삭제 처리해도 레코드 자체는 남는다.
        self.assertIn(("MOCK", "MOCK-BE-001"), store)

    def test_reappearing_job_returns_to_open(self):
        store = _store_from(self.jobs)
        store, _ = reconcile(store, self.kept, source="MOCK")
        store, _ = reconcile(store, self.kept, source="MOCK")
        self.assertEqual(STATUS_REMOVED, store[("MOCK", "MOCK-BE-001")].status)

        store, report = reconcile(store, self.jobs, source="MOCK")
        record = store[("MOCK", "MOCK-BE-001")]
        self.assertEqual(STATUS_OPEN, record.status)
        self.assertEqual(0, record.missing_runs)
        self.assertIn("MOCK-BE-001", report.unchanged)

    def test_deadline_passed_marks_expired_even_without_observation(self):
        store = _store_from(self.jobs)
        # Mock 공고 마감일(2026-09-30) 이후 시점
        later = AS_OF + timedelta(days=60)
        store, report = reconcile(store, [], source="MOCK", as_of=later)

        self.assertEqual(len(self.jobs), len(report.expired))
        self.assertEqual([], report.removed)
        for record in store.values():
            self.assertEqual(STATUS_EXPIRED, record.status)

    def test_other_source_jobs_are_not_marked_missing(self):
        other = [
            replace(job, source="OTHER", job_id=f"OTHER-{job.source_job_id}")
            for job in self.jobs
        ]
        store, _ = reconcile({}, other + self.jobs, source="MOCK")
        # 이번 수집은 MOCK만 책임진다. 다른 소스 공고는 대상이 아니다.
        store, report = reconcile(store, [], source="MOCK")

        self.assertEqual(len(self.jobs), len(report.still_missing))
        for job in other:
            self.assertNotIn(job.job_id, report.still_missing)
            self.assertEqual(0, store[(job.source, job.source_job_id)].missing_runs)

    def test_resolve_status_uses_deadline(self):
        job = mock_jobs()[0]
        self.assertEqual(STATUS_OPEN, resolve_status(job, AS_OF))
        self.assertEqual(STATUS_EXPIRED, resolve_status(job, AS_OF + timedelta(days=60)))


class QualityReportTest(unittest.TestCase):
    def test_missing_required_fields_are_reported(self):
        broken = replace(mock_jobs()[0], company="", source_url="")
        _, report = reconcile({}, [broken], source="MOCK")

        self.assertIn("MOCK-BE-001", report.missing_fields)
        self.assertEqual(["company", "source_url"], report.missing_fields["MOCK-BE-001"])

    def test_parser_versions_are_counted(self):
        _, report = reconcile({}, mock_jobs(), source="MOCK")
        self.assertEqual({"mock-0.1.0": 3}, report.parser_versions)


class PersistenceTest(unittest.TestCase):
    def test_store_round_trips_through_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "store.sqlite"
            with SqliteJobStore(path) as store:
                store.upsert(mock_jobs(), source="MOCK")
                original = store.get("MOCK-BE-001")

            with SqliteJobStore(path) as reloaded:
                self.assertEqual(len(mock_jobs()), reloaded.count())
                self.assertEqual(original.to_dict(), reloaded.get("MOCK-BE-001").to_dict())

    def test_active_jobs_exclude_expired_and_removed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with SqliteJobStore(Path(temp_dir) / "store.sqlite") as store:
                store.upsert(mock_jobs(), source="MOCK")
                self.assertEqual(3, len(store.active_jobs()))

                store.upsert([], source="MOCK", as_of=AS_OF + timedelta(days=60))
                self.assertEqual([], store.active_jobs())
                # 만료돼도 레코드는 남아 있다.
                self.assertEqual(3, store.stats()["total"])


class RawStoreTest(unittest.TestCase):
    def setUp(self):
        self.records = saramin_records(3)

    def test_ingest_preserves_raw_and_populates_store(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = ingest(
                self.records,
                source="SARAMIN_POC",
                store_path=root / "store.sqlite",
                raw_root=root / "job_raw",
            )
            self.assertEqual(len(self.records), len(report.new))

            saved = raw_store.load_raw(root / "job_raw", "SARAMIN_POC")
            self.assertEqual(len(self.records), len(saved))
            self.assertTrue(all(item["parse_status"] == "OK" for item in saved))
            self.assertEqual([], raw_store.failed_raw(root / "job_raw"))

    def test_saved_raw_can_be_reparsed_without_recollecting(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ingest(
                self.records,
                source="SARAMIN_POC",
                store_path=root / "store.sqlite",
                raw_root=root / "job_raw",
            )
            parsed, failures = raw_store.reparse(root / "job_raw", normalize_saramin)
            self.assertEqual(len(self.records), len(parsed))
            self.assertEqual([], failures)

    def test_reparse_reports_failures_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            raw_store.save_raw(root, "MOCK", "broken", {"list_item": "잘못된 형식"})
            parsed, failures = raw_store.reparse(root, normalize_saramin)
            self.assertEqual([], parsed)
            self.assertEqual(1, len(failures))
            self.assertIn("parse_error", failures[0])

    def test_source_job_id_cannot_escape_the_raw_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            path = raw_store.save_raw(root, "MOCK", "../../escape", {"a": 1})
            self.assertTrue(path.resolve().is_relative_to(root.resolve()))


class RecordSerializationTest(unittest.TestCase):
    def test_record_survives_dict_round_trip(self):
        record = JobRecord(
            job=mock_jobs()[0],
            first_seen_at=AS_OF.isoformat(),
            last_seen_at=AS_OF.isoformat(),
            status=STATUS_OPEN,
            missing_runs=1,
            revisions=2,
        )
        restored = JobRecord.from_dict(record.to_dict())
        self.assertEqual(record.to_dict(), restored.to_dict())
        self.assertEqual(record.job.required_skills, restored.job.required_skills)


class SaraminIngestTest(unittest.TestCase):
    """사람인 수집본이 같은 저장소 경로를 탄다. 실제 크롤 결과가 있을 때만 돈다."""

    @classmethod
    def setUpClass(cls):
        cls.records = (
            list(latest_by_id(read_records(DEFAULT_SARAMIN_INPUT)).values())
        )

    def test_saramin_records_enter_store_with_tech_stack(self):
        if not self.records:
            self.skipTest("사람인 수집본 없음")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = ingest(
                self.records,
                source="SARAMIN_POC",
                store_path=root / "store.sqlite",
                raw_root=root / "job_raw",
            )
            self.assertEqual(len(self.records), len(report.new))
            self.assertEqual({}, report.missing_fields)

            # 저장 → 다시 읽어도 기술스택이 살아 있어야 랭킹이 쓸 수 있다.
            with SqliteJobStore(root / "store.sqlite") as store:
                reloaded = [record.job for record in store.all_records()]
            self.assertTrue(any(job.tech_stack for job in reloaded))
            self.assertTrue(all(job.job_id.startswith("SARAMIN-") for job in reloaded))

    def test_second_run_is_idempotent(self):
        if not self.records:
            self.skipTest("사람인 수집본 없음")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            kwargs = dict(source="SARAMIN_POC", store_path=root / "store.sqlite", raw_root=root / "job_raw")
            ingest(self.records, **kwargs)
            report = ingest(self.records, **kwargs)
            self.assertEqual(len(self.records), len(report.unchanged))
            self.assertEqual([], report.new)
            self.assertEqual([], report.removed)

    def test_sources_do_not_expire_each_other(self):
        # 한 소스만 수집한 날 다른 소스 공고가 안 보인 것은 삭제가 아니다.
        if not self.records:
            self.skipTest("사람인 수집본 없음")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with SqliteJobStore(root / "store.sqlite") as store:
                store.upsert(mock_jobs(), source="MOCK")
            report = ingest(
                self.records, source="SARAMIN_POC",
                store_path=root / "store.sqlite", raw_root=root / "job_raw",
            )
            self.assertEqual([], report.removed)
            self.assertEqual([], report.still_missing)
            with SqliteJobStore(root / "store.sqlite") as store:
                self.assertEqual(len(mock_jobs()) + len(self.records), store.stats()["total"])
                self.assertEqual(0, store.get("MOCK-BE-001").missing_runs)


if __name__ == "__main__":
    unittest.main()
