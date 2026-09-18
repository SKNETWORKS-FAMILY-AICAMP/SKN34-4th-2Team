"""목록 회사명 칸의 버튼·뱃지 떼기. 예시는 2026-09-13 밤 목록에서 실제로 나온 표기다."""

import unittest

from job_matching_bot.ingestion.company_name import clean_company_name, clean_listing_text


class CleanCompanyNameTest(unittest.TestCase):
    def test_badges_after_the_name_are_removed(self):
        self.assertEqual("현대카드(주)", clean_company_name("현대카드(주) 현대자동차그룹 대기업"))
        self.assertEqual("(주)알파프라임", clean_company_name("(주)알파프라임 관심기업 등록"))
        self.assertEqual("NEZOT주식회사", clean_company_name("NEZOT주식회사 관심기업 등록 외국계"))
        self.assertEqual("SELPEO", clean_company_name("SELPEO 외국계 파견·도급·대행"))
        self.assertEqual("(주)라이드플럭스", clean_company_name("(주)라이드플럭스 쏘카그룹"))
        self.assertEqual("에스디바이오센서(주)", clean_company_name("에스디바이오센서(주) 에스디바이오센서그룹 외국계"))

    def test_a_company_whose_name_ends_with_group_keeps_it(self):
        """떼고 나서 법인 표기만 남으면 '~그룹'이 회사명이었던 것이다."""
        self.assertEqual("주식회사 와이앤컨설팅그룹", clean_company_name("주식회사 와이앤컨설팅그룹"))
        self.assertEqual("주식회사 메가서치그룹", clean_company_name("주식회사 메가서치그룹 관심기업 등록"))
        self.assertEqual("해커스교육그룹", clean_company_name("해커스교육그룹"))

    def test_a_clean_name_is_unchanged(self):
        for name in ("(주)크루컴퍼니", "메리티움(주)", "주식회사브이링크글로벌(VLINKGLOBALCo.,Ltd.)", "대기업"):
            with self.subTest(name):
                self.assertEqual(name, clean_company_name(name))


class CleanListingTextTest(unittest.TestCase):
    def test_html_entities_in_titles_are_decoded(self):
        self.assertEqual("안드로이드&ios 개발자", clean_listing_text("안드로이드&amp;ios 개발자"))
        self.assertEqual("R&D", clean_listing_text("R&amp;amp;D"), "두 번 감싼 것도 푼다")
        self.assertEqual("[코레이즈]  Python", clean_listing_text("[코레이즈]  Python"), "띄어쓰기는 그대로")


if __name__ == "__main__":
    unittest.main()
