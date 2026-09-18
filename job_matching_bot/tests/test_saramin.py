"""사람인 정규화 검증.

실제 수집본(`artifacts/raw/saramin_detail.jsonl`)이 있으면 그것으로도
확인한다. 없으면 파싱 규칙만 본다.
"""

import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot.ingestion.record_files import latest_by_id, read_records
from job_matching_bot.config import ARTIFACTS_DIR, REPO_ROOT
from job_matching_bot.ingestion.company_name import clean_company_name
from job_matching_bot.tests import AS_OF, SARAMIN_SAMPLE
from job_matching_bot.ingestion.saramin import (
    normalize_many,
    normalize_saramin,
    parse_career,
    parse_deadline,
    parse_education,
    parse_employment,
    parse_tech_stack,
)

SAMPLE = SARAMIN_SAMPLE


class CareerTest(unittest.TestCase):
    def test_entry_only(self):
        self.assertEqual(("ENTRY", 0), parse_career("신입")[:2])

    def test_entry_and_experienced_is_any(self):
        # "신입·경력"은 신입도 지원 가능하다는 뜻이다.
        self.assertEqual(("ANY", None), parse_career("신입·경력")[:2])

    def test_years_become_experienced(self):
        self.assertEqual(("EXPERIENCED", 3), parse_career("경력 3년")[:2])
        self.assertEqual(("EXPERIENCED", 3), parse_career("3~5년")[:2])

    def test_experience_irrelevant_is_any(self):
        self.assertEqual(("ANY", None), parse_career("경력무관")[:2])
        self.assertEqual(("ANY", None), parse_career("경력무관(신입포함)")[:2])

    def test_experience_irrelevant_but_entry_excluded_is_not_any(self):
        # 신입에게 지원 불가 공고를 추천하면 안 된다.
        self.assertEqual(("EXPERIENCED", None), parse_career("경력무관(신입제외)")[:2])

    def test_blank_is_unknown_not_entry(self):
        # 모르는 것을 신입 가능으로 단정하지 않는다.
        self.assertEqual(("UNKNOWN", None), parse_career("")[:2])


class EducationTest(unittest.TestCase):
    def test_variants(self):
        self.assertEqual("학력무관", parse_education("학력무관")[0])
        # 사람인 실제 표기들
        self.assertEqual("고졸", parse_education("고교졸업 이상")[0])
        self.assertEqual("초대졸", parse_education("대졸(2,3년제) 이상 부문별 상이")[0])
        self.assertEqual("대졸", parse_education("대졸(4년제) 이상")[0])
        self.assertEqual("대졸", parse_education("대학교(4년)↑")[0])
        self.assertEqual("고졸", parse_education("고졸 이상")[0])
        self.assertEqual("석사", parse_education("석사 이상")[0])

    def test_blank_is_unrecorded(self):
        self.assertEqual("미기재", parse_education("")[0])


class EmploymentTest(unittest.TestCase):
    def test_strips_trailing_description(self):
        self.assertEqual("정규직", parse_employment("정규직 수습기간 3개월")[0])

    def test_known_types(self):
        self.assertEqual("계약직", parse_employment("계약직")[0])
        self.assertEqual("인턴", parse_employment("인턴")[0])

    def test_blank_is_unrecorded(self):
        self.assertEqual("미기재", parse_employment("")[0])


class DeadlineTest(unittest.TestCase):
    def test_absolute_date(self):
        deadline, _ = parse_deadline("홈페이지 지원 ~09.13(일) 1시간 전 등록")
        self.assertTrue(deadline.startswith("2026-09-13"))

    def test_relative_days(self):
        deadline, _ = parse_deadline("입사지원 D-6 7일 전 등록")
        self.assertEqual((AS_OF + timedelta(days=6)).isoformat(), deadline)

    def test_tomorrow(self):
        deadline, _ = parse_deadline("입사지원 내일마감 29일 전 등록")
        self.assertEqual((AS_OF + timedelta(days=1)).isoformat(), deadline)

    def test_always_open_has_no_deadline(self):
        self.assertIsNone(parse_deadline("상시채용")[0])

    def test_past_month_rolls_to_next_year(self):
        # 12월 공고를 이듬해 1월에 수집하면 지난 연도로 잡히면 안 된다.
        january = datetime.fromisoformat("2027-01-05T12:00:00+09:00")
        deadline, _ = parse_deadline("~12.20(금)", as_of=january)
        self.assertTrue(deadline.startswith("2027-12-20"))


class NormalizeTest(unittest.TestCase):
    def test_removes_company_ui_noise(self):
        record = json.loads(json.dumps(SAMPLE))
        record["list_item"]["company"] = "(주)엣지크로스 관심기업 등록"
        self.assertEqual("(주)엣지크로스", normalize_saramin(record).company)

    def test_only_removes_company_noise_at_the_end(self):
        self.assertEqual(
            "관심기업 등록 연구소",
            clean_company_name("관심기업 등록 연구소"),
        )

    def test_maps_to_common_schema(self):
        job = normalize_saramin(SAMPLE)
        self.assertEqual("SARAMIN-54845055", job.job_id)
        self.assertEqual("주식회사 아이티에스코", job.company)
        self.assertEqual("ANY", job.career_type)
        self.assertEqual("대졸", job.education)
        self.assertEqual("정규직", job.employment_type)
        # "지도보기" 같은 표시용 문구는 걷어낸다.
        self.assertEqual("서울 마포구", job.region)
        self.assertEqual("OPEN", job.status)

    def test_keeps_evidence_for_every_parsed_field(self):
        job = normalize_saramin(SAMPLE)
        self.assertEqual("신입·경력", job.field_provenance["career"]["evidence"])
        self.assertEqual("대졸(4년제) 이상", job.field_provenance["education"]["evidence"])
        self.assertEqual(
            ["백엔드/서버개발", "데이터엔지니어"],
            job.field_provenance["job_sectors"]["evidence"],
        )

    def test_without_llm_only_job_sectors_are_available(self):
        job = normalize_saramin(SAMPLE)
        self.assertEqual([], job.required_skills)
        self.assertEqual("job_sector_only", job.field_provenance["required_skills"]["method"])

    def test_llm_result_fills_required_and_preferred(self):
        requirements = {
            "required_skills": ["Python", "FastAPI"],
            "preferred_skills": ["Docker"],
            "unknown_skills": [],
            "method": "llm_extraction",
        }
        job = normalize_saramin(SAMPLE, requirements=requirements)
        self.assertEqual(["Python", "FastAPI"], job.required_skills)
        self.assertEqual(["Docker"], job.preferred_skills)
        self.assertEqual(1.0, job.field_provenance["required_skills"]["confidence"])

    def test_image_flag_yields_to_requirement_text(self):
        """크롤러의 이미지 표시보다 글이 우선한다.

        저장소는 읽을 때 "글에 요건이 있으면 이미지 아님"으로 뒤집는다. 쓸 때 크롤러
        표시를 그대로 넣으면 쓴 지문과 읽은 지문이 달라져, 바뀐 것이 없는데도 다시
        올릴 대상이 된다. 실제로 4,316건이 그렇게 잡혔다. 쓰는 쪽도 같은 규칙을 쓴다.
        """
        long_text = "자격요건 " + "Python으로 서비스를 만들어 본 분. " * 60
        job = normalize_saramin({**SAMPLE, "needs_human_review": True, "description": long_text})
        self.assertFalse(job.body_is_image, "글이 넉넉하면 이미지 공고가 아니다")
        self.assertTrue(job.field_provenance["needs_human_review"], "크롤러 표시 자체는 기록에 남긴다")

        short = normalize_saramin({**SAMPLE, "needs_human_review": True, "description": "이미지 참고"})
        self.assertTrue(short.body_is_image, "글이 없으면 크롤러 표시대로 이미지 공고다")

    def test_image_only_body_is_flagged_for_review(self):
        record = {**SAMPLE, "needs_human_review": True}
        job = normalize_saramin(record)
        self.assertTrue(job.field_provenance["needs_human_review"])

    def test_recently_passed_deadline_sets_expired(self):
        record = {**SAMPLE, "list_item": {**SAMPLE["list_item"], "support_text": "~08.30(토)"}}
        job = normalize_saramin(record)
        self.assertEqual("EXPIRED", job.status)


class BodyCareerOverrideTest(unittest.TestCase):
    """메타는 경력무관인데 자격요건이 연차를 요구하면 본문이 이긴다. 신입 명시는 뒤집지 않는다."""

    @staticmethod
    def _record(meta: str, required: str, title: str = "백엔드 개발자 채용") -> dict:
        return {
            **SAMPLE,
            "conditions": {**SAMPLE["conditions"], "경력": meta},
            "list_item": {**SAMPLE["list_item"], "title": title},
            "description": "자격요건\n" + required + "\n근무조건\n- 정규직",
        }

    def test_any_meta_with_body_years_becomes_experienced(self):
        job = normalize_saramin(self._record("경력무관", "- Spring Boot 개발 경력 5년 이상"))
        self.assertEqual(("EXPERIENCED", 5), (job.career_type, job.min_career_years))
        self.assertEqual("body_required", job.field_provenance["career"]["method"])
        self.assertEqual("경력무관", job.field_provenance["career"]["evidence"])

    def test_any_meta_with_required_but_no_years(self):
        job = normalize_saramin(self._record("경력무관", "- 백엔드 개발 경력자"))
        self.assertEqual(("EXPERIENCED", None), (job.career_type, job.min_career_years))

    def test_entry_mention_in_body_or_title_keeps_any(self):
        job = normalize_saramin(self._record("경력무관", "- 신입 또는 경력 3년 이상"))
        self.assertEqual("ANY", job.career_type)
        job = normalize_saramin(self._record("경력무관", "- 경력 3년 이상", title="각 부문별 신입/경력 모집"))
        self.assertEqual("ANY", job.career_type)

    def test_explicit_entry_meta_is_not_overridden(self):
        job = normalize_saramin(self._record("신입", "- 경력 5년 이상"))
        self.assertEqual(("ENTRY", 0), (job.career_type, job.min_career_years))

    def test_one_year_is_left_alone(self):
        job = normalize_saramin(self._record("경력무관", "- 경력 1년 이상"))
        self.assertEqual("ANY", job.career_type)


class TechStackTest(unittest.TestCase):
    """기업이 고른 기술 태그는 본문 덤프의 숨김 분류 블록에서 나온다."""

    def test_explicit_selection_lines(self):
        body = (
            "직종\t선택 : IT개발·데이터 > 직무·직업 > 백엔드/서버개발\n"
            "선택 : IT개발·데이터 > 기술스택 > Python\n"
            "선택 : IT개발·데이터 > 기술스택 > Django\r\n"
            "선택 : IT개발·데이터 > 작업Tool > Figma\n"
        )
        stack, provenance = parse_tech_stack(body)
        self.assertEqual(["Python", "Django", "Figma"], stack)
        self.assertTrue(provenance["explicit_selection"])
        self.assertEqual(["기술스택", "작업Tool"], provenance["axes"])

    def test_role_categories_are_not_tech_stack(self):
        # "백엔드/서버개발"은 직무 분류지 기술이 아니다.
        body = "선택 : IT개발·데이터 > 직무·직업 > 백엔드/서버개발\n"
        self.assertEqual([], parse_tech_stack(body)[0])

    def test_lines_without_prefix_are_kept_with_lower_confidence(self):
        # 접두 없는 블록은 대분류 전체가 펼쳐진 목록일 수 있다.
        body = "IT개발·데이터 > 기술스택 > Java\nIT개발·데이터 > 기술스택 > Kotlin\n"
        stack, provenance = parse_tech_stack(body)
        self.assertEqual(["Java", "Kotlin"], stack)
        self.assertFalse(provenance["explicit_selection"])
        self.assertLess(provenance["confidence"], 0.9)

    def test_chip_delete_button_suffix_is_stripped(self):
        body = "IT개발·데이터 > 기술스택 > AWS X\nIT개발·데이터 > 기술스택 > Vue.js X\n"
        self.assertEqual(["AWS", "Vue.js"], parse_tech_stack(body)[0])

    def test_real_name_ending_in_x_is_not_truncated(self):
        # 블록 전체가 칩 형태일 때만 X를 걷어낸다.
        body = "선택 : IT개발·데이터 > 기술스택 > OS X\n선택 : IT개발·데이터 > 기술스택 > Linux\n"
        self.assertEqual(["OS X", "Linux"], parse_tech_stack(body)[0])

    def test_duplicates_collapse_in_order(self):
        body = (
            "선택 : IT개발·데이터 > 기술스택 > Java\n"
            "선택 : IT개발·데이터 > 기술스택 > Python\n"
            "선택 : IT개발·데이터 > 기술스택 > Java\n"
        )
        self.assertEqual(["Java", "Python"], parse_tech_stack(body)[0])

    def test_body_without_category_block_yields_empty(self):
        stack, provenance = parse_tech_stack("Python과 FastAPI로 백엔드 API를 개발합니다.")
        self.assertEqual([], stack)
        self.assertEqual([], provenance["evidence"])

    def test_normalized_job_carries_tech_stack_and_evidence(self):
        record = {
            **SAMPLE,
            "description": SAMPLE["description"]
            + "\n선택 : IT개발·데이터 > 기술스택 > Python\n선택 : IT개발·데이터 > 기술스택 > FastAPI\n",
        }
        job = normalize_saramin(record)
        self.assertEqual(["Python", "FastAPI"], job.tech_stack)
        self.assertEqual(["Python", "FastAPI"], job.field_provenance["tech_stack"]["evidence"])
        # LLM 추출 없이도 매칭 텍스트에 들어간다.
        self.assertIn("fastapi", job.matching_text())

    def test_image_only_body_still_gets_tech_stack(self):
        # 이미지 공고여도 숨김 분류 블록은 텍스트라 기술스택이 채워진다.
        record = {
            **SAMPLE,
            "needs_human_review": True,
            "description": "상세요강\n선택 : IT개발·데이터 > 기술스택 > Docker\n",
        }
        job = normalize_saramin(record)
        self.assertTrue(job.field_provenance["needs_human_review"])
        self.assertEqual(["Docker"], job.tech_stack)


class RealDataTest(unittest.TestCase):
    """실제 수집본이 있으면 그것으로도 확인한다."""

    @classmethod
    def setUpClass(cls):
        path = ARTIFACTS_DIR / "raw" / "saramin_detail.jsonl"
        cls.records = (
            list(latest_by_id(read_records(path)).values())
        )

    def test_all_records_normalize(self):
        if not self.records:
            self.skipTest("수집본 없음")
        jobs = normalize_many(self.records)
        self.assertEqual(len(self.records), len(jobs))
        self.assertTrue(all(job.job_id.startswith("SARAMIN-") for job in jobs))
        self.assertTrue(all(job.content_hash.startswith("sha256:") for job in jobs))

    def test_core_conditions_are_populated(self):
        if not self.records:
            self.skipTest("수집본 없음")
        jobs = normalize_many(self.records)
        # 경력·학력은 상세 dl에 항상 있다(3,100건 실측 100%).
        self.assertTrue(all(job.career_type != "UNKNOWN" for job in jobs))
        self.assertTrue(all(job.education != "미기재" for job in jobs))
        # 근무지역은 아예 안 적는 공고가 드물게 있다(3,100건 중 3건). 그건 "미기재"가
        # 맞는 값이므로 전부를 요구하지 않고, 파서가 무너지면 잡히도록 하한만 둔다.
        with_region = sum(1 for job in jobs if job.region != "미기재")
        self.assertGreaterEqual(with_region / len(jobs), 0.99)

    def test_image_body_records_still_have_tech_stack_when_block_exists(self):
        # 이미지 본문이라 LLM 추출이 안 되는 공고도 기술스택은 별도 경로로 채워진다.
        if not self.records:
            self.skipTest("수집본 없음")
        jobs = normalize_many(self.records)
        image_jobs = [job for job in jobs if job.field_provenance["needs_human_review"]]
        if not image_jobs:
            self.skipTest("이미지 본문 공고 없음")
        with_stack = [job for job in image_jobs if job.tech_stack]
        # 전부는 보장 못 하지만(기업이 태그를 안 고를 수 있다) 하나도 없으면
        # 파서가 블록을 못 찾고 있는 것이다.
        self.assertTrue(with_stack, "이미지 본문 공고에서 기술스택을 하나도 못 찾음")


if __name__ == "__main__":
    unittest.main()
