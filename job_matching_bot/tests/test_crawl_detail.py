"""상세 수집 — 본문이 이미지인지 가르는 규칙.

이 판정이 틀리면 두 곳이 함께 틀린다. 하드 필터가 "요구사항 미확인"을 달고, 화면에도
"공고 상세가 이미지" 라고 뜬다. 실제로 요건이 다 적힌 공고에 그 딱지가 붙으면 사용자가
멀쩡한 공고를 의심하게 된다.

길이만 보던 규칙이 어긋난 자리가 있었다. 자격요건·주요업무가 모두 적힌 789자짜리 공고가
기준 800자에 4글자 모자라 이미지로 넘어갔다. 저장소에서 이미지로 표시된 8,951건 가운데
5,245건이 본문에 요건 글을 갖고 있었다.
"""

from __future__ import annotations

import unittest

from job_matching_bot.crawling.crawl_detail import (
    REQUIREMENT_MIN_CHARS,
    TEXT_BODY_MIN_CHARS,
    has_requirement_text,
)

# 실제로 잘못 걸렸던 공고를 줄인 것. 요건이 다 적혀 있는데 800자에 못 미친다.
REAL_SHORT_BODY = (
    "상세요강 [주피터랩스] 백엔드 개발자 채용 모집분야 백엔드 개발자 (1명) "
    "주요업무 서비스 개발 및 운영, OMS / FMS / WMS 등 시스템 개발 및 운영, "
    "Java, Node를 통한 백엔드 서비스 개발, DB설계 및 운영. "
    "자격요건 경력 3년 이상 ~ 10년 이하, 대학졸업(2,3년)이상, "
    "ERP / OMS / WMS 등 시스템 개발 경험 1년 이상, "
    "Spring / SpringBoot 프레임워크를 이용한 웹 어플리케이션 개발 경험 1년 이상, "
    "Restful API를 활용한 서비스 개발 경험 2년 이상. "
    "우대사항 AWS / OCI / Azure를 활용한 서비스 개발 경험, 빌드 및 배포도구 사용 경험."
)


class RequirementTextTest(unittest.TestCase):
    def test_long_body_is_text_even_without_markers(self) -> None:
        """충분히 길면 표시어가 없어도 글로 본다. 예전 규칙을 그대로 지킨다."""
        self.assertTrue(has_requirement_text("가" * TEXT_BODY_MIN_CHARS))
        self.assertTrue(has_requirement_text("가" * (TEXT_BODY_MIN_CHARS + 500)))

    def test_short_body_with_requirements_is_text(self) -> None:
        """짧아도 요건이 적혀 있으면 글이다. 이것이 고친 대목이다."""
        self.assertLess(len(REAL_SHORT_BODY), TEXT_BODY_MIN_CHARS)
        self.assertTrue(has_requirement_text(REAL_SHORT_BODY))

    def test_empty_or_tiny_body_is_image(self) -> None:
        """본문이 없거나 거의 없으면 이미지 공고다. 전체의 3분의 1이 여기 든다."""
        for body in ("", "상세요강", "상세요강 채용합니다"):
            self.assertFalse(has_requirement_text(body), body)

    def test_marker_alone_is_not_enough(self) -> None:
        """표시어만 있고 내용은 이미지인 공고를 글로 보면 안 된다."""
        self.assertFalse(has_requirement_text("상세요강 자격요건 주요업무 우대사항"))

    def test_boundary(self) -> None:
        """최소 길이 바로 아래는 이미지, 바로 위는 글."""
        just_under = "자격요건 " + "가" * (REQUIREMENT_MIN_CHARS - 6)
        just_over = "자격요건 " + "가" * REQUIREMENT_MIN_CHARS
        self.assertLess(len(just_under), REQUIREMENT_MIN_CHARS)
        self.assertFalse(has_requirement_text(just_under))
        self.assertTrue(has_requirement_text(just_over))

    def test_no_marker_and_medium_length_is_image(self) -> None:
        """길이는 어중간하고 요건도 안 적혔으면 판단할 근거가 없다. 이미지로 둔다."""
        self.assertFalse(has_requirement_text("회사 소개와 인사말만 길게 적힌 글. " * 15))


if __name__ == "__main__":
    unittest.main()
