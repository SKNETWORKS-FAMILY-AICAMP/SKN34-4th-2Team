"""SQLite로 동작하는 공고 저장소.

JSON 파일 저장소(`job_store.JobStore`)는 전량을 메모리에 올렸다 통째로 다시 쓴다.
11,493건에 68MB일 땐 문제가 없었지만, 전 카테고리 활성 공고 약 176,000건이면
1GB짜리 JSON을 매번 읽고 쓰게 되어 감당이 안 된다. 여기서는 바뀐 행만 갱신하고
`job_id` 하나만 꺼내 읽을 수 있다. 첨삭이 공고 원문을 조회할 때도 이 경로를 쓴다.

판정 규칙은 `job_store.reconcile`과 **같아야 한다.** 이 클래스는 그 규칙을 SQL 위에서
다시 구현한 것이라, 규칙을 고칠 때는 두 곳을 함께 고친다(`tests/test_sqlite_store.py`가
두 구현의 결과가 같은지 대조한다).

스키마
    jobs      공고 한 건 = 한 행. Job 필드 + 생애주기(status, first/last_seen, missing_runs,
              revisions) + 인덱스 추적(embed_hash, indexed_embed_hash, indexed_at)
    job_tags  목록형 값(기술 태그·카테고리 등)을 (job_id, kind, value)로 풀어 둔 것. 조회용
    runs      배치 실행 기록
    list_seen   목록 sweep에서 (공고, 대분류)를 마지막으로 본 시각. 사라짐 판정의 근거
    list_sweeps 대분류별로 마지막으로 끝까지 훑은 시각

목록·딕셔너리 필드는 JSON 문자열로 넣는다. SQLite는 타입이 느슨해 읽을 때
`_JSON_FIELDS` / `_BOOL_FIELDS` / `_INT_FIELDS`로 되돌린다.
"""

from __future__ import annotations

from dataclasses import replace

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator

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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    {job_columns},
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    missing_runs INTEGER NOT NULL DEFAULT 0,
    revisions INTEGER NOT NULL DEFAULT 0,
    embed_hash TEXT,
    indexed_embed_hash TEXT,
    indexed_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS jobs_source_key ON jobs(source, source_job_id);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_deadline ON jobs(deadline);
CREATE INDEX IF NOT EXISTS jobs_content_hash ON jobs(content_hash);
CREATE TABLE IF NOT EXISTS job_tags (
    job_id TEXT NOT NULL REFERENCES jobs(job_id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY (job_id, kind, value)
);
CREATE INDEX IF NOT EXISTS job_tags_kind_value ON job_tags(kind, value);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    source TEXT,
    new INTEGER, updated INTEGER, unchanged INTEGER,
    expired INTEGER, removed INTEGER, observed INTEGER, still_missing INTEGER,
    vectors INTEGER,
    error TEXT
);
CREATE TABLE IF NOT EXISTS list_seen (
    source_job_id TEXT NOT NULL,
    cat_mcls TEXT NOT NULL,
    seen_at TEXT NOT NULL,
    first_seen_at TEXT,
    source TEXT NOT NULL DEFAULT 'SARAMIN_POC',
    -- 번호는 사이트마다 따로 매긴다. 사람인 rec_idx도 8자리, 잡코리아 공고번호도
    -- 8자리라 출처를 키에 넣지 않으면 다른 공고가 같은 행을 덮어쓴다.
    PRIMARY KEY (source, source_job_id, cat_mcls)
);
CREATE INDEX IF NOT EXISTS list_seen_at ON list_seen(seen_at);
-- 키 앞자리가 source라 번호만으로 찾는 질의가 인덱스를 잃는다. 따로 둔다.
CREATE INDEX IF NOT EXISTS list_seen_job ON list_seen(source_job_id);
CREATE TABLE IF NOT EXISTS link_checks (
    job_id TEXT PRIMARY KEY,
    checked_at TEXT NOT NULL,
    alive INTEGER NOT NULL
);
-- 목록에서만 본 공고. **챗봇 검색만** 읽는다.
--
-- 상세를 받아야 `jobs`에 들어가므로 IT 밖 10개 대분류가 영영 0건이다. "서울 영업직
-- 있어?"에 없어서가 아니라 안 갖고 있어서 답을 못 한다. 조건은 목록에 이미 있고
-- `listing_conditions.py`가 가른다.
--
-- `jobs`와 따로 둔다. 같은 표에 두면 매주 일요일 목록 4만 건이 멀쩡한 상세 행을
-- 덮으려 들고, `jobs`를 읽는 모든 곳(추천·하드 필터·시장 통계·팀원 공유)이
-- "본문 없는 행"을 알아야 한다. 표를 나누면 그 위험이 아예 없다.
--
-- 열 이름을 `jobs`와 같게 둔다. 검색이 두 표를 같은 규칙으로 읽는다.
CREATE TABLE IF NOT EXISTS list_jobs (
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
    deadline TEXT,            -- 목록의 `~09.30` `오늘마감` 을 읽은 값. 모르면 NULL
    support_text TEXT,        -- 마감 표기 원문
    seen_at TEXT NOT NULL,
    first_seen_at TEXT,
    source TEXT NOT NULL DEFAULT 'SARAMIN_POC',
    PRIMARY KEY (source, source_job_id)
);
CREATE INDEX IF NOT EXISTS list_jobs_seen ON list_jobs(seen_at);
CREATE INDEX IF NOT EXISTS list_jobs_job ON list_jobs(source_job_id);
-- 조건 검색이 `jobs`에 쓰는 SQL을 그대로 쓰기 위한 뷰. 목록에는 없는 칸을 상수로
-- 채운다. 실제 값을 저장해 두면 늘 같은 값이 4만 줄 쌓이고, 나중에 "이게 진짜 값인가"
-- 헷갈린다. 뷰로 두면 없다는 것이 드러난다.
CREATE VIEW IF NOT EXISTS list_jobs_search AS
SELECT
    source_job_id, job_id, source_url, company, title, keywords,
    region, career_type, min_career_years, education, employment_type,
    'OPEN'  AS status,        -- 목록에 보이면 열려 있는 것으로 본다
    deadline,                 -- `~09.30` `오늘마감` 을 읽은 값. 못 읽으면 NULL
    '[]'    AS tech_stack,    -- 기술 태그는 상세에서만 나온다
    ''      AS description,   -- 본문 없음. 이것이 상세 미수집의 표시다
    seen_at, first_seen_at, source
FROM list_jobs;
CREATE TABLE IF NOT EXISTS list_sweeps (
    cat_mcls TEXT PRIMARY KEY,
    swept_at TEXT NOT NULL,
    total_count INTEGER,
    seen INTEGER
);
"""


def _encode(field: str, value: Any) -> Any:
    if field in _JSON_FIELDS:
        return json.dumps(value if value is not None else ([] if field != "field_provenance" else {}), ensure_ascii=False)
    if field in _BOOL_FIELDS:
        return 1 if value else 0
    return value


def _decode(field: str, value: Any) -> Any:
    if field in _JSON_FIELDS:
        if value is None:
            return {} if field == "field_provenance" else []
        return json.loads(value)
    if field in _BOOL_FIELDS:
        # 컬럼은 INTEGER지만, 혹시 문자열 '0'이 오더라도 True로 읽히면 안 된다.
        return bool(int(value)) if value is not None else False
    if field in _INT_FIELDS:
        return None if value is None else int(value)
    return value


def _column_type(field: str) -> str:
    if field in _BOOL_FIELDS or field in _INT_FIELDS:
        return "INTEGER"
    return "TEXT"


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
    """`JobStore`와 같은 겉모습(`load` / `save` / `upsert` / `active_jobs` / `stats`)을 가진 SQLite 저장소."""

    # SQLite 변수 한도(999) 안에서 IN 절을 쪼개는 크기.
    _IN_CHUNK = 400

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        job_columns = ",\n    ".join(f"{name} {_column_type(name)}" for name in JOB_FIELDS if name != "job_id")
        self.conn.executescript(_SCHEMA.format(job_columns=job_columns))
        self._add_missing_columns()

    def _add_missing_columns(self) -> None:
        """이미 만들어진 표에 뒤늦게 생긴 컬럼을 붙인다.

        `CREATE TABLE IF NOT EXISTS`는 표가 있으면 아무것도 하지 않아서, 컬럼만
        늘리면 기존 저장소에는 반영되지 않는다. 값이 없는 옛 행은 NULL로 남는다.
        """
        for table, column, kind in (
            ("list_seen", "first_seen_at", "TEXT"),
            ("list_jobs", "deadline", "TEXT"),
            ("list_jobs", "support_text", "TEXT"),
        ):
            have = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                with self.conn:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

        # `Job`에 필드를 더하면 여기서 저절로 따라온다. 옛 행은 NULL로 남고 읽을 때
        # 빈 값이 된다. 24,762건을 다시 만들지 않아도 새 필드를 쓸 수 있다.
        have = {row[1] for row in self.conn.execute("PRAGMA table_info(jobs)")}
        for column in _COLUMNS:
            if column in have:
                continue
            with self.conn:
                self.conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")

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
                json.dumps(list(record.get("job_sectors") or []), ensure_ascii=False),
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
                [(job_id, stamp, int(alive)) for job_id, alive in results.items()],
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
