"""수집원과 무관하게 사용하는 공통 채용공고 스키마."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Job:
    job_id: str
    source: str
    source_job_id: str
    source_url: str
    company: str
    company_type: str
    title: str
    description: str
    required_skills: list[str]
    preferred_skills: list[str]
    career_type: str
    min_career_years: int | None
    education: str
    region: str
    employment_type: str
    posted_at: str | None
    deadline: str | None
    status: str
    content_hash: str
    parser_version: str
    field_provenance: dict[str, Any]
    # 기업이 공고 등록 때 고른 기술 태그. 필수·우대가 구분돼 있지 않아
    # required/preferred와 별도로 둔다. 소스에 그런 태그가 없으면 빈 목록이다.
    tech_stack: list[str] = field(default_factory=list)
    # 기업이 고른 분류 태그 중 기술이 아닌 것(직무·전문분야). 직무 점수의 근거가 된다.
    keywords: list[str] = field(default_factory=list)
    # 본문이 이미지뿐이라 요구역량을 텍스트로 확보하지 못한 공고. 크롤러의
    # needs_human_review에서 온다. 매칭은 기업이 고른 기술 태그로만 한다.
    body_is_image: bool = False
    # 자격요건 구간에서 뽑은 전공·자격증·병역 조건(ingestion/qualifications.py).
    # majors는 표시명, major_terms는 이력서 전공에 부분 일치시킬 정규화 용어.
    required_majors: list[str] = field(default_factory=list)
    required_major_terms: list[str] = field(default_factory=list)
    required_certifications: list[str] = field(default_factory=list)
    # 자격증 묶음. 각 묶음에서 **하나만** 맞으면 충족이다. 공고 대부분이
    # "A 또는 B", "A, B 등"처럼 대안을 나열하기 때문이다.
    required_certification_groups: list[list[str]] = field(default_factory=list)
    # 어학 성적. 이력서에 대응하는 칸이 없고 점수 문턱도 비교할 수 없어 조건으로
    # 걸지 않는다. 보여 주기만 한다.
    required_language_tests: list[str] = field(default_factory=list)
    military_required: bool = False
    # 우대사항 구간에서 뽑은 전공·자격증. 없어도 지원에 지장이 없으므로 조건으로 걸지
    # 않는다. 지금은 화면과 채점에 보여 쓸모가 있는지 재는 용도다.
    preferred_majors: list[str] = field(default_factory=list)
    preferred_major_terms: list[str] = field(default_factory=list)
    preferred_certifications: list[str] = field(default_factory=list)
    preferred_language_tests: list[str] = field(default_factory=list)

    def matching_text(self) -> str:
        return " ".join(
            [
                self.title,
                self.description,
                " ".join(self.required_skills),
                " ".join(self.preferred_skills),
                " ".join(self.tech_stack),
                " ".join(self.keywords),
            ]
        ).lower()
