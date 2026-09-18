"""크롤 원본에서 Pinecone까지 한 번에 돌리는 적재 파이프라인.

    python -m job_matching_bot.sync                      # 전체
    python -m job_matching_bot.sync --dry-run            # 계획만
    python -m job_matching_bot.sync --skip-index         # 저장소까지만
    python -m job_matching_bot.sync --observed <목록.json>  # 사이트에서 내려간 공고 판정

스케줄러는 이 명령 하나만 부르면 된다. 단계마다 건수와 제외 사유를 세어
`artifacts/sync_report.json`에 남기므로, 어느 단계에서 데이터가 줄었는지 추적할 수 있다.

## 단계

1. 원본 읽기      크롤러가 쌓은 JSONL
2. 유효성 검사    필수 필드·본문·마감일이 읽히는지
3. 중복 제거      같은 공고를 여러 번 받은 줄에서 최신 것만
4. 정규화        출처별 파서로 공통 스키마로
5. 본문 정제      자격요건·우대사항 구간 분리, 요구역량 추출
6. 저장소 반영    신규·갱신·만료·삭제 판정 (증분)
7. 품질 판정      마감 지남·재등록·요건 없음 제외
8. 변경 확인      저장소의 embed_hash와 indexed_embed_hash 대조 (인덱스 조회 없음)
9. 임베딩·적재    바뀐 것만 OpenAI 호출 후 Pinecone upsert

청킹 단계는 두지 않는다. 인덱싱 텍스트가 요건 구간만이라 문서 중앙값이 500자
안팎이고, 공고 하나가 문서 하나로 들어간다. 본문 전체를 넣게 되면 그때 붙인다.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from job_matching_bot.config import ARTIFACTS_DIR, DEFAULT_SARAMIN_INPUT
from job_matching_bot.env import ensure_loaded
from job_matching_bot.ingest import DEFAULT_RAW_ROOT, DEFAULT_STORE, SOURCES, ingest
from job_matching_bot.ingestion.record_files import latest_by_id, read_records, record_ids
from job_matching_bot.schemas.job_record import CollectionReport

DEFAULT_REPORT = ARTIFACTS_DIR / "sync_report.json"
KST = timezone(timedelta(hours=9))

# 이 필드가 없으면 정규화가 의미 있는 값을 못 만든다.
REQUIRED_FIELDS = ("source_job_id",)


def validate(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """읽을 수 있는 레코드만 남긴다. 버린 이유를 센다."""
    kept: list[dict[str, Any]] = []
    stats = {"입력": len(records), "필수 필드 없음": 0, "본문·조건 모두 없음": 0}
    for record in records:
        listing = record.get("list_item") or {}
        if not any(record.get(f) or listing.get(f) for f in REQUIRED_FIELDS):
            stats["필수 필드 없음"] += 1
            continue
        # 본문도 조건표도 없으면 정규화해도 쓸 값이 없다.
        if not (record.get("description") or record.get("conditions") or record.get("sections")):
            stats["본문·조건 모두 없음"] += 1
            continue
        kept.append(record)
    stats["통과"] = len(kept)
    return kept, stats


def record_run(
    store_path: Path, collection: CollectionReport, started: datetime, *, vectors: int | None = None, error: str | None = None
) -> None:
    """SQLite 저장소면 runs 표에 이번 실행을 남긴다. JSON 저장소는 건너뛴다."""
    from job_matching_bot.ingestion.job_store import open_store

    store = open_store(store_path)
    if not hasattr(store, "record_run"):
        return
    store.record_run(collection, started_at=started, finished_at=datetime.now(), vectors=vectors, error=error)
    store.save()
    store.close()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="크롤 원본 → 저장소 → Pinecone 적재")
    parser.add_argument("--input", type=Path, default=DEFAULT_SARAMIN_INPUT, help="크롤 원본 JSONL")
    parser.add_argument("--source", default="SARAMIN_POC", choices=sorted(SOURCES))
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--observed",
        type=Path,
        default=None,
        help="목록 수집 결과. 주면 목록에서 사라진 공고를 삭제 후보로 판정한다",
    )
    parser.add_argument(
        "--as-of",
        type=datetime.fromisoformat,
        default=None,
        help="수집 기준 시각(ISO). 마감 판정과 last_seen_at에 쓴다. 기본은 지금",
    )
    parser.add_argument("--no-llm", action="store_true", default=True, help="요건 추출에 LLM을 쓰지 않는다(기본)")
    parser.add_argument("--llm", dest="no_llm", action="store_false", help="LLM 요건 추출을 켠다")
    parser.add_argument("--skip-index", action="store_true", help="저장소까지만 하고 Pinecone은 건드리지 않는다")
    parser.add_argument("--dry-run", action="store_true", help="아무것도 쓰지 않고 계획만 출력")
    args = parser.parse_args()

    ensure_loaded()
    started = datetime.now()
    as_of = args.as_of or datetime.now(KST)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=KST)
    report: dict[str, Any] = {"started_at": started.isoformat(timespec="seconds"), "as_of": as_of.isoformat()}
    print(f"적재 파이프라인 시작 · 원본 {args.input}")

    # 1~2. 원본 읽기와 유효성 검사
    records = read_records(args.input)
    records, valid_stats = validate(records)
    report["validate"] = valid_stats
    print("\n[1-2] 원본·유효성")
    for key, value in valid_stats.items():
        print(f"  {key}: {value:,}")

    # 3. 같은 공고를 여러 번 받았으면 마지막 줄만 쓴다. 줄마다 저장하면 revisions만 올라간다.
    total_lines = len(records)
    records = list(latest_by_id(records).values())
    report["dedup"] = {"고유 공고": len(records), "중복 줄": total_lines - len(records)}
    print(f"\n[3] 중복 제거: 고유 {len(records):,}건 (중복 줄 {total_lines - len(records):,})")

    observed = record_ids(read_records(args.observed)) if args.observed else None
    if observed is not None:
        print(f"[6] 목록에서 확인된 공고 {len(observed):,}건 — 없는 공고는 삭제 후보")

    if args.dry_run:
        print("\n(--dry-run: 저장소와 인덱스를 건드리지 않았습니다)")
        return 0

    # 4~6. 정규화·본문 정제·저장소 반영
    print("\n[4-6] 정규화 · 본문 정제 · 저장소 반영")
    collection = ingest(
        records,
        source=args.source,
        store_path=args.store,
        raw_root=args.raw_root,
        as_of=as_of,
        observed_ids=observed,
        extract=True,
        allow_llm=not args.no_llm,
    )
    report["collection"] = {
        "신규": len(collection.new),
        "갱신": len(collection.updated),
        "변경없음": len(collection.unchanged),
        "만료": len(collection.expired),
        "삭제": len(collection.removed),
        "미관측(상태유지)": len(collection.still_missing),
    }
    for key, value in report["collection"].items():
        print(f"  {key}: {value:,}")

    # 7~9. 품질 판정 · 변경 확인 · 임베딩 적재
    vectors = 0
    if args.skip_index:
        print("\n[7-9] --skip-index: Pinecone을 건드리지 않았습니다")
    else:
        from job_matching_bot.retrieval.pinecone_index import client, ensure_index
        from job_matching_bot.retrieval.upsert import delete_ids, load_store, plan, upsert

        print("\n[7-9] 품질 판정 · 변경 확인 · 적재")
        info = ensure_index()
        index = client().Index(info["name"])
        jobs, tracker = load_store(args.store)
        try:
            changed, to_delete, stats = plan(jobs, index, force=False, tracker=tracker)
            for key, value in stats.items():
                print(f"  {key}: {value:,}")
            if to_delete:
                delete_ids(index, to_delete, tracker=tracker)
                print(f"  {len(to_delete):,}건 삭제")
            if changed:
                vectors = upsert(changed, index, tracker=tracker)
            total = index.describe_index_stats().get("total_vector_count", 0)
            report["index"] = {**stats, "삭제": len(to_delete), "적재 후 벡터": total}
            print(f"  인덱스 벡터 수: {total:,}")
        except Exception as error:
            if tracker is not None:
                tracker.close()
            record_run(args.store, collection, started, vectors=vectors, error=repr(error))
            raise
        if tracker is not None:
            tracker.close()
    record_run(args.store, collection, started, vectors=vectors)

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    report["elapsed_seconds"] = round((datetime.now() - started).total_seconds(), 1)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n완료 ({report['elapsed_seconds']}초) · 리포트: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
