"""직무 이름 표준화 — 같은 직무를 다르게 말해도 같은 공고.

1. AI 계열(AI 엔지니어 · AI엔지니어 · 인공지능 개발자 · 인공지능 엔지니어)은 「AI 개발자」 하나로.
2. 표에 없는 말은 영문 · 한글이 붙은 곳만 띄운다(QA엔지니어 → QA 엔지니어). 한글끼리는 건드리지 않는다.
3. 「AI」만 말하면 그대로 둔다 — 직무가 아니라 분야라 더 넓게 찾는다.
4. 조건(JobFilters)이 만들어질 때 접히므로 검색 · 집계 · 기억 열쇠가 같은 값을 쓴다.
5. 실제 검색: 말이 달라도 같은 공고가 나온다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.matching.role_normalize import canonical_role, canonical_roles
from job_matching_bot.retrieval import store_search
from job_matching_bot.retrieval.store_search import JobFilters

AI_WAYS = ["AI 엔지니어", "AI엔지니어", "인공지능 개발자", "인공지능 엔지니어", "AI 개발자", "ai개발자"]


class CanonicalRoleTest(unittest.TestCase):
    def test_ai_family_folds_into_one(self):
        self.assertEqual({"AI 개발자"}, {canonical_role(name) for name in AI_WAYS})

    def test_unknown_roles_only_get_latin_hangul_spacing(self):
        self.assertEqual("QA 엔지니어", canonical_role("QA엔지니어"))
        self.assertEqual("iOS 개발자", canonical_role("iOS개발자"))
        self.assertEqual("C++ 개발자", canonical_role("C++개발자"))
        self.assertEqual("데이터분석", canonical_role("데이터분석"), "한글끼리는 건드리지 않는다")
        self.assertEqual("데이터 엔지니어", canonical_role("데이터  엔지니어"), "겹친 공백은 하나로")

    def test_bare_ai_stays_a_field(self):
        self.assertEqual("AI", canonical_role("AI"))

    def test_dedupe_keeps_order(self):
        self.assertEqual(["AI 개발자", "백엔드"], canonical_roles(["AI 엔지니어", "백엔드", "인공지능 개발자"]))


class FiltersTest(unittest.TestCase):
    def test_filters_fold_roles_so_cache_keys_match(self):
        keys = {
            store_search.cache_key("search", Path("artifacts/job_store.sqlite"), JobFilters(roles=[name], career="신입"),
                                   __import__("datetime").datetime(2026, 10, 7, tzinfo=store_search.KST))
            for name in AI_WAYS
        }
        self.assertEqual(1, len(keys))


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        base = mock_jobs()[0]
        titles = {"A1": "AI 개발자 채용", "A2": "인공지능 엔지니어 모집", "A3": "AI엔지니어 (LLM)", "B1": "백엔드 개발자"}
        jobs = [replace(base, job_id=k, source_job_id=k, title=v, description="", tech_stack=[], keywords=[],
                        status="OPEN", deadline=None, career_type="ANY") for k, v in titles.items()]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")

    def tearDown(self):
        self.tmp.cleanup()

    def found(self, role: str) -> set[str]:
        result = store_search.search(self.path, JobFilters(roles=[role]), limit=10)
        return {hit.job_id for hit in result.jobs}

    def test_every_way_of_saying_it_finds_the_same_jobs(self):
        results = {name: self.found(name) for name in AI_WAYS}
        self.assertEqual(1, len({frozenset(v) for v in results.values()}), results)
        self.assertNotIn("B1", next(iter(results.values())))


if __name__ == "__main__":
    unittest.main()
