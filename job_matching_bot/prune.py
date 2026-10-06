"""닫힌 지 오래된 공고를 저장소에서 지운다.

    python -m job_matching_bot.prune                    # 무엇을 지울지 세기만 한다
    python -m job_matching_bot.prune --apply            # 백업하고 지운다
    python -m job_matching_bot.prune --apply --vacuum   # 지운 뒤 표 파일까지 줄인다(그동안 표가 잠긴다)

## 왜 지우나

검색 · 집계는 공고 표를 처음부터 끝까지 훑는다. 2026-10-06 `jobs` 10.4만 건 중 5.5만 건이 닫힌 공고였고,
목록 표까지 합치면 검색에 절대 안 나오는 공고 12만 건(약 190MB)을 매번 같이 읽었다. RDS 캐시(약 360MB)보다
표가 커서 매번 디스크를 읽어, 조건 조회 · 집계가 3~20초씩 흔들렸다. 닫힌 공고는 주 1.5만~2만 건씩 는다.

## 무엇을 지우나 — 닫힌 지 `KEEP_DAYS`(15일)가 지난 것

- `jobs` EXPIRED: 마감일로부터 15일. REMOVED · CLOSED: 마지막으로 본 날로부터 15일. 같은 번호로 다시
  올라오면(마감 연장 · 재게시) 보통 그 안에 보인다 — 밤 배치가 되살린다(`refresh_listing_deadlines`).
  15일 뒤에 다시 보이면 새 공고로 상세를 다시 받는다.
- `list_jobs`: 목록에서 15일 넘게 안 보였거나(밤 배치도 내려간 공고로 본다, `OBSERVED_WINDOW_DAYS`)
  마감일이 15일 넘게 지난 것.
- 함께: 지운 공고의 `job_tags` · `link_checks`, 잡코리아 누적 상세(`details.jsonl`)의 그 공고 줄 — 남겨 두면
  잡코리아 관측을 건너뛰는 밤에 누적 상세 전부가 다시 적재돼 지운 공고가 되살아난다.

## 무엇을 남기나

- **첨삭 중인 공고.** 맞춤 이력서(`resumes.linked_job_id`)가 가리키는 공고는 닫혀도 남긴다 — 공고 맞춤 지원 ·
  맞춤 공고 카드가 그 행을 읽는다. `cover_letters.job_id`(팀원 migration 0012)가 생기면 그것도 남긴다.
  표가 없으면 건너뛴다.
- **아직 Pinecone 에 올라가 있는 공고**(`indexed_embed_hash`). 행을 먼저 지우면 밤 인덱스가 그 벡터를 지울
  근거를 잃는다. 밤 배치가 벡터를 지운 뒤 다음 정리에서 지운다.

지우기 전에 지울 행을 `artifacts/backup/` 에 압축해 둔다. 밤 배치(23:00~) 중에는 돌리지 않는다.
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.env import ensure_loaded

KEEP_DAYS = 15
BACKUP_DIR = ARTIFACTS_DIR / "backup"
# 첨삭 중인 공고를 가리키는 칸. 없는 표는 건너뛴다(cover_letters 는 팀원 migration 뒤에 생긴다).
REFERENCES = (("public", "resumes", "linked_job_id"), ("public", "cover_letters", "job_id"))


def protected_ids(conn) -> set[str]:
    """첨삭 중인 공고 — 닫혀도 지우지 않는다."""
    ids: set[str] = set()
    for schema, table, column in REFERENCES:
        exists = conn.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = %s AND table_name = %s AND column_name = %s",
            (schema, table, column),
        ).fetchone()
        if not exists:
            continue
        rows = conn.execute(f'SELECT DISTINCT "{column}" AS job_id FROM {schema}."{table}" WHERE "{column}" IS NOT NULL')
        ids.update(str(row["job_id"]) for row in rows)
    return ids


def job_candidates(conn, now: datetime, keep_days: int, protect: set[str]) -> list[dict]:
    """닫힌 지 `keep_days`가 지났고, 첨삭 중이 아니고, 인덱스에 없는 `jobs` 행(전 칸)."""
    cutoff = now - timedelta(days=keep_days)
    rows = conn.execute(
        "SELECT * FROM jobs WHERE indexed_embed_hash IS NULL AND ("
        " (status = 'EXPIRED' AND deadline IS NOT NULL AND deadline <> '' AND substr(deadline, 1, 10) < %s)"
        " OR (status IN ('REMOVED', 'CLOSED') AND last_seen_at IS NOT NULL AND last_seen_at::timestamptz < %s))",
        (cutoff.date().isoformat(), cutoff.isoformat()),
    ).fetchall()
    return [dict(row) for row in rows if str(row["job_id"]) not in protect]


def listing_candidates(conn, now: datetime, keep_days: int) -> list[dict]:
    """목록에서 `keep_days` 넘게 안 보였거나 마감이 그만큼 지난 `list_jobs` 행."""
    cutoff = now - timedelta(days=keep_days)
    rows = conn.execute(
        "SELECT * FROM list_jobs WHERE seen_at::timestamptz < %s"
        " OR (deadline IS NOT NULL AND deadline <> '' AND substr(deadline, 1, 10) < %s)",
        (cutoff.isoformat(), cutoff.date().isoformat()),
    ).fetchall()
    return [dict(row) for row in rows]


def backup(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as out:
        for row in rows:
            out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")


def prune_jobkorea_file(path: Path, removed: set[str], backup_path: Path, apply: bool) -> tuple[int, int]:
    """잡코리아 누적 상세에서 지운 공고 줄을 뺀다. (전체 줄, 뺀 줄)."""
    if not path.exists():
        return 0, 0
    kept: list[str] = []
    total = dropped = 0
    with path.open(encoding="utf-8") as src:
        for line in src:
            if not line.strip():
                continue
            total += 1
            if str(json.loads(line).get("source_job_id")) in removed:
                dropped += 1
                continue
            kept.append(line if line.endswith("\n") else line + "\n")
    if apply and dropped:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup_path)
        temp = path.with_suffix(".jsonl.tmp")
        temp.write_text("".join(kept), encoding="utf-8")
        temp.replace(path)
    return total, dropped


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="닫힌 지 오래된 공고 지우기")
    parser.add_argument("--store", type=Path, default=None)
    parser.add_argument("--keep-days", type=int, default=KEEP_DAYS)
    parser.add_argument("--apply", action="store_true", help="백업하고 실제로 지운다")
    parser.add_argument("--vacuum", action="store_true", help="지운 뒤 VACUUM FULL — 그동안 공고 표가 잠긴다")
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()
    ensure_loaded()

    from job_matching_bot.crawling.nightly import JOBKOREA_DETAIL_FILE, KST
    from job_matching_bot.ingest import DEFAULT_STORE
    from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

    now = datetime.now(KST)
    stamp = now.strftime("%Y%m%d-%H%M%S")
    store = SqliteJobStore(args.store or DEFAULT_STORE)
    conn = store.conn
    report: dict = {"at": now.isoformat(timespec="seconds"), "keep_days": args.keep_days, "applied": args.apply}
    try:
        protect = protected_ids(conn)
        jobs = job_candidates(conn, now, args.keep_days, protect)
        listings = listing_candidates(conn, now, args.keep_days)
        job_ids = [str(row["job_id"]) for row in jobs]
        jobkorea = {str(row["source_job_id"]) for row in jobs if row.get("source") == "JOBKOREA_POC"}
        tags = conn.execute("SELECT count(*) AS n FROM job_tags WHERE job_id = ANY(%s)", (job_ids,)).fetchone()["n"]
        checks = conn.execute("SELECT count(*) AS n FROM link_checks WHERE job_id = ANY(%s)", (job_ids,)).fetchone()["n"]
        by_status: dict[str, int] = {}
        for row in jobs:
            key = f"{row['source']} {row['status']}"
            by_status[key] = by_status.get(key, 0) + 1
        report.update({
            "protected": len(protect), "jobs": len(jobs), "jobs_by_status": by_status,
            "job_tags": tags, "link_checks": checks, "list_jobs": len(listings),
        })
        total, dropped = prune_jobkorea_file(
            JOBKOREA_DETAIL_FILE, jobkorea, BACKUP_DIR / f"prune-{stamp}-jobkorea-details.jsonl", apply=False
        )
        report["jobkorea_file"] = {"lines": total, "drop": dropped}

        print(f"닫힌 지 {args.keep_days}일 지난 공고 — 첨삭 중이라 남기는 공고 {len(protect):,}건")
        print(f"  jobs {len(jobs):,}건  {by_status}")
        print(f"  job_tags {tags:,}줄 · link_checks {checks:,}줄")
        print(f"  list_jobs {len(listings):,}건")
        print(f"  잡코리아 누적 상세 {total:,}줄 중 {dropped:,}줄")

        if not args.apply:
            print("\n세기만 했습니다. 지우려면 --apply 를 붙이세요.")
            return 0

        backup(jobs, BACKUP_DIR / f"prune-{stamp}-jobs.jsonl.gz")
        backup(listings, BACKUP_DIR / f"prune-{stamp}-list_jobs.jsonl.gz")
        print(f"\n백업 {BACKUP_DIR}/prune-{stamp}-*")

        started = time.monotonic()
        list_keys = [(row["source"], row["source_job_id"]) for row in listings]
        with conn:
            conn.execute("DELETE FROM job_tags WHERE job_id = ANY(%s)", (job_ids,))
            conn.execute("DELETE FROM link_checks WHERE job_id = ANY(%s)", (job_ids,))
            deleted_jobs = conn.execute("DELETE FROM jobs WHERE job_id = ANY(%s)", (job_ids,)).rowcount
            deleted_list = 0
            for start in range(0, len(list_keys), 5000):
                part = list_keys[start:start + 5000]
                deleted_list += conn.execute(
                    "DELETE FROM list_jobs WHERE (source, source_job_id) IN (SELECT * FROM unnest(%s::text[], %s::text[]))",
                    ([s for s, _ in part], [i for _, i in part]),
                ).rowcount
        report.update({"deleted_jobs": deleted_jobs, "deleted_list_jobs": deleted_list,
                       "delete_seconds": round(time.monotonic() - started, 1)})
        print(f"지움: jobs {deleted_jobs:,} · list_jobs {deleted_list:,} ({report['delete_seconds']}초)")

        # DB 를 먼저 지우고 파일을 뺀다. 파일만 빠지고 DB 가 남는 것보다 반대가 안전하다 — 다음 정리가 다시 센다.
        total, dropped = prune_jobkorea_file(
            JOBKOREA_DETAIL_FILE, jobkorea, BACKUP_DIR / f"prune-{stamp}-jobkorea-details.jsonl", apply=True
        )
        report["jobkorea_file"] = {"lines": total, "dropped": dropped}
        print(f"잡코리아 누적 상세 {dropped:,}줄 뺌")

        if args.vacuum:
            for table in ("jobs", "job_tags", "list_jobs", "link_checks"):
                began = time.monotonic()
                conn.execute(f"VACUUM (FULL, ANALYZE) {table}")
                # FULL 은 표를 새로 쓰며 가시성 지도를 비운다. 그대로 두면 목록 검색의 「상세에 있는 공고 빼기」가
                # 인덱스만 읽는 길을 못 써서 jobs 를 작업자마다 통째로 훑었다(2026-10-06 첫 정리 뒤 검색 4~8초 → 7~14초).
                # 보통 VACUUM 이 지도를 다시 채운다.
                conn.execute(f"VACUUM (ANALYZE) {table}")
                print(f"VACUUM FULL + VACUUM {table} ({time.monotonic() - began:.0f}초)")
            sizes = conn.execute(
                "SELECT relname, pg_size_pretty(pg_total_relation_size(relid)) AS size FROM pg_stat_user_tables"
                " WHERE schemaname = current_schema() AND relname IN ('jobs', 'list_jobs', 'job_tags')"
            ).fetchall()
            report["sizes_after"] = {row["relname"]: row["size"] for row in sizes}
            print("크기:", report["sizes_after"])
        return 0
    finally:
        store.close()
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
