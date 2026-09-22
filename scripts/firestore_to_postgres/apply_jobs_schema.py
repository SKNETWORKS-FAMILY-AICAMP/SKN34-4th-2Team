"""Create the jobs schema on an existing lms database. Does not DROP public."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from psycopg.sql import SQL, Identifier

ROOT = Path(__file__).resolve().parent
SCHEMA = ROOT / "jobs_schema.sql"


def statements(script: str) -> list[str]:
    lines = [line for line in script.splitlines() if line.strip() and not line.strip().startswith("--")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def main() -> int:
    url = os.environ["DATABASE_URL"]
    sql = SCHEMA.read_text(encoding="utf-8")
    with psycopg.connect(url) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS jobs")
        conn.execute("SET search_path TO jobs")
        for stmt in statements(sql):
            conn.execute(stmt)
        conn.commit()
        print("jobs_schema=ok")
        for table in ("jobs", "job_tags", "list_jobs", "list_seen", "list_sweeps", "link_checks", "runs"):
            count = conn.execute(
                SQL("SELECT COUNT(*) FROM {}.{}").format(Identifier("jobs"), Identifier(table))
            ).fetchone()[0]
            print(f"{table}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
