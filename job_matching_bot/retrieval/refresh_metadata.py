"""인덱스의 메타데이터만 갱신한다. 벡터는 건드리지 않아 임베딩 비용이 없다.

    python -m job_matching_bot.retrieval.refresh_metadata            # 전량
    python -m job_matching_bot.retrieval.refresh_metadata --limit 100

`documents.to_metadata()`가 만드는 값으로 통째로 덮어쓴다. excerpt 길이를 바꾸거나
회사명·제목 정제 규칙을 고쳤을 때, 다시 임베딩하지 않고 반영하는 용도다.

`upsert`와 달리 `content_hash`를 비교하지 않는다. 메타데이터 규칙이 바뀐 것이지
공고 내용이 바뀐 것이 아니라서, 해시로는 변경을 감지할 수 없기 때문이다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.env import ensure_loaded
from job_matching_bot.retrieval import dedup, documents as doc
from job_matching_bot.retrieval.pinecone_index import client, ensure_index
from job_matching_bot.schemas.job_record import JobRecord

DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"
PAUSE_EVERY = 200
PAUSE_SECONDS = 0.5


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Pinecone 메타데이터만 갱신")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    ensure_loaded()
    info = ensure_index()
    index = client().Index(info["name"])

    from job_matching_bot.ingestion.job_store import open_store

    jobs = [record.job for record in open_store(args.store).load().all_records()]
    selected, _ = dedup.select(jobs)
    if args.limit:
        selected = selected[: args.limit]
    print(f"인덱스 {info['name']} · 대상 {len(selected):,}건 (excerpt 상한 {doc._META_TEXT_LIMIT}자)", flush=True)

    started = time.time()
    for i, job in enumerate(selected, 1):
        index.update(id=job.job_id, set_metadata=doc.clean_metadata(doc.to_metadata(job)))
        if i % PAUSE_EVERY == 0:
            print(f"  {i:,}/{len(selected):,} ({time.time() - started:.0f}초)", flush=True)
            time.sleep(PAUSE_SECONDS)

    print(f"완료 {len(selected):,}건 ({time.time() - started:.0f}초) · 임베딩 재생성 없음", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
