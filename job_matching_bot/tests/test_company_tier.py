"""같은 적합도 안에서는 대기업 · 공기업 → 외국계 · 중견 · 상장 → 그 밖 순으로 선다."""

from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest import mock

from job_matching_bot.api import schemas, service
from job_matching_bot.api.service import RecommendService
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.matching.company_tier import company_tier
from job_matching_bot.retrieval.search import Hit

RESUME = "Python과 FastAPI로 추천 API를 만들고 벡터 검색을 붙였습니다."
BODY = "[자격요건]\nPython 백엔드 개발 경험\n[주요업무]\n추천 API 개발"


class CompanyTierTest(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(0, company_tier("코스피, 대기업, 1000대기업, 외부감사법인"))
        self.assertEqual(0, company_tier("공공기관·공기업"))
        self.assertEqual(1, company_tier("중견기업, 코스닥상장"))
        self.assertEqual(1, company_tier("외국계기업"))
        self.assertEqual(1, company_tier("코스닥, 중소기업"))
        self.assertEqual(2, company_tier("중소기업, 1000대기업"), "1000대기업은 중소에도 붙는다")
        self.assertEqual(2, company_tier("미기재"))
        self.assertEqual(2, company_tier(None))


def _fit(job_id: str, fit: str) -> schemas.JobFit:
    reason = schemas.Reason(claim="API 개발 경험이 맞닿아 있습니다.", resume_quote="추천 API를 만들고",
                            job_quote="추천 API 개발")
    return schemas.JobFit(job_id=job_id, job_core="Python", resume_core="Python", overlap="Python",
                          fit=fit, reasons=[reason], concerns=[])


class RecommendOrderTest(unittest.TestCase):
    def test_company_tier_orders_within_the_same_fit_only(self):
        base = replace(mock_jobs()[0], description=BODY, deadline=None, career_type="ANY", min_career_years=None,
                       education="학력무관", required_majors=[], required_major_terms=[],
                       required_certifications=[], required_certification_groups=[],
                       required_language_tests=[], military_required=False, body_is_image=False)
        plan = [  # (회사, 기업형태, 적합도) — 벡터 순위는 이 순서
            ("작은회사", "중소기업", "높음"),
            ("큰회사B", "대기업", "보통"),
            ("큰회사A", "코스피, 대기업", "높음"),
            ("중간회사", "중견기업", "높음"),
        ]
        jobs = [replace(base, job_id=f"MOCK-{i}", source_job_id=str(i), company=name, company_type=kind)
                for i, (name, kind, _) in enumerate(plan)]
        fits = schemas.RerankOut(results=[_fit(job.job_id, fit) for job, (_, _, fit) in zip(jobs, plan)])
        svc = RecommendService(
            profiler=lambda _: schemas.ResumeProfileOut(search_query="Python 백엔드", target_roles=["백엔드"],
                                                        skills=["Python"], career_years=0, summary=""),
            reranker=lambda _: fits,
        )
        svc._load_reviewable_hits = lambda hits, warnings: list(zip(hits, jobs))
        svc.drop_dead = lambda ids: set(ids)
        hits = [Hit(job_id=j.job_id, score=0.5, rank=i + 1, metadata={}) for i, j in enumerate(jobs)]
        with mock.patch.object(service.retrieval, "search", return_value=hits), redirect_stdout(io.StringIO()):
            response = svc.recommend(schemas.RecommendRequest(resume_text=RESUME))
        self.assertEqual(
            [("큰회사A", "높음"), ("중간회사", "높음"), ("작은회사", "높음"), ("큰회사B", "보통")],
            [(r.company, r.fit) for r in response.recommendations],
        )


if __name__ == "__main__":
    unittest.main()
