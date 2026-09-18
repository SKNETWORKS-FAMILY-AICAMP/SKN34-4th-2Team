"""사람인 수집본을 공통 `Job` 스키마로 정규화한다.

입력은 `job_matching_bot/crawling/crawl_detail.py`가 만든 레코드다. 상세 페이지의
`핵심 정보` dl에서 경력·학력·근무형태·지역을 가져오는데, 이 값들은 표본
15건에서 100% 채워져 있어 목록의 `condition_text`를 문자열로 쪼개는 것보다
훨씬 안정적이다.

요구역량은 세 곳에서 채운다.

1. 해시태그 블록(`tags`) — 기업이 공고 등록 때 고른 분류가 전부 들어 있다.
   그중 기술 어휘(`saramin_tech_vocab`)에 있는 것이 기술스택이고, 나머지(직무·
   전문분야)는 `keywords`로 둔다. 표준 UI라 모든 공고에 있다. 필수·우대 구분은 없다.
   (초기 표본 15건에선 숨김 텍스트 블록의 `> 기술스택 >` 줄로 87%가 잡혔지만, 3,100건
   실측에선 그 블록이 2%에만 있었다. 프리미엄 공고 전용이었다. 그 파서도 남겨 두고
   두 출처를 합친다.)
2. `job_sectors` — 목록 페이지의 직무 분류. "백엔드/서버개발" 같은 **직무 분류**이지
   기술명이 아니라 근거로만 남긴다.
3. 상세 본문 → LLM 추출(`coach.skill_source`). 필수/우대를 구분하고 근거를 남긴다.
   키가 없으면 규칙 기반으로 내려간다.

본문이 이미지에만 있는 공고(표본의 약 42%)는 3번을 못 하므로
`field_provenance`에 `needs_human_review`로 남긴다. 1번은 그래도 채워진다.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Any

from job_matching_bot.config import now
from job_matching_bot.ingestion.company_name import clean_company_name, clean_listing_text
from job_matching_bot.ingestion.detail_quality import is_image_only_detail
from job_matching_bot.ingestion.saramin_tech_vocab import split_tags
from job_matching_bot.schemas.job_posting import Job

PARSER_VERSION = "saramin-poc-0.2.0"

# 제목에 이 말이 있으면 신입도 뽑는 공고다. 본문 연차로 경력직으로 바꾸지 않는다.
_ENTRY_IN_TITLE = re.compile(r"신입|인턴|경력\s*무관")
SOURCE = "SARAMIN_POC"

def _clean(value: str) -> str:
    """표시용 군더더기를 걷어낸다."""
    return re.sub(r"\s+", " ", value.replace("지도보기", "")).strip()


def parse_career(text: str) -> tuple[str, int | None, str]:
    """경력 조건을 `career_type`과 최소 연수로 나눈다.

    사람인 표기: "신입", "경력", "신입·경력", "경력무관(신입포함)",
    "경력무관(신입제외)", "경력 3년 ↑", "경력 5~15년"
    """
    evidence = _clean(text) or "미기재"
    if not evidence or evidence == "미기재":
        return "UNKNOWN", None, "미기재"
    if "경력무관" in evidence:
        # "경력무관(신입제외)"는 연차를 안 보겠다는 뜻이지 신입을 받는다는 뜻이
        # 아니다. 이걸 ANY로 두면 신입 사용자에게 지원 불가 공고를 추천한다.
        if "신입제외" in evidence or "신입 제외" in evidence:
            return "EXPERIENCED", None, evidence
        return "ANY", None, evidence
    has_entry = "신입" in evidence
    # "5~15년"은 최소 5년이라는 뜻이다. 뒤 숫자를 잡으면 8년 경력자가
    # 부당하게 탈락하므로 구간의 앞 숫자를 먼저 찾는다.
    span = re.search(r"(\d+)\s*~\s*\d+\s*년", evidence)
    years = span or re.search(r"(\d+)\s*년", evidence)
    # "신입·경력"은 둘 다 받는다는 뜻이므로 신입도 지원 가능하다.
    if has_entry and ("경력" in evidence or years):
        return "ANY", None, evidence
    if has_entry:
        return "ENTRY", 0, evidence
    if years:
        return "EXPERIENCED", int(years.group(1)), evidence
    if "경력" in evidence:
        return "EXPERIENCED", None, evidence
    return "UNKNOWN", None, evidence


def parse_education(text: str) -> tuple[str, str]:
    """학력 조건. 사람인 표기: "학력무관", "대졸(4년제) 이상", "고졸 이상"."""
    evidence = _clean(text) or "미기재"
    if "무관" in evidence:
        return "학력무관", evidence
    # 초대졸(2,3년제)은 학력 랭크에 별도 값이 없어 고졸 위로만 본다.
    for level in ("박사", "석사"):
        if level in evidence:
            return level, evidence
    # "대졸(2,3년제)"는 초대졸이다. 4년제와 같이 두면 조건을 과하게 잡는다.
    if "2,3년" in evidence or "2, 3년" in evidence or "초대졸" in evidence:
        return "초대졸", evidence
    if "대학교" in evidence or "4년" in evidence or "대졸" in evidence:
        return "대졸", evidence
    # 사람인은 "고교졸업 이상"으로도 표기한다.
    if "고졸" in evidence or "고교졸업" in evidence:
        return "고졸", evidence
    return "미기재", evidence


def parse_employment(text: str) -> tuple[str, str]:
    """고용형태. "정규직 수습기간 3개월"처럼 뒤에 설명이 붙는다."""
    evidence = _clean(text) or "미기재"
    for known in ("정규직", "계약직", "인턴", "파트타임", "프리랜서", "비정규직"):
        if known in evidence:
            return known, evidence
    return "미기재", evidence


# 기업이 고른 분류 줄. 세 가지 표기가 섞여 나온다.
#   선택 : IT개발·데이터 > 기술스택 > Python    ← 기업이 명시적으로 고른 항목
#   IT개발·데이터 > 기술스택 > Python           ← 접두 없는 변형(양식 차이로 추정)
#   IT개발·데이터 > 기술스택 > Python X         ← 삭제 버튼(X)이 붙은 칩 형태
# `작업Tool`(Figma, PhotoShop 등)도 기술 태그이므로 같이 본다.
_TECH_STACK_LINE = re.compile(
    r"^\s*(?:선택\s*:\s*)?[^>\n]+?>\s*(기술스택|작업Tool)\s*>\s*(.+?)\s*$"
)


def parse_tech_stack(description: str) -> tuple[list[str], dict[str, Any]]:
    """본문에 섞여 있는 기술 태그를 뽑는다. (태그 목록, 근거)를 돌려준다."""
    entries: list[tuple[str, str, bool]] = []
    for raw in description.splitlines():
        match = _TECH_STACK_LINE.match(raw)
        if match:
            entries.append((match.group(1), match.group(2), raw.lstrip().startswith("선택")))

    if not entries:
        return [], {"method": "category_block", "evidence": [], "explicit_selection": False}

    values = [value for _, value, _ in entries]
    # 칩 UI의 삭제 버튼 "X"가 값 뒤에 붙어 나오는 공고가 있다. 블록 전체가 그
    # 형태일 때만 걷어낸다. "OS X"처럼 X로 끝나는 진짜 이름을 자르지 않기 위해서다.
    if all(value.endswith(" X") for value in values):
        values = [value[:-2].rstrip() for value in values]
    ordered = list(dict.fromkeys(values))
    # "선택 :" 접두는 기업이 직접 고른 항목이라는 표시다. 접두 없는 블록은
    # 대분류 전체가 펼쳐진 목록일 수 있어(한 공고에 54개) 신뢰도를 낮춰 둔다.
    explicit = all(is_explicit for _, _, is_explicit in entries)
    return ordered, {
        "method": "category_block",
        "evidence": ordered,
        "explicit_selection": explicit,
        "confidence": 0.9 if explicit else 0.6,
        "axes": sorted({axis for axis, _, _ in entries}),
    }


def parse_deadline(support_text: str, as_of: datetime | None = None) -> tuple[str | None, str]:
    """지원 마감일. 사람인은 상대 표기를 섞어 쓴다.

    "~09.13(일)" / "D-6" / "내일마감" / "오늘마감" / "상시채용"
    """
    as_of = as_of or now()
    text = _clean(support_text)
    if not text:
        return None, "미기재"
    if "상시" in text or "채용시" in text:
        return None, text

    absolute = re.search(r"~\s*(\d{1,2})\.(\d{1,2})", text)
    if absolute:
        month, day = int(absolute.group(1)), int(absolute.group(2))
        year = as_of.year
        try:
            deadline = datetime(year, month, day, 23, 59, 59, tzinfo=as_of.tzinfo)
        except ValueError:
            return None, text
        # 마감일이 기준일보다 많이 지났으면 내년 공고로 본다.
        if (as_of - deadline).days > 180:
            deadline = deadline.replace(year=year + 1)
        return deadline.isoformat(), text

    relative = re.search(r"D-\s*(\d+)", text)
    if relative:
        return (as_of + timedelta(days=int(relative.group(1)))).isoformat(), text
    if "내일마감" in text:
        return (as_of + timedelta(days=1)).isoformat(), text
    if "오늘마감" in text:
        return as_of.isoformat(), text
    return None, text


def _status(deadline: str | None, as_of: datetime) -> str:
    if not deadline:
        return "OPEN"
    try:
        parsed = datetime.fromisoformat(deadline)
    except ValueError:
        return "OPEN"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=as_of.tzinfo)
    return "OPEN" if parsed >= as_of else "EXPIRED"


def normalize_saramin(
    record: dict[str, Any],
    as_of: datetime | None = None,
    requirements: dict[str, Any] | None = None,
) -> Job:
    """상세 수집 레코드 하나를 공통 스키마로 만든다.

    `requirements`는 `coach.skill_source.extract_requirements()` 결과다.
    주지 않으면 `job_sectors`만으로 채운다.
    """
    as_of = as_of or now()
    listing = record.get("list_item") or {}
    conditions = record.get("conditions") or {}
    company_info = record.get("company_info") or {}
    description = record.get("description") or ""

    source_job_id = str(record.get("source_job_id") or listing.get("source_job_id") or "")
    career_type, min_years, career_evidence = parse_career(conditions.get("경력", ""))
    education, education_evidence = parse_education(conditions.get("학력", ""))
    employment, employment_evidence = parse_employment(conditions.get("근무형태", ""))
    region = _clean(conditions.get("근무지역", "")) or "미기재"
    deadline, deadline_evidence = parse_deadline(listing.get("support_text", ""), as_of)

    sectors = [s for s in (listing.get("job_sectors") or []) if s]
    block_stack, tech_stack_provenance = parse_tech_stack(description)
    tag_stack, keywords = split_tags(list(record.get("tags") or []))
    # 두 출처를 합친다. 표기 변형은 split_tags 쪽에서 이미 접었고, 여기서는 순서만 유지한다.
    tech_stack = list(dict.fromkeys(block_stack + tag_stack))
    tech_stack_provenance = {
        **tech_stack_provenance,
        "from_hidden_block": block_stack,
        "from_tags": tag_stack,
        "method": "hidden_block+tags" if block_stack and tag_stack else ("tags" if tag_stack else tech_stack_provenance["method"]),
    }
    if requirements:
        required = list(requirements.get("required_skills") or [])
        preferred = list(requirements.get("preferred_skills") or [])
        # LLM이 필수/우대를 못 가른 항목과 직무 분류를 합쳐 근거 목록으로 둔다.
        unknown = list(requirements.get("unknown_skills") or [])
        skill_method = requirements.get("method", "unknown")
    else:
        required, preferred, unknown = [], [], sectors
        skill_method = "job_sector_only"

    # 자격요건 구간의 전공·자격증·병역. LLM 유무와 무관하게 규칙으로 뽑는다.
    from job_matching_bot.ingestion.qualifications import extract_qualifications
    from job_matching_bot.ingestion.requirement_sections import split_sections

    sections = split_sections(description)
    qualifications = extract_qualifications(sections.required)
    # 우대사항 구간의 전공·자격증. 조건으로 걸지 않고 보여 주기만 한다.
    preferred_quals = extract_qualifications(sections.preferred, preferred=True)

    # 메타는 "경력무관"인데 자격요건이 연차를 요구하는 공고가 60건쯤 있다. 이대로 두면
    # 신입 이력서에 경력 5년 공고가 1위로 올라온다. 메타가 경력무관일 때만 본문으로
    # 바로잡는다. 기업이 "신입"이라고 명시한 것은 본문 추정으로 뒤집지 않고, 제목이나
    # 요건 어디든 신입을 언급하면 다직무 공고라 그대로 둔다. 1년 이상은 검색 필터가
    # 이미 신입 가능으로 보고 있어 여기서만 엄격하게 하지 않는다.
    career_method = "detail_dl"
    entry_in_title = bool(_ENTRY_IN_TITLE.search(str(listing.get("title") or "")))
    if career_type == "ANY" and not qualifications.mentions_entry and not entry_in_title:
        if qualifications.min_career_years is not None and qualifications.min_career_years >= 2:
            career_type, min_years, career_method = "EXPERIENCED", qualifications.min_career_years, "body_required"
        elif qualifications.career_required:
            # 연차를 지어내지 않는다. 하드 필터가 "연수 미기재"로 다룬다.
            career_type, min_years, career_method = "EXPERIENCED", None, "body_required"

    raw_for_hash = json.dumps(record, ensure_ascii=False, sort_keys=True)

    return Job(
        job_id=f"SARAMIN-{source_job_id}",
        source=SOURCE,
        source_job_id=source_job_id,
        source_url=str(record.get("source_url") or listing.get("source_url") or ""),
        # 옛 수집본의 회사명에는 뱃지가 붙어 있다. 수집기를 고친 뒤에도 원본은 그대로라 여기서도 뗀다.
        company=clean_company_name(listing.get("company")),
        company_type=_clean(company_info.get("기업형태", "")) or "미기재",
        title=clean_listing_text(str(listing.get("title") or "")),
        description=description,
        required_skills=required,
        preferred_skills=preferred,
        tech_stack=tech_stack,
        keywords=keywords,
        # 크롤러가 이미지라고 표시했어도 글에 요건이 있으면 이미지 공고가 아니다.
        # 저장소가 읽을 때 같은 규칙으로 뒤집는데, 쓸 때 다른 값을 넣으면 쓴 지문과
        # 읽은 지문이 어긋난다. 실제로 4,316건이 그렇게 어긋나 다시 올려야 했다.
        body_is_image=is_image_only_detail(description, record.get("needs_human_review")),
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
        posted_at=None,
        deadline=deadline,
        status=_status(deadline, as_of),
        content_hash=f"sha256:{hashlib.sha256(raw_for_hash.encode('utf-8')).hexdigest()}",
        parser_version=PARSER_VERSION,
        field_provenance={
            "career": {"method": career_method, "evidence": career_evidence, "body": qualifications.evidence["career"]},
            "education": {"method": "detail_dl", "evidence": education_evidence},
            "employment_type": {"method": "detail_dl", "evidence": employment_evidence},
            "region": {"method": "detail_dl", "evidence": region},
            "deadline": {"method": "support_text", "evidence": deadline_evidence},
            "required_skills": {
                "method": skill_method,
                "evidence": required or unknown,
                "confidence": 1.0 if required else (0.5 if unknown else 0.0),
            },
            "job_sectors": {"method": "list_page", "evidence": sectors},
            "tech_stack": tech_stack_provenance,
            "tags": {"method": "detail_tags_block", "evidence": list(record.get("tags") or [])},
            # 본문이 이미지에만 있으면 요구역량을 텍스트로 확보하지 못한 상태다.
            "needs_human_review": bool(record.get("needs_human_review")),
            "qualifications": {"method": "section_rules", "evidence": qualifications.evidence},
        },
    )


def normalize_many(
    records: list[dict[str, Any]],
    as_of: datetime | None = None,
    extract: bool = False,
    cache_path: Any = None,
) -> list[Job]:
    """여러 건을 정규화한다. `extract=True`면 본문에 LLM 추출을 돌린다."""
    as_of = as_of or now()
    jobs = []
    for record in records:
        requirements = None
        if extract:
            from job_matching_bot.coach.skill_source import extract_requirements

            listing = record.get("list_item") or {}
            requirements = extract_requirements(
                str(listing.get("title") or ""),
                record.get("description") or "",
                cache_path=cache_path,
            )
        jobs.append(normalize_saramin(record, as_of=as_of, requirements=requirements))
    return jobs
