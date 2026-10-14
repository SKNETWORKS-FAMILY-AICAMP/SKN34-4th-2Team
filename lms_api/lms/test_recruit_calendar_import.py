"""공채 달력 → company_profiles · apply_method 계획 — 빈 칸만 채우고 관리자 값은 덮지 않는다"""

from unittest import skipUnless

from django.db import connection
from django.test import SimpleTestCase, TestCase

from lms.models import CompanyProfiles
from lms.recruit_calendar_import import apply, by_key, current_state, plan

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


@skipUnless(connection.vendor == "postgresql", "jobs 스키마는 PostgreSQL")
class RecruitCalendarApplyTests(TestCase):
    """실제로 쓴다(테스트 DB) — 두 번 돌려도 같고, 관리자 값과 이미 정한 지원 방법은 그대로"""

    def setUp(self) -> None:
        with connection.cursor() as cur:
            for job_id, sid, method in (("SARAMIN_POC:1", "1", None), ("SARAMIN_POC:2", "2", "SITE")):
                cur.execute(
                    """INSERT INTO jobs.jobs(job_id, source, source_job_id, apply_method, first_seen_at, last_seen_at)
                       VALUES (%s, 'SARAMIN_POC', %s, %s, now(), now())""",
                    [job_id, sid, method],
                )
        CompanyProfiles.objects.create(company_key="카카오", company_name="카카오", company_type="인기 기업")

    def run_import(self) -> None:
        existing, open_methods = current_state(POSTINGS)
        apply(plan(COMPANIES, POSTINGS, existing, open_methods))

    def test_apply_twice(self) -> None:
        self.run_import()
        self.run_import()
        rows = {r.company_key: r for r in CompanyProfiles.objects.all()}
        self.assertEqual(set(rows), {"카카오", "토스뱅크"})
        self.assertEqual((rows["카카오"].company_type, rows["카카오"].logo_url), ("인기 기업", "https://clogo/kakao.png"))
        self.assertEqual(rows["토스뱅크"].company_name, "토스뱅크(주)")
        with connection.cursor() as cur:
            cur.execute("SELECT source_job_id, apply_method FROM jobs.jobs WHERE source = 'SARAMIN_POC' ORDER BY 1")
            self.assertEqual(cur.fetchall(), [("1", "HOMEPAGE"), ("2", "SITE")])

    def test_card_query_finds_logo(self) -> None:
        """공채 카드 조회의 열쇠(PROFILE_KEY_SQL)로 「(주)카카오」 공고가 카카오 로고를 찾는다"""
        from lms.featured_postings import PROFILE_KEY_SQL

        self.run_import()
        with connection.cursor() as cur:
            cur.execute(
                f"""SELECT p.logo_url FROM (SELECT '(주)카카오 '::varchar AS company) j
                    LEFT JOIN public.company_profiles p ON p.company_key = {PROFILE_KEY_SQL}"""
            )
            self.assertEqual(cur.fetchone()[0], "https://clogo/kakao.png")
