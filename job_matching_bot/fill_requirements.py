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
import re
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
# 실패한 공고를 다시 보기 전에 쉬는 시간. 분당 토큰 한도가 1분 단위로 풀린다
RETRY_PAUSE_SECONDS = 60.0


def run(store_path: Path, *, limit: int, workers: int = 8, dry_run: bool = False,
        job_ids: list[str] | None = None, extractor=None, show: int = 0, min_days_left: int | None = None,
        entry_check: bool = False, retry_pause: float | None = RETRY_PAUSE_SECONDS) -> dict[str, Any]:
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
        failed: list = []

        def handle(results) -> None:
            nonlocal shown
            for job, fill, error in results:
                if fill is None:
                    failed.append((job, error))
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

        for start in range(0, len(jobs), CHUNK):
            handle(req.analyze(jobs[start:start + CHUNK], workers=workers, extractor=extractor))
            if len(jobs) > CHUNK:
                print(f"[요건 채우기] {min(start + CHUNK, len(jobs)):,}/{len(jobs):,} · {dict(counts)} · "
                      f"실패 {len(failed):,} · {time.monotonic() - started:.0f}초", flush=True)
        # 실패는 거의 다 분당 토큰 한도(429)다. 한도가 풀리는 1분을 쉬고 한 번만 더 본다.
        # 그래도 실패하면 표시를 안 남겨 다음 밤에 다시 본다.
        if failed and retry_pause is not None:
            counts["retried"] = len(failed)
            print(f"[요건 채우기] 실패 {len(failed):,}건 — {retry_pause:.0f}초 쉬고 한 번 더", flush=True)
            time.sleep(retry_pause)
            retry, failed = [job for job, _ in failed], []
            handle(req.analyze(retry, workers=workers, extractor=extractor))
    finally:
        store.close()
    if failed:
        counts["failed"] = len(failed)
    # 실패 이유를 종류별로 남긴다(429 · 시간 초과 …). 예전에는 버려서 로그로 원인을 알 수 없었다.
    reasons = Counter(_reason(error) for _, error in failed)
    summary = {"targets": len(jobs), **counts, **({"fail_reasons": dict(reasons)} if reasons else {}),
               "dry_run": dry_run, "seconds": round(time.monotonic() - started, 1)}
    return summary


def _reason(error: str) -> str:
    """'OpenAIRateLimitError: Error code: 429 - {...}' → 'OpenAIRateLimitError 429'."""
    kind = error.split(":", 1)[0].strip() or "알 수 없음"
    code = re.search(r"Error code: (\d{3})", error)
    return f"{kind} {code.group(1)}" if code else kind


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
