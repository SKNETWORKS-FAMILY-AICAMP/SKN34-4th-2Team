"""공고 맞춤 지원 첫 화면의 주요 기업 카드 — 어떤 회사 · 공고를 올리는가."""

from datetime import date
from unittest import TestCase

from django.test import Client, SimpleTestCase

from lms.featured_postings import date_of, pick_live, pick_past, season_of, tier_of, wanted

TODAY = date(2026, 9, 30)


def job(job_id, company, *, company_type="미기재", title="백엔드 개발자 채용", deadline="2026-10-05T23:59",
        employment_type="정규직", career_type="ENTRY", tech_stack=None, source="SARAMIN_POC", group_key=None,
        posted_at=None, apply_method=None, logo_url=None):
    return {
        "job_id": job_id, "source": source, "group_key": group_key, "company": company, "company_type": company_type,
        "title": title, "deadline": deadline, "posted_at": posted_at, "employment_type": employment_type,
        "career_type": career_type, "tech_stack": tech_stack or [], "apply_method": apply_method, "logo_url": logo_url,
    }


class TierTests(TestCase):
    def test_big_company_by_company_type_not_1000_list(self):
        self.assertEqual(tier_of("현대자동차(주)", "코스피, 대기업, 1000대기업, 외부감사법.."), "대기업")
        self.assertIsNone(tier_of("중간회사", "중견기업, 1000대기업"), "1000대기업은 중견도 들어간다")

    def test_jobkorea_big_company_is_known_by_name(self):
        self.assertIsNone(tier_of("(주)케이티", "미기재"))
        self.assertEqual(tier_of("(주)케이티", "미기재", frozenset({"케이티"})), "대기업")

    def test_saramin_mid_sized_overrides_jobkorea_big(self):
        """잡코리아는 비상교육을 대기업으로 달았지만 사람인은 코스피 · 중견기업으로 적었다."""
        self.assertEqual(tier_of("㈜비상교육", "대기업, 코스피상장"), "대기업")
        self.assertIsNone(tier_of("㈜비상교육", "대기업, 코스피상장", small_names=frozenset({"비상교육"})))

    def test_popular_names_ignore_legal_marks_and_look_alikes(self):
        self.assertEqual(tier_of("(주)카카오페이", "미기재"), "인기 기업")
        self.assertEqual(tier_of("비바리퍼블리카", "스타트업, 외부감사법인"), "인기 기업")
        self.assertEqual(tier_of("쿠팡 (주)", "미기재"), "인기 기업")
        self.assertIsNone(tier_of("넥슨화장품", "중소기업"))
        self.assertIsNone(tier_of("라인건설", "중소기업"))
        self.assertEqual(tier_of("쿠팡풀필먼트서비스(유)", "대기업, 1000대기업"), "대기업", "계열사는 기업형태로 본다")

    def test_foreign_only_when_mid_sized_or_listed_and_no_agencies(self):
        self.assertEqual(tier_of("아나패스", "코스닥, 중견기업, 외국인 투자기업"), "외국계")
        self.assertIsNone(tier_of("에이치알그룹", "중소기업, 외국 법인기업, 주식회사"))
        self.assertIsNone(tier_of("(주)아데코코리아", "중견기업, 외국인 투자기업, 외부감사법.."))


class WantedTests(TestCase):
    def test_dev_titles_and_open_hiring_pass(self):
        self.assertTrue(wanted(job("1", "가", title="Security Analyst")))
        self.assertTrue(wanted(job("2", "가", title="2026 CJ그룹 신입사원 모집")))
        self.assertTrue(wanted(job("3", "가", title="[NHN]그룹 각 부문 수시 채용")))
        self.assertTrue(wanted(job("4", "가", title="2026년 KT 대졸신입 채용")))
        self.assertTrue(wanted(job("5", "가", title="2026 LG CNS 신입채용")))

    def test_field_jobs_contracts_and_career_only_are_left_out(self):
        self.assertFalse(wanted(job("1", "가", title="[쿠팡CFS] 현장관리자 정규직 대규모 채용")))
        self.assertFalse(wanted(job("2", "가", title="[HL만도] 시험평가 계약직 채용")))
        self.assertFalse(wanted(job("3", "가", title="백엔드 개발자", employment_type="계약직")))
        self.assertFalse(wanted(job("4", "가", title="물리보안 SI 엔지니어 경력직 채용")))
        self.assertTrue(wanted(job("5", "가", title="백엔드 개발 신입/경력 채용")))
        self.assertFalse(wanted(job("6", "가", title="[KFC] 체험형 인턴 채용(개발본부)")))
        self.assertFalse(wanted(job("7", "가", title="Email marketing with mail")), "영문 두 글자는 낱말일 때만")

    def test_training_programs_are_left_out_unless_hiring_linked(self):
        self.assertFalse(wanted(job("1", "가", title="[IBM] Cloud Native Dev base AI agent 6기")))
        self.assertFalse(wanted(job("2", "가", title="SW 개발자 부트캠프 교육생 모집")))
        self.assertFalse(wanted(job("3", "가", title="2026 K-뉴딜 아카데미 Let's Grow with LG전자 2기")))
        self.assertTrue(wanted(job("4", "가", title="채용연계형 SW 아카데미 개발자 모집")))
        self.assertTrue(wanted(job("5", "가", title="2026년 하반기 AI 인재 1기 신입사원 공개채용")), "기수가 있어도 채용이면 둔다")
        self.assertTrue(wanted(job("6", "가", title="AI 개발자 채용 (AI개발 국비 교육 이수必)")), "국비 수료자 채용")
        self.assertFalse(wanted(job("7", "가", title="[K-뉴딜] 어도비 AI 콘텐츠 마케팅 과정")))

    def test_open_hiring_with_non_dev_field_is_left_out(self):
        self.assertFalse(wanted(job("1", "가", title="2026년 하반기 신입사원 채용(건축-플랜트건축)")))
        self.assertFalse(wanted(job("2", "가", title="FY2026 하반기 신입사원(5급) 공개채용 (지점영업)")))
        self.assertFalse(wanted(job("3", "가", title="2026년 하반기 신입사원 공개채용_경영지원 (경영기획)")))
        self.assertFalse(wanted(job("4", "가", title="2026년 하반기 대우건설 신입사원 채용(사업-국내)")))
        self.assertFalse(wanted(job("5", "가", title="데이터센터 시공현장 채용(상시)")), "데이터센터는 개발 직무가 아니다")

    def test_foreign_companies_only_with_dev_titles(self):
        self.assertFalse(wanted(job("1", "가", title="2026 신입사원 공개채용"), "외국계"))
        self.assertTrue(wanted(job("2", "가", title="반도체장비 SW개발 신입사원 채용"), "외국계"))


class DateAndSeasonTests(TestCase):
    def test_dates(self):
        self.assertEqual(date_of("2026-10-05T23:59:59+09:00"), "2026-10-05")
        self.assertEqual(date_of("2026.09.20 20:00"), "2026-09-20")
        self.assertIsNone(date_of("상시채용"))
        self.assertIsNone(date_of(None))

    def test_season_from_title_first_then_start_date(self):
        self.assertEqual(season_of("2026년 하반기 신입사원 채용", None, "2026-09-15"), "2026 하반기")
        self.assertEqual(season_of("26년 상반기 공채", None, "2026-09-15"), "2026 상반기")
        self.assertEqual(season_of("27년 신입사원 채용", "2026-09-23", "2026-10-12"), "2026 하반기", "시작일로")
        self.assertEqual(season_of("신입 채용", None, "2026-03-20"), "2026 상반기", "시작일을 모르면 마감일로")
        self.assertEqual(season_of("각 부문 수시 채용", None, "2026-10-01"), "수시")
        self.assertEqual(season_of("신입 채용", None, None), "수시")


class PickLiveTests(TestCase):
    def test_one_card_per_company_with_the_nearest_deadline(self):
        cards = pick_live(
            [
                job("C-2", "쿠팡(주)", deadline="2026-10-09"),
                job("C-1", "쿠팡(주)", deadline="2026-10-02"),
                job("C-3", "쿠팡 (주)", deadline=None),
            ],
            TODAY,
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual((cards[0]["job_id"], cards[0]["posting_count"], cards[0]["company"]), ("C-1", 3, "쿠팡"))

    def test_same_posting_on_both_sites_counts_once_and_prefers_saramin(self):
        cards = pick_live(
            [
                job("JOBKOREA-1", "㈜엘지씨엔에스", group_key="g1", source="JOBKOREA_POC", apply_method="HOMEPAGE"),
                job("SARAMIN-1", "(주)엘지씨엔에스", group_key="g1", company_type="대기업"),
            ],
            TODAY,
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual((cards[0]["job_id"], cards[0]["posting_count"]), ("SARAMIN-1", 1))
        self.assertTrue(cards[0]["homepage"], "잡코리아 사본의 지원 방법도 본다")

    def test_english_aliases_do_not_split_a_company(self):
        cards = pick_live(
            [
                job("A", "엠디엑스 주식회사(MDX Inc.)", company_type="대기업"),
                job("B", "엠디엑스 주식회사(MDX lnc.)", company_type="대기업", source="JOBKOREA_POC"),
            ],
            TODAY,
        )
        self.assertEqual(len(cards), 1)

    def test_sorted_by_deadline_with_rolling_last_and_past_dropped(self):
        cards = pick_live(
            [
                job("A", "(주)카카오", deadline=None),
                job("B", "DB그룹", company_type="대기업", deadline="2026-10-02"),
                job("C", "CJ(주)", company_type="대기업", deadline="2026-09-30T23:59"),
                job("D", "한화오션(주)", company_type="대기업", deadline="2026-09-25"),
                job("E", "작은회사", company_type="중소기업", deadline="2026-09-30"),
            ],
            TODAY,
        )
        self.assertEqual([c["job_id"] for c in cards], ["C", "B", "A"])
        self.assertIsNone(cards[-1]["deadline"])

    def test_homepage_is_unknown_without_apply_method(self):
        cards = pick_live([job("A", "(주)카카오")], TODAY)
        self.assertIsNone(cards[0]["homepage"])
        self.assertFalse(pick_live([job("A", "(주)카카오", apply_method="SITE")], TODAY)[0]["homepage"])


class PickPastTests(TestCase):
    def test_closed_hiring_grouped_by_company_and_season(self):
        cards = pick_past(
            [
                job("S1", "삼성전자(주)", company_type="대기업", title="2026년 하반기 3급 신입사원 채용 (DX부문)(재무)", deadline="2026-09-15"),
                job("S2", "삼성전자(주)", company_type="대기업", title="2026년 하반기 3급 신입사원 채용 (DX부문)(소프트웨어)", deadline="2026-09-15"),
                job("S3", "삼성전자(주)", company_type="대기업", title="2026년 상반기 3급 신입사원 채용 (소프트웨어)", deadline="2026-03-20"),
                job("K1", "(주)케이티", company_type="대기업", title="2026년 KT 대졸신입 채용", deadline="2026-09-04"),
                job("OPEN", "(주)카카오", deadline="2026-10-05"),
            ],
            TODAY,
        )
        self.assertEqual([(c["company"], c["season"]) for c in cards],
                         [("삼성전자", "2026 하반기"), ("케이티", "2026 하반기"), ("삼성전자", "2026 상반기")])
        self.assertEqual(cards[0]["job_id"], "S2", "개발 직무 공고가 대표")
        self.assertTrue(all(c["closed"] for c in cards))

    def test_older_than_a_year_is_dropped(self):
        self.assertEqual(pick_past([job("A", "(주)카카오", deadline="2025-09-01")], TODAY), [])


class FeaturedRouteTests(SimpleTestCase):
    def test_needs_login(self):
        client = Client(HTTP_HOST="127.0.0.1")
        self.assertEqual(client.get("/api/featured-postings").status_code, 401)
