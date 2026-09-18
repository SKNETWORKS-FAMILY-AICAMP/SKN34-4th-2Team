"""추천 단계별 시간.

요청 전체 시간만 남아서 "추천이 10초대"가 어느 단계 탓인지 가릴 수 없었다.

여기서 지키는 약속 셋.

1. **단계 시간은 겹치지 않고 이어진다.** 합치면 전체와 같아야 병목을 읽을 수 있다.
2. **응답과 로그 둘 다에 남는다.** 앱은 응답을, 사람은 서버 로그를 본다.
3. **구조화가 0초인 이유를 같이 적는다.** 앱이 보냈는지 캐시인지 시간만으로는 모른다.
"""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from job_matching_bot.api import schemas, service
from job_matching_bot.api.service import RecommendService, StageClock, format_timings
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.retrieval.search import Hit

RESUME = "Python과 FastAPI로 추천 API를 만들고 벡터 검색을 붙였습니다."
STAGES = ["profile", "search", "filter", "liveness", "pre_rank", "rerank", "verify", "total"]


class FakeClock:
    def __init__(self, *ticks: float) -> None:
        self._ticks = list(ticks)

    def __call__(self) -> float:
        return self._ticks.pop(0)


class StageClockTest(unittest.TestCase):
    def test_laps_are_measured_from_the_previous_lap(self):
        clock = StageClock(now=FakeClock(0.0, 2.7, 3.5, 10.0, 10.2))
        clock.lap("profile")
        clock.lap("search")
        clock.lap("rerank")
        self.assertEqual(
            {"profile": 2700, "search": 800, "rerank": 6500, "total": 10200}, clock.timings()
        )

    def test_log_line_names_stages_in_korean_and_the_profile_source(self):
        line = format_timings({"profile": 0, "rerank": 7100, "total": 8000}, "앱")
        self.assertEqual("[추천 시간] 구조화 출처=앱 · 구조화 0.0 · 재정렬 7.1 · 합계 8.0초", line)


def _profile() -> schemas.ResumeProfileOut:
    return schemas.ResumeProfileOut(
        search_query="Python 백엔드", target_roles=["백엔드"], skills=["Python"],
        career_years=0, summary="",
    )


class RecommendTimingsTest(unittest.TestCase):
    def _service(self, jobs):
        svc = RecommendService(
            profiler=lambda _: _profile(),
            reranker=lambda _: schemas.RerankOut(results=[]),
        )
        svc._load_reviewable_hits = lambda hits, warnings: [
            (hit, job) for hit, job in zip(hits, jobs)
        ]
        svc.drop_dead = lambda ids: set(ids)
        return svc

    def _run(self, svc, hits, request):
        out = io.StringIO()
        with mock.patch.object(service.retrieval, "search", return_value=hits), redirect_stdout(out):
            response = svc.recommend(request)
        return response, out.getvalue()

    def test_every_stage_is_timed_and_logged(self):
        jobs = mock_jobs()[:3]
        hits = [Hit(job_id=j.job_id, score=0.5, rank=i + 1, metadata={}) for i, j in enumerate(jobs)]
        response, log = self._run(
            self._service(jobs), hits, schemas.RecommendRequest(resume_text=RESUME)
        )
        self.assertEqual(STAGES, list(response.timings_ms))
        self.assertTrue(all(v >= 0 for v in response.timings_ms.values()))
        self.assertLessEqual(
            sum(v for k, v in response.timings_ms.items() if k != "total"),
            response.timings_ms["total"] + len(STAGES),  # 단계마다 반올림 1ms
        )
        self.assertEqual("LLM", response.profile_source)
        self.assertIn("[추천 시간] 구조화 출처=LLM", log)
        self.assertIn("재정렬", log)

    def test_profile_source_tells_app_and_cache_apart(self):
        svc = self._service([])
        sent = schemas.RecommendRequest(resume_text=RESUME, profile=_profile())
        self.assertEqual("앱", self._run(svc, [], sent)[0].profile_source)

        plain = schemas.RecommendRequest(resume_text=RESUME)
        self.assertEqual("LLM", self._run(svc, [], plain)[0].profile_source)
        self.assertEqual("캐시", self._run(svc, [], plain)[0].profile_source)

    def test_no_hits_still_reports_time_up_to_search(self):
        response, log = self._run(
            self._service([]), [], schemas.RecommendRequest(resume_text=RESUME)
        )
        self.assertEqual(["profile", "search", "total"], list(response.timings_ms))
        self.assertIn("[추천 시간]", log)


if __name__ == "__main__":
    unittest.main()
