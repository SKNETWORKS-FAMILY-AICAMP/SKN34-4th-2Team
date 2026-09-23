"""Postgres(jobs 스키마)로 동작하는 공고 저장소.

클래스 이름 `SqliteJobStore`는 기존 호출·테스트를 깨지 않으려고 둔다.
같은 RDS의 `jobs` 스키마를 쓰고, 테스트는 경로마다 격리 스키마를 만든다.
공유 파일(`.sqlite`)이 있으면 그 내용을 읽기 전용으로 들여온다.

판정 규칙은 `job_store.reconcile`과 **같아야 한다.**
"""

from __future__ import annotations

from dataclasses import replace

import hashlib
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

import psycopg
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier
from psycopg.types.json import Jsonb

from job_matching_bot.config import now
from job_matching_bot.ingestion.job_store import (
    REQUIRED_FIELDS,
    _is_expired,
    keep_listing_fields,
    resolve_status,
)
from job_matching_bot.ingestion.company_name import clean_company_name, clean_listing_text
from job_matching_bot.ingestion.detail_quality import has_requirement_text
from job_matching_bot.retrieval.documents import embed_hash as _embed_hash
from job_matching_bot.schemas.job_posting import Job
from job_matching_bot.schemas.job_record import (
    DEFAULT_MISSING_RUN_LIMIT,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_REMOVED,
    CollectionReport,
    JobRecord,
)

JOB_FIELDS: tuple[str, ...] = tuple(Job.__dataclass_fields__)
_JSON_FIELDS = frozenset(
    {
        "required_skills", "preferred_skills", "tech_stack", "keywords",
        "required_majors", "required_major_terms", "required_certifications",
        "preferred_majors", "preferred_major_terms", "preferred_certifications",
        "required_certification_groups", "required_language_tests", "preferred_language_tests",
        "field_provenance",
    }
)
_BOOL_FIELDS = frozenset({"body_is_image", "military_required"})
_INT_FIELDS = frozenset({"min_career_years"})
LIFECYCLE_FIELDS: tuple[str, ...] = ("first_seen_at", "last_seen_at", "missing_runs", "revisions")
# status는 Job에도 있고 생애주기에도 있다. 저장소가 관리하므로 한 컬럼만 둔다.
_COLUMNS: tuple[str, ...] = JOB_FIELDS + LIFECYCLE_FIELDS
# job_tags로 풀어 두는 목록 필드. kind 이름은 필드명과 같다.
TAG_FIELDS: tuple[str, ...] = ("tech_stack", "required_skills", "preferred_skills", "keywords")

_JOBS_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "scripts" / "firestore_to_postgres" / "jobs_schema.sql"
_DEFAULT_STORE_NAMES = frozenset({"job_store.sqlite", "job_store.sqlite3", "job_store.db"})


def _encode(field: str, value: Any) -> Any:
    if field in _JSON_FIELDS:
        payload = value if value is not None else ({} if field == "field_provenance" else [])
        return Jsonb(payload)
    if field in _BOOL_FIELDS:
        return bool(value)
    return value


def _decode(field: str, value: Any) -> Any:
    if field in _JSON_FIELDS:
        if value is None:
            return {} if field == "field_provenance" else []
        if isinstance(value, str):
            return json.loads(value)
        return value
    if field in _BOOL_FIELDS:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        return bool(int(value))
    if field in _INT_FIELDS:
        return None if value is None else int(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _column_type(field: str) -> str:
    if field in _JSON_FIELDS:
        default = "'{}'" if field == "field_provenance" else "'[]'"
        return f"jsonb NOT NULL DEFAULT {default}::jsonb"
    if field in _BOOL_FIELDS:
        return "boolean NOT NULL DEFAULT false"
    if field in _INT_FIELDS:
        return "integer"
    return "varchar"


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


class _Row:
    def __init__(self, mapping: dict[str, Any]):
        self._d = {key: _cell(val) for key, val in mapping.items()}
        self._keys = list(self._d.keys())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._d[self._keys[key]]
        return self._d[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._d.get(key, default)

    def keys(self):
        return self._d.keys()

    def __iter__(self):
        return iter(self._d)

    def __contains__(self, key: object) -> bool:
        return key in self._d


class _Result:
    def __init__(self, rows: list[_Row], rowcount: int = -1):
        self._rows = rows
        self.rowcount = rowcount
        self._i = 0

    def fetchone(self) -> _Row | None:
        if self._i >= len(self._rows):
            return None
        row = self._rows[self._i]
        self._i += 1
        return row

    def fetchall(self) -> list[_Row]:
        rest = self._rows[self._i :]
        self._i = len(self._rows)
        return rest

    def __iter__(self):
        return iter(self._rows)


def _adapt_sql(sql: str) -> str:
    sql = sql.strip()
    upper = sql.upper()
    if upper.startswith("INSERT OR IGNORE"):
        sql = "INSERT" + sql[len("INSERT OR IGNORE") :]
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip(";") + " ON CONFLICT DO NOTHING"
    elif upper.startswith("INSERT OR REPLACE"):
        sql = "INSERT" + sql[len("INSERT OR REPLACE") :]
        if "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip(";") + (
                " ON CONFLICT (job_id) DO UPDATE SET "
                "checked_at = EXCLUDED.checked_at, alive = EXCLUDED.alive"
            )
    sql = re.sub(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)", r"%(\1)s", sql)
    return sql.replace("?", "%s")


class _PgConn:
    """기존 sqlite3 SQL(?, :name, INSERT OR IGNORE)을 psycopg로 돌린다."""

    def __init__(self, conn: psycopg.Connection):
        self._pg = conn
        self._tx = None

    def execute(self, sql: str, params: Any = None) -> _Result:
        adapted = _adapt_sql(sql)
        if params is None:
            cur = self._pg.execute(adapted)
        else:
            cur = self._pg.execute(adapted, params)
        rows = []
        if cur.description:
            for raw in cur.fetchall():
                rows.append(_Row(dict(raw)))
        return _Result(rows, cur.rowcount)

    def executemany(self, sql: str, seq: Iterable[Any]) -> _Result:
        adapted = _adapt_sql(sql)
        rows = list(seq)
        if not rows:
            return _Result([], 0)
        with self._pg.cursor() as cur:
            cur.executemany(adapted, rows)
            return _Result([], cur.rowcount)

    def executescript(self, script: str) -> None:
        for stmt in script.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._pg.execute(stmt)

    def commit(self) -> None:
        self._pg.commit()

    def close(self) -> None:
        self._pg.close()

    def __enter__(self) -> "_PgConn":
        self._tx = self._pg.transaction()
        self._tx.__enter__()
        return self

    def __exit__(self, *exc) -> Any:
        assert self._tx is not None
        result = self._tx.__exit__(*exc)
        self._tx = None
        return result


def _schema_for_path(path: Path) -> str:
    resolved = str(path.resolve())
    if path.name in _DEFAULT_STORE_NAMES:
        return "jobs"
    digest = hashlib.sha1(resolved.encode("utf-8")).hexdigest()[:16]
    return "j" + digest


def _sql_statements(script: str) -> list[str]:
    lines = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(line)
    statements = []
    for stmt in "\n".join(lines).split(";"):
        stmt = stmt.strip()
        if stmt:
            statements.append(stmt)
    return statements


def _looks_like_sqlite(path: Path) -> bool:
    if not path.exists() or path.stat().st_size < 100:
        return False
    with path.open("rb") as handle:
        return handle.read(16).startswith(b"SQLite format 3")


def _chunks(items: list[Any], size: int) -> Iterator[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _effective_image_flag(description: str | None, flagged: object) -> bool:
    """크롤러가 이미지라고 표시했어도 글에 요건이 있으면 이미지 공고가 아니다.

    읽기와 쓰기가 **같은 함수**를 거친다. 둘 중 한쪽만 뒤집으면 같은 행의 지문이
    쓸 때와 읽을 때 달라진다.
    """
    return bool(flagged) and not has_requirement_text(description or "")


# `jobs.job_id`는 `SARAMIN-54947118` 꼴이다. 목록 표도 같은 규칙을 써야 두 표를
# 오갈 수 있다. 접두사는 출처 이름에서 `_POC`를 뗀 것인데, 새 사이트가 그 규칙을
# 벗어나면 여기에 적는다.
_JOB_ID_PREFIX = {
    "SARAMIN_POC": "SARAMIN",
    "JOBKOREA_POC": "JOBKOREA",
}


def job_id_prefix(source: str) -> str:
    return _JOB_ID_PREFIX.get(source, source.removesuffix("_POC"))


class SqliteJobStore:
    """`JobStore`와 같은 겉모습. 실제 저장은 Postgres `jobs` 스키마(또는 테스트 격리 스키마)."""

    _IN_CHUNK = 400

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        url = os.environ.get("DATABASE_URL") or os.environ.get("JOBS_DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL 이 필요합니다 (jobs 스키마)")
        self.schema = _schema_for_path(self.path)
        raw = psycopg.connect(url, row_factory=dict_row, autocommit=False)
        try:
            if self.schema != "jobs":
                # Test stores use isolated schemas and may bootstrap them locally.
                raw.execute(SQL("CREATE SCHEMA IF NOT EXISTS {}").format(Identifier(self.schema)))
            raw.execute(SQL("SET search_path TO {}, public").format(Identifier(self.schema)))
            if self.schema != "jobs":
                for stmt in _sql_statements(_JOBS_SCHEMA_PATH.read_text(encoding="utf-8")):
                    raw.execute(stmt)
                raw.commit()
            self._pg = raw
            self.conn = _PgConn(raw)
            if self.schema == "jobs":
                self._verify_managed_schema()
            else:
                self._add_missing_columns()
        except Exception:
            raw.close()
            raise
        if _looks_like_sqlite(self.path):
            self._import_sqlite_file(self.path)

    def _verify_managed_schema(self) -> None:
        """Production schema comes from Django migrations, never crawler DDL."""
        required_tables = (
            "jobs", "job_tags", "runs", "list_seen", "link_checks",
            "list_jobs", "list_sweeps", "list_jobs_search",
        )
        missing_tables = [
            table for table in required_tables
            if self._pg.execute("SELECT to_regclass(%s)", (f"jobs.{table}",)).fetchone()["to_regclass"] is None
        ]
        required_columns = set(_COLUMNS) | {"embed_hash", "indexed_embed_hash", "indexed_at", "group_key"}
        missing_columns = required_columns - self._table_columns("jobs") if not missing_tables else set()
        if missing_tables or missing_columns:
            raise RuntimeError(
                "jobs schema가 Django migration과 일치하지 않습니다. "
                "manage.py migrate를 먼저 실행하세요. "
                f"missing tables/views={sorted(missing_tables)}, columns={sorted(missing_columns)}"
            )

    def _table_columns(self, table: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (table,),
        )
        return {row[0] for row in rows}

    def _add_missing_columns(self) -> None:
        """이미 만들어진 표에 뒤늦게 생긴 컬럼을 붙인다."""
        for table, column, kind in (
            ("list_seen", "first_seen_at", "timestamptz"),
            ("list_jobs", "deadline", "varchar"),
            ("list_jobs", "support_text", "varchar"),
            ("jobs", "group_key", "varchar"),
        ):
            if column not in self._table_columns(table):
                with self.conn:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

        have = self._table_columns("jobs")
        for column in _COLUMNS:
            if column in have:
                continue
            with self.conn:
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {_column_type(column)}")

        with self.conn:
            self.conn.execute("CREATE INDEX IF NOT EXISTS jobs_group ON jobs (group_key)")

    def _import_sqlite_file(self, path: Path) -> None:
        """공유로 받은 SQLite 파일을 Postgres 스키마로 들인다. 원본 파일은 그대로 둔다."""
        source = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        try:
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "jobs" not in tables:
                return
            if self.count() > 0:
                return
            self.conn.commit()
            columns = [row[1] for row in source.execute("PRAGMA table_info(jobs)")]
            with self.conn:
                for row in source.execute("SELECT * FROM jobs"):
                    values = {name: row[name] for name in columns if name in set(_COLUMNS) | {"embed_hash", "indexed_embed_hash", "indexed_at", "group_key"}}
                    for name in list(values):
                        if name in _JSON_FIELDS:
                            values[name] = _encode(name, json.loads(values[name]) if isinstance(values[name], str) else values[name])
                        elif name in _BOOL_FIELDS:
                            values[name] = _encode(name, values[name])
                    names = [name for name in values if values[name] is not None or name in ("missing_runs", "revisions")]
                    placeholders = ", ".join(f"%({name})s" for name in names)
                    self._pg.execute(
                        f"INSERT INTO jobs ({', '.join(names)}) VALUES ({placeholders}) ON CONFLICT (job_id) DO NOTHING",
                        {name: values[name] for name in names},
                    )
        finally:
            source.close()
            self.conn.commit()

    # ── 옛 호출 방식(load/save) 호환 ─────────────────────────────
    def load(self) -> "SqliteJobStore":
        return self

    def save(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ── 읽기 ──────────────────────────────────────────────────
    def _row_to_record(self, row: sqlite3.Row) -> JobRecord:
        job_fields = {name: _decode(name, row[name]) for name in JOB_FIELDS}
        # 구 사람인 수집본에 저장된 UI 버튼 문구도 읽는 즉시 보정한다.
        if str(job_fields.get("source", "")).startswith("SARAMIN"):
            from job_matching_bot.ingestion.company_name import clean_company_name

            job_fields["company"] = clean_company_name(job_fields.get("company"))
        # 구 버전은 상세 영역 안의 보조 이미지가 하나라도 있으면 image 플래그를
        # 남겼다. 실제 요구사항 텍스트가 저장돼 있으면 텍스트 공고로 복구한다.
        # 옛 행을 위해 읽을 때도 한 번 더 적용한다 — 쓰는 쪽과 같은 규칙이다.
        job_fields["body_is_image"] = _effective_image_flag(job_fields["description"], job_fields["body_is_image"])
        return JobRecord(
            job=Job(**job_fields),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            status=row["status"],
            missing_runs=row["missing_runs"],
            revisions=row["revisions"],
        )

    def get(self, job_id: str) -> JobRecord | None:
        row = self.conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return self._row_to_record(row) if row else None

    def iter_records(self, status: str | None = None) -> Iterator[JobRecord]:
        sql, params = "SELECT * FROM jobs", ()
        if status:
            sql, params = sql + " WHERE status = ?", (status,)
        for row in self.conn.execute(sql + " ORDER BY job_id", params):
            yield self._row_to_record(row)

    def __enter__(self) -> "SqliteJobStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def active_jobs(self) -> list[Job]:
        """추천 대상에 넣을 수 있는 공고. 만료·삭제된 공고는 뺀다."""
        return [record.job for record in self.iter_records(STATUS_OPEN)]

    def all_records(self) -> list[JobRecord]:
        return list(self.iter_records())

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])

    def stats(self) -> dict[str, Any]:
        by_status = {
            row["status"]: row["n"]
            for row in self.conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status")
        }
        return {"total": self.count(), "by_status": by_status}

    # ── 쓰기 ──────────────────────────────────────────────────
    def _write_record(self, record: JobRecord) -> None:
        job = record.job
        # 읽을 때 뒤집을 값이면 쓸 때 미리 뒤집는다. 쓴 지문과 읽은 지문이 같아야
        # 적재가 "바뀐 것 없음"을 믿을 수 있다. 읽을 때만 뒤집던 동안 4,316건의
        # 지문이 어긋나 바뀐 것이 없는데도 다시 올릴 대상으로 잡혔다.
        flag = _effective_image_flag(job.description, job.body_is_image)
        if flag != job.body_is_image:
            job = replace(job, body_is_image=flag)
        values = {name: _encode(name, getattr(job, name)) for name in JOB_FIELDS}
        values["status"] = record.status
        # 인덱스에 올라갈 내용의 지문. indexed_embed_hash는 여기서 건드리지 않는다 —
        # 마지막으로 올린 지문은 적재 단계(mark_indexed)만 바꾼다.
        values["embed_hash"] = _embed_hash(job)
        values.update(
            first_seen_at=record.first_seen_at,
            last_seen_at=record.last_seen_at,
            missing_runs=record.missing_runs,
            revisions=record.revisions,
        )
        columns = ", ".join(values)
        placeholders = ", ".join(f":{name}" for name in values)
        updates = ", ".join(f"{name} = excluded.{name}" for name in values if name != "job_id")
        self.conn.execute(
            f"INSERT INTO jobs ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(job_id) DO UPDATE SET {updates}",
            values,
        )
        self.conn.execute("DELETE FROM job_tags WHERE job_id = ?", (job.job_id,))
        rows = [
            (job.job_id, kind, str(value))
            for kind in TAG_FIELDS
            for value in (getattr(job, kind) or [])
            if str(value).strip()
        ]
        if rows:
            self.conn.executemany("INSERT OR IGNORE INTO job_tags (job_id, kind, value) VALUES (?, ?, ?)", rows)

    def put(self, record: JobRecord) -> None:
        """레코드 하나를 그대로 넣는다. 이관과 테스트용. 판정 없이 덮어쓴다."""
        self._write_record(record)

    def _existing_light(self, keys: list[tuple[str, str]]) -> dict[tuple[str, str], sqlite3.Row]:
        """collected 공고의 기존 행 중 판정에 필요한 컬럼만."""
        found: dict[tuple[str, str], sqlite3.Row] = {}
        for chunk in _chunks(keys, self._IN_CHUNK):
            marks = ", ".join("(?, ?)" for _ in chunk)
            params = [v for key in chunk for v in key]
            rows = self.conn.execute(
                "SELECT source, source_job_id, content_hash, first_seen_at, revisions, "
                "company, title, deadline "
                f"FROM jobs WHERE (source, source_job_id) IN (VALUES {marks})",
                params,
            )
            for row in rows:
                found[(row["source"], row["source_job_id"])] = row
        return found

    def _lifecycle(self, keys: list[tuple[str, str]]) -> dict[tuple[str, str], sqlite3.Row]:
        """`refresh`가 이어받을 값. `_existing_light`보다 생애주기 열을 더 가져온다."""
        found: dict[tuple[str, str], sqlite3.Row] = {}
        for chunk in _chunks(keys, self._IN_CHUNK):
            marks = ", ".join("(?, ?)" for _ in chunk)
            params = [v for key in chunk for v in key]
            rows = self.conn.execute(
                "SELECT source, source_job_id, content_hash, first_seen_at, last_seen_at, "
                "status, missing_runs, revisions, company, title, deadline "
                f"FROM jobs WHERE (source, source_job_id) IN (VALUES {marks})",
                params,
            )
            for row in rows:
                found[(row["source"], row["source_job_id"])] = row
        return found

    def refresh(self, collected: Iterable[Job], *, as_of: datetime | None = None) -> dict[str, list[str]]:
        """이미 저장된 공고를 **다시 파싱한 내용으로만** 덮어쓴다.

        `upsert`와 다른 점은 "이번에 안 보인 공고"를 세지 않는다는 것이다. 파서를
        고친 뒤 영향받은 몇백 건만 다시 받을 때 `upsert`를 쓰면, 이번 목록에 없는
        나머지 수만 건이 전부 "안 보임" 한 번으로 세여 결국 REMOVED로 넘어간다.
        다시 파싱하는 일은 크롤 한 바퀴가 아니므로 그 셈에 넣으면 안 된다.

        `first_seen_at`과 `revisions`는 이어받는다. 저장소에 없는 공고는 건너뛴다 —
        새 공고를 들이는 것은 `upsert`가 할 일이다.

        **상태와 미관측 횟수는 손대지 않는다.** 다시 파싱하는 것은 저장해 둔 글을
        다시 읽는 일이지, 그 공고가 아직 살아 있는지 확인하는 일이 아니다. 처음에는
        `resolve_status`로 다시 계산했는데, 그 판정이 9일 전에 고정된 기준 시각(옛 `config.AS_OF`)을 기준으로
        해서 만료·삭제된 공고 7,090건이 한꺼번에 OPEN으로 되살아났다. 살아 있는지는
        목록 관측과 링크 확인이 정하는 것이고, 여기서 알 수 있는 것이 아니다.
        """
        as_of = as_of or now()
        collected = list(collected)
        keys = [(job.source, job.source_job_id) for job in collected]
        existing = self._lifecycle(list(dict.fromkeys(keys)))
        result: dict[str, list[str]] = {"changed": [], "same": [], "unknown": []}
        with self.conn:
            for job in collected:
                previous = existing.get((job.source, job.source_job_id))
                if previous is None:
                    result["unknown"].append(job.job_id)
                    continue
                job = keep_listing_fields(job, previous["company"], previous["title"], previous["deadline"])
                changed = previous["content_hash"] != job.content_hash
                self._write_record(
                    JobRecord(
                        job=job,
                        first_seen_at=previous["first_seen_at"],
                        last_seen_at=previous["last_seen_at"],
                        status=previous["status"],
                        missing_runs=int(previous["missing_runs"]),
                        revisions=int(previous["revisions"]) + (1 if changed else 0),
                    )
                )
                result["changed" if changed else "same"].append(job.job_id)
        return result

    def upsert(
        self,
        collected: Iterable[Job],
        *,
        source: str,
        as_of: datetime | None = None,
        missing_run_limit: int = DEFAULT_MISSING_RUN_LIMIT,
        observed_ids: set[str] | None = None,
    ) -> CollectionReport:
        """`job_store.reconcile`과 같은 판정을 SQL 위에서 한다. 결과 리포트도 같은 모양."""
        as_of = as_of or now()
        collected = list(collected)
        report = CollectionReport(source=source, collected_at=as_of.isoformat())
        timestamp = as_of.isoformat()
        seen: set[tuple[str, str]] = set()

        # ① 이번에 받은 공고: 신규 / 갱신 / 변경 없음
        keys = [(job.source, job.source_job_id) for job in collected]
        existing = self._existing_light(list(dict.fromkeys(keys)))
        with self.conn:
            for job in collected:
                key = (job.source, job.source_job_id)
                seen.add(key)
                previous = existing.get(key)
                if previous is not None:
                    job = keep_listing_fields(job, previous["company"], previous["title"], previous["deadline"])
                status = resolve_status(job, as_of)
                missing = [name for name in REQUIRED_FIELDS if not getattr(job, name, None)]
                if missing:
                    report.missing_fields[job.job_id] = missing
                report.parser_versions[job.parser_version] = report.parser_versions.get(job.parser_version, 0) + 1

                if previous is None:
                    record = JobRecord(job=job, first_seen_at=timestamp, last_seen_at=timestamp, status=status)
                    report.new.append(job.job_id)
                else:
                    changed = previous["content_hash"] != job.content_hash
                    record = JobRecord(
                        job=job,
                        first_seen_at=previous["first_seen_at"],
                        last_seen_at=timestamp,
                        status=status,
                        missing_runs=0,
                        revisions=int(previous["revisions"]) + (1 if changed else 0),
                    )
                    (report.updated if changed else report.unchanged).append(job.job_id)
                self._write_record(record)
                # 같은 공고가 collected에 두 번 오면 두 번째는 '기존'으로 보이게 한다 (reconcile과 동일).
                existing[key] = {
                    "content_hash": job.content_hash,
                    "first_seen_at": record.first_seen_at,
                    "revisions": record.revisions,
                    "company": job.company,
                    "title": job.title,
                    "deadline": job.deadline,
                }

            # ② 이번에 안 보인 같은 소스의 공고: 만료 / 목록에서 봄 / 미관측 누적 / 삭제
            rows = self.conn.execute(
                "SELECT job_id, source_job_id, deadline, status, missing_runs FROM jobs WHERE source = ?",
                (source,),
            ).fetchall()
            seen_ids = {sid for (_, sid) in seen}
            expire: list[str] = []
            touch: list[tuple[str, str]] = []      # (status, job_id)
            bump: list[tuple[int, str, str]] = []   # (missing_runs, status, job_id)
            for row in rows:
                if row["source_job_id"] in seen_ids:
                    continue
                probe = Job.__new__(Job)
                probe.deadline = row["deadline"]
                if _is_expired(probe, as_of):
                    expire.append(row["job_id"])
                    report.expired.append(row["job_id"])
                    continue
                if observed_ids is not None and row["source_job_id"] in observed_ids:
                    new_status = STATUS_OPEN if row["status"] == STATUS_REMOVED else row["status"]
                    touch.append((new_status, row["job_id"]))
                    report.observed.append(row["job_id"])
                    continue
                runs = int(row["missing_runs"]) + 1
                if runs >= missing_run_limit:
                    bump.append((runs, STATUS_REMOVED, row["job_id"]))
                    report.removed.append(row["job_id"])
                else:
                    bump.append((runs, row["status"], row["job_id"]))
                    report.still_missing.append(row["job_id"])

            self.conn.executemany("UPDATE jobs SET status = 'EXPIRED' WHERE job_id = ?", [(j,) for j in expire])
            self.conn.executemany(
                "UPDATE jobs SET status = ?, last_seen_at = ?, missing_runs = 0 WHERE job_id = ?",
                [(s, timestamp, j) for (s, j) in touch],
            )
            self.conn.executemany(
                "UPDATE jobs SET missing_runs = ?, status = ? WHERE job_id = ?", bump
            )
        return report

    # ── 인덱스 추적 (적재 단계가 쓴다) ─────────────────────────
    # embed_hash         지금 내용으로 만든 지문(쓸 때마다 갱신)
    # indexed_embed_hash 마지막으로 인덱스에 올렸을 때의 지문
    # 둘이 다르면 올릴 대상, 같으면 건너뛴다. 인덱스를 조회하지 않고 판정한다.

    def index_state(self) -> dict[str, tuple[str | None, str | None]]:
        """{job_id: (embed_hash, indexed_embed_hash)}. 전 행."""
        return {
            row["job_id"]: (row["embed_hash"], row["indexed_embed_hash"])
            for row in self.conn.execute("SELECT job_id, embed_hash, indexed_embed_hash FROM jobs")
        }

    def mark_indexed(self, hashes: dict[str, str], at: datetime) -> None:
        """벡터를 올린 뒤 부른다. 바로 커밋해 중간에 멈춰도 올린 만큼은 기록이 남는다."""
        stamp = at.isoformat()
        with self.conn:
            self.conn.executemany(
                "UPDATE jobs SET embed_hash = ?, indexed_embed_hash = ?, indexed_at = ? WHERE job_id = ?",
                [(h, h, stamp, job_id) for job_id, h in hashes.items()],
            )

    def group_keys(self) -> dict[str, str | None]:
        """{job_id: group_key}. 어제와 견줘 오늘 새로 묶인 짝을 찾을 때 쓴다."""
        return {
            row["job_id"]: row["group_key"]
            for row in self.conn.execute("SELECT job_id, group_key FROM jobs")
        }

    def set_group_keys(self, keys: dict[str, str]) -> int:
        """묶음 표시를 적는다. 값이 그대로인 행은 건드리지 않는다."""
        current = self.group_keys()
        changed = [(key, job_id) for job_id, key in keys.items() if current.get(job_id) != key]
        with self.conn:
            self.conn.executemany("UPDATE jobs SET group_key = ? WHERE job_id = ?", changed)
        return len(changed)

    def clear_indexed(self, job_ids: Iterable[str]) -> None:
        with self.conn:
            self.conn.executemany(
                "UPDATE jobs SET indexed_embed_hash = NULL, indexed_at = NULL WHERE job_id = ?",
                [(j,) for j in job_ids],
            )

    def refresh_embed_hashes(self) -> int:
        """저장된 embed_hash를 다시 계산한다. 지문 규칙이 바뀌었거나 이관 직후처럼
        값이 비어 있을 때 한 번 돌린다. 바뀐 행 수를 돌려준다."""
        changed: list[tuple[str, str]] = []
        for row in self.conn.execute("SELECT * FROM jobs"):
            job = Job(**{name: _decode(name, row[name]) for name in JOB_FIELDS})
            fresh = _embed_hash(job)
            if fresh != row["embed_hash"]:
                changed.append((fresh, row["job_id"]))
        with self.conn:
            self.conn.executemany("UPDATE jobs SET embed_hash = ? WHERE job_id = ?", changed)
        return len(changed)

    # ── 목록 관측 기록 (야간 배치가 쓴다) ──────────────────────
    # 대분류마다 훑는 주기가 다르다(IT 인접 4개는 매일, 나머지는 일요일). 그래서
    # "오늘 목록에 없었다"만으로는 사라졌다고 할 수 없다. 여기 남긴 기록으로,
    # 나중에 끝까지 훑은 대분류에서 안 보인 공고만 사라진 것으로 친다.

    def waiting_since(self) -> dict[str, str]:
        """{공고 id: 목록에서 처음 본 시각}. 상세 큐 순서를 정할 때 쓴다.

        같은 공고가 여러 대분류에 걸리면 가장 이른 것을 쓴다. 옛 행은 값이 없어
        빠지는데, 부르는 쪽이 그런 공고를 **가장 오래 기다린 것**으로 본다.
        """
        return {
            row["source_job_id"]: row["first_seen"]
            for row in self.conn.execute(
                "SELECT source_job_id, MIN(first_seen_at) AS first_seen FROM list_seen "
                "WHERE first_seen_at IS NOT NULL GROUP BY source_job_id"
            )
        }

    def record_list_seen(
        self,
        seen: dict[str, set[str]],
        complete: dict[str, int],
        at: datetime,
        *,
        source: str,
        keep_days: int = 60,
    ) -> None:
        """seen: {대분류: 오늘 본 source_job_id}. complete: {끝까지 훑은 대분류: 사이트 total_count}.

        `source`는 기본값을 두지 않는다. 빠뜨리면 다른 사이트의 공고가 사람인으로
        기록되는데, 그건 조용히 틀리는 쪽이라 부를 때마다 적게 한다.
        """
        stamp = at.isoformat()
        with self.conn:
            self.conn.executemany(
                # seen_at은 갱신하고 first_seen_at은 처음 값을 지킨다. 상세를 아직
                # 못 받은 공고가 얼마나 기다렸는지 재는 근거가 된다.
                "INSERT INTO list_seen (source, source_job_id, cat_mcls, seen_at, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(source, source_job_id, cat_mcls) DO UPDATE SET seen_at = excluded.seen_at",
                [(source, job_id, cat, stamp, stamp) for cat, ids in seen.items() for job_id in ids],
            )
            self.conn.executemany(
                "INSERT INTO list_sweeps (cat_mcls, swept_at, total_count, seen) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(cat_mcls) DO UPDATE SET swept_at = excluded.swept_at, "
                "total_count = excluded.total_count, seen = excluded.seen",
                [(cat, stamp, total, len(seen.get(cat, ()))) for cat, total in complete.items()],
            )
            self.conn.execute(
                # 제 출처만 지운다. 사이트마다 수집 주기가 달라, 한쪽 배치가 다른
                # 쪽 관측을 지우면 그쪽 공고가 통째로 사라진 것처럼 보인다.
                "DELETE FROM list_seen WHERE source = ? AND seen_at < ?",
                (source, (at - timedelta(days=keep_days)).isoformat()),
            )

    def record_list_jobs(
        self,
        records: Iterable[dict[str, Any]],
        at: datetime,
        *,
        source: str,
        skip_categories: Iterable[str] = (),
        keep_days: int = 60,
    ) -> int:
        """목록 레코드를 `list_jobs`에 담는다. 챗봇 검색만 읽는 표다.

        `skip_categories`에는 **상세를 받는 대분류**를 준다. 그쪽 공고는 며칠 안에
        상세가 들어와 `jobs`에 자리를 잡으므로, 목록에 담아 봐야 곧 검색에서 제외될
        중복이 된다. 목록만으로 남는 것은 상세를 안 받기로 한 대분류뿐이다.

        같은 공고가 여러 대분류에 나온다. 그중 **하나라도** 상세를 받는 대분류면
        건너뛴다. 그 경로로 상세가 들어오기 때문이다.

        조건은 `listing_conditions`가 가른다 — 상세와 **같은 파서**를 쓰므로 두 표가
        섞여도 검색 결과가 어긋나지 않는다.

        `first_seen_at`은 처음 값을 지킨다. 목록에서 오래 기다린 공고를 재는 근거다.
        """
        from job_matching_bot.ingestion.listing_conditions import (
            conditions_from_listing,
            deadline_from_listing,
        )

        stamp = at.isoformat()
        records = list(records)
        skip = set(skip_categories)
        # 상세를 받는 대분류에 한 번이라도 나온 공고는 통째로 뺀다.
        detailed = {
            str(r.get("source_job_id") or "")
            for r in records
            if str(r.get("cat_mcls") or "") in skip
        } if skip else set()

        rows = []
        prefix = job_id_prefix(source)
        seen: set[str] = set()
        for record in records:
            job_id = str(record.get("source_job_id") or "")
            if not job_id or job_id in seen or job_id in detailed:
                continue
            seen.add(job_id)
            text = str(record.get("condition_text") or "")
            cond = conditions_from_listing(text)
            rows.append((
                source,
                job_id,
                f"{prefix}-{job_id}",
                str(record.get("source_url") or ""),
                clean_company_name(str(record.get("company") or "")),
                clean_listing_text(str(record.get("title") or "")),
                Jsonb(list(record.get("job_sectors") or [])),
                cond["region"],
                cond["career_type"],
                cond["min_career_years"],
                cond["education"],
                cond["employment_type"],
                text,
                deadline_from_listing(str(record.get("support_text") or ""), at.date()),
                str(record.get("support_text") or ""),
                stamp,
                stamp,
            ))
        with self.conn:
            self.conn.executemany(
                "INSERT INTO list_jobs (source, source_job_id, job_id, source_url, company, title, "
                "keywords, region, career_type, min_career_years, education, employment_type, "
                "condition_text, deadline, support_text, seen_at, first_seen_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source, source_job_id) DO UPDATE SET "
                "source_url = excluded.source_url, company = excluded.company, "
                "title = excluded.title, keywords = excluded.keywords, "
                "region = excluded.region, career_type = excluded.career_type, "
                "min_career_years = excluded.min_career_years, education = excluded.education, "
                "employment_type = excluded.employment_type, "
                "condition_text = excluded.condition_text, deadline = excluded.deadline, "
                "support_text = excluded.support_text, seen_at = excluded.seen_at",
                rows,
            )
            # 목록에서 사라진 지 오래된 것은 지운다. 상세를 받은 공고는 `jobs`에 있으니
            # 여기서 지워도 잃는 것이 없다.
            self.conn.execute(
                # 관측 표와 같은 이유로 제 출처만 지운다.
                "DELETE FROM list_jobs WHERE source = ? AND seen_at < ?",
                (source, (at - timedelta(days=keep_days)).isoformat()),
            )
        return len(rows)

    def get_listing(self, job_id: str) -> dict[str, Any] | None:
        """목록에서만 본 공고 한 건. 상세를 받았으면 `jobs`에 있으므로 None을 돌려준다.

        챗봇이 "2번 자격요건 알려줘"에 답하려다 `jobs`에서 못 찾았을 때 여기를 본다.
        찾으면 마감된 것이 아니라 **아직 상세를 안 받은 것**이므로, 그렇게 말하고
        원문 링크로 안내한다.
        """
        row = self.conn.execute(
            "SELECT * FROM list_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def source_job_ids(self, source: str, statuses: Iterable[str] | None = None) -> set[str]:
        sql, params = "SELECT source_job_id FROM jobs WHERE source = ?", [source]
        if statuses:
            statuses = list(statuses)
            sql += f" AND status IN ({', '.join('?' for _ in statuses)})"
            params.extend(statuses)
        return {row[0] for row in self.conn.execute(sql, params)}

    def list_observed(
        self, source: str, *, seen_today: set[str], as_of: datetime, within_days: int, authoritative: bool
    ) -> set[str]:
        """목록 기준으로 살아 있다고 볼 공고. `upsert(observed_ids=...)`에 넘긴다.

        - 오늘 본 것
        - `within_days` 안에 본 기록이 있고, 그 뒤로 그 대분류를 끝까지 훑은 적이 없는 것
          (끝까지 훑었는데 안 보였으면 그 기록은 근거가 아니다)
        - 기록이 전혀 없는 것 — 오늘 전 대분류를 끝까지 훑은 게 아니면(`authoritative=False`)
          모르는 것이지 사라진 게 아니므로 남긴다
        """
        observed = set(seen_today)
        candidates = self.source_job_ids(source) - observed
        if not candidates:
            return observed
        cutoff = (as_of - timedelta(days=within_days)).isoformat()
        swept = {row["cat_mcls"]: row["swept_at"] for row in self.conn.execute("SELECT cat_mcls, swept_at FROM list_sweeps")}
        evidence: dict[str, bool] = {}
        for row in self.conn.execute("SELECT source_job_id, cat_mcls, seen_at FROM list_seen"):
            job_id = row["source_job_id"]
            if job_id not in candidates:
                continue
            alive = row["seen_at"] >= cutoff and row["seen_at"] >= swept.get(row["cat_mcls"], "")
            evidence[job_id] = evidence.get(job_id, False) or alive
        for job_id in candidates:
            if job_id in evidence:
                if evidence[job_id]:
                    observed.add(job_id)
            elif not authoritative:
                observed.add(job_id)
        return observed

    def removal_candidates(self, source: str, observed: set[str], missing_run_limit: int = DEFAULT_MISSING_RUN_LIMIT) -> list[str]:
        """이번 upsert에서 REMOVED로 넘어갈 진행 중 공고. 링크 확인 대상이다."""
        rows = self.conn.execute(
            "SELECT source_job_id, missing_runs FROM jobs WHERE source = ? AND status = ?", (source, STATUS_OPEN)
        )
        return sorted(
            row["source_job_id"]
            for row in rows
            if row["source_job_id"] not in observed and int(row["missing_runs"]) + 1 >= missing_run_limit
        )

    # ── 링크 확인 기록 ────────────────────────────────────────
    def recent_link_checks(self, job_ids: Iterable[str], since: datetime) -> dict[str, bool]:
        """`since` 이후에 열어 본 공고 → 살아 있었나. 낮 확인이 같은 공고를 되풀이해 열지 않게."""
        ids = list(job_ids)
        if not ids:
            return {}
        placeholders = ", ".join("?" for _ in ids)
        rows = self.conn.execute(
            f"SELECT job_id, alive FROM link_checks WHERE checked_at >= ? AND job_id IN ({placeholders})",
            (since.isoformat(), *ids),
        )
        return {row["job_id"]: bool(row["alive"]) for row in rows}

    def record_link_checks(self, results: dict[str, bool], at: datetime) -> list[str]:
        """확인 결과를 남기고, 내려간 공고는 CLOSED로 넘긴다. 넘어간 job_id 목록을 돌려준다.

        OPEN인 것만 넘긴다. EXPIRED·REMOVED는 이미 인덱스 밖이라 건드릴 이유가 없다.
        """
        stamp = at.isoformat()
        closed = [job_id for job_id, alive in results.items() if not alive]
        with self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO link_checks (job_id, checked_at, alive) VALUES (?, ?, ?)",
                [(job_id, stamp, bool(alive)) for job_id, alive in results.items()],
            )
            if closed:
                placeholders = ", ".join("?" for _ in closed)
                rows = self.conn.execute(
                    f"SELECT job_id FROM jobs WHERE status = ? AND job_id IN ({placeholders})", (STATUS_OPEN, *closed)
                ).fetchall()
                moved = [row["job_id"] for row in rows]
                self.conn.executemany(
                    "UPDATE jobs SET status = ? WHERE job_id = ?", [(STATUS_CLOSED, job_id) for job_id in moved]
                )
                return moved
        return []

    # ── 실행 기록 ─────────────────────────────────────────────
    def record_run(self, report: CollectionReport, *, started_at: datetime, finished_at: datetime,
                   vectors: int | None = None, error: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO runs (started_at, finished_at, source, new, updated, unchanged, expired, removed, "
            "observed, still_missing, vectors, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                started_at.isoformat(), finished_at.isoformat(), report.source,
                len(report.new), len(report.updated), len(report.unchanged), len(report.expired),
                len(report.removed), len(report.observed), len(report.still_missing), vectors, error,
            ),
        )
        self.conn.commit()


def is_sqlite_path(path: Path) -> bool:
    return Path(path).suffix.lower() in (".sqlite", ".sqlite3", ".db")
