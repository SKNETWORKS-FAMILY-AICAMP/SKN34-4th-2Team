"""저장소의 공고를 Pinecone 인덱스에 올린다.

    python -m job_matching_bot.retrieval.upsert            # 바뀐 것만 (증분)
    python -m job_matching_bot.retrieval.upsert --limit 100  # 앞에서 N건만
    python -m job_matching_bot.retrieval.upsert --force     # 전량 다시 임베딩
    python -m job_matching_bot.retrieval.upsert --dry-run   # 올리지 않고 계획만

증분이 기본이다. 문서 ID를 공고 ID로 고정하고, 저장소가 기억하는 두 지문을 대조한다.
`embed_hash`(지금 내용)와 `indexed_embed_hash`(마지막으로 올린 내용)가 다른 것만
임베딩한다. 지문은 요건 구간과 필터 값으로만 만들어서, 마감일이나 수집 시각만 바뀐
공고는 다시 올리지 않는다(`documents.embed_hash`). 판정에 Pinecone 조회가 없다.
JSON 저장소(테스트용)는 추적 컬럼이 없어 인덱스 메타데이터를 받아 대조한다.

임베딩은 OpenAI 호출이라 비용이 나가고(1M 토큰당 약 $0.02), 저장은 Pinecone
무료 등급 안이다. 저장소와 인덱스가 어긋났을 때는 `retrieval.index_state`로 맞춘다.

마감·삭제된 공고는 인덱스에서 지운다. 앱이 만료 공고를 추천하지 않게 하기 위해서다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.env import ensure_loaded
from job_matching_bot.retrieval import dedup, documents as doc
from job_matching_bot.retrieval.pinecone_index import (
    DIMENSION,
    EMBEDDING_MODEL,
    client,
    ensure_index,
    index_name,
)
from job_matching_bot.schemas.job_posting import Job

DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"

# 한 번에 보내는 건수. 두 서비스의 한도가 서로 달라 따로 둔다.
#   OpenAI  — 분당 토큰 한도(TPM). 문서가 평균 500자라 100건이면 약 2.5만 토큰
#   Pinecone — 요청당 페이로드 4MB. 벡터 하나가 1536 × 4바이트 ≈ 6KB이므로
#              100건이면 약 600KB. 메타데이터를 더해도 여유가 있다
EMBED_BATCH = 100
UPSERT_BATCH = 100
FETCH_BATCH = 200

# 배치 사이에 쉬는 시간(초). 분당 한도에 닿기 전에 스스로 속도를 낮춘다.
EMBED_PAUSE = 1.0
UPSERT_PAUSE = 0.2
DELETE_BATCH = 500


def load_store(store_path: Path) -> tuple[list[Job], Any]:
    """(공고 전체, 인덱스 추적 저장소). JSON 저장소는 추적 컬럼이 없어 None."""
    from job_matching_bot.ingestion.job_store import open_store

    store = open_store(store_path).load()
    jobs = [record.job for record in store.all_records()]
    return jobs, (store if hasattr(store, "index_state") else None)


def existing_hashes(index, ids: list[str]) -> dict[str, str]:
    """인덱스에 이미 있는 벡터의 embed_hash. 없는 ID는 결과에 안 들어온다. JSON 저장소용 폴백."""
    found: dict[str, str] = {}
    for start in range(0, len(ids), FETCH_BATCH):
        batch = ids[start : start + FETCH_BATCH]
        result = index.fetch(ids=batch)
        vectors = getattr(result, "vectors", None) or {}
        for vector_id, vector in vectors.items():
            meta = getattr(vector, "metadata", None) or {}
            found[vector_id] = str(meta.get("embed_hash", ""))
    return found


def embed_batch(embeddings, batch: list[str], attempts: int = 6) -> list[list[float]]:
    """분당 토큰 한도(429)에 걸리면 기다렸다 다시 시도한다."""
    import time

    from openai import RateLimitError

    delay = 5.0
    for attempt in range(1, attempts + 1):
        try:
            return embeddings.embed_documents(batch)
        except RateLimitError:
            if attempt == attempts:
                raise
            print(f"    분당 한도 도달 — {delay:.0f}초 쉬고 재시도 ({attempt}/{attempts - 1})")
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
    raise RuntimeError("unreachable")


def plan(jobs: list[Job], index, force: bool, tracker=None) -> tuple[list[Job], list[str], dict[str, int]]:
    """(올릴 공고, 지울 ID, 통계).

    올릴 대상은 `dedup.select`가 정한다. 마감 지난 공고와 재등록 공고를 걸러서,
    저장소에는 남기되 인덱스에는 올리지 않는다.

    `tracker`(SQLite 저장소)가 있으면 그 안의 embed_hash / indexed_embed_hash만으로
    판정한다. 없으면 인덱스에서 메타데이터를 받아 대조한다.
    """
    stats = {"저장소": len(jobs)}
    selected, select_stats = dedup.select(jobs)
    stats.update(select_stats)
    keep = {j.job_id for j in selected}

    if tracker is not None:
        state = tracker.index_state()
        indexed = {job_id for job_id, (_, done) in state.items() if done is not None}

        def is_current(job: Job) -> bool:
            embed, done = state.get(job.job_id, (None, None))
            return embed is not None and done == embed

        # 올린 기록이 있는데 지금은 대상이 아닌 것(마감·삭제·재등록·요건 사라짐)은 지운다.
        to_delete = sorted(job_id for job_id in indexed if job_id not in keep)
    else:
        known = {} if force else existing_hashes(index, [j.job_id for j in selected])
        indexed = set(known)

        def is_current(job: Job) -> bool:
            return known.get(job.job_id) == doc.embed_hash(job)

        stale_ids = [j.job_id for j in jobs if j.job_id not in keep]
        to_delete = list(existing_hashes(index, stale_ids)) if stale_ids else []

    stats["인덱스에 이미 있음"] = len(indexed & keep)
    changed = list(selected) if force else [j for j in selected if not is_current(j)]
    stats["올릴 것"] = len(changed)
    stats["변경 없음(건너뜀)"] = len(selected) - len(changed)
    stats["지울 것"] = len(to_delete)
    return changed, to_delete, stats


def upsert_batch(index, payload: list[dict], attempts: int = 5) -> None:
    """Pinecone 쓰기. 429·5xx면 기다렸다 다시 시도한다."""
    import time

    delay = 2.0
    for attempt in range(1, attempts + 1):
        try:
            index.upsert(vectors=payload)
            return
        except Exception as error:  # SDK 예외 이름이 버전마다 달라 상태 코드로 판단한다
            status = getattr(error, "status", None) or getattr(error, "status_code", None)
            if attempt == attempts or status not in (429, 500, 502, 503, 504):
                raise
            print(f"    Pinecone {status} — {delay:.0f}초 쉬고 재시도 ({attempt}/{attempts - 1})")
            time.sleep(delay)
            delay = min(delay * 2, 30.0)


def upsert(jobs: list[Job], index, tracker=None, embeddings=None) -> int:
    """작은 덩이로 나눠 임베딩하고 바로 올린다.

    한 덩이를 끝내고 다음으로 가므로, 중간에 멈춰도 그때까지는 인덱스에 남는다.
    문서 ID가 공고 ID라 다시 돌리면 덮어쓰기이고 중복이 생기지 않는다.
    덩이 사이에 잠깐 쉬어 분당 한도에 닿지 않게 한다.
    `tracker`가 있으면 덩이마다 올린 지문을 저장소에 기록한다.
    `embeddings`는 테스트가 대역을 넣는 자리다. 없으면 OpenAI를 쓴다.
    """
    import time

    if embeddings is None:
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(model=EMBEDDING_MODEL)
    done = 0
    for start in range(0, len(jobs), EMBED_BATCH):
        chunk = jobs[start : start + EMBED_BATCH]
        vectors = embed_batch(embeddings, [doc.index_body(j) for j in chunk])
        if vectors and len(vectors[0]) != DIMENSION:
            raise RuntimeError(f"임베딩 차원 {len(vectors[0])}이 인덱스 {DIMENSION}과 다릅니다.")

        payload = [
            {
                "id": job.job_id,
                "values": vector,
                "metadata": doc.clean_metadata(doc.to_metadata(job)),
            }
            for job, vector in zip(chunk, vectors, strict=True)
        ]
        for offset in range(0, len(payload), UPSERT_BATCH):
            upsert_batch(index, payload[offset : offset + UPSERT_BATCH])
            if offset + UPSERT_BATCH < len(payload):
                time.sleep(UPSERT_PAUSE)

        if tracker is not None:
            tracker.mark_indexed({job.job_id: doc.embed_hash(job) for job in chunk}, at=datetime.now())
        done += len(chunk)
        print(f"  적재 {done:,}/{len(jobs):,}")
        if done < len(jobs):
            time.sleep(EMBED_PAUSE)
    return done


def delete_ids(index, ids: list[str], tracker=None) -> int:
    """삭제도 나눠 보낸다. 한 번에 많이 보내면 요청이 거부된다."""
    import time

    for start in range(0, len(ids), DELETE_BATCH):
        batch = ids[start : start + DELETE_BATCH]
        index.delete(ids=batch)
        if tracker is not None:
            tracker.clear_indexed(batch)
        if start + DELETE_BATCH < len(ids):
            time.sleep(UPSERT_PAUSE)
    return len(ids)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="공고를 Pinecone 인덱스에 올린다")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 N건만")
    parser.add_argument("--force", action="store_true", help="해시 비교 없이 전량 다시 임베딩")
    parser.add_argument("--dry-run", action="store_true", help="올리지 않고 계획만 출력")
    args = parser.parse_args()

    ensure_loaded()
    info = ensure_index()
    print(f"인덱스 {info['name']} (차원 {info['dimension']}, {info['metric']})")

    index = client().Index(info["name"])
    jobs, tracker = load_store(args.store)
    changed, to_delete, stats = plan(jobs, index, args.force, tracker=tracker)
    if args.limit:
        changed = changed[: args.limit]

    for key, value in stats.items():
        print(f"  {key}: {value:,}")
    chars = sum(len(doc.index_body(j)) for j in changed)
    print(f"  예상 임베딩: {chars:,}자 ≈ {chars / 2 / 1e6:.2f}M 토큰 (약 ${chars / 2 / 1e6 * 0.02:.2f})")

    if args.dry_run:
        print("  (--dry-run: 아무것도 올리지 않았습니다)")
        return 0

    if to_delete:
        delete_ids(index, to_delete, tracker=tracker)
        print(f"  {len(to_delete):,}건 삭제")
    if changed:
        upsert(changed, index, tracker=tracker)

    total = index.describe_index_stats().get("total_vector_count")
    print(f"완료. 인덱스 벡터 수: {total:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
