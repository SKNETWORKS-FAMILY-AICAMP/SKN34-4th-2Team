"""공고 요건 채우기 — 본문에서 최소 연차 · 전공 · 자격증을 뽑아 빈 칸만 채운다(ingestion/requirements_llm).

    python -m job_matching_bot.fill_requirements --job-id JOBKOREA-49917023 --dry-run   # 한 건, 쓰지 않고 보기
    python -m job_matching_bot.fill_requirements --limit 200                             # 새 공고부터 200건
    python -m job_matching_bot.fill_requirements --limit 8000 --workers 12 --min-days-left 14   # 기존 공고(2주 넘게 남은 것)

밤 배치는 묶기 뒤 · 인덱스 앞에 부른다(crawling/nightly.run_fill_requirements). 채운 연차는 인덱스 메타데이터에도
실려야 하므로 인덱스보다 먼저여야 한다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

from job_matching_bot.env import ensure_loaded
from job_matching_bot.ingestion import requirements_llm as req
from job_matching_bot.ingestion.job_store import open_store

# 한 번에 분석하고 쓰는 묶음 크기
CHUNK = 200


def run(store_path: Path, *, limit: int, workers: int = 8, dry_run: bool = False,
        job_ids: list[str] | None = None, extractor=None, show: int = 0, min_days_left: int | None = None,
        entry_check: bool = False) -> dict[str, Any]:
    started = time.monotonic()
    store = open_store(store_path)
    counts: Counter = Counter()
    shown = 0
    try:
        # entry_check — 본문에 「신입도 가능」이 있는 경력 공고(연차가 이미 차 있어도)를 신입 여부 때문에 다시 본다
        targets = store.entry_targets(limit) if entry_check else store.requirement_targets(limit, job_ids, min_days_left)
        jobs = [r.job for r in targets]
        # 조금씩 분석하고 바로 쓴다 — 한꺼번에 뽑고 끝에 쓰면 중간에 끊길 때 그때까지 쓴 비용이 날아간다.
        # 쓴 공고는 표시가 남아 다시 돌리면 건너뛰므로 이어서 할 수 있다.
        for start in range(0, len(jobs), CHUNK):
            for job, fill, error in req.analyze(jobs[start:start + CHUNK], workers=workers, extractor=extractor):
                if fill is None:
                    counts["failed"] += 1
                    continue
                counts["analyzed"] += 1
                if fill.accepts_entry and "career_type" in fill.values:
                    counts["to_any"] += 1
                elif fill.note:
                    counts["multi_role"] += 1
                for name in fill.values:
                    if not name.endswith(("_terms", "_groups")):
                        counts[f"filled_{name}"] += 1
                if show and shown < show and fill.values:
                    shown += 1
                    print(f"  {job.job_id} {job.company[:14]} | {job.title[:30]} → {fill.values}")
                if not dry_run:
                    store.fill_requirements(job.job_id, fill.values, req.marker(fill))
            if len(jobs) > CHUNK:
                print(f"[요건 채우기] {min(start + CHUNK, len(jobs)):,}/{len(jobs):,} · {dict(counts)} · "
                      f"{time.monotonic() - started:.0f}초", flush=True)
    finally:
        store.close()
    summary = {"targets": len(jobs), **counts, "dry_run": dry_run, "seconds": round(time.monotonic() - started, 1)}
    return summary


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="공고 요건 채우기(빈 칸만)")
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--job-id", action="append", default=None)
    parser.add_argument("--dry-run", action="store_true", help="뽑기만 하고 쓰지 않는다")
    parser.add_argument("--min-days-left", type=int, default=None,
                        help="마감까지 이만큼(일) 남은 공고만. 기존 공고를 한꺼번에 채울 때 곧 마감될 것은 건너뛴다")
    parser.add_argument("--entry-check", action="store_true",
                        help="본문에 「신입도 가능」이 있는 경력 공고를 신입 여부 때문에 다시 본다(연차가 차 있어도)")
    parser.add_argument("--show", type=int, default=20, help="채울 값을 몇 건 보여 줄지")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args(argv)
    ensure_loaded()
    from job_matching_bot.ingest import DEFAULT_STORE

    summary = run(args.store or DEFAULT_STORE, limit=args.limit, workers=args.workers, dry_run=args.dry_run,
                  job_ids=args.job_id, show=args.show, min_days_left=args.min_days_left, entry_check=args.entry_check)
    print("[요건 채우기] " + json.dumps(summary, ensure_ascii=False))
    if args.report:
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
