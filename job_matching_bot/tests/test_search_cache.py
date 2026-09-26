"""검색 결과 재사용 — 운영 저장소만 담아 두고, 같은 조건 · 같은 날이면 다시 쓴다."""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from job_matching_bot.retrieval import store_search
from job_matching_bot.retrieval.store_search import KST, JobFilters, cache_key, remember


class SearchCacheTest(unittest.TestCase):
    def setUp(self):
        store_search._cache.clear()
        self.now = datetime(2026, 9, 26, 15, tzinfo=KST)

    def test_only_the_managed_store_is_cached(self):
        # 테스트 저장소는 같은 경로에 공고를 더 넣고 다시 찾는다 — 담아 두면 옛 결과가 나간다
        self.assertIsNone(cache_key("search", Path("tmp/store.sqlite"), JobFilters(roles=["백엔드"]), self.now))
        self.assertIsNotNone(cache_key("search", Path("artifacts/job_store.sqlite"), JobFilters(roles=["백엔드"]), self.now))

    def test_same_conditions_same_day_reuse_the_result(self):
        path = Path("artifacts/job_store.sqlite")
        calls = []
        load = lambda: calls.append(1) or ["결과"]
        key = cache_key("search", path, JobFilters(roles=["백엔드"], regions=["서울"]), self.now)
        self.assertEqual(["결과"], remember(key, load))
        self.assertEqual(["결과"], remember(key, load))
        self.assertEqual(1, len(calls))
        # 조건이 다르거나 날이 바뀌면 다시 찾는다
        other = cache_key("search", path, JobFilters(roles=["백엔드"], regions=["부산"]), self.now)
        tomorrow = cache_key("search", path, JobFilters(roles=["백엔드"], regions=["서울"]), self.now.replace(day=27))
        remember(other, load)
        remember(tomorrow, load)
        self.assertEqual(3, len(calls))

    def test_old_results_expire(self):
        key = cache_key("stats", Path("artifacts/job_store.sqlite"), JobFilters(roles=["QA"]), self.now)
        calls = []
        load = lambda: calls.append(1) or len(calls)
        with patch.object(store_search.time, "monotonic", return_value=1000.0):
            remember(key, load)
        with patch.object(store_search.time, "monotonic", return_value=1000.0 + store_search._CACHE_SECONDS + 1):
            self.assertEqual(2, remember(key, load))


if __name__ == "__main__":
    unittest.main()
