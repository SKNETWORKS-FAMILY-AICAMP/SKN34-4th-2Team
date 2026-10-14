"""본문 이미지 공고 플래그가 정규화·하드 필터·수집 레코드로 전달되는지 확인한다."""

from __future__ import annotations

import unittest

from job_matching_bot.matching.hard_filter import hard_filter
from job_matching_bot.schemas.resume import mock_resumes
from job_matching_bot.tests.test_resumes import _saramin_job


class BodyIsImageTest(unittest.TestCase):
    def test_image_only_job_is_check_required_not_fail(self):
        resume = mock_resumes()["embedded_entry_regional"]
        job = _saramin_job("img1", region="전국")
        job.body_is_image = True
        result = hard_filter(job, resume)
        self.assertNotEqual("FAIL", result["status"])
        self.assertIn("공고 상세가 이미지라 요구사항 미확인", result["unknown"])

    def test_text_job_has_no_image_note(self):
        resume = mock_resumes()["embedded_entry_regional"]
        job = _saramin_job("txt1", region="전국")
        self.assertFalse(job.body_is_image)
        self.assertNotIn("공고 상세가 이미지라 요구사항 미확인", hard_filter(job, resume)["unknown"])


if __name__ == "__main__":
    unittest.main()
