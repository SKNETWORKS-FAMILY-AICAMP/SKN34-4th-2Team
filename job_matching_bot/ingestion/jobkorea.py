"""잡코리아 상세 레코드를 공통 `Job` 스키마로 옮긴다.

`ingestion/saramin.py`와 같은 자리다. 크롤러가 저장한 한 건을 받아 저장소에 넣을
모양으로 만든다.

## 사람인 파서와 나눠 쓰는 것

경력·학력·고용형태 표기와 자격요건 구간 해석은 **사이트가 아니라 한국어 채용공고의
관례**라 사람인 쪽 함수를 그대로 부른다(`parse_career` 등). 표본을 보면 잡코리아도
"신입·경력", "초대졸 이상", "정규직 (수습 3개월)" 처럼 같은 말을 쓴다.

## 사람인과 다른 것

1. **마감일을 글에서 읽지 않는다.** 잡코리아 상세에는 schema.org JobPosting이 있고
   `validThrough`가 `2026-10-02T23:59` 형태로 들어 있다. 사람인은 목록의 `~09.30`을
   해석해야 했지만 여기서는 그 값을 그대로 쓴다. 등록일(`datePosted`)도 마찬가지다.

2. **기술 태그의 출처가 다르다.** 사람인은 본문에 숨은 블록
   (`IT개발·데이터 > 기술스택 > Python`)이 있는데 잡코리아에는 없다. 대신
   - 목록 행의 `job_sectors`(`p.dsc`): "솔루션, 소프트웨어개발, WAS"
   - 본문의 `스킬` 구간: "ㆍPython, RAG, LLM, Vector DB, RDB, Elasticsearch"
   둘을 합쳐 `split_tags`에 태워 기술/비기술로 가른다.

3. **헤드헌팅 공고는 JSON-LD가 없다.** 표본 22건 중 1건이 그랬다. 제목·회사가 비어
   버리므로 `is_parsable()`로 먼저 거르고 저장소에 넣지 않는다.

## 마감 판정 (2026-09-19 표본 21건으로 검증)

열린 공고 10건 / 마감일이 지난 공고 11건을 실제로 열어 문구별로 쟀다.

    문구            마감 잡음    열린 공고 오탐
    마감되었습니다      11/11        0/10      ← 쓴다
    마감되           11/11        0/10      (위 문구의 일부라 따로 안 쓴다)
    마감             11/11        9/10      ← 쓰면 안 된다
    공고마감          0/11         0/10
    접수가 마감        0/11         0/10

**"마감"만 보면 안 된다.** 열린 공고에도 "마감일은 기업의 사정으로 인해 조기 마감
또는 변경될 수 있습니다", "마감일 2026.10.24(토)", 근무시간의 "마감 10:30~22:30"이
나온다. 사람인에서 겪은 것과 같은 함정이다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from job_matching_bot.config import now
from job_matching_bot.ingestion.company_name import clean_company_name, clean_listing_text
from job_matching_bot.ingestion.detail_quality import is_image_only_detail
from job_matching_bot.ingestion.saramin import (
    _clean,
    _status,
    parse_career,
    parse_education,
    parse_employment,
)
from job_matching_bot.ingestion.saramin_tech_vocab import split_tags
from job_matching_bot.schemas.job_posting import Job

PARSER_VERSION = "jobkorea-poc-0.1.0"

SOURCE = "JOBKOREA_POC"

# 상세 페이지가 이 문구를 담으면 공고가 내려간 것으로 본다. 위 표본 검증 참고.
CLOSED_MARKER = "마감되었습니다"

# 본문의 `스킬` 구간. "스킬" 다음 줄부터 다음 구간 제목 전까지가 기술 목록이다.
_SKILL_BLOCK = re.compile(r"^\s*스킬\s*$(.*?)(?=^\s*(?:핵심역량|자격요건|우대사항|담당업무|복리후생)\s*$|\Z)",
                          re.MULTILINE | re.DOTALL)
# 본문은 각 항목을 "ㆍ"로 시작한다.
_BULLET = re.compile(r"[ㆍ·•]")


def is_closed_page(text: str) -> bool:
    """상세 페이지 글에서 마감 여부를 본다."""
    return CLOSED_MARKER in text


def is_parsable(record: dict[str, Any]) -> bool:
    """저장소에 넣을 수 있는 레코드인지.

    헤드헌팅 공고는 JSON-LD가 없어 제목·회사가 비어 온다. 빈 행을 넣으면 추천이
    "회사 없음" 공고를 내놓게 되므로 아예 받지 않는다.
    """
    return bool(str(record.get("title") or "").strip())


def parse_skills(description: str) -> list[str]:
    """본문 `스킬` 구간에서 기업이 고른 기술을 뽑는다.

    사람인의 숨은 기술스택 블록에 해당한다. 기업이 직접 고른 값이라 글에서 추정한
    것보다 믿을 만하다.
    """
    match = _SKILL_BLOCK.search(description or "")
    if not match:
        return []
    skills: list[str] = []
    for line in _BULLET.split(match.group(1)):
        for token in line.split(","):
            token = token.strip()
            if token and token not in skills:
                skills.append(token)
    return skills


def normalize_jobkorea(
    record: dict[str, Any],
    as_of: datetime | None = None,
    requirements: dict[str, Any] | None = None,
) -> Job:
    """크롤러가 저장한 상세 한 건을 `Job`으로.

    `requirements`는 `coach.skill_source.extract_requirements`가 본문에서 뽑은
    필수·우대 기술이다. 주지 않으면 기업이 고른 태그만으로 채운다.
    """
    as_of = as_of or now()
    listing = record.get("list_item") or {}
    conditions = record.get("conditions") or {}
    description = record.get("description") or ""

    source_job_id = str(
        record.get("source_job_id") or listing.get("source_job_id") or ""
    )
    career_type, min_years, _ = parse_career(conditions.get("경력", ""))
    education, _ = parse_education(conditions.get("학력", ""))
    employment, _ = parse_employment(conditions.get("근무형태", ""))
    region = _clean(conditions.get("근무지역", "")) or "미기재"

    # 마감일·등록일은 JSON-LD 값을 그대로 쓴다. 글에서 추정하지 않는다.
    deadline = (record.get("deadline_raw") or "").strip() or None
    posted_at = (record.get("posted_at") or "").strip() or None

    # 기업이 고른 분류·기술. 본문 `스킬` 구간과 목록의 job_sectors를 합친다.
    chosen = parse_skills(description) + list(listing.get("job_sectors") or [])
    tech_stack, keywords = split_tags(chosen)

    if requirements:
        required = list(requirements.get("required_skills") or [])
        preferred = list(requirements.get("preferred_skills") or [])
        unknown = list(requirements.get("unknown_skills") or [])
        skill_method = requirements.get("method", "unknown")
    else:
        required, preferred, unknown = [], [], list(keywords)
        skill_method = "chosen_tags_only"

    # 자격요건 구간의 전공·자격증·병역. 사람인과 같은 규칙을 그대로 쓴다.
    from job_matching_bot.ingestion.qualifications import extract_qualifications
    from job_matching_bot.ingestion.requirement_sections import split_sections

    sections = split_sections(description)
    qualifications = extract_qualifications(sections.required)
    preferred_quals = extract_qualifications(sections.preferred, preferred=True)

    # 소스가 마감이라고 말하면 마감일과 무관하게 CLOSED다. 그렇지 않으면 마감일로 본다.
    status = "CLOSED" if record.get("closed") else _status(deadline, as_of)

    raw_for_hash = json.dumps(record, ensure_ascii=False, sort_keys=True)

    return Job(
        job_id=f"JOBKOREA-{source_job_id}",
        source=SOURCE,
        source_job_id=source_job_id,
        source_url=str(record.get("source_url") or listing.get("source_url") or ""),
        company=clean_company_name(record.get("company") or listing.get("company")),
        # 잡코리아 상세에는 기업형태 칸이 없다. 지어내지 않고 모른다고 둔다.
        company_type="미기재",
        title=clean_listing_text(str(record.get("title") or listing.get("title") or "")),
        description=description,
        required_skills=required,
        preferred_skills=preferred,
        tech_stack=tech_stack,
        keywords=keywords,
        body_is_image=is_image_only_detail(description, record.get("image_body")),
        required_majors=qualifications.majors,
        required_major_terms=qualifications.major_terms,
        required_certifications=qualifications.certifications,
        required_certification_groups=qualifications.certification_groups,
        required_language_tests=qualifications.language_tests,
        military_required=qualifications.military_required,
        preferred_majors=preferred_quals.majors,
        preferred_major_terms=preferred_quals.major_terms,
        preferred_certifications=preferred_quals.certifications,
        preferred_language_tests=preferred_quals.language_tests,
        career_type=career_type,
        min_career_years=min_years,
        education=education,
        region=region,
        employment_type=employment,
        posted_at=posted_at,
        deadline=deadline,
        status=status,
        content_hash=f"sha256:{hashlib.sha256(raw_for_hash.encode('utf-8')).hexdigest()}",
        parser_version=PARSER_VERSION,
        field_provenance={
            "career": conditions.get("경력", ""),
            "education": conditions.get("학력", ""),
            "employment": conditions.get("근무형태", ""),
            "region": conditions.get("근무지역", ""),
            "deadline": "json_ld.validThrough",
            "posted_at": "json_ld.datePosted",
            "skills": skill_method,
            "tech_stack": "body_skill_block+list_sectors",
            "unknown_skills": unknown,
        },
    )
