"""가상 이력서가 Hard Filter·Ranking의 서로 다른 갈래를 실제로 밟는지 확인한다.

공고는 사람인 정규화기(`normalize_saramin`)에 실제 표기를 넣어 만든다. 그래야
"경력 5~15년" 같은 원문이 파서를 거쳐 어떻게 판정되는지까지 한 번에 본다.
"""

import json
import unittest
from dataclasses import replace

from job_matching_bot.ingestion.record_files import latest_by_id, read_records
from job_matching_bot.config import DEFAULT_SARAMIN_INPUT, REPO_ROOT
from job_matching_bot.exporters.resume_mocks_dart import build_resume_mocks_module
from job_matching_bot.ingestion.saramin import normalize_many, normalize_saramin
from job_matching_bot.matching.hard_filter import EDUCATION_RANK, hard_filter
from job_matching_bot.matching.skill_normalize import canonical_set
from job_matching_bot.schemas.resume import mock_resumes, sample_resume


def _saramin_job(
    job_id: str,
    *,
    career: str = "신입",
    education: str = "학력무관",
    region: str = "서울 마포구",
    employment: str = "정규직",
    title: str = "개발자 채용",
    tech_stack: tuple[str, ...] = (),
):
    """사람인 실제 표기로 공고 하나를 만든다."""
    body = "상세요강\n" + "".join(
        f"선택 : IT개발·데이터 > 기술스택 > {tag}\n" for tag in tech_stack
    )
    return normalize_saramin(
        {
            "source_job_id": job_id,
            "source_url": f"https://www.saramin.co.kr/zf_user/jobs/view?rec_idx={job_id}",
            "conditions": {
                "경력": career,
                "학력": education,
                "근무형태": employment,
                "근무지역": region,
            },
            "company_info": {},
            "description": body,
            "needs_human_review": False,
            "list_item": {"company": "테스트", "title": title, "job_sectors": [], "support_text": "상시채용"},
        }
    )


class FixtureShapeTest(unittest.TestCase):
    def test_ids_are_unique_and_levels_are_known(self):
        resumes = mock_resumes()
        ids = [resume.resume_id for resume in resumes.values()]
        self.assertEqual(len(ids), len(set(ids)))
        for resume in resumes.values():
            self.assertIn(resume.education_level, EDUCATION_RANK)
            self.assertTrue(resume.target_roles)
            self.assertTrue(resume.skills)

    def test_sample_resume_is_the_backend_entry_persona(self):
        self.assertEqual(mock_resumes()["backend_entry"], sample_resume())


class CareerBranchTest(unittest.TestCase):
    def test_three_year_backend_fails_five_year_range_and_passes_three_year_minimum(self):
        resume = mock_resumes()["backend_experienced_3y"]
        senior = _saramin_job("1", career="경력 5~15년")
        mid = _saramin_job("2", career="경력 3년 ↑")
        self.assertIn("최소 경력 5년", hard_filter(senior, resume)["failed"])
        self.assertIn("경력 조건 충족", hard_filter(mid, resume)["passed"])

    def test_entry_persona_fails_experienced_only_posting(self):
        """연차를 안 적었어도 경력자를 뽑는 공고는 신입에게 탈락이다.

        확인 필요로 두었더니 신입 이력서에 경력 공고가 적합도 "높음"으로 나갔다
        (이력서 5종 실측, 25건 중 6건). 미기재인 것은 연차이지 "경력자를 뽑는다"는
        사실이 아니다.
        """
        resume = mock_resumes()["frontend_entry"]
        # "경력무관(신입제외)"는 신입에게 지원 불가다.
        job = _saramin_job("3", career="경력무관(신입제외)")
        result = hard_filter(job, resume)
        self.assertEqual("FAIL", result["status"])
        self.assertIn("경력자 채용 (연차 미기재)", result["failed"])

    def test_experienced_persona_still_passes_that_posting(self):
        """경력자에게는 그대로 통과다. 연차를 모를 뿐 경력은 있다."""
        resume = mock_resumes()["backend_experienced_3y"]
        job = _saramin_job("3", career="경력무관(신입제외)")
        result = hard_filter(job, resume)
        self.assertNotEqual("FAIL", result["status"])
        self.assertIn("경력 조건 충족 (연차 미기재, 경력 보유)", result["passed"])


    def test_an_experienced_resume_fails_an_entry_only_posting(self):
        """방향이 반대인 경우도 봐야 한다.

        연차 조건을 오래 "이 사람이 모자라지 않은가"로만 봤다. 그래서 신입만 뽑는
        공고가 경력자에게 그대로 통과했다. 사람이 매긴 43건에서 경력 3년 이력서에
        "백엔드 개발자 (신입)" 공고가 올라왔고 사람이 걸렀다.
        """
        resume = mock_resumes()["backend_experienced_3y"]
        result = hard_filter(_saramin_job("4", career="신입"), resume)
        self.assertEqual("FAIL", result["status"])
        self.assertIn("신입 채용 (경력자 대상 아님)", result["failed"])

    def test_an_entry_resume_still_passes_an_entry_only_posting(self):
        resume = mock_resumes()["backend_entry"]
        result = hard_filter(_saramin_job("4", career="신입"), resume)
        self.assertNotEqual("FAIL", result["status"])
        self.assertIn("경력 조건 충족", result["passed"])

    def test_an_open_posting_is_not_touched(self):
        """`경력무관`은 신입 전용이 아니다. 경력자도 지원한다."""
        resume = mock_resumes()["backend_experienced_3y"]
        result = hard_filter(_saramin_job("5", career="경력무관"), resume)
        self.assertNotEqual("FAIL", result["status"])


class CertificationGroupBranchTest(unittest.TestCase):
    """`대기환경기사 또는 산업위생관리기사` 는 하나만 있으면 된다.

    묶지 않고 하나씩 따로 검사하면, 대기환경기사를 가진 사람이 나머지를 안 가졌다는
    이유로 "확인 필요"가 붙는다. 이걸 탈락으로 바꾸면 자격 있는 사람이 떨어진다.
    """

    def _job(self, groups, flat=None):
        return replace(
            _saramin_job("9"),
            required_certifications=flat if flat is not None else [c for g in groups for c in g],
            required_certification_groups=groups,
        )

    def test_holding_one_of_the_group_is_enough(self):
        resume = replace(mock_resumes()["backend_entry"], certifications=["대기환경기사"])
        result = hard_filter(self._job([["대기환경기사", "산업위생관리기사"]]), resume)
        self.assertIn("자격증 요건 충족: 대기환경기사, 산업위생관리기사", result["passed"])
        self.assertEqual([], [u for u in result["unknown"] if "자격증" in u])

    def test_holding_none_of_the_group_fails(self):
        """자격요건에 적힌 필수 자격증이다. 하나도 없으면 지원해도 안 된다."""
        resume = replace(mock_resumes()["backend_entry"], certifications=["SQLD"])
        result = hard_filter(self._job([["대기환경기사", "산업위생관리기사"]]), resume)
        self.assertIn("필수 자격증 대기환경기사, 산업위생관리기사", result["failed"])
        self.assertEqual("FAIL", result["status"])

    def test_separate_groups_are_checked_separately(self):
        resume = replace(mock_resumes()["backend_entry"], certifications=["정보처리기사"])
        result = hard_filter(self._job([["정보처리기사"], ["정보보안기사"]]), resume)
        self.assertIn("자격증 요건 충족: 정보처리기사", result["passed"])
        self.assertIn("필수 자격증 정보보안기사", result["failed"])

    def test_an_old_row_without_groups_behaves_as_before(self):
        """묶음 열이 비어 있는 옛 저장소 행. 재파싱 전까지 예전 규칙 그대로다."""
        resume = replace(mock_resumes()["backend_entry"], certifications=["정보처리기사"])
        result = hard_filter(self._job([], flat=["정보처리기사", "정보보안기사"]), resume)
        self.assertIn("자격증 요건 충족: 정보처리기사", result["passed"])
        self.assertIn("필수 자격증 정보보안기사", result["failed"])


class EducationBranchTest(unittest.TestCase):
    def test_junior_college_fails_four_year_requirement_and_passes_two_year(self):
        resume = mock_resumes()["data_entry_junior_college"]
        four_year = _saramin_job("4", education="대졸(4년제) 이상", region="경기 성남시")
        two_year = _saramin_job("5", education="대졸(2,3년제) 이상", region="경기 성남시")
        self.assertIn("필수 학력 대졸", hard_filter(four_year, resume)["failed"])
        self.assertIn("학력 조건 충족", hard_filter(two_year, resume)["passed"])


class RegionBranchTest(unittest.TestCase):
    def test_regional_persona_passes_daejeon_and_fails_seoul(self):
        resume = mock_resumes()["embedded_entry_regional"]
        daejeon = _saramin_job("6", region="대전 유성구")
        seoul = _saramin_job("7", region="서울 강남구")
        self.assertIn("희망 근무지역 일치", hard_filter(daejeon, resume)["passed"])
        self.assertEqual("FAIL", hard_filter(seoul, resume)["status"])


class WebMockParityTest(unittest.TestCase):
    """웹(Firestore)용 목업(scripts/resume_mocks.json)이 매칭 엔진 인물과 어긋나지 않는지.

    두 파일은 언어가 달라 한쪽만 고치기 쉽다. 웹 이력서의 기술스택이 엔진 인물의
    skills 를 전부 담고 있어야, 웹에서 그 이력서로 분석을 돌렸을 때 여기서 검증한
    갈래와 같은 결과가 나온다.
    """

    @classmethod
    def setUpClass(cls):
        path = REPO_ROOT / "scripts" / "resume_mocks.json"
        cls.web = json.loads(path.read_text(encoding="utf-8"))["personas"]

    def test_same_persona_keys(self):
        self.assertEqual(set(mock_resumes()), set(self.web))

    def test_web_tech_stack_covers_engine_skills(self):
        for key, resume in mock_resumes().items():
            with self.subTest(persona=key):
                web_names = [item["name"] for item in self.web[key]["content"]["techStack"]]
                self.assertTrue(
                    canonical_set(resume.skills) <= canonical_set(web_names),
                    f"{key}: 엔진 skills 중 웹 techStack 에 없는 것 "
                    f"{canonical_set(resume.skills) - canonical_set(web_names)}",
                )

    def test_career_years_match_experience_entries(self):
        # 경력 연수가 있는 인물만 경력 항목을 가진다. Functions 는 experience 로 연차를 추정한다.
        for key, resume in mock_resumes().items():
            with self.subTest(persona=key):
                has_experience = any(
                    item["company"].strip() for item in self.web[key]["content"]["experience"]
                )
                self.assertEqual(resume.career_years > 0, has_experience)

    def test_web_mocks_have_matching_evidence(self):
        # ResumeContent.hasMatchingEvidence 와 같은 조건. 이게 거짓이면 앱이 추천을 막는다.
        for key, persona in self.web.items():
            with self.subTest(persona=key):
                content = persona["content"]
                self.assertTrue(
                    content["coreCompetencies"]["text"].strip()
                    or any(i["name"].strip() for i in content["techStack"])
                    or any(i["name"].strip() for i in content["projects"])
                )
                # 시드 스크립트가 계정 값으로 채우므로 비어 있어야 한다.
                self.assertEqual("", content["basicInfo"]["name"])
                self.assertEqual("", content["basicInfo"]["email"])
                self.assertTrue(persona["title"].startswith("[목업]"))


class ResumeMockDartExportTest(unittest.TestCase):
    def test_every_persona_is_emitted(self):
        mocks = json.loads((REPO_ROOT / "scripts" / "resume_mocks.json").read_text(encoding="utf-8"))
        module = build_resume_mocks_module(mocks)
        for key in mocks["personas"]:
            self.assertIn(f'key: "{key}"', module)
        self.assertIn("const resumeMockPersonas = <ResumeMockPersona>[", module)

    def test_dollar_sign_is_escaped_for_dart(self):
        # Dart 문자열에서 `$`는 보간이다. 이스케이프하지 않으면 컴파일이 깨진다.
        module = build_resume_mocks_module(
            {"personas": {"x": {"title": "가격 $100", "content": {"note": "a$b"}}}}
        )
        self.assertIn(r"\$100", module)
        self.assertIn(r"a\$b", module)
        self.assertNotIn(" $1", module)


class RealDataTest(unittest.TestCase):
    """실제 사람인 수집본이 있으면 인물 전원으로 돌려 본다."""

    @classmethod
    def setUpClass(cls):
        cls.jobs = (
            normalize_many(list(latest_by_id(read_records(DEFAULT_SARAMIN_INPUT)).values()))
        )

    def test_every_persona_filters_without_error(self):
        if not self.jobs:
            self.skipTest("수집본 없음")
        for name, resume in mock_resumes().items():
            with self.subTest(persona=name):
                for job in self.jobs:
                    hard_filter(job, resume)

    def test_experienced_only_postings_never_pass_for_entry_personas(self):
        """신입 이력서에 연차를 요구하는 공고가 통과하면 안 된다.

        추천 순위는 서버(벡터 검색 + LLM 재정렬)가 정하지만, 연차 같은 숫자 조건은
        여기 하드 필터가 끝까지 책임진다.
        """
        if not self.jobs:
            self.skipTest("수집본 없음")
        for name, resume in mock_resumes().items():
            if resume.career_years > 0:
                continue
            with self.subTest(persona=name):
                for job in self.jobs:
                    if job.career_type == "EXPERIENCED" and job.min_career_years:
                        result = hard_filter(job, resume)
                        if result["status"] != "FAIL":
                            self.fail(
                                f"{name}에게 경력 {job.min_career_years}년 공고 {job.job_id}가 통과됨"
                            )


if __name__ == "__main__":
    unittest.main()
