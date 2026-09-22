"""Create the lms database if it does not exist. Reads DATABASE_URL."""

from __future__ import annotations

import os
from urllib.parse import urlparse, urlunparse

import psycopg


def admin_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path="/postgres"))


def main() -> None:
    url = os.environ["DATABASE_URL"]
    parsed = urlparse(url)
    dbname = (parsed.path or "/lms").lstrip("/") or "lms"
    with psycopg.connect(admin_url(url), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                print(f"database exists: {dbname}")
                return
            cur.execute(f'CREATE DATABASE "{dbname}"')
            print(f"database created: {dbname}")


if __name__ == "__main__":
    main()
