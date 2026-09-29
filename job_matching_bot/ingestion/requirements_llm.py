"""공고 본문에서 필수 자격요건(최소 연차 · 전공 · 자격증)을 LLM 으로 뽑아 **빈 칸만** 채운다.

## 왜 필요한가

규칙 파서가 요건 칸을 채우지만 본문에만 적힌 요건을 자주 놓친다. 2026-09-28 열린 공고(본문 있는 42,843건)에서
경력 공고 26,237건 중 **11,049건(42%)이 최소 연차가 비어** 있었다. 본문에 "경력 N년 이상"이 적힌 공고는 15,298건이다.
칸이 비면 하드 필터가 연차를 못 따져, 경력 3년 이력서에 "관련 경력 4년 이상" 공고(링크투어스)가 추천됐다.

## 규칙

- **빈 칸만 채운다.** 파서나 사이트 칸에 값이 있으면 건드리지 않는다.
- 최소 연차는 **경력 공고(career_type=EXPERIENCED)에만**. 신입 · 경력무관 공고에 연차를 적으면 신입 검색(연차 ≤ 1)에서 빠진다.
- 여러 부문을 한 공고에서 뽑으면 연차는 **가장 낮은 것**을 적는다(파서 qualifications 와 같은 규칙 — 문턱이 낮은
  자리 기준이어야 억울한 탈락이 없다). 전공 · 자격증은 부문마다 달라 채우지 않는다(회계 부문 자격증이 개발 부문에 붙는다).
- 전공 · 자격증은 LLM 이 뽑은 말을 **기존 파서(qualifications)에 한 번 더 통과**시켜, 파서가 아는 전공 분류 · 자격증
  이름만 적는다. 모양이 파서 값과 같아 하드 필터가 그대로 읽고, "교육과정 수료" 같은 것은 걸러진다.
- 한 번 본 공고는 `field_provenance.requirements_llm.hash`(본문 지문)가 같으면 다시 보지 않는다.

2026-09-28 공고 50건 시험(gpt-6-luna low): 연차가 빈 20건 중 18건을 본문 숫자대로 채웠다. 틀린 1건은 여러 부문
공고였다(그래서 여러 부문은 채우지 않는다). 한 건 약 0.4원(입력 1,500 · 출력 250 토큰).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from job_matching_bot.ingestion.qualifications import extract_qualifications
from job_matching_bot.schemas.job_posting import Job

MODEL = os.environ.get("REQUIREMENTS_MODEL", "gpt-6-luna")
EFFORT = "low"
PROVENANCE_KEY = "requirements_llm"
# 이보다 크면 숫자를 잘못 읽은 것이다(전화번호 · 설립 연도 등)
MAX_YEARS = 30


class Extracted(BaseModel):
    multi_role: bool = Field(description="여러 부문 · 직무를 한 공고에서 따로 뽑고 부문마다 요건이 다르면 true")
    min_career_years: int | None = Field(
        description="필수 자격요건에 숫자로 적힌 최소 경력 연수. '경력 N년 이상'처럼 적힌 것만. 여러 부문이면 그중 가장 낮은 연수. "
                    "신입 가능 · 경력무관 · 숫자 없음이면 null")
    required_majors: list[str] = Field(description="필수 전공 · 학과. 우대 전공은 넣지 않는다. 없으면 빈 목록")
    required_certifications: list[str] = Field(
        description="필수 국가 · 민간 자격증 이름만. 교육과정 수료 · 어학 점수 · 우대 자격증은 넣지 않는다. 없으면 빈 목록")


SYSTEM = (
    "채용공고 본문에서 **필수 자격요건**만 뽑는다. 우대사항('우대', '있으면 좋음', '가산점', '~하신 분 환영')은 넣지 않는다. "
    "본문에 없는 것은 지어내지 않는다. 경력 연수는 '경력 N년 이상', 'N년 이상 경력'처럼 숫자로 적힌 것만 쓴다. "
    "'N~M년'이면 N 을 쓴다. 신입도 받는다고 적혀 있으면 null 이다. 여러 부문을 따로 뽑으면 연차는 가장 낮은 것을 쓴다."
)


def _chain():
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    prompt = ChatPromptTemplate.from_messages([("system", SYSTEM), ("human", "[공고 제목]\n{title}\n\n[공고 본문]\n{body}")])
    model = ChatOpenAI(model=MODEL, reasoning_effort=EFFORT, max_retries=2)
    return prompt | model.with_structured_output(Extracted, method="json_schema")


@dataclass
class Fill:
    """한 공고에 적을 값. 빈 dict 면 적을 것이 없다(표시만 남긴다)."""

    job_id: str
    content_hash: str
    values: dict[str, Any] = field(default_factory=dict)
    note: str = ""


def plan_fill(job: Job, extracted: Extracted) -> Fill:
    """뽑은 값 중 **빈 칸에 들어갈 것만** 고른다. LLM 을 부르지 않는다(테스트할 수 있게)."""
    fill = Fill(job.job_id, job.content_hash)
    years = extracted.min_career_years
    if job.career_type == "EXPERIENCED" and job.min_career_years is None and years and 1 <= years <= MAX_YEARS:
        fill.values["min_career_years"] = years
    if extracted.multi_role:
        fill.note = "여러 부문 공고라 연차(가장 낮은 것)만 채움"
        return fill
    if not job.required_majors and extracted.required_majors:
        parsed = extract_qualifications([f"전공: {', '.join(extracted.required_majors)}"])
        if parsed.majors:
            fill.values["required_majors"] = parsed.majors
            fill.values["required_major_terms"] = parsed.major_terms
    if not job.required_certifications and extracted.required_certifications:
        parsed = extract_qualifications([f"필수 자격증: {', '.join(extracted.required_certifications)}"])
        if parsed.certifications:
            fill.values["required_certifications"] = parsed.certifications
            fill.values["required_certification_groups"] = parsed.certification_groups
    return fill


def marker(fill: Fill) -> dict[str, Any]:
    """`field_provenance.requirements_llm` — 본 공고 지문 · 모델 · 채운 칸. 지문이 같으면 다시 보지 않는다."""
    return {
        "hash": fill.content_hash,
        "model": f"{MODEL}/{EFFORT}",
        "filled": sorted(fill.values),
        "note": fill.note,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def analyze(jobs: list[Job], *, workers: int = 8, extractor=None) -> list[tuple[Job, Fill | None, str]]:
    """공고마다 (공고, 채울 값, 실패 이유). 여러 건을 동시에 부른다. 실패한 공고는 표시하지 않아 다음에 다시 본다."""
    invoke = extractor or _chain().invoke

    def one(job: Job) -> tuple[Job, Fill | None, str]:
        try:
            extracted = invoke({"title": job.title, "body": job.description[:6000]})
            return job, plan_fill(job, extracted), ""
        except Exception as error:  # noqa: BLE001 — 한 건 실패가 나머지를 막지 않게
            return job, None, f"{type(error).__name__}: {error}"[:200]

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(one, jobs))
