"""연차 6개월 여유 · 경력 소수 · 「높음」은 다 맞아야(판정 뒤 코드로)."""

from __future__ import annotations

import unittest
from dataclasses import replace

from job_matching_bot.api import schemas
from job_matching_bot.api.service import RecommendService
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.matching.hard_filter import hard_filter
from job_matching_bot.schemas.resume import ResumeProfile

JOB = replace(mock_jobs()[0], career_type="EXPERIENCED", min_career_years=3, education="학력무관",
              required_majors=[], required_major_terms=[], required_certifications=[], required_certification_groups=[])


def resume(years: float) -> ResumeProfile:
    return ResumeProfile(resume_id="r", target_roles=["백엔드"], skills=["Java"], project_skills=["Java"],
                         preferred_regions=[], preferred_employment_types=[], education_level="대졸",
                         career_years=years, majors=["컴퓨터공학"], certifications=[])


class CareerToleranceTest(unittest.TestCase):
    def test_short_by_six_months_or_less_is_check_required_not_failed(self):
        r = hard_filter(JOB, resume(2.5))
        self.assertEqual("CHECK_REQUIRED", r["status"])
        self.assertIn("경력 6개월 모자람 (최소 3년)", r["unknown"])

    def test_fraction_of_a_year_is_kept(self):
        """2년 8개월을 2년으로 자르면 「3년 이상」에서 1년 모자란 것으로 탈락했다."""
        self.assertEqual("CHECK_REQUIRED", hard_filter(JOB, resume(2 + 8 / 12))["status"])

    def test_short_by_more_than_six_months_fails(self):
        r = hard_filter(JOB, resume(2.4))
        self.assertEqual("FAIL", r["status"])
        self.assertIn("최소 경력 3년", r["failed"])

    def test_enough_years_pass(self):
        self.assertNotIn("경력", " ".join(hard_filter(JOB, resume(3))["unknown"]))


def fit(grade="높음", concerns=()):
    return schemas.JobFit(job_id="J", job_core="Java", resume_core="Java", overlap="Java", fit=grade, concerns=list(concerns))


class HighNeedsEverythingTest(unittest.TestCase):
    def test_all_met_stays_high(self):
        self.assertEqual("높음", RecommendService.require_all_met(fit(), {"unknown": ["근무지역 미기재"]}).fit,
                         "공고 쪽 정보가 없는 것은 지원자 탓이 아니다")

    def test_llm_concerns_alone_do_not_cap(self):
        """사소한 요건 하나(「CDN · DNS 이해」)로 내리면 사람 채점과 어긋났다. 하드 요건만 본다."""
        kept = RecommendService.require_all_met(fit(concerns=["CDN·네트워크·DNS 이해는 확인되지 않는다"]), {"unknown": []})
        self.assertEqual("높음", kept.fit)
        self.assertEqual(["CDN·네트워크·DNS 이해는 확인되지 않는다"], kept.concerns, "카드에는 그대로 보여 준다")

    def test_major_or_years_short_caps_at_medium_and_says_why(self):
        for unmet in ("전공 요건 미확인: 공고 전자·전기 / 이력서 컴퓨터공학", "경력 6개월 모자람 (최소 3년)"):
            capped = RecommendService.require_all_met(fit(), {"unknown": [unmet]})
            self.assertEqual("보통", capped.fit, unmet)
            self.assertIn(unmet, capped.concerns, "카드에 까닭을 보여 준다")

    def test_major_not_written_on_the_resume_does_not_cap(self):
        """이력서에 전공을 안 적은 것은 안 맞는다는 증거가 아니다."""
        self.assertEqual("높음", RecommendService.require_all_met(fit(), {"unknown": ["전공 확인 필요: 컴퓨터·소프트웨어"]}).fit)

    def test_never_raises_a_grade(self):
        self.assertEqual("낮음", RecommendService.require_all_met(fit("낮음"), {"unknown": []}).fit)


if __name__ == "__main__":
    unittest.main()
