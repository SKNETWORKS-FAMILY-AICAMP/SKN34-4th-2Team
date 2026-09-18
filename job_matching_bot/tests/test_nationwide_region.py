"""공고 지역이 '전국'이면 희망 지역과 무관하게 통과하는지 확인한다."""

from __future__ import annotations

import unittest
from dataclasses import replace

from job_matching_bot.api.service import fit_order
from job_matching_bot.matching.hard_filter import hard_filter, is_nationwide
from job_matching_bot.schemas.resume import mock_resumes
from job_matching_bot.tests.test_resumes import _saramin_job


class NationwideRegionTest(unittest.TestCase):
    def test_nationwide_job_passes_any_preferred_region(self):
        resume = mock_resumes()["embedded_entry_regional"]  # 대전 희망
        job = _saramin_job("n1", region="대구 동구, 서울전체, 전국")
        result = hard_filter(job, resume)
        self.assertEqual([], result["failed"])
        self.assertIn("전국 근무 가능 — 지역 조건 충족", result["passed"])

    def test_non_nationwide_job_still_fails_on_mismatch(self):
        resume = mock_resumes()["embedded_entry_regional"]
        job = _saramin_job("n2", region="서울 강남구")
        self.assertEqual("FAIL", hard_filter(job, resume)["status"])

    def test_no_preferred_region_means_any_region_passes(self):
        """희망 지역을 안 골랐으면 지역은 따지지 않는다.

        앱은 '상관없음'을 빈 목록으로 보낸다. 빈 목록을 그대로 대조하면 어느 지역에도
        안 맞아 거의 모든 공고가 탈락했다.
        """
        resume = replace(mock_resumes()["embedded_entry_regional"], preferred_regions=[])
        job = _saramin_job("n3", region="부산 해운대구")
        result = hard_filter(job, resume)
        self.assertNotIn("FAIL", result["status"])
        self.assertIn("희망 지역 제한 없음", result["passed"])

    def test_no_preferred_employment_type_passes(self):
        resume = replace(mock_resumes()["embedded_entry_regional"], preferred_employment_types=[])
        job = _saramin_job("n4", region="대전 유성구")
        result = hard_filter(job, resume)
        self.assertFalse(any("고용형태 불일치" in f for f in result["failed"]))
        self.assertIn("고용형태 제한 없음", result["passed"])

    def test_unjudged_sorts_after_low(self):
        """판정을 못 받은 공고가 판정된 '낮음'보다 위에 서면 안 된다."""
        self.assertLess(fit_order("낮음"), fit_order(None))
        self.assertEqual([fit_order(x) for x in ("높음", "보통", "낮음")], [0, 1, 2])

    def test_helper(self):
        self.assertTrue(is_nationwide("전국"))
        self.assertTrue(is_nationwide("서울 강남구, 전국"))
        self.assertFalse(is_nationwide("전남광주 나주시"))


if __name__ == "__main__":
    unittest.main()
