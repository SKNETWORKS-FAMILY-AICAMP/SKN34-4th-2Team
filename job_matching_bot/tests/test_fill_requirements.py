"""공고 요건 채우기 — 빈 칸만 · 경력 공고만 · 여러 부문은 안 채움 · 파서가 아는 값만. LLM 은 가짜로 갈아 끼운다."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from job_matching_bot import fill_requirements
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.requirements_llm import Extracted, plan_fill
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

BODY = "[자격요건] 관련 경력 4년 이상 · 컴퓨터공학 전공 · 정보처리기사 필수 · Java Spring 개발 " * 5


def ext(years=4, majors=("컴퓨터공학",), certs=("정보처리기사",), multi=False):
    return Extracted(multi_role=multi, min_career_years=years, required_majors=list(majors), required_certifications=list(certs))


class PlanTest(unittest.TestCase):
    def setUp(self):
        self.job = replace(mock_jobs()[0], career_type="EXPERIENCED", min_career_years=None, description=BODY,
                           required_majors=[], required_major_terms=[], required_certifications=[],
                           required_certification_groups=[])

    def test_fills_only_empty_fields(self):
        fill = plan_fill(self.job, ext())
        self.assertEqual(4, fill.values["min_career_years"])
        self.assertEqual(["컴퓨터·소프트웨어"], fill.values["required_majors"])
        self.assertIn("컴퓨터", fill.values["required_major_terms"])
        self.assertEqual([["정보처리기사"]], fill.values["required_certification_groups"])
        kept = plan_fill(replace(self.job, min_career_years=2, required_majors=["전자·전기"]), ext())
        self.assertNotIn("min_career_years", kept.values)
        self.assertNotIn("required_majors", kept.values)

    def test_years_only_for_experienced_postings(self):
        """신입 · 무관 공고에 연차를 적으면 신입 검색(연차 ≤ 1)에서 빠진다."""
        self.assertNotIn("min_career_years", plan_fill(replace(self.job, career_type="ANY"), ext()).values)

    def test_multi_role_postings_get_years_only(self):
        """여러 부문이면 연차(가장 낮은 것)만 — 전공 · 자격증은 부문마다 달라 안 채운다."""
        fill = plan_fill(self.job, ext(years=1, multi=True))
        self.assertEqual({"min_career_years": 1}, fill.values)
        self.assertTrue(fill.note)

    def test_only_what_the_parser_knows(self):
        """교육과정 수료는 자격증이 아니다. 모르는 전공 이름은 적지 않는다. 터무니없는 연차도."""
        fill = plan_fill(self.job, ext(years=2019, majors=("조리학과",), certs=("정부 AI 인재 양성 교육과정 수료",)))
        self.assertEqual({}, fill.values)


class StoreRunTest(unittest.TestCase):
    """로컬 테스트 DB(격리 스키마)에서 고르기 · 채우기 · 다시 안 보기."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        self.gap = replace(base, job_id="MOCK-GAP", source_job_id="GAP", career_type="EXPERIENCED", min_career_years=None,
                           description=BODY, required_majors=[], required_major_terms=[],
                           required_certifications=[], required_certification_groups=[], body_is_image=False)
        self.full = replace(self.gap, job_id="MOCK-FULL", source_job_id="FULL", min_career_years=3)
        with SqliteJobStore(self.path) as store:
            store.upsert([self.gap, self.full], source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def test_fills_gaps_and_does_not_look_twice(self):
        calls = []

        def fake(values):
            calls.append(values["title"])
            return ext()

        with SqliteJobStore(self.path) as store:
            self.assertEqual(["MOCK-GAP"], [r.job.job_id for r in store.requirement_targets(10)], "연차가 찬 공고는 안 본다")
        dry = fill_requirements.run(self.path, limit=10, dry_run=True, extractor=fake)
        self.assertEqual(1, dry["filled_min_career_years"])
        with SqliteJobStore(self.path) as store:
            self.assertIsNone(store.get("MOCK-GAP").job.min_career_years, "dry-run 은 쓰지 않는다")

        summary = fill_requirements.run(self.path, limit=10, extractor=fake)
        self.assertEqual(1, summary["analyzed"])
        with SqliteJobStore(self.path) as store:
            job = store.get("MOCK-GAP").job
            self.assertEqual(4, job.min_career_years)
            self.assertEqual(["정보처리기사"], job.required_certifications)
            self.assertEqual(job.content_hash, job.field_provenance["requirements_llm"]["hash"])
            self.assertEqual(3, store.get("MOCK-FULL").job.min_career_years)
            self.assertEqual([], store.requirement_targets(10), "한 번 본 공고는 다시 안 본다")
        self.assertEqual(2, len(calls))  # dry-run 1 + 실제 1

    def test_min_days_left_skips_postings_closing_soon(self):
        from datetime import date, timedelta
        with SqliteJobStore(self.path) as store:
            store.conn.execute("UPDATE jobs SET deadline = ? WHERE job_id = 'MOCK-GAP'", ((date.today() + timedelta(days=3)).isoformat(),))
            self.assertEqual([], store.requirement_targets(10, min_days_left=14), "3일 뒤 마감은 건너뛴다")
            self.assertEqual(1, len(store.requirement_targets(10, min_days_left=2)))
            store.conn.execute("UPDATE jobs SET deadline = NULL WHERE job_id = 'MOCK-GAP'")
            self.assertEqual(1, len(store.requirement_targets(10, min_days_left=14)), "마감일 없는 상시 채용은 넣는다")

    def test_failed_extraction_is_retried_next_time(self):
        def broken(values):
            raise RuntimeError("LLM 실패")

        summary = fill_requirements.run(self.path, limit=10, extractor=broken)
        self.assertEqual(1, summary["failed"])
        with SqliteJobStore(self.path) as store:
            self.assertEqual(1, len(store.requirement_targets(10)), "표시를 안 남겨 다음에 다시 본다")


if __name__ == "__main__":
    unittest.main()
