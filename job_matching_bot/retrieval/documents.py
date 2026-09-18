"""공고 하나를 벡터 인덱스에 넣을 문서로 만든다.

임베딩 대상은 **요건 구간만**이다. 본문 앞에 붙는 분류 경로 줄
(`IT개발·데이터 > 직무·직업 > 백엔드/서버개발`)은 넣지 않는다. 이 줄이 수백 개씩
붙어 모든 공고를 서로 비슷하게 만들고, 실측에서 유사도가 0.37~0.50에 뭉치는 원인이었다.

메타데이터는 검색할 때 조건을 함께 걸기 위한 것이다. Pinecone은 문자열 부분 일치를
못 하므로 지역은 시·도만 뽑아 배열로 넣는다("서울 성동구" → ["서울"]).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from job_matching_bot.ingestion.requirement_sections import split_sections
from job_matching_bot.schemas.job_posting import Job

# 이 길이 미만이면 임베딩해도 의미를 담지 못한다. 인덱스에 넣지 않는다.
MIN_BODY_CHARS = 120

# 사람인 지역 표기에서 뽑아 쓰는 시·도. 앱의 희망 지역 선택지와 같은 값이다.
PROVINCES = (
    "서울", "경기", "인천", "부산", "대구", "대전", "광주", "울산", "세종",
    "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
NATIONWIDE = "전국"

# 메타데이터에 담을 요건 본문 길이. LLM 재정렬이 이 값을 읽어 적합도를 판단하므로,
# 자격요건까지 들어갈 만큼 넉넉해야 한다. 300자로 자르면 주요업무에서 끊겨
# 모델이 "필수 요건에 근거가 있다"고 판단하지 못하고 전부 '보통'으로 나온다.
# 1,200자면 공고의 88%가 온전히 담기고, 메타데이터는 4KB 안이라 40KB 한도에 여유가 있다.
_META_TEXT_LIMIT = 1200


def index_body(job: Job) -> str:
    """임베딩할 텍스트. 요건 구간만 라벨을 붙여 잇는다."""
    sections = split_sections(job.description)
    parts: list[str] = []
    for label, lines in (
        ("주요업무", sections.duties),
        ("자격요건", sections.required),
        ("우대사항", sections.preferred),
    ):
        body = [line.strip() for line in lines if line.strip()]
        if body:
            parts.append(f"[{label}]\n" + "\n".join(body))
    return "\n\n".join(parts).strip()


def is_indexable(job: Job) -> bool:
    return len(index_body(job)) >= MIN_BODY_CHARS


def regions_of(region_text: str) -> list[str]:
    """"서울 영등포구, 경기전체" → ["서울", "경기"]. 못 찾으면 빈 목록."""
    found = [p for p in PROVINCES if p in (region_text or "")]
    return found


def _index_fields(job: Job) -> dict[str, Any]:
    """벡터와 함께 올라가는 검색 필터·근거 값. 이 값이 바뀌면 다시 올린다."""
    return {
        "job_id": job.job_id,
        "company": job.company,
        "title": job.title,
        "source": job.source,
        "source_url": job.source_url,
        # 조건 필터
        "regions": regions_of(job.region),
        "nationwide": NATIONWIDE in (job.region or ""),
        "region_text": job.region,
        "career_type": job.career_type,
        "min_career_years": job.min_career_years if job.min_career_years is not None else -1,
        "education": job.education,
        "employment_type": job.employment_type,
        # 근거 표시
        "required_skills": list(job.required_skills),
        "preferred_skills": list(job.preferred_skills),
        "tech_stack": list(job.tech_stack),
        "body_is_image": job.body_is_image,
    }


def embed_hash(job: Job) -> str:
    """인덱스에 올라가는 내용의 지문. 이 값이 그대로면 다시 올리지 않는다.

    `content_hash`는 크롤 원본 전체의 해시라 수집 시각이나 조회수처럼 매칭과 무관한
    값이 바뀌어도 달라진다. 그걸 기준으로 삼으면 다시 받은 공고를 전부 다시 임베딩한다.
    여기서는 임베딩 텍스트(`index_body`)와 필터·근거 메타데이터만 본다.

    마감일과 상태는 뺀다. 마감은 인덱스에서 지우는 것으로 처리하지, 다시 올리지 않는다.
    """
    payload = {"body": index_body(job), **_index_fields(job)}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def to_metadata(job: Job) -> dict[str, Any]:
    """검색 필터와 카드 표시에 쓰는 값. Pinecone은 중첩 객체를 못 받아 평평하게 둔다."""
    return {
        **_index_fields(job),
        "status": job.status,
        "deadline": job.deadline or "",
        # LLM 재정렬이 읽을 원문 일부. 전체를 넣으면 메타데이터 한도를 넘는다.
        "excerpt": index_body(job)[:_META_TEXT_LIMIT],
        # 증분 적재: 저장소의 indexed_embed_hash와 같은 값. 원본 해시는 대조용으로 남긴다.
        "embed_hash": embed_hash(job),
        "content_hash": job.content_hash,
    }


def clean_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Pinecone이 받는 타입만 남긴다: 문자열, 숫자, 불리언, 문자열 배열."""
    cleaned: dict[str, Any] = {}
    for key, value in meta.items():
        if value is None:
            continue
        if isinstance(value, bool | int | float | str):
            cleaned[key] = value
        elif isinstance(value, list | tuple):
            items = [str(v) for v in value if v is not None and str(v).strip()]
            if items:
                cleaned[key] = items
    return cleaned


_WS = re.compile(r"[ \t]+")


def normalize(text: str) -> str:
    return _WS.sub(" ", text or "").strip()
