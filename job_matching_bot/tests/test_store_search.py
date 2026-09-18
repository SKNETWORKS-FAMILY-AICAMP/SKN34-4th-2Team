"""조건으로 공고를 찾는 부분. 챗봇이 쓴다.

핵심 약속: **사용자가 말하지 않은 조건으로 거르지 않는다.** 그리고 마감된 공고는
살아 있는 것처럼 보여주지 않는다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.retrieval.store_search import KST, JobFilters, deadline_passed, search

NOW = datetime(2026, 9, 7, 12, tzinfo=KST)


class StoreSearchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        self.jobs = [
            replace(
                base,
                job_id="A",
                source_job_id="A",
                company="가회사",
                title="백엔드 개발자",
                description="Python으로 API를 만듭니다",
                tech_stack=["Python", "FastAPI"],
                keywords=["IT개발·데이터"],
                region="서울 강남구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline="2026-09-30",
                status="OPEN",
            ),
            replace(
                base,
                job_id="B",
                source_job_id="B",
                company="나회사",
                title="프론트엔드 개발자",
                description="React로 화면을 만듭니다",
                tech_stack=["React"],
                keywords=["IT개발·데이터"],
                region="경기 성남시",
                career_type="EXPERIENCED",
                min_career_years=3,
                employment_type="정규직",
                deadline=None,
                status="OPEN",
            ),
            replace(
                base,
                job_id="C",
                source_job_id="C",
                company="다회사",
                title="생산관리 담당자",
                description="공정을 관리합니다",
                tech_stack=[],
                keywords=["생산"],
                region="서울 금천구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="계약직",
                deadline="2026-09-08",
                status="OPEN",
            ),
            replace(
                base,
                job_id="D",
                source_job_id="D",
                company="라회사",
                title="백엔드 개발자 (마감)",
                description="Python 서버",
                tech_stack=["Python"],
                keywords=["IT개발·데이터"],
                region="서울 마포구",
                career_type="ENTRY",
                min_career_years=None,
                employment_type="정규직",
                deadline="2026-09-01",
                status="OPEN",
            ),
        ]
        with SqliteJobStore(self.path) as store:
            store.upsert(self.jobs, source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def find(self, **kwargs):
        return search(self.path, JobFilters(**kwargs), limit=10, as_of=NOW)

    def test_no_conditions_returns_every_live_posting(self):
        result = self.find()
        self.assertEqual({"A", "B", "C"}, {job.job_id for job in result.jobs})

    def test_expired_postings_never_surface(self):
        """마감일이 지난 공고는 status가 OPEN이어도 보여주지 않는다."""
        result = self.find(roles=["백엔드"])
        self.assertEqual(["A"], [job.job_id for job in result.jobs])

    def test_role_matches_title_tags_or_body(self):
        self.assertEqual(["B"], [job.job_id for job in self.find(roles=["프론트엔드"]).jobs])
        self.assertEqual(["A"], [job.job_id for job in self.find(skills=["FastAPI"]).jobs])
        # 본문에만 있는 말도 찾는다.
        self.assertEqual(["C"], [job.job_id for job in self.find(keywords=["공정"]).jobs])

    def test_several_terms_match_any_of_them(self):
        """'백엔드 React'는 둘 다인 공고가 아니라 하나라도 걸리는 공고를 찾는다."""
        result = self.find(roles=["백엔드", "프론트엔드"])
        self.assertEqual({"A", "B"}, {job.job_id for job in result.jobs})

    def test_role_and_skill_together_must_both_match(self):
        """'파이썬 쓰는 프론트엔드'에 Python 백엔드 공고가 나가면 안 된다.

        예전에는 직무·기술을 하나라도 맞으면 걸어서, Python만 적힌 공고가 프론트엔드 공고로 나갔다.
        """
        with SqliteJobStore(self.path) as store:
            store.upsert(self.jobs + [replace(
                self.jobs[1], job_id="E", source_job_id="E", title="프론트엔드 개발자 (Python 도구)",
                tech_stack=["React", "Python"], region="서울 강남구",
            )], source="MOCK")
        found = {job.job_id for job in self.find(roles=["프론트엔드"], skills=["Python"]).jobs}
        self.assertEqual({"E"}, found, "Python만 있는 A, 프론트엔드만 있는 B는 빠진다")

    def test_a_role_only_in_the_body_does_not_count_when_a_skill_is_given(self):
        """본문의 '프론트엔드와 협업'은 프론트엔드를 뽑는 공고가 아니다."""
        with SqliteJobStore(self.path) as store:
            store.upsert(self.jobs + [replace(
                self.jobs[0], job_id="F", source_job_id="F", title="백엔드 개발자",
                description="Python API를 만들고 프론트엔드와 협업합니다",
            )], source="MOCK")
        self.assertEqual([], self.find(roles=["프론트엔드"], skills=["Python"]).jobs)
        # 직무만 말했을 때는 예전처럼 본문도 본다.
        self.assertIn("F", {job.job_id for job in self.find(roles=["프론트엔드"]).jobs})

    def _add(self, *jobs):
        with SqliteJobStore(self.path) as store:
            store.upsert(self.jobs + list(jobs), source="MOCK")

    def _job(self, job_id, **fields):
        return replace(self.jobs[0], job_id=job_id, source_job_id=job_id, **fields)

    def test_a_long_role_is_found_word_by_word(self):
        """'AI 엔지니어'는 한 덩어리가 아니다. 'AI Engineer'·'인공지능 개발'도 같은 일이다."""
        self._add(
            self._job("E1", title="AI Engineer 채용", company="가"),
            self._job("E2", title="인공지능 엔지니어 모집", company="나"),
            self._job("E3", title="메일 서버 엔지니어", company="다", description="Mail 서버 운영"),
        )
        found = {job.job_id for job in self.find(roles=["AI 엔지니어"]).jobs}
        self.assertTrue({"E1", "E2"} <= found)
        self.assertNotIn("E3", found, "Mail의 ai는 AI가 아니다")

    def test_the_exact_phrase_in_the_title_comes_first(self):
        """낱말로 나눠 찾아도 제목에 말 그대로 있는 공고가 앞이다."""
        self._add(
            self._job("S1", title="서비스 사업기획 담당", company="가", tech_stack=[], keywords=["기획"]),
            self._job("S2", title="서비스 기획자 채용", company="나", tech_stack=[], keywords=["기획"]),
        )
        self.assertEqual("S2", self.find(roles=["서비스 기획"]).jobs[0].job_id)

    def test_korean_tool_names_find_english_titles(self):
        self._add(self._job("U1", title="Unity 클라이언트 개발자", company="가", description="모바일 게임"))
        self.assertIn("U1", {job.job_id for job in self.find(roles=["유니티 클라이언트"]).jobs})

    def test_develop_is_not_business_development(self):
        """'개발'로 찾을 때 '사업개발'만 적힌 공고는 걸리지 않는다."""
        self._add(
            self._job("F1", title="B2B 사업개발 매니저", company="가", description="영업 채널 확대", tech_stack=[], keywords=["영업"]),
            self._job("F2", title="앱 개발 인턴", company="나", tech_stack=[], keywords=["IT개발·데이터"]),
        )
        found = {job.job_id for job in self.find(roles=["개발"]).jobs}
        self.assertIn("F2", found)
        self.assertNotIn("F1", found)

    def test_company_type_words_filter_by_company_info_not_text(self):
        """'대기업'은 기업 정보 칸으로 거른다. 제목의 '(대기업 상주)'나 '1000대기업'은 아니다."""
        self._add(
            self._job("G1", title="IT 신입", company="큰회사", company_type="대기업, 주식회사"),
            self._job("G2", title="시스템 엔지니어 (대기업 상주)", company="파견사", company_type="중소기업"),
            self._job("G3", title="IT 운영", company="중간회사", company_type="중견기업, 1000대기업"),
        )
        found = {job.job_id for job in self.find(roles=["IT"], keywords=["대기업"]).jobs}
        self.assertEqual({"G1"}, found)

    def test_the_same_posting_listed_per_region_shows_once(self):
        """회사와 머리말 뗀 제목이 같으면 한 공고다. 소괄호가 다르면 다른 공고다."""
        self._add(
            self._job("H1", company="고려휴먼스", title="[공기업/부산] 사무 보조"),
            self._job("H2", company="고려휴먼스", title="[공기업/강남] 사무 보조"),
            self._job("H3", company="고려휴먼스", title="사무 보조 (경력 3년)"),
        )
        result = self.find(roles=["사무"])
        ids = [job.job_id for job in result.jobs]
        self.assertEqual(1, len({"H1", "H2"} & set(ids)))
        self.assertIn("H3", ids)
        self.assertEqual(len(ids), result.total)

    def test_excluded_company_type_is_left_out(self):
        """'스타트업은 빼고'는 기업 정보 칸에 스타트업이 있는 공고를 뺀다."""
        self._add(
            self._job("X1", title="데이터 분석 신입", company="작은회사", company_type="스타트업, 주식회사"),
            self._job("X2", title="데이터 분석 신입", company="큰회사", company_type="대기업"),
        )
        found = {job.job_id for job in self.find(roles=["데이터 분석"], exclude_keywords=["스타트업"]).jobs}
        self.assertIn("X2", found)
        self.assertNotIn("X1", found)

    def test_excluded_employment_type_and_title_words(self):
        """고용형태는 고용형태 칸에서, 나머지 말은 제목·회사명에서 뺀다. 본문은 보지 않는다."""
        self._add(
            self._job("Y1", title="QA 테스터", company="가", employment_type="파견직"),
            self._job("Y2", title="[헤드헌팅] QA 매니저", company="나", employment_type="정규직"),
            self._job("Y3", title="QA 엔지니어", company="다", employment_type="정규직",
                      description="파견 근무 없음, 헤드헌팅 아님"),
        )
        found = {job.job_id for job in self.find(roles=["QA"], exclude_keywords=["파견", "헤드헌팅"]).jobs}
        self.assertEqual({"Y3"}, found & {"Y1", "Y2", "Y3"})

    def test_posted_within_days_counts_from_first_seen(self):
        """'오늘 올라온'은 마지막 수집에서 처음 본 공고다. 밤에 수집하므로 오늘 날짜로 세면 낮엔 0건이다."""
        with SqliteJobStore(self.path) as store:
            store.upsert(self.jobs, source="MOCK", as_of=datetime(2026, 9, 1, tzinfo=KST))
            store.upsert([self._job("N1", title="백엔드 신규", company="새회사")], source="MOCK", as_of=NOW)
        self.assertEqual(["N1"], [job.job_id for job in self.find(roles=["백엔드"], posted_within_days=0).jobs])
        self.assertIn("A", {job.job_id for job in self.find(roles=["백엔드"], posted_within_days=7).jobs})

    def test_summary_names_exclusions_and_posted_days(self):
        filters = JobFilters(roles=["백엔드"], exclude_keywords=["스타트업"], posted_within_days=0)
        self.assertEqual("백엔드 · 새로 올라온 · 스타트업 제외", filters.summary())

    def test_region_narrows(self):
        self.assertEqual({"A", "C"}, {job.job_id for job in self.find(regions=["서울"]).jobs})

    def test_entry_level_includes_open_to_all(self):
        """신입을 찾을 때 '경력무관'도 포함한다. 지원할 수 있는 자리다."""
        with SqliteJobStore(self.path) as store:
            store.upsert([replace(self.jobs[1], job_id="E", source_job_id="E", career_type="ANY")], source="MOCK")
        result = self.find(career="신입")
        self.assertIn("E", {job.job_id for job in result.jobs})
        self.assertNotIn("B", {job.job_id for job in result.jobs})

    def test_experienced_excludes_entry_only(self):
        result = self.find(career="경력")
        self.assertEqual(["B"], [job.job_id for job in result.jobs])

    def test_employment_type_narrows(self):
        self.assertEqual(["C"], [job.job_id for job in self.find(employment_types=["계약직"]).jobs])

    def test_deadline_soon_keeps_only_dated_and_near(self):
        """마감 임박은 날짜가 없는 상시 공고를 빼야 한다. 급한 것만 보려는 요청이다."""
        result = self.find(deadline_within_days=3)
        self.assertEqual(["C"], [job.job_id for job in result.jobs])

    def test_conditions_combine_with_and(self):
        result = self.find(regions=["서울"], career="신입", employment_types=["정규직"])
        self.assertEqual(["A"], [job.job_id for job in result.jobs])

    def test_total_counts_beyond_the_shown_page(self):
        result = search(self.path, JobFilters(), limit=1, as_of=NOW)
        self.assertEqual(1, len(result.jobs))
        self.assertEqual(3, result.total)

    def test_career_label_is_readable(self):
        by_id = {job.job_id: job for job in self.find().jobs}
        self.assertEqual("신입", by_id["A"].career_label)
        self.assertEqual("경력 3년 이상", by_id["B"].career_label)

    def test_title_match_outranks_a_body_mention(self):
        """본문에 말이 스친 범용 공고가 그 일을 뽑는 공고를 밀어내면 안 된다.

        "신입/경력 공개채용" 같은 공고는 본문에 온갖 직무를 다 적어 둔다. 정렬을 안 하면
        무엇을 물어도 그런 공고만 올라온다.
        """
        with SqliteJobStore(self.path) as store:
            store.upsert(
                [
                    replace(
                        self.jobs[0],
                        job_id="Z",
                        source_job_id="Z",
                        company="마회사",
                        title="2026 공개채용",
                        description="백엔드, 프론트엔드, 기획 등 전 직군을 뽑습니다",
                        tech_stack=[],
                        keywords=["총무·법무·사무"],
                    )
                ],
                source="MOCK",
            )
        jobs = self.find(roles=["백엔드"]).jobs
        self.assertEqual("A", jobs[0].job_id, "제목에 있는 공고가 먼저")
        self.assertEqual(3, jobs[0].relevance)
        self.assertEqual("Z", jobs[1].job_id)
        self.assertEqual(1, jobs[1].relevance, "본문에만 있으면 낮게")

    def test_strong_counts_only_title_and_tag_matches(self):
        with SqliteJobStore(self.path) as store:
            store.upsert(
                [
                    replace(
                        self.jobs[0],
                        job_id="Z",
                        source_job_id="Z",
                        title="2026 공개채용",
                        description="백엔드 등 전 직군",
                        tech_stack=[],
                        keywords=["총무·법무·사무"],
                    )
                ],
                source="MOCK",
            )
        result = self.find(roles=["백엔드"])
        self.assertEqual(2, result.total)
        self.assertEqual(1, result.strong, "본문에만 스친 것은 빼고 센다")

    def test_a_keyword_narrows_instead_of_widening(self):
        """"재택 가능한 QA"에 QA 공고 전부가 걸렸다. 키워드는 직무와 함께 맞아야 한다."""
        with SqliteJobStore(self.path) as store:
            store.upsert([replace(self.jobs[0], job_id="R", source_job_id="R",
                                  title="백엔드 개발자 (재택 가능)")], source="MOCK")
        both = self.find(roles=["백엔드"], keywords=["재택"])
        self.assertEqual(["R"], [job.job_id for job in both.jobs])
        self.assertGreater(self.find(roles=["백엔드"]).total, both.total)

    def test_keywords_of_the_same_meaning_are_either_or(self):
        """"재택이나 원격근무"는 둘 중 하나만 적혀 있어도 된다."""
        with SqliteJobStore(self.path) as store:
            store.upsert([replace(self.jobs[0], job_id="P", source_job_id="P",
                                  title="백엔드 개발자 (원격근무)")], source="MOCK")
        found = self.find(roles=["백엔드"], keywords=["재택", "원격근무"])
        self.assertEqual(["P"], [job.job_id for job in found.jobs])

    def test_company_type_words_of_the_same_meaning_are_either_or(self):
        """"공기업이나 공공기관"은 기업 정보 칸의 '공사/공기업'이다. 제목의 "(공공기관)"은 아니다."""
        with SqliteJobStore(self.path) as store:
            store.upsert([
                replace(self.jobs[0], job_id="P", source_job_id="P", title="백엔드 개발자",
                        company="공사", company_type="공사/공기업"),
                replace(self.jobs[0], job_id="Q", source_job_id="Q", title="백엔드 개발자 (공공기관)",
                        company="파견사", company_type="중소기업"),
            ], source="MOCK")
        found = self.find(roles=["백엔드"], keywords=["공기업", "공공기관"])
        self.assertEqual(["P"], [job.job_id for job in found.jobs])

    def test_deadline_time_is_checked_not_only_the_date(self):
        now = datetime(2026, 9, 14, 0, 23, tzinfo=KST)
        self.assertTrue(deadline_passed("2026-09-13T23:59:59+09:00", now), "자정이 지났다")
        self.assertFalse(deadline_passed("2026-09-14T23:59:59+09:00", now))
        self.assertFalse(deadline_passed("2026-09-14", now), "날짜만 있으면 그날 끝까지 열림")
        self.assertTrue(deadline_passed("2026-09-13", now))
        self.assertFalse(deadline_passed(None, now))
        self.assertFalse(deadline_passed("상시채용", now), "못 읽으면 빼지 않는다")

    def test_excluded_ids_give_the_next_ones(self):
        """이미 보여 준 공고를 빼고 다음을 준다. 전체 건수는 그대로다."""
        first = self.find(roles=["백엔드"])
        shown = [job.job_id for job in first.jobs]
        again = search(self.path, JobFilters(roles=["백엔드"]), limit=5, as_of=NOW,
                       exclude_ids=shown[:1])
        self.assertNotIn(shown[0], [job.job_id for job in again.jobs])
        self.assertEqual(first.total, again.total)
        self.assertEqual(1, again.skipped)

    def test_tag_match_ranks_between_title_and_body(self):
        jobs = self.find(skills=["Python"]).jobs
        self.assertEqual("A", jobs[0].job_id)
        self.assertEqual(2, jobs[0].relevance, "기술 태그에 있으면 2")

    def test_summary_shows_what_was_used(self):
        filters = JobFilters(roles=["백엔드"], regions=["서울"], career="신입")
        self.assertEqual("백엔드 · 서울 · 신입", filters.summary())
        self.assertEqual("조건 없음", JobFilters().summary())
        self.assertTrue(JobFilters().is_empty)


if __name__ == "__main__":
    unittest.main()


class ListingOnlySearchTest(unittest.TestCase):
    """목록에서만 본 공고도 조건 검색에 잡힌다.

    상세를 받아야 `jobs`에 들어가서 IT 밖 10개 대분류가 영영 0건이었다. "서울 영업직
    있어?"에 없어서가 아니라 안 갖고 있어서 답을 못 했다. 목록에는 회사·제목·직무·
    조건·링크가 다 있고, 조건 검색은 원래 그 값들로만 거른다.

    `jobs` 표는 건드리지 않는다. 추천·하드 필터·시장 통계는 그대로다.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        detailed = replace(
            base, job_id="SARAMIN-1", source_job_id="1", company="상세회사",
            title="백엔드 개발자", region="서울 강남구", career_type="ENTRY",
            employment_type="정규직", status="OPEN", deadline=None,
            description="Python으로 서버를 만듭니다", keywords=["백엔드/서버개발"],
        )
        with SqliteJobStore(self.path) as store:
            store.upsert([detailed], source="SARAMIN_POC", as_of=NOW)
            store.record_list_jobs([
                {"source_job_id": "1", "company": "상세회사", "title": "백엔드 개발자",
                 "job_sectors": ["백엔드/서버개발"], "source_url": "https://x/1",
                 "condition_text": "서울 강남구 신입 · 정규직 대학교(4년)↑"},
                {"source_job_id": "2", "company": "목록회사", "title": "영업관리 신입 채용",
                 "job_sectors": ["영업관리", "영업지원"], "source_url": "https://x/2",
                 "condition_text": "서울 마포구 신입 · 정규직 고졸↑"},
                {"source_job_id": "3", "company": "부산회사", "title": "영업관리",
                 "job_sectors": ["영업관리"], "source_url": "https://x/3",
                 "condition_text": "부산 해운대구 경력 3년↑ · 계약직 학력무관"},
            ], NOW)

    def tearDown(self):
        self.temp.cleanup()

    def find(self, **kwargs):
        return search(self.path, JobFilters(**kwargs), limit=10, as_of=NOW)

    def test_a_job_type_the_store_never_crawled_is_found(self):
        titles = [h.title for h in self.find(roles=["영업"]).jobs]
        self.assertEqual(2, len(titles))
        self.assertIn("영업관리 신입 채용", titles)

    def test_the_conditions_from_the_listing_actually_filter(self):
        seoul = self.find(roles=["영업"], regions=["서울"]).jobs
        self.assertEqual(["영업관리 신입 채용"], [h.title for h in seoul])

    def test_the_career_condition_filters_too(self):
        entry = self.find(roles=["영업"], career="신입").jobs
        self.assertEqual(["영업관리 신입 채용"], [h.title for h in entry])

    def test_a_posting_with_a_detail_is_not_shown_twice(self):
        """같은 공고가 두 표에 다 있다. 상세 쪽만 한 번 나와야 한다."""
        hits = self.find(roles=["백엔드"]).jobs
        self.assertEqual(1, len(hits))
        self.assertTrue(hits[0].has_detail)

    def test_detailed_postings_come_first(self):
        """본문이 있는 쪽이 먼저 보여야 한다."""
        hits = self.find(roles=["백엔드", "영업"]).jobs
        self.assertTrue(hits[0].has_detail)
        self.assertFalse(hits[-1].has_detail)

    def test_title_matches_come_before_body_only_mentions(self):
        """답이 말하는 건수는 제목·태그에 맞은 공고다. 넘겨 보다가 그 건수만큼 본 뒤에
        본문에만 스친 공고가 나와야 말과 목록이 맞는다. 본문이 있다는 이유로 본문에만
        '영업'이 스친 공고가 목록의 '영업관리' 공고보다 앞서면 안 된다."""
        with SqliteJobStore(self.path) as store:
            store.upsert([replace(
                mock_jobs()[0], job_id="SARAMIN-9", source_job_id="9", company="본문회사",
                title="사무 보조", description="영업 부서 지원 업무", keywords=["사무보조"],
                tech_stack=[], region="서울 중구", career_type="ANY", employment_type="정규직",
                status="OPEN", deadline=None,
            )], source="SARAMIN_POC", as_of=NOW)
        hits = self.find(roles=["영업"]).jobs
        self.assertEqual("사무 보조", hits[-1].title, "본문에만 스친 공고는 맨 뒤")
        self.assertEqual(1, hits[-1].relevance)

    def test_a_listing_only_hit_is_marked(self):
        """챗봇이 이걸 보고 '상세 내용이 없어요, 링크를 확인해 주세요'로 답한다."""
        hit = next(h for h in self.find(roles=["영업"]).jobs if h.title == "영업관리")
        self.assertFalse(hit.has_detail)
        self.assertEqual("https://x/3", hit.source_url)
        self.assertEqual("경력 3년 이상", hit.career_label)


class ListingSkipCategoryTest(unittest.TestCase):
    """상세를 받는 대분류는 목록 표에 담지 않는다.

    그쪽 공고는 며칠 안에 상세가 들어와 `jobs`에 자리를 잡는다. 목록에 담아 봐야
    곧 검색에서 제외될 중복이고, 그동안 본문 없는 카드가 섞인다. 목록만으로 남겨야
    하는 것은 **상세를 안 받기로 한 대분류**뿐이다.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "store.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def rec(job_id, cat, title="공고"):
        return {"source_job_id": job_id, "cat_mcls": cat, "company": "회사",
                "title": title, "job_sectors": ["영업관리"], "source_url": f"https://x/{job_id}",
                "condition_text": "서울 마포구 신입 · 정규직 고졸↑", "support_text": "~12.31"}

    def stored(self, records, skip=()):
        with SqliteJobStore(self.path) as store:
            store.record_list_jobs(records, NOW, skip_categories=skip)
            rows = store.conn.execute(
                "SELECT source_job_id FROM list_jobs ORDER BY source_job_id").fetchall()
        return [r["source_job_id"] for r in rows]

    def test_detail_categories_are_left_out(self):
        kept = self.stored([self.rec("1", "2"), self.rec("2", "9"), self.rec("3", "4")],
                           skip=("2", "9"))
        self.assertEqual(["3"], kept)

    def test_a_posting_in_both_is_left_out(self):
        """같은 공고가 여러 대분류에 나온다. 하나라도 상세를 받는 쪽이면 건너뛴다."""
        kept = self.stored([self.rec("7", "4"), self.rec("7", "2")], skip=("2",))
        self.assertEqual([], kept)

    def test_giving_no_skip_list_keeps_everything(self):
        kept = self.stored([self.rec("1", "2"), self.rec("2", "4")])
        self.assertEqual(["1", "2"], kept)


class CareerYearsTest(unittest.TestCase):
    """몇 년차인지 말했으면 모자란 공고를 뺀다.

    "3년차인데 갈 만한 데 있어?"에 경력 5년 이상 공고가 나갔다. 경력이냐 신입이냐만
    보고 숫자를 버렸기 때문이다. 사람이 채점하다 잡았다.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "store.sqlite"
        base = mock_jobs()[0]
        made = [
            ("any", "ANY", None),
            ("y2", "EXPERIENCED", 2),
            ("y5", "EXPERIENCED", 5),
            ("blank", "EXPERIENCED", None),
            ("entry", "ENTRY", None),
        ]
        jobs = [
            replace(base, job_id=name, source_job_id=name, title="백엔드 개발자",
                    description="서버를 만듭니다", tech_stack=[], keywords=["IT개발·데이터"],
                    region="서울 강남구", career_type=kind, min_career_years=years,
                    employment_type="정규직", deadline=None, status="OPEN")
            for name, kind, years in made
        ]
        with SqliteJobStore(self.path) as store:
            store.upsert(jobs, source="MOCK")

    def found(self, **kwargs) -> set[str]:
        result = search(self.path, JobFilters(roles=["백엔드"], **kwargs), limit=20, as_of=NOW)
        return {hit.job_id for hit in result.jobs}

    def test_a_posting_asking_more_years_is_dropped(self):
        self.assertNotIn("y5", self.found(career_years=3))

    def test_a_posting_within_reach_stays(self):
        self.assertIn("y2", self.found(career_years=3))

    def test_an_unstated_minimum_stays(self):
        # 미기재인 것은 연차이지 "안 맞는다"는 사실이 아니다. 검색에서 빠지면
        # 사용자가 아예 못 본다. 판단할 거리를 남긴다.
        self.assertIn("blank", self.found(career_years=3))

    def test_entry_only_postings_drop_for_the_experienced(self):
        self.assertNotIn("entry", self.found(career_years=3))

    def test_entry_only_postings_stay_for_a_first_year(self):
        self.assertIn("entry", self.found(career_years=1))

    def test_saying_nothing_about_years_changes_nothing(self):
        self.assertEqual(self.found(), {"any", "y2", "y5", "blank", "entry"})


class CareerYearsSummaryTest(unittest.TestCase):
    def test_the_summary_says_the_year(self):
        self.assertIn("3년차", JobFilters(career_years=3).summary())

    def test_the_year_replaces_the_coarse_label(self):
        # "경력 · 3년차"는 같은 말을 두 번 하는 것이다.
        self.assertEqual(JobFilters(career="경력", career_years=3).summary(), "3년차")

    def test_a_year_alone_is_not_an_empty_filter(self):
        self.assertFalse(JobFilters(career_years=3).is_empty)
