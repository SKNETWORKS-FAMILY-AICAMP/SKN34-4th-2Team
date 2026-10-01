"""본문 구간 분리와 규칙 기반 필수·우대 추출 테스트."""

from __future__ import annotations

import unittest

from job_matching_bot.coach.skill_source import METHOD_SECTION_RULES, extract_requirements
from job_matching_bot.ingestion.requirement_sections import heading_kind, split_sections

BODY = """
㈜샘플 | 백엔드 개발자 채용
📋 주요업무
- 학습 플랫폼 REST API 개발
- 데이터 파이프라인 운영
📋 자격요건
- Python 기반 백엔드 개발 경험 2년 이상
- PostgreSQL 등 RDBMS 사용 경험
📋 우대사항
- FastAPI, Docker 사용 경험
- AWS 운영 경험
🏠 근무조건
- 정규직, 서울 성동구
🚀 채용절차
서류전형 > 면접
"""


class HeadingKindTest(unittest.TestCase):
    def test_recognizes_decorated_headings(self):
        self.assertEqual("required", heading_kind("📋 자격요건"))
        self.assertEqual("required", heading_kind("[지원 자격]"))
        self.assertEqual("preferred", heading_kind("■ 우대사항"))
        self.assertEqual("duties", heading_kind("담당업무 :"))
        self.assertEqual("stop", heading_kind("🏠 근무조건"))
        self.assertEqual("required", heading_kind("자격요건 (공통)"))

    def test_body_lines_are_not_headings(self):
        self.assertIsNone(heading_kind("- Python 기반 백엔드 개발 경험 2년 이상"))
        self.assertIsNone(heading_kind("우대사항에 해당하는 분은 가산점이 있습니다"))


class SplitSectionsTest(unittest.TestCase):
    def test_splits_required_preferred_duties(self):
        sections = split_sections(BODY)
        self.assertEqual(2, len(sections.required))
        self.assertIn("- FastAPI, Docker 사용 경험", sections.preferred)
        self.assertEqual(2, len(sections.duties))
        # 근무조건 이후 줄은 어느 구간에도 들어가지 않는다.
        self.assertFalse(any("정규직" in line for line in sections.required + sections.preferred))

    def test_inline_heading_with_content_on_same_line(self):
        body = (
            "우리는 Python과 FastAPI로 백엔드 API를 개발합니다.\n"
            "[자격요건] PostgreSQL 사용 경험이 필요합니다.\n"
            "[우대사항] Docker 기반 배포 경험이 있으면 좋습니다."
        )
        sections = split_sections(body)
        self.assertEqual(["PostgreSQL 사용 경험이 필요합니다."], sections.required)
        self.assertEqual(["Docker 기반 배포 경험이 있으면 좋습니다."], sections.preferred)

    def test_startup_style_headings(self):
        """'자격요건'이란 말 없이 말하듯 나눈 공고. 실제 공고(파스토로보틱스)의 구조다.

        이런 공고가 저장소에 665건 있었고 IT만 151건이 요건 0자로 잡혀 인덱스에
        못 올랐다. 제목만 알려주면 나머지 규칙은 그대로 맞는다.
        """
        body = (
            "팀 소개\n물류 로봇을 만듭니다.\n"
            "이런 일을 해요\n• 물류 ERP 운영 및 신규 기능 개발\n• WMS 고도화 개발\n"
            "이런 분을 찾습니다\n• Java, Spring Boot 사용 경험\n"
            "이런 분이면 더욱 좋아요\n• 물류 도메인 경험\n"
            "채용 프로세스\n서류 → 면접"
        )
        sections = split_sections(body)
        self.assertEqual(["• 물류 ERP 운영 및 신규 기능 개발", "• WMS 고도화 개발"], sections.duties)
        self.assertEqual(["• Java, Spring Boot 사용 경험"], sections.required)
        self.assertEqual(["• 물류 도메인 경험"], sections.preferred)
        self.assertFalse(any("서류" in line for line in sections.preferred), "채용 프로세스에서 끝난다")

    def test_no_headings_returns_empty(self):
        self.assertFalse(split_sections("이미지 공고입니다.\n자세한 내용은 이미지를 참고하세요.").found)


class RuleExtractionTest(unittest.TestCase):
    def test_sections_split_required_and_preferred(self):
        result = extract_requirements("백엔드 개발자", BODY, allow_llm=False)
        self.assertEqual(METHOD_SECTION_RULES, result["method"])
        self.assertIn("Python", result["required_skills"])
        self.assertIn("PostgreSQL", result["required_skills"])
        self.assertIn("FastAPI", result["preferred_skills"])
        self.assertIn("Docker", result["preferred_skills"])
        self.assertIn("AWS", result["preferred_skills"])
        # 필수에 있는 기술은 우대에 중복으로 들어가지 않는다.
        self.assertNotIn("Python", result["preferred_skills"])
        # 근거 문장이 남는다.
        python = next(s for s in result["skills"] if s["name"] == "Python")
        self.assertEqual("REQUIRED", python["requirement_type"])
        self.assertIn("Python", python["evidence"])

    def test_jobkorea_skill_block_is_required(self):
        """잡코리아 양식은 「자격요건」 칸에 학력 · 경력만 두고 기술은 「스킬」 칸에 둔다."""
        body = (
            "포지션 및 자격요건\n의료정보시스템 구축 및 유지보수 인력 채용\n( 1명 )\n담당업무\n"
            "ㆍ의료정보 시스템 개발 및 유지 보수\n스킬\nㆍ.Net, C#, MS-SQL, Oracle\n"
            "자격요건\nㆍ학력 : 초대졸이상\nㆍ경력 : 경력\n우대사항\nㆍ인근거주자\n"
        )
        result = extract_requirements("경력 개발자 수시 채용", body, allow_llm=False)
        self.assertIn("C#", result["required_skills"])
        self.assertIn("SQL", result["required_skills"])
        self.assertEqual("required", heading_kind("이런 기술이 필요해요"))

    def test_heading_name_with_colon_content_keeps_the_content(self):
        """「ㆍ필요스킬 : C#, Oracle」은 제목이 아니라 자격요건 구간의 한 줄이다."""
        sections = split_sections("[자격요건]\nㆍ경력 : 개발 경력 5년이상~\nㆍ필요스킬 : C#, Oracle\n[우대사항]\nㆍMES 경험")
        self.assertIn("ㆍ필요스킬 : C#, Oracle", sections.required)
        self.assertIsNone(heading_kind("ㆍ필요스킬 : C#, Oracle"))

    def test_without_headings_falls_back_to_unknown(self):
        result = extract_requirements("개발자", "Python과 Java를 다루는 분을 찾습니다.", allow_llm=False)
        self.assertEqual("keyword_extractor", result["method"])
        self.assertEqual([], result["required_skills"])
        self.assertIn("Python", result["unknown_skills"])


if __name__ == "__main__":
    unittest.main()
