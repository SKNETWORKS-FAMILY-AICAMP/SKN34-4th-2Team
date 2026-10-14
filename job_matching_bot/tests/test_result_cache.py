"""추천 결과 재사용(#23) — 같은 이력서 · 조건이면 검색 · 재정렬을 건너뛴다.

지키는 약속.

1. **요청이 조금이라도 다르면 새로 추천한다.** 이력서 글 · 조건 · 개수가 열쇠다.
2. **공고가 새로 적재되면 버린다.** 적재 시각(runs)이 바뀌었거나 모르면 재사용하지 않는다.
3. **실패해 물러난 결과는 두지 않는다.** 재정렬을 못 받은 결과는 다음에 다시 해 본다.
4. **그 사이 마감된 공고는 뺀다.** 마감 확인은 재사용할 때도 새로 한다.
"""

from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest import mock

from job_matching_bot.api import schemas, service
from job_matching_bot.api.service import RecommendService
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.retrieval.search import Hit

RESUME = "Python과 FastAPI로 추천 API를 만들고 벡터 검색을 붙였습니다."


def _profile() -> schemas.ResumeProfileOut:
    return schemas.ResumeProfileOut(
        search_query="Python 백엔드", target_roles=["백엔드"], skills=["Python"], career_years=0, summary="",
    )


class ResultCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.jobs = mock_jobs()[:3]
        self.hits = [Hit(job_id=j.job_id, score=0.5, rank=i + 1, metadata={}) for i, j in enumerate(self.jobs)]
        self.judged = 0
        self.version = "2026-09-28T04:00:00"
        self.alive: set[str] | None = None

        def rerank(values):
            self.judged += 1
            job_id = json.loads(values["jobs"])[0]["job_id"]
            return schemas.RerankOut(results=[schemas.JobFit(
                job_id=job_id, job_core="Python", resume_core="Python", overlap="Python", fit="보통",
            )])

        svc = RecommendService(profiler=lambda _: _profile(), reranker=rerank, result_cache=True)
        svc._load_reviewable_hits = lambda hits, warnings: [(hit, job) for hit, job in zip(hits, self.jobs)]
        svc.drop_dead = lambda ids: set(ids) if self.alive is None else set(ids) & self.alive
        svc.store_version = lambda: self.version
        self.svc = svc

    def _run(self, request: schemas.RecommendRequest, hits=None) -> schemas.RecommendResponse:
        with mock.patch.object(service.retrieval, "search", return_value=self.hits if hits is None else hits), \
                redirect_stdout(io.StringIO()):
            return self.svc.recommend(request)

    def test_same_request_reuses_the_result_without_llm(self):
        first = self._run(schemas.RecommendRequest(resume_text=RESUME))
        judged = self.judged
        again = self._run(schemas.RecommendRequest(resume_text=RESUME))
        self.assertEqual(judged, self.judged, "재정렬을 다시 부르지 않는다")
        self.assertEqual("결과 재사용", again.profile_source)
        self.assertEqual(["cache", "total"], list(again.timings_ms))
        self.assertEqual([r.job_id for r in first.recommendations], [r.job_id for r in again.recommendations])

    def test_any_difference_in_the_request_is_a_new_recommendation(self):
        self._run(schemas.RecommendRequest(resume_text=RESUME))
        other = self._run(schemas.RecommendRequest(resume_text=RESUME, preferred_regions=["서울"]))
        self.assertNotEqual("결과 재사용", other.profile_source)
        fewer = self._run(schemas.RecommendRequest(resume_text=RESUME, top_k=3))
        self.assertNotEqual("결과 재사용", fewer.profile_source)

    def test_new_postings_or_unknown_store_state_skip_the_cache(self):
        self._run(schemas.RecommendRequest(resume_text=RESUME))
        self.version = "2026-09-29T04:00:00"
        self.assertNotEqual("결과 재사용", self._run(schemas.RecommendRequest(resume_text=RESUME)).profile_source)
        self.version = None
        self._run(schemas.RecommendRequest(resume_text=RESUME))
        self.assertNotEqual("결과 재사용", self._run(schemas.RecommendRequest(resume_text=RESUME)).profile_source)

    def test_fallback_results_are_not_kept(self):
        self.svc._reranker = lambda values: (_ for _ in ()).throw(RuntimeError("LLM 실패"))
        failed = self._run(schemas.RecommendRequest(resume_text=RESUME))
        self.assertFalse(failed.reranked)
        self.assertNotEqual("결과 재사용", self._run(schemas.RecommendRequest(resume_text=RESUME)).profile_source)

    def test_postings_closed_since_are_dropped_on_reuse(self):
        first = self._run(schemas.RecommendRequest(resume_text=RESUME))
        closed = first.recommendations[0].job_id
        self.alive = {r.job_id for r in first.recommendations} - {closed}
        again = self._run(schemas.RecommendRequest(resume_text=RESUME))
        self.assertEqual("결과 재사용", again.profile_source)
        self.assertNotIn(closed, [r.job_id for r in again.recommendations])

    def test_off_by_default(self):
        svc = RecommendService(profiler=lambda _: _profile(), reranker=lambda _: schemas.RerankOut(results=[]))
        self.assertIsNone(svc.cached_result(RecommendService.result_key(schemas.RecommendRequest(resume_text=RESUME))))
        self.assertFalse(svc._result_cache)


if __name__ == "__main__":
    unittest.main()
