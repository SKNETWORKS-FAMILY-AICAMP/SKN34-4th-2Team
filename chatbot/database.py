"""AI service PostgreSQL connection using the same DB_* priority as Django."""

from __future__ import annotations

import os

import psycopg


def connect_params(*, fallback_url: str | None = None, use_db_host: bool = True) -> tuple[str, dict]:
    """(conninfo, keyword arguments) for psycopg.connect — shared by direct and pooled connections."""
    host = os.environ.get("DB_HOST") if use_db_host else None
    if host:
        missing = [name for name in ("DB_NAME", "DB_USER", "DB_PASSWORD") if not os.environ.get(name)]
        if missing:
            raise RuntimeError(f"DB_HOST is set but DB settings are missing: {', '.join(missing)}")
        return "", dict(
            host=host,
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            sslmode=os.environ.get("DB_SSLMODE", "require"),
        )
    url = os.environ.get("DATABASE_URL") or fallback_url
    if not url:
        raise RuntimeError("DB_HOST or DATABASE_URL is required for the AI service")
    return url, {}


def connect(*, fallback_url: str | None = None, use_db_host: bool = True, **kwargs):
    conninfo, params = connect_params(fallback_url=fallback_url, use_db_host=use_db_host)
    return psycopg.connect(conninfo, **params, **kwargs)
