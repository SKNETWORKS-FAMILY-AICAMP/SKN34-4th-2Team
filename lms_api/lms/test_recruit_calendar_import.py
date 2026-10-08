"""공채 달력 → company_profiles · apply_method 계획 — 빈 칸만 채우고 관리자 값은 덮지 않는다"""

from django.test import SimpleTestCase

from lms.recruit_calendar_import import by_key, plan

COMPANIES = [
    {"company_name": "(주)카카오", "company_type": "대기업", "logo_url": None, "postings": 1},
    {"company_name": "카카오", "company_type": None, "logo_url": "https://clogo/kakao.png", "postings": 5},
    {"company_name": "토스뱅크(주)", "company_type": "대기업", "logo_url": "https://clogo/toss.png", "postings": 2},
    {"company_name": "  ", "company_type": "대기업", "logo_url": None, "postings": 1},
]
POSTINGS = [
    {"source": "SARAMIN_POC", "source_job_id": "1", "apply_method": "HOMEPAGE"},
    {"source": "SARAMIN_POC", "source_job_id": "2", "apply_method": "EMAIL"},
    {"source": "JOBKOREA_POC", "source_job_id": "9"},
]


class RecruitCalendarImportTests(SimpleTestCase):
    def test_same_key_merges(self) -> None:
        merged = by_key(COMPANIES)
        self.assertEqual(set(merged), {"카카오", "토스뱅크"}, "법인 표기만 다른 이름은 한 회사 · 빈 이름은 버림")
        self.assertEqual(merged["카카오"]["company_name"], "카카오", "공고가 많은 쪽 이름")
        self.assertEqual((merged["카카오"]["company_type"], merged["카카오"]["logo_url"]), ("대기업", "https://clogo/kakao.png"))

    def test_fill_only_empty(self) -> None:
        existing = {"카카오": {"company_key": "카카오", "company_type": "인기 기업", "logo_url": None}}
        result = plan(COMPANIES, POSTINGS, existing, open_methods={("SARAMIN_POC", "1")})
        self.assertEqual([c["company_key"] for c in result.create], ["토스뱅크"])
        self.assertEqual(result.fill, {"카카오": {"logo_url": "https://clogo/kakao.png"}}, "관리자가 정한 형태는 그대로")
        self.assertEqual(result.apply_methods, {("SARAMIN_POC", "1"): "HOMEPAGE"}, "이미 값이 있거나 우리에게 없는 공고는 건너뜀")
