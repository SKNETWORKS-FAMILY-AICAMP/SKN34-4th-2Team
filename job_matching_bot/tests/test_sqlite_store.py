"""SQLite 저장소가 판정 규칙(`job_store.reconcile`)과 같은 판정을 내리는지 대조한다.

규칙과 저장소를 같은 입력으로 돌려 리포트와 상태를 비교한다. 규칙을 한쪽만 고치면
여기서 깨진다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path

from job_matching_bot.ingestion.job_store import open_store, reconcile
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore, is_sqlite_path
from job_matching_bot.schemas.job_record import STATUS_EXPIRED, STATUS_OPEN, STATUS_REMOVED
from job_matching_bot.tests import AS_OF


def _report_view(report):
    return {
        "new": sorted(report.new), "updated": sorted(report.updated), "unchanged": sorted(report.unchanged),
        "expired": sorted(report.expired), "removed": sorted(report.removed),
        "still_missing": sorted(report.still_missing), "observed": sorted(report.observed),
    }


def _status_view(records):
    return {r.job.job_id: (r.status, r.missing_runs, r.revisions) for r in records}


class SqliteVersusRulesTest(unittest.TestCase):
    """같은 시나리오를 규칙과 저장소에 돌리고 결과가 같은지 본다."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "store.sqlite")
        self.jobs = mock_jobs()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _both(self, steps):
        """steps: [(collected, kwargs)] 를 두 구현에 순서대로 적용하고 (리포트들, 상태) 쌍을 돌려준다."""
        json_records = {}
        json_reports, sqlite_reports = [], []
        for collected, kwargs in steps:
            json_records, report = reconcile(json_records, collected, **kwargs)
            json_reports.append(_report_view(report))
            sqlite_reports.append(_report_view(self.store.upsert(collected, **kwargs)))
        return (json_reports, _status_view(json_records.values())), (sqlite_reports, _status_view(self.store.all_records()))

    def test_first_collection_matches(self):
        a, b = self._both([(self.jobs, dict(source="MOCK"))])
        self.assertEqual(a, b)
        self.assertEqual(len(self.jobs), self.store.count())

    def test_recollect_unchanged_and_changed(self):
        changed = [replace(self.jobs[0], description=self.jobs[0].description + " 수정", content_hash="sha256:changed")]
        a, b = self._both([
            (self.jobs, dict(source="MOCK")),
            (changed + self.jobs[1:], dict(source="MOCK", as_of=AS_OF + timedelta(days=1))),
        ])
        self.assertEqual(a, b)
        self.assertEqual(1, self.store.get(self.jobs[0].job_id).revisions)

    def test_missing_then_removed_after_limit(self):
        later = AS_OF + timedelta(days=1)
        a, b = self._both([
            (self.jobs, dict(source="MOCK")),
            (self.jobs[1:], dict(source="MOCK", as_of=later)),
            (self.jobs[1:], dict(source="MOCK", as_of=later + timedelta(days=1))),
        ])
        self.assertEqual(a, b)
        self.assertEqual(STATUS_REMOVED, self.store.get(self.jobs[0].job_id).status)

    def test_observed_in_listing_keeps_and_revives(self):
        later = AS_OF + timedelta(days=1)
        gone = self.jobs[0]
        a, b = self._both([
            (self.jobs, dict(source="MOCK")),
            ([], dict(source="MOCK", as_of=later, missing_run_limit=1)),                       # 전부 REMOVED
            ([], dict(source="MOCK", as_of=later, observed_ids={gone.source_job_id})),         # 하나만 목록에서 봄 → 부활
        ])
        self.assertEqual(a, b)
        self.assertEqual(STATUS_OPEN, self.store.get(gone.job_id).status)

    def test_expired_by_deadline(self):
        expiring = replace(self.jobs[0], deadline=(AS_OF - timedelta(days=1)).isoformat())
        a, b = self._both([
            ([expiring] + self.jobs[1:], dict(source="MOCK")),
            (self.jobs[1:], dict(source="MOCK", as_of=AS_OF + timedelta(days=1))),
        ])
        self.assertEqual(a, b)
        self.assertEqual(STATUS_EXPIRED, self.store.get(expiring.job_id).status)

    def test_refetch_without_listing_keeps_title_company_and_deadline(self):
        """번호만 들고 상세를 다시 받으면 목록 값이 비어 온다. 저장된 값을 지우면 안 된다.

        2026-09-11에 328건을 그렇게 다시 받아 313건의 제목·회사명·마감일이 빈 값으로 덮였다.
        """
        target = replace(self.jobs[0], deadline=(AS_OF + timedelta(days=10)).isoformat())
        blank = replace(target, company="", title="", deadline=None, content_hash="sha256:refetched")
        a, b = self._both([
            ([target] + self.jobs[1:], dict(source="MOCK")),
            ([blank], dict(source="MOCK", as_of=AS_OF + timedelta(days=1), observed_ids={j.source_job_id for j in self.jobs})),
        ])
        self.assertEqual(a, b)
        kept = self.store.get(target.job_id).job
        self.assertEqual((target.company, target.title, target.deadline), (kept.company, kept.title, kept.deadline))
        # 본문 쪽 변경(다시 파싱한 내용)은 그대로 들어온다.
        self.assertEqual("sha256:refetched", kept.content_hash)

    def test_a_real_listing_still_replaces_the_title(self):
        """목록 값이 있으면 바뀐 제목이 들어간다. 막는 것은 **둘 다 빈** 경우뿐이다."""
        renamed = replace(self.jobs[0], title="새 제목", content_hash="sha256:renamed")
        self.store.upsert(self.jobs, source="MOCK")
        self.store.upsert([renamed] + self.jobs[1:], source="MOCK", as_of=AS_OF + timedelta(days=1))
        self.assertEqual("새 제목", self.store.get(renamed.job_id).job.title)

    def test_other_source_is_not_touched(self):
        other = [replace(j, source="OTHER", job_id=f"OTHER:{j.source_job_id}") for j in self.jobs[:2]]
        a, b = self._both([
            (self.jobs + other, dict(source="MOCK")),
            ([], dict(source="MOCK", as_of=AS_OF + timedelta(days=1), missing_run_limit=1)),
        ])
        self.assertEqual(a, b)
        for job in other:
            self.assertEqual(STATUS_OPEN, self.store.get(job.job_id).status)


class UnchangedFastPathTest(unittest.TestCase):
    """변경 없는 공고는 통째로 다시 쓰지 않고 생애주기만 고친다 — RDS 에서 누적 상세를 매일 다시 쓰던 것."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "store.sqlite")
        self.jobs = mock_jobs()
        self.writes: list[str] = []
        original = self.store._write_record

        def counting(record):
            self.writes.append(record.job.job_id)
            original(record)

        self.store._write_record = counting

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_unchanged_is_not_rewritten_but_last_seen_moves(self):
        self.store.upsert(self.jobs, source="MOCK")
        self.writes.clear()
        later = AS_OF + timedelta(hours=12)
        report = self.store.upsert(self.jobs, source="MOCK", as_of=later)
        self.assertEqual([], self.writes)
        self.assertEqual(sorted(j.job_id for j in self.jobs), sorted(report.unchanged))
        record = self.store.get(self.jobs[0].job_id)
        self.assertEqual(later.isoformat(), record.last_seen_at)
        self.assertEqual((0, 0), (record.missing_runs, record.revisions))

    def test_new_parser_version_rewrites(self):
        self.store.upsert(self.jobs, source="MOCK")
        self.writes.clear()
        reparsed = [replace(self.jobs[0], parser_version=f"{self.jobs[0].parser_version}+next")] + self.jobs[1:]
        self.store.upsert(reparsed, source="MOCK", as_of=AS_OF + timedelta(hours=12))
        self.assertEqual([self.jobs[0].job_id], self.writes)
        self.assertEqual(reparsed[0].parser_version, self.store.get(self.jobs[0].job_id).job.parser_version)

    def test_deadline_passing_still_expires_without_rewrite(self):
        soon = replace(self.jobs[0], deadline=(AS_OF + timedelta(days=1)).isoformat())
        self.store.upsert([soon], source="MOCK")
        self.writes.clear()
        self.store.upsert([soon], source="MOCK", as_of=AS_OF + timedelta(days=3))
        self.assertEqual([], self.writes)
        self.assertEqual(STATUS_EXPIRED, self.store.get(soon.job_id).status)


class RoundTripTest(unittest.TestCase):
    def test_every_field_survives(self):
        # Windows는 열린 SQLite 파일을 못 지운다. 실패해도 연결을 닫도록 with로 감싼다.
        with tempfile.TemporaryDirectory() as temp, SqliteJobStore(Path(temp) / "s.sqlite") as store:
            job = replace(
                mock_jobs()[0],
                tech_stack=["Python", "FastAPI"], keywords=["백엔드/서버개발"],
                required_majors=["컴퓨터·소프트웨어"], required_major_terms=["컴퓨터"],
                # True와 False를 하나씩 둔다. 둘 다 True면 '0'이 True로 읽히는 버그를 못 잡는다.
                required_certifications=["정보처리기사"], military_required=True, body_is_image=False,
                min_career_years=3, field_provenance={"career": {"method": "detail_dl", "evidence": "경력 3년"}},
            )
            store.upsert([job], source="MOCK")
            back = store.get(job.job_id).job
            self.assertEqual(asdict(replace(job, status=STATUS_OPEN)), asdict(back))
            tags = {(r["kind"], r["value"]) for r in store.conn.execute("SELECT kind, value FROM job_tags")}
            self.assertIn(("tech_stack", "FastAPI"), tags)
            self.assertIn(("keywords", "백엔드/서버개발"), tags)
            self.assertEqual(1, store.stats()["by_status"][STATUS_OPEN])
            self.assertEqual([job.job_id], [j.job_id for j in store.active_jobs()])

    def test_legacy_image_flag_with_requirement_text_is_repaired_on_read(self):
        """구 수집본의 잘못된 이미지 플래그가 추천 카드까지 전파되지 않는다."""
        with tempfile.TemporaryDirectory() as temp, SqliteJobStore(Path(temp) / "s.sqlite") as store:
            job = replace(
                mock_jobs()[0],
                description="주요업무 " + "Python 기반 데이터 분석과 API 개발을 수행합니다. " * 12,
                body_is_image=True,
            )
            store.upsert([job], source="MOCK")
            self.assertFalse(store.get(job.job_id).job.body_is_image)

    def test_open_store_rejects_non_sqlite_paths(self):
        # JSON 파일 저장소는 없앴다. 예전 경로를 넘기면 조용히 새 파일을 만들지 않고 멈춘다.
        self.assertTrue(is_sqlite_path(Path("x/store.sqlite")))
        self.assertFalse(is_sqlite_path(Path("x/store.json")))
        with self.assertRaises(ValueError):
            open_store(Path("x/store.json"))


if __name__ == "__main__":
    unittest.main()


class RefreshTest(unittest.TestCase):
    """파서를 고친 뒤 몇백 건만 다시 파싱해 덮어쓰는 통로.

    `upsert`로 이 일을 하면 안 된다. `upsert`는 이번 목록에 없는 공고를 전부
    "안 보임" 한 번으로 세고, 그것이 쌓이면 REMOVED로 넘어간다. 다시 파싱하는
    일은 크롤 한 바퀴가 아니므로 그 셈에 넣으면 안 된다. 실제로 사람인 파싱을
    고친 뒤 272건만 다시 받아야 했고, 그때 `upsert`를 썼다면 나머지 22,000여 건이
    한 번씩 안 보인 것으로 세졌을 것이다.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "store.sqlite")
        self.jobs = mock_jobs()
        self.store.upsert(self.jobs, source=self.jobs[0].source, as_of=AS_OF)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _record(self, job_id):
        return self.store.get(job_id)

    def test_the_untouched_postings_are_not_counted_as_missing(self):
        """이게 이 메서드가 있는 이유다."""
        one = replace(self.jobs[0], description="다시 파싱한 본문입니다.")
        self.store.refresh([one], as_of=AS_OF)
        for job in self.jobs[1:]:
            with self.subTest(job.job_id):
                record = self._record(job.job_id)
                self.assertEqual(0, record.missing_runs)
                self.assertEqual(STATUS_OPEN, record.status)

    def test_the_new_body_replaces_the_old_one(self):
        # `content_hash`는 파서가 넣는 값이다. 다시 파싱하면 본문과 함께 바뀐다.
        one = replace(self.jobs[0], description="ㆍ주요 개발 언어 : javascript", content_hash="새-지문")
        result = self.store.refresh([one], as_of=AS_OF)
        self.assertEqual([one.job_id], result["changed"])
        self.assertIn("javascript", self._record(one.job_id).job.description)

    def test_the_first_seen_date_is_kept(self):
        """다시 파싱했다고 처음 본 날이 오늘로 바뀌면 안 된다."""
        before = self._record(self.jobs[0].job_id).first_seen_at
        self.store.refresh(
            [replace(self.jobs[0], description="바뀐 본문", content_hash="새-지문")], as_of=AS_OF)
        self.assertEqual(before, self._record(self.jobs[0].job_id).first_seen_at)

    def test_an_unchanged_body_does_not_bump_the_revision(self):
        result = self.store.refresh([self.jobs[0]], as_of=AS_OF)
        self.assertEqual([self.jobs[0].job_id], result["same"])
        self.assertEqual(0, self._record(self.jobs[0].job_id).revisions)

    def test_a_changed_body_bumps_the_revision_once(self):
        self.store.refresh(
            [replace(self.jobs[0], description="바뀐 본문", content_hash="새-지문")], as_of=AS_OF)
        self.assertEqual(1, self._record(self.jobs[0].job_id).revisions)

    def test_the_parser_hash_decides_whether_it_changed(self):
        """본문만 다르고 지문이 같으면 안 바뀐 것으로 본다. 판단은 파서 몫이다."""
        same_hash = replace(self.jobs[0], description="글자는 다르지만 지문은 그대로")
        self.assertEqual([self.jobs[0].job_id], self.store.refresh([same_hash], as_of=AS_OF)["same"])

    def test_an_expired_posting_does_not_come_back_to_life(self):
        """**이 테스트가 있는 이유.** 처음에는 `resolve_status`로 상태를 다시 계산했다.
        그 판정이 9일 전에 고정된 기준 시각(옛 `config.AS_OF`)을 기준으로 해서, 실제로 돌려 보니 만료·삭제된
        공고 7,090건이 한꺼번에 OPEN으로 되살아났다.

        다시 파싱하는 것은 저장해 둔 글을 다시 읽는 일이지, 그 공고가 아직 살아 있는지
        확인하는 일이 아니다. 살아 있는지는 목록 관측과 링크 확인이 정한다.
        """
        gone = self.jobs[0]
        record = self._record(gone.job_id)
        self.store.put(replace(record, status=STATUS_EXPIRED, missing_runs=2))
        self.store.refresh([replace(gone, description="다시 파싱한 본문", content_hash="새-지문")])
        after = self._record(gone.job_id)
        self.assertEqual(STATUS_EXPIRED, after.status)
        self.assertEqual(2, after.missing_runs, "미관측 횟수도 건드리지 않는다")

    def test_a_removed_posting_stays_removed(self):
        gone = self.jobs[1]
        self.store.put(replace(self._record(gone.job_id), status=STATUS_REMOVED, missing_runs=3))
        self.store.refresh([gone])
        self.assertEqual(STATUS_REMOVED, self._record(gone.job_id).status)

    def test_the_last_seen_date_is_not_moved_forward(self):
        """다시 파싱한 날을 "마지막으로 본 날"로 적으면 사라진 공고가 살아 있어 보인다."""
        before = self._record(self.jobs[0].job_id).last_seen_at
        self.store.refresh([replace(self.jobs[0], description="바뀐 본문", content_hash="새-지문")])
        self.assertEqual(before, self._record(self.jobs[0].job_id).last_seen_at)

    def test_refresh_without_listing_keeps_title_company_and_deadline(self):
        """다시 파싱해 덮어쓰는 통로에서도 목록 값이 빈 레코드는 저장된 값을 이어받는다."""
        original = self._record(self.jobs[0].job_id).job
        blank = replace(self.jobs[0], company="", title="", deadline=None, content_hash="새-지문")
        self.store.refresh([blank], as_of=AS_OF)
        after = self._record(self.jobs[0].job_id).job
        self.assertEqual((original.company, original.title, original.deadline), (after.company, after.title, after.deadline))

    def test_a_posting_the_store_never_had_is_not_added(self):
        """새 공고를 들이는 것은 `upsert`가 할 일이다."""
        stranger = replace(self.jobs[0], job_id="NEW-1", source_job_id="99999")
        result = self.store.refresh([stranger], as_of=AS_OF)
        self.assertEqual(["NEW-1"], result["unknown"])
        self.assertEqual(len(self.jobs), self.store.count())
