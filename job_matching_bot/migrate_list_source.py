"""목록 표(`list_seen`·`list_jobs`)에 출처(`source`)를 넣는 마이그레이션.

## 왜 필요한가

두 표의 `source_job_id`는 맨 숫자다(`44743994`). 사람인 `rec_idx`도 8자리,
잡코리아 공고번호도 8자리라 번호가 겹치면 **다른 회사 공고가 같은 행으로 덮어써진다.**
상세 표(`jobs`)는 이미 `source` 칸과 `UNIQUE(source, source_job_id)`가 있어 안전하지만,
목록 단계에는 그 구분이 없다.

## 왜 ALTER 로 안 되는가

`ALTER TABLE ... ADD COLUMN` 으로 칸은 붙지만 SQLite는 기본키를 바꾸지 못한다.
`list_jobs`의 PK는 `source_job_id` 단독, `list_seen`은 `(source_job_id, cat_mcls)`이라
출처를 키에 넣으려면 표를 다시 만드는 수밖에 없다. 이 스크립트가 그 일을 한다.

## 하는 일

1. 여유가 되면 백업을 뜬다 (`artifacts/backups/`, `VACUUM INTO`)
2. 새 정의로 표를 만들고 → 옮겨 담고 → 바꿔 끼운다 (한 트랜잭션)
3. 인덱스와 `list_jobs_search` 뷰를 다시 만든다
4. 행 수와 무결성을 확인한다

옛 행의 출처는 `list_jobs`는 `job_id`의 접두사(`SARAMIN-…`)에서 뽑고,
`list_seen`은 그 칸이 없으므로 `--default-source` 값(기본 `SARAMIN_POC`)으로 채운다.

## 쓰는 법

    python -m job_matching_bot.migrate_list_source            # 무엇을 할지만 보여 준다
    python -m job_matching_bot.migrate_list_source --apply    # 실제로 바꾼다

야간 배치가 도는 동안에는 쓰지 말 것. 다른 쓰기 연결이 잡혀 있으면 스스로 멈춘다.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR

DB_PATH = ARTIFACTS_DIR / "job_store.sqlite"
BACKUP_DIR = ARTIFACTS_DIR / "backups"

# `jobs.source`와 같은 표기를 쓴다. 두 표의 값이 어긋나면 조인이 조용히 빈다.
DEFAULT_SOURCE = "SARAMIN_POC"

# `job_id` 접두사 → `source`. 잡코리아 수집기가 `JOBKOREA-<번호>`로 만든다.
PREFIX_TO_SOURCE = {
    "SARAMIN": "SARAMIN_POC",
    "JOBKOREA": "JOBKOREA_POC",
}

NEW_LIST_SEEN = """
CREATE TABLE list_seen_new (
    source_job_id TEXT NOT NULL,
    cat_mcls TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    first_seen_at TEXT,
    source TEXT NOT NULL DEFAULT '{default_source}',
    PRIMARY KEY (source, source_job_id, cat_mcls)
)
"""

NEW_LIST_JOBS = """
CREATE TABLE list_jobs_new (
    source_job_id TEXT NOT NULL,
    job_id TEXT NOT NULL,
    source_url TEXT,
    company TEXT,
    title TEXT,
    keywords TEXT,            -- 목록의 job_sectors. jobs.keywords와 같은 자리
    region TEXT,
    career_type TEXT,
    min_career_years INTEGER,
    education TEXT,
    employment_type TEXT,
    condition_text TEXT,      -- 가르기 전 원문. 규칙을 고칠 때 다시 볼 근거
    seen_at TEXT NOT NULL,
    first_seen_at TEXT,
    deadline TEXT,
    support_text TEXT,
    source TEXT NOT NULL DEFAULT '{default_source}',
    PRIMARY KEY (source, source_job_id)
)
"""

# PK 앞자리가 `source`로 바뀌어 `source_job_id`만으로 찾는 질의가 인덱스를 잃는다.
# 출처를 모른 채 번호로 찾는 길이 남아 있으므로 따로 인덱스를 둔다.
INDEXES = (
    "CREATE INDEX list_seen_at ON list_seen(seen_at)",
    "CREATE INDEX list_seen_job ON list_seen(source_job_id)",
    "CREATE INDEX list_jobs_seen ON list_jobs(seen_at)",
    "CREATE INDEX list_jobs_job ON list_jobs(source_job_id)",
)

# 원래 뷰에 `source`만 더한다. 나머지 칸과 주석은 그대로 둔다.
NEW_VIEW = """
CREATE VIEW list_jobs_search AS
SELECT
    source_job_id, job_id, source_url, company, title, keywords,
    region, career_type, min_career_years, education, employment_type,
    'OPEN'  AS status,        -- 목록에 보이면 열려 있는 것으로 본다
    NULL    AS deadline,      -- 목록은 "내일마감" 같은 말뿐이라 날짜가 없다
    '[]'    AS tech_stack,    -- 기술 태그는 상세에서만 나온다
    ''      AS description,   -- 본문 없음. 이것이 상세 미수집의 표시다
    seen_at, first_seen_at, source
FROM list_jobs
"""


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def already_done(conn: sqlite3.Connection) -> bool:
    """두 표 모두 `source`를 키에 들고 있으면 할 일이 없다."""
    for table in ("list_seen", "list_jobs"):
        if "source" not in _columns(conn, table):
            return False
        pk = [row[1] for row in conn.execute(f"PRAGMA table_info({table})") if row[5]]
        if "source" not in pk:
            return False
    return True


def check_writable(conn: sqlite3.Connection) -> None:
    """다른 쓰기 연결(야간 배치 등)이 잡고 있으면 손대지 않는다."""
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError as error:
        raise SystemExit(
            f"저장소가 다른 곳에서 쓰이는 중입니다({error}). 배치가 끝난 뒤 다시 실행하세요."
        ) from error


def backup(db: Path) -> Path:
    """`VACUUM INTO`로 조각을 턴 사본을 남긴다. 원본보다 작고 일관된 시점이다."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"job_store-{stamp}-pre-list-source.sqlite"

    free = shutil.disk_usage(BACKUP_DIR).free
    need = db.stat().st_size
    if free < need * 1.2:
        raise SystemExit(
            f"디스크 여유가 모자랍니다. 필요 {need / 1e9:.1f}GB · 남음 {free / 1e9:.1f}GB"
        )

    conn = sqlite3.connect(db)
    try:
        conn.execute("VACUUM INTO ?", (str(target),))
    finally:
        conn.close()
    return target


def migrate(conn: sqlite3.Connection, default_source: str) -> dict[str, int]:
    """표 둘을 다시 만들어 옮겨 담는다. 한 트랜잭션 안에서 끝낸다."""
    before = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("list_seen", "list_jobs")
    }

    # `job_id` 접두사로 출처를 가른다. 아는 접두사가 없으면 기본값으로 둔다.
    case_sql = " ".join(
        f"WHEN job_id LIKE '{prefix}-%' THEN '{source}'"
        for prefix, source in PREFIX_TO_SOURCE.items()
    )

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DROP VIEW IF EXISTS list_jobs_search")

        conn.execute(NEW_LIST_SEEN.format(default_source=default_source))
        conn.execute(
            "INSERT INTO list_seen_new (source_job_id, cat_mcls, seen_at, first_seen_at, source) "
            "SELECT source_job_id, cat_mcls, seen_at, first_seen_at, ? FROM list_seen",
            (default_source,),
        )
        conn.execute("DROP TABLE list_seen")
        conn.execute("ALTER TABLE list_seen_new RENAME TO list_seen")

        conn.execute(NEW_LIST_JOBS.format(default_source=default_source))
        conn.execute(
            "INSERT INTO list_jobs_new (source_job_id, job_id, source_url, company, title, "
            "keywords, region, career_type, min_career_years, education, employment_type, "
            "condition_text, seen_at, first_seen_at, deadline, support_text, source) "
            "SELECT source_job_id, job_id, source_url, company, title, "
            "keywords, region, career_type, min_career_years, education, employment_type, "
            "condition_text, seen_at, first_seen_at, deadline, support_text, "
            f"CASE {case_sql} ELSE ? END FROM list_jobs",
            (default_source,),
        )
        conn.execute("DROP TABLE list_jobs")
        conn.execute("ALTER TABLE list_jobs_new RENAME TO list_jobs")

        for statement in INDEXES:
            conn.execute(statement)
        conn.execute(NEW_VIEW)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    after = {
        table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("list_seen", "list_jobs")
    }
    for table, count in before.items():
        if after[table] != count:
            raise SystemExit(f"{table}: 행 수가 달라졌습니다 {count:,} → {after[table]:,}")
    return after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="실제로 바꾼다 (없으면 계획만 보여 준다)")
    parser.add_argument("--db", type=Path, default=DB_PATH, help=f"기본값: {DB_PATH}")
    parser.add_argument("--default-source", default=DEFAULT_SOURCE, help=f"기본값: {DEFAULT_SOURCE}")
    parser.add_argument("--no-backup", action="store_true", help="백업을 건너뛴다 (권하지 않음)")
    args = parser.parse_args()

    if not args.db.exists():
        raise SystemExit(f"저장소가 없습니다: {args.db}")

    conn = sqlite3.connect(args.db)
    try:
        if already_done(conn):
            print("이미 적용돼 있습니다. 할 일이 없습니다.")
            return 0

        counts = {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("list_seen", "list_jobs")
        }
        print(f"저장소: {args.db}  ({args.db.stat().st_size / 1e9:.2f} GB)")
        print(f"  list_seen  {counts['list_seen']:,}건  PK (source_job_id, cat_mcls)"
              f" → (source, source_job_id, cat_mcls)")
        print(f"  list_jobs  {counts['list_jobs']:,}건  PK (source_job_id)"
              f" → (source, source_job_id)")
        print(f"  옛 행의 출처: list_jobs는 job_id 접두사에서, list_seen은 '{args.default_source}'")

        if not args.apply:
            print("\n계획만 보였습니다. 실제로 바꾸려면 --apply 를 붙이세요.")
            return 0

        check_writable(conn)

        if not args.no_backup:
            print("\n백업 중…")
            path = backup(args.db)
            print(f"  {path}  ({path.stat().st_size / 1e9:.2f} GB)")

        print("\n표 재작성 중…")
        after = migrate(conn, args.default_source)

        problem = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if problem != "ok":
            raise SystemExit(f"무결성 확인 실패: {problem}")

        print(f"  list_seen  {after['list_seen']:,}건")
        print(f"  list_jobs  {after['list_jobs']:,}건")
        for source, count in conn.execute("SELECT source, COUNT(*) FROM list_jobs GROUP BY source"):
            print(f"    {source}: {count:,}")
        print("\n완료. 무결성 확인 ok.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
