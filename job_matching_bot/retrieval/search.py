"""Pinecone 벡터 검색.

메타데이터 필터를 벡터 검색과 같이 걸어 후보를 한 번에 좁힌다. Pinecone은
문자열 부분 일치를 못 하므로, 지역은 적재할 때 시·도 배열(`regions`)로 넣어 두었다.

희망 지역이 있어도 `nationwide`(전국 근무) 공고는 함께 잡아야 한다. `$or`로 묶는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from job_matching_bot.retrieval.pinecone_index import (
    EMBEDDING_MODEL,
    client,
    index_name,
    index as get_index,
    namespace,
)


@dataclass(frozen=True)
class Hit:
    job_id: str
    score: float
    rank: int
    metadata: dict[str, Any]


def build_filter(
    regions: list[str],
    employment_types: list[str],
    career_years: float,
) -> dict[str, Any]:
    """벡터 검색과 함께 걸 조건. 값이 없으면 그 조건은 걸지 않는다."""
    clauses: list[dict[str, Any]] = [{"status": {"$eq": "OPEN"}}]

    if regions:
        # 희망 지역과 겹치거나, 전국 근무인 공고
        clauses.append(
            {"$or": [{"regions": {"$in": regions}}, {"nationwide": {"$eq": True}}]}
        )
    if employment_types:
        clauses.append({"employment_type": {"$in": employment_types}})

    # 신입(경력 근거 없음)에게 최소 경력이 명시된 공고를 보내지 않는다.
    # -1은 적재할 때 "미기재"를 담은 값이다.
    if career_years < 1:
        clauses.append({"min_career_years": {"$lte": 1}})

    return {"$and": clauses} if len(clauses) > 1 else clauses[0]


# 마감·삭제된 공고를 걸러 낼 때 쓰는 값. 인덱스에는 이것만 올라간다.
OPEN_ONLY: dict[str, Any] = {"status": {"$eq": "OPEN"}}


def _today() -> str:
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


def drop_closed(matches: list[dict], today: str | None = None) -> list[dict]:
    """마감일이 지난 것을 뺀다.

    인덱스에서 빼는 일은 야간 배치가 한다. 그런데 그건 하루에 한 번이라, 오늘 마감인
    공고가 내일 낮까지 남는다. 챗봇 조건 검색은 SQL 에서 매번 거르는데 추천만 그러지
    못했다. 여기서 한 번 더 본다.

    Pinecone 필터로는 못 한다. 문자열 대소 비교를 지원하지 않는다. 25건 중 몇 건을
    빼는 일이라 가져온 뒤 거르는 편이 확실하고 비용도 없다.
    """
    today = today or _today()
    kept = []
    for match in matches:
        meta = match.get("metadata") or {}
        if (meta.get("status") or "OPEN") != "OPEN":
            continue
        deadline = str(meta.get("deadline") or "")[:10]
        if deadline and deadline < today:
            continue
        kept.append(match)
    return kept


def search(query: str, top_k: int, filter: dict[str, Any] | None = None) -> list[Hit]:
    """질의문을 임베딩해 Top-k를 가져온다.

    조건이 좁아 결과가 비면 **좁히는 조건만** 풀고 다시 찾는다. 예전에는 필터를 통째로
    버렸는데, 그러면 `status: OPEN` 까지 같이 풀려 마감·삭제된 공고가 섞일 수 있었다.
    넓히려는 것은 지역·고용형태·경력이지 "열려 있는 공고"가 아니다.
    """
    from langchain_openai import OpenAIEmbeddings

    vector = OpenAIEmbeddings(model=EMBEDDING_MODEL).embed_query(query)
    # 클라이언트와 인덱스 손잡이는 재사용한다. 매번 새로 만들면 인덱스 해석 1.2초와
    # 연결 수립이 되풀이되어 검색 한 번이 2.9초가 된다(재사용 시 0.25초).
    index = get_index()
    kwargs: dict[str, Any] = {
        "vector": vector,
        "top_k": top_k,
        "include_metadata": True,
    }
    ns = namespace()
    if ns:
        kwargs["namespace"] = ns

    result = index.query(**kwargs, filter=filter or OPEN_ONLY)
    matches = drop_closed(result.get("matches") or [])
    if not matches and filter:
        # 지역·경력이 너무 좁아 아무것도 안 걸린 경우. 그것만 풀고 하드 필터에 맡긴다.
        # OPEN 조건은 남긴다 — 넓히려는 것이 "마감된 공고까지"는 아니다.
        result = index.query(**kwargs, filter=OPEN_ONLY)
        matches = drop_closed(result.get("matches") or [])

    return [
        Hit(
            job_id=m["id"],
            score=float(m.get("score", 0)),
            rank=i,
            metadata=dict(m.get("metadata") or {}),
        )
        for i, m in enumerate(matches, start=1)
    ]
