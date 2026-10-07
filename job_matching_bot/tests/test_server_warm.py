"""서버 준비 — 자주 묻는 집계를 미리 세고, 준비는 한 번만 돈다.

1. 미리 셀 조합: 전체 3 + 직무 25 × 경력 3 + 기술 조합 7 = 85. 하나가 실패해도 나머지를 센다.
2. 준비는 lifespan 과 첫 요청 둘 다에서 부르지만 한 번만 시작한다 — 통합 앱에 mount 되면 lifespan 이 안 돈다.
3. `SERVER_WARM=0`이면 아무것도 띄우지 않는다.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from job_matching_bot.retrieval import market_stats


class WarmFiltersTest(unittest.TestCase):
    def test_counts_the_common_combinations(self):
        filters = market_stats.warm_filters()
        self.assertEqual(3 + len(market_stats.WARM_ROLES) * 3 + 7, len(filters))
        self.assertTrue(any(f.roles == ["백엔드"] and f.skills == ["Spring"] and f.career == "신입" for f in filters))
        self.assertTrue(any(not f.roles and f.career == "무관" for f in filters), "전체도 센다")

    def test_one_failure_does_not_stop_the_rest(self):
        seen = []

        def summarize(path, item, as_of=None):
            seen.append(item)
            if len(seen) == 2:
                raise RuntimeError("RDS 끊김")

        with mock.patch.object(market_stats, "summarize", summarize):
            done = market_stats.warm(Path("x"), market_stats.warm_filters()[:5], log=lambda _: None)
        self.assertEqual(5, len(seen))
        self.assertEqual(4, done)


class StartWarmingTest(unittest.TestCase):
    def setUp(self):
        from job_matching_bot.api import main

        self.main = main
        self.addCleanup(setattr, main, "_warm_started", False)
        main._warm_started = False

    def test_starts_once(self):
        with mock.patch.dict(os.environ, {"SERVER_WARM": "1"}), \
                mock.patch.object(self.main.threading, "Thread") as thread:
            self.main._start_warming()
            self.main._start_warming()
        self.assertEqual(4, thread.call_count, "마감 확인 둘 · 임베딩 · 집계 — 두 번째 부름은 아무것도 안 한다")

    def test_switch_off(self):
        with mock.patch.dict(os.environ, {"SERVER_WARM": "0"}), \
                mock.patch.object(self.main.threading, "Thread") as thread:
            self.main._start_warming()
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
