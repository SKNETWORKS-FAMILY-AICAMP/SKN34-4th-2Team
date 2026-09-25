"""Verify a jobs schema created by Django migrations; never create it here."""

from __future__ import annotations

import os

import psycopg
from psycopg.sql import SQL, Identifier


def main() -> int:
    url = os.environ["DATABASE_URL"]
    with psycopg.connect(url) as conn:
        required = ("jobs", "job_tags", "list_jobs", "list_seen", "list_sweeps", "link_checks", "runs", "list_jobs_search")
        missing = [
            name for name in required
            if conn.execute("SELECT to_regclass(%s)", (f"jobs.{name}",)).fetchone()[0] is None
        ]
        if missing:
            raise RuntimeError(f"jobs schema missing {missing}; run Django manage.py migrate first")
        print("jobs_schema=verified")
        for table in ("jobs", "job_tags", "list_jobs", "list_seen", "list_sweeps", "link_checks", "runs"):
            count = conn.execute(
                SQL("SELECT COUNT(*) FROM {}.{}").format(Identifier("jobs"), Identifier(table))
            ).fetchone()[0]
            print(f"{table}={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
