"""자격요건 구간의 전공·자격증·병역 추출과 하드 필터 판정."""

from __future__ import annotations

import dataclasses
import unittest

from job_matching_bot.ingestion.qualifications import extract_qualifications, normalize_term
from job_matching_bot.ingestion.requirement_sections import split_sections
from job_matching_bot.matching.hard_filter import hard_filter
from job_matching_bot.schemas.resume import mock_resumes
from job_matching_bot.tests.test_resumes import _saramin_job

BODY = """
📋 자격요건
- 컴퓨터공학, 소프트웨어 관련 학과 졸업자
- 정보처리기사 자격증 소지자
- 병역필 또는 면제자
- SQLD 소지자 우대
🏠 근무조건
- 정규직
"""


class CareerYearsTest(unittest.TestCase):
    """자격요건에서 최소 연차를 뽑는다. 우대 줄과 신입 언급 줄은 요구로 세지 않는다."""

    def test_min_years_from_various_phrasings(self):
        self.assertEqual(5, extract_qualifications(["- 경력 5년 이상"]).min_career_years)
        self.assertEqual(3, extract_qualifications(["IT 서비스 기획 경력 3년 이상 10년 이하"]).min_career_years)
        self.assertEqual(5, extract_qualifications(["자동차 전장 실무 경험 5~10년"]).min_career_years)
        self.assertEqual(3, extract_qualifications(["ㆍ경력 : 3년"]).min_career_years)

    def test_lowest_requirement_wins_across_roles(self):
        q = extract_qualifications(["풀스택 개발 경력 5년 이상", "PM 경험 소유자 (2년 이상)"])
        self.assertEqual(2, q.min_career_years)
        self.assertEqual(2, len(q.evidence["career"]))

    def test_years_that_are_not_requirements(self):
        self.assertIsNone(extract_qualifications(["2026년 하반기 채용"]).min_career_years)
        self.assertIsNone(extract_qualifications(["대졸(2년제) 이상"]).min_career_years)
        self.assertIsNone(extract_qualifications(["경력 3년 이하"]).min_career_years)
        self.assertIsNone(extract_qualifications(["경력 3년 이상 우대"]).min_career_years)

    def test_entry_mention_suppresses_years(self):
        q = extract_qualifications(["신입 또는 경력 2년 이상"])
        self.assertIsNone(q.min_career_years)
        self.assertTrue(q.mentions_entry)

    def test_required_without_years(self):
        q = extract_qualifications(["- NC 또는 MCT 가공 관련 경력자"])
        self.assertIsNone(q.min_career_years)
        self.assertTrue(q.career_required)
        self.assertFalse(extract_qualifications(["경력자 우대"]).career_required)


class ExtractQualificationsTest(unittest.TestCase):
    def test_extracts_major_certification_and_military(self):
        q = extract_qualifications(split_sections(BODY).required)
        self.assertEqual(["컴퓨터·소프트웨어"], q.majors)
        self.assertIn("컴퓨터", q.major_terms)
        self.assertIn("소프트웨어", q.major_terms)
        self.assertEqual(["정보처리기사"], q.certifications)  # SQLD는 우대 줄이라 제외
        self.assertTrue(q.military_required)
        self.assertEqual(1, len(q.evidence["majors"]))

    def test_major_any_and_military_any_are_ignored(self):
        q = extract_qualifications(["전공 무관", "병역 무관", "학력무관"])
        self.assertEqual([], q.majors)
        self.assertFalse(q.military_required)

    def test_generic_gisa_and_normalization(self):
        q = extract_qualifications(["- 전기기사 또는 산업안전기사 자격 보유자"])
        self.assertIn("전기기사", q.certifications)
        self.assertIn("산업안전기사", q.certifications)
        self.assertEqual("정보처리기사", normalize_term("정보 처리 기사"))


class HardFilterQualificationTest(unittest.TestCase):
    def _job(self):
        job = _saramin_job("q1", region="전국")
        job.required_majors = ["컴퓨터·소프트웨어"]
        job.required_major_terms = ["컴퓨터", "소프트웨어", "전산"]
        job.required_certifications = ["정보처리기사"]
        job.military_required = True
        return job

    def test_matching_resume_passes_major_and_certification(self):
        resume = dataclasses.replace(
            mock_resumes()["backend_entry"],
            majors=["컴퓨터소프트웨어공학과"],
            certifications=["정보처리기사"],
        )
        result = hard_filter(self._job(), resume)
        self.assertIn("전공 요건 충족: 컴퓨터소프트웨어공학과", result["passed"])
        self.assertIn("자격증 요건 충족: 정보처리기사", result["passed"])
        self.assertIn("병역 조건 확인 필요 (병역필 또는 면제)", result["unknown"])
        self.assertEqual([], result["failed"])

    def test_a_wrong_major_is_check_required_but_a_missing_certificate_fails(self):
        """전공과 자격증을 다르게 다룬다.

        학과 이름은 제각각이라(첨단융합학부, 스마트팩토리과 …) 못 맞췄다고 잘라내면
        억울한 탈락이 많다. 자격증은 이름이 정해져 있고, 자격요건에 적힌 것이 없으면
        실제로 지원이 안 된다.
        """
        resume = dataclasses.replace(
            mock_resumes()["backend_entry"], majors=["경영학과"], certifications=["SQLD"]
        )
        result = hard_filter(self._job(), resume)
        self.assertIn("필수 자격증 정보처리기사", result["failed"])
        self.assertTrue(any("전공 요건 미확인" in u for u in result["unknown"]))

    def test_a_resume_with_nothing_filled_in(self):
        """전공도 자격증도 안 적은 이력서. 전공은 확인 필요, 자격증은 탈락이다."""
        result = hard_filter(self._job(), mock_resumes()["backend_entry"])
        self.assertIn("전공 확인 필요: 컴퓨터·소프트웨어", result["unknown"])
        self.assertIn("필수 자격증 정보처리기사", result["failed"])


if __name__ == "__main__":
    unittest.main()


class LanguageTestTest(unittest.TestCase):
    """어학 성적은 자격증과 성격이 다르다. 섞으면 조건을 잘못 건다.

    자격요건에서 자격증이 잡힌 모집 중 공고 669건 중 361건(54%)이 어학 성적뿐이었다.
    OPIc 301건, TOEIC 203건이다. 앱 이력서의 자격사항 칸에 토익 점수를 적는 사람은
    드물어서, 이걸 자격증으로 취급하면 이력서에 안 적었다는 이유로 걸린다.
    """

    def test_a_language_score_is_not_a_certification(self):
        q = extract_qualifications(["• TOEIC 700점 이상 또는 그에 준하는 영어능력 보유자"])
        self.assertEqual([], q.certifications)
        self.assertEqual(["TOEIC"], q.language_tests)

    def test_opic_and_hsk_too(self):
        q = extract_qualifications(["ㆍ중국어 활용능력 우수자 (필수)_HSK6급 이상", "· OPIc IM2 이상"])
        self.assertEqual([], q.certifications)
        self.assertIn("HSK", q.language_tests)
        self.assertIn("OPIc", q.language_tests)

    def test_a_real_certification_still_lands_in_certifications(self):
        q = extract_qualifications(["• 정보처리기사 소지자"])
        self.assertEqual(["정보처리기사"], q.certifications)
        self.assertEqual([], q.language_tests)

    def test_a_line_with_both_splits_them(self):
        q = extract_qualifications(["• 자격 : 정보처리기사, TOEIC 800점 이상"])
        self.assertEqual(["정보처리기사"], q.certifications)
        self.assertEqual(["TOEIC"], q.language_tests)


class CertificationGroupTest(unittest.TestCase):
    """한 줄에 나열된 자격증은 '이 중 하나'다.

    쉼표로 나열한 99개 줄을 전부 읽어 보니 "정보처리기사, 네트워크관리사, 리눅스마스터 등",
    "CCNA/CCNP/CCIE 등"처럼 다 대안이었다. 둘 다 가지라는 공고는 하나도 없었다.
    """

    def test_either_or_becomes_one_group(self):
        q = extract_qualifications(["-대기환경기사 또는 산업위생관리기사"])
        self.assertEqual([["대기환경기사", "산업위생관리기사"]], q.certification_groups)

    def test_a_comma_list_is_also_one_group(self):
        q = extract_qualifications(["• 자격증: 실내건축기사, 실내건축산업기사"])
        self.assertEqual(1, len(q.certification_groups))
        self.assertEqual(2, len(q.certification_groups[0]))

    def test_asking_for_all_of_them_splits_the_group(self):
        q = extract_qualifications(["ㆍ정보처리기사 및 정보보안기사 모두 보유"])
        self.assertEqual([["정보처리기사"], ["정보보안기사"]], q.certification_groups)

    def test_one_certification_is_a_group_of_one(self):
        self.assertEqual([["정보처리기사"]], extract_qualifications(["• 정보처리기사"]).certification_groups)

    def test_the_flat_list_still_holds_every_name(self):
        """화면에는 평평한 목록을 쓴다. 묶음은 판정용이다."""
        q = extract_qualifications(["-대기환경기사 또는 산업위생관리기사"])
        self.assertEqual(["대기환경기사", "산업위생관리기사"], q.certifications)
