"""조건에 맞는 공고를 세어 분포를 낸다. 챗봇이 "요즘 뭘 요구해?"에 답하는 근거.

핵심 약속: **검색과 같은 모수를 센다.** "412건 중 61%"라고 말해 놓고 목록에는 다른
공고가 나오면 답이 거짓말이 된다. 그래서 조건 조립부를 `store_search`와 함께 쓴다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.retrieval import store_search
from job_matching_bot.retrieval.market_stats import summarize
from job_matching_bot.retrieval.store_search import KST, JobFilters


class MarketStatsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        self.now = datetime(2026, 9, 7, tzinfo=KST)
        base = mock_jobs()[0]
        # 백엔드 10건 중 8건이 Python, 2건만 Go. 서울 6 / 부산 4.
        jobs = [
            replace(
                base,
                job_id=f"B{i}",
                source_job_id=f"B{i}",
                company=f"{i}회사",
                title="백엔드 개발자",
                description="서버를 만듭니다",
                tech_stack=["Python"] if i <= 8 else ["Go"],
                keywords=["IT개발·데이터", "백엔드/서버개발", "서울", "강남구"],
                region="서울특별시 강남구" if i <= 6 else "부산광역시 해운대구",
                career_type="ENTRY",
                min_career_years=None,
                education="대졸",
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            )
            for i in range(1, 11)
        ]
        # 다른 직무 한 건. 조건에 걸리지 않아야 한다.
        jobs.append(
            replace(
                base,
                job_id="D1",
                source_job_id="D1",
                company="디자인회사",
                title="UI 디자이너",
                description="화면을 그립니다",
                tech_stack=["Figma"],
                keywords=["디자인"],
                region="서울특별시 마포구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            )
        )
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def stats(self, **kwargs):
        return summarize(self.path, JobFilters(**kwargs), as_of=self.now)

    def test_counts_only_jobs_that_match_the_conditions(self):
        self.assertEqual(10, self.stats(roles=["백엔드"]).total)

    def test_the_count_matches_what_search_would_show(self):
        """이 둘이 어긋나면 "10건 중 8건"이라 말해 놓고 다른 공고를 보여 주게 된다."""
        filters = JobFilters(roles=["백엔드"], regions=["서울"])
        found = store_search.search(self.path, filters, as_of=self.now)
        self.assertEqual(found.total, summarize(self.path, filters, as_of=self.now).total)

    def test_skill_share_is_a_percentage_of_the_matched_jobs(self):
        skills = {share.name: share for share in self.stats(roles=["백엔드"]).skills}
        self.assertEqual(8, skills["Python"].count)
        self.assertEqual(80, skills["Python"].percent)

    def test_regions_are_grouped_by_province(self):
        """구 단위로 세면 "서울 강남구 17%"처럼 흩어져 정작 쓸모 있는 사실이 안 보인다."""
        regions = {share.name: share.count for share in self.stats(roles=["백엔드"]).regions}
        self.assertEqual({"서울": 6, "부산": 4}, regions)

    def test_region_tags_are_not_counted_as_roles(self):
        """사이트 분류 태그에는 직무와 지역이 한 칸에 섞여 있다."""
        roles = {share.name for share in self.stats(roles=["백엔드"]).roles}
        self.assertIn("백엔드/서버개발", roles)
        self.assertNotIn("서울", roles)
        self.assertNotIn("강남구", roles)

    def test_a_lone_value_is_not_reported_as_a_share(self):
        """한 건짜리는 비율로 말할 것이 못 된다. 10%라고 하면 경향처럼 들린다."""
        stats = self.stats(roles=["디자인"])
        self.assertEqual(1, stats.total)
        self.assertEqual([], stats.skills)

    def test_closing_soon_is_counted_separately(self):
        soon = (self.now + timedelta(days=3)).date().isoformat()
        with SqliteJobStore(self.path) as store:
            store.upsert(
                [
                    replace(
                        mock_jobs()[0],
                        job_id="B1",
                        source_job_id="B1",
                        title="백엔드 개발자",
                        description="서버를 만듭니다",
                        tech_stack=["Python"],
                        keywords=["백엔드/서버개발"],
                        region="서울특별시 강남구",
                        career_type="ENTRY",
                        min_career_years=None,
                        employment_type="정규직",
                        deadline=soon,
                        status="OPEN",
                    )
                ],
                source="MOCK",
            )
        self.assertEqual(1, self.stats(roles=["백엔드"]).closing_soon)

    def test_no_match_returns_an_empty_table(self):
        stats = self.stats(roles=["용접"])
        self.assertEqual(0, stats.total)
        self.assertEqual([], stats.skills)

    def test_prompt_table_carries_counts_not_just_percentages(self):
        """비율만 주면 세 건 중 두 건도 67%가 된다. 사용자가 의심할 수 있어야 한다."""
        table = self.stats(roles=["백엔드"]).to_prompt()
        self.assertIn("10건", table)
        self.assertIn("Python 8건(80%)", table)


if __name__ == "__main__":
    unittest.main()
