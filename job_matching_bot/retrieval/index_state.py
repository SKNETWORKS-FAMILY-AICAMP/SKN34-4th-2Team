"""저장소가 기억하는 인덱스 상태를 보고, 맞추고, 되살린다.

    python -m job_matching_bot.retrieval.index_state            # 상태 요약
    python -m job_matching_bot.retrieval.index_state --refresh  # embed_hash 다시 계산
    python -m job_matching_bot.retrieval.index_state --adopt    # 인덱스에 이미 있는 벡터를 '올린 것'으로 등록

증분 적재는 저장소의 두 컬럼을 대조한다. `embed_hash`는 지금 내용으로 만든 지문이고
`indexed_embed_hash`는 마지막으로 인덱스에 올렸을 때의 지문이다. 둘이 다르면 올리고,
같으면 건너뛴다. 인덱스를 조회하지 않으므로 매일 17만 건을 돌려도 Pinecone 읽기가 없다.

`--adopt`는 JSON→SQLite 이관 직후처럼 저장소가 인덱스 상태를 모를 때 한 번 쓴다.
인덱스 벡터의 `content_hash` 메타데이터가 저장소와 같으면 그 벡터는 지금 내용으로
만든 것이므로 `indexed_embed_hash`를 채운다. 다르면 비워 두어 다음 적재 때 다시 올린다.
진행 중이 아닌 공고(만료·삭제)는 인덱스에 있기만 하면 등록해서, 다음 적재가 지우게 한다.

`--refresh`는 지문 규칙(`documents.embed_hash`)을 고쳤을 때 돌린다. 그 뒤 적재를 돌리면
지문이 달라진 공고만 다시 임베딩된다.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.env import ensure_loaded
from job_matching_bot.ingestion.job_store import open_store
from job_matching_bot.schemas.job_record import STATUS_OPEN

DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"
FETCH_BATCH = 200


def summary(store) -> dict[str, int]:
    def one(sql: str) -> int:
        return int(store.conn.execute(sql).fetchone()[0])

    return {
        "저장소 전체": one("SELECT COUNT(*) FROM jobs"),
        "진행 중(OPEN)": one("SELECT COUNT(*) FROM jobs WHERE status = 'OPEN'"),
        "embed_hash 없음": one("SELECT COUNT(*) FROM jobs WHERE embed_hash IS NULL"),
        "인덱스에 올린 것으로 기록": one("SELECT COUNT(*) FROM jobs WHERE indexed_embed_hash IS NOT NULL"),
        "올릴 것(OPEN인데 지문 다름·미적재, 품질 판정 전)": one(
            "SELECT COUNT(*) FROM jobs WHERE status = 'OPEN' AND "
            "(embed_hash IS NULL OR indexed_embed_hash IS NULL OR indexed_embed_hash != embed_hash)"
        ),
        "지울 것(OPEN 아닌데 인덱스에 있음)": one(
            "SELECT COUNT(*) FROM jobs WHERE status != 'OPEN' AND indexed_embed_hash IS NOT NULL"
        ),
    }


def adopt(store, index) -> dict[str, int]:
    """인덱스에 이미 있는 벡터를 저장소에 '올린 것'으로 등록한다."""
    refreshed = store.refresh_embed_hashes()
    rows = store.conn.execute("SELECT job_id, status, content_hash, embed_hash FROM jobs").fetchall()
    by_id = {row["job_id"]: row for row in rows}
    ids = list(by_id)

    found: dict[str, str] = {}
    for start in range(0, len(ids), FETCH_BATCH):
        result = index.fetch(ids=ids[start : start + FETCH_BATCH])
        for vector_id, vector in (getattr(result, "vectors", None) or {}).items():
            meta = getattr(vector, "metadata", None) or {}
            found[vector_id] = str(meta.get("content_hash", ""))
        if (start // FETCH_BATCH) % 20 == 19:
            print(f"  조회 {min(start + FETCH_BATCH, len(ids)):,}/{len(ids):,}", flush=True)

    adopted: dict[str, str] = {}
    stale: list[str] = []
    for job_id, indexed_content_hash in found.items():
        row = by_id[job_id]
        if row["status"] != STATUS_OPEN or indexed_content_hash == row["content_hash"]:
            adopted[job_id] = row["embed_hash"]
        else:
            stale.append(job_id)
    store.mark_indexed(adopted, at=datetime.now())
    return {
        "embed_hash 계산": refreshed,
        "인덱스에 있음": len(found),
        "등록": len(adopted),
        "내용이 달라 다음 적재 때 다시 올릴 것": len(stale),
        "인덱스에 없음": len(ids) - len(found),
    }


def recent_runs(store, limit: int = 5) -> list[dict]:
    rows = store.conn.execute(
        "SELECT started_at, finished_at, source, new, updated, unchanged, expired, removed, vectors, error "
        "FROM runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="저장소 ↔ 인덱스 추적 상태")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--refresh", action="store_true", help="embed_hash를 전 행 다시 계산한다")
    parser.add_argument("--adopt", action="store_true", help="인덱스에 이미 있는 벡터를 올린 것으로 등록한다")
    args = parser.parse_args()

    store = open_store(args.store)
    if not hasattr(store, "index_state"):
        print(f"SQLite 저장소만 지원합니다: {args.store}")
        return 1

    if args.refresh:
        print(f"embed_hash 다시 계산: {store.refresh_embed_hashes():,}행 바뀜")
    if args.adopt:
        ensure_loaded()
        from job_matching_bot.retrieval.pinecone_index import client, ensure_index

        info = ensure_index()
        print(f"인덱스 {info['name']} 조회")
        for key, value in adopt(store, client().Index(info["name"])).items():
            print(f"  {key}: {value:,}")

    print("상태")
    for key, value in summary(store).items():
        print(f"  {key}: {value:,}")
    runs = recent_runs(store)
    if runs:
        print("최근 실행")
        for run in runs:
            outcome = f"오류 {run['error']}" if run["error"] else f"벡터 {run['vectors'] if run['vectors'] is not None else '-'}"
            print(
                f"  {run['started_at'][:19]} {run['source'] or ''} 신규 {run['new']} 갱신 {run['updated']} "
                f"변경없음 {run['unchanged']} 만료 {run['expired']} 삭제 {run['removed']} · {outcome}"
            )
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
