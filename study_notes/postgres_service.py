"""PostgreSQL-backed study-note operations for Django-authenticated AI calls.

The existing Git/LLM helpers remain in ``study_notes.service``. Only identity,
source lookup, note persistence, and generation ownership move from Firestore.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from chatbot.database import connect

LOCK_AGE = timedelta(minutes=10)


class StudyNotesError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _identity(user_pk: int, cohort_code: str) -> tuple[int, str]:
    with connect(row_factory=dict_row) as conn:
        row = conn.execute(
            """SELECT u.id, u.role, u.is_active, c.code AS cohort_code
               FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
               WHERE u.id = %s""",
            (user_pk,),
        ).fetchone()
    if not row or row["is_active"] is not True:
        raise StudyNotesError(403, "사용자 정보를 찾을 수 없거나 비활성 계정입니다.")
    if row["role"] != "admin" and row["cohort_code"] != cohort_code:
        raise StudyNotesError(403, "해당 기수에 접근할 수 없습니다.")
    return int(row["id"]), str(row["role"])


def _source(cohort_code: str, source_id: str):
    from study_notes.git_tools import GitToolError, parse_repo_url, sanitize_branch
    from study_notes.service import StudySource, _normalize_prefixes

    with connect(row_factory=dict_row) as conn:
        row = conn.execute(
            """SELECT s.id, s.legacy_id, s.title, s.repo_url, s.branch,
                      s.allowed_prefixes, s.is_active
               FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
               WHERE c.code = %s AND (s.legacy_id = %s OR CAST(s.id AS text) = %s)
               LIMIT 1""",
            (cohort_code, source_id, source_id),
        ).fetchone()
    if not row:
        raise StudyNotesError(404, "공부 소스를 찾을 수 없습니다.")
    if row["is_active"] is not True:
        raise StudyNotesError(409, "비활성 수업 저장소입니다.")
    try:
        repo_url = str(row["repo_url"] or "")
        parse_repo_url(repo_url)
        branch = sanitize_branch(str(row["branch"] or "main"))
    except GitToolError as exc:
        raise StudyNotesError(422, str(exc)) from exc
    return int(row["id"]), StudySource(
        id=str(row["legacy_id"] or row["id"]),
        title=str(row["title"] or ""),
        repo_url=repo_url,
        branch=branch,
        allowed_prefixes=_normalize_prefixes(row["allowed_prefixes"]),
    )


def _public_note(note_id: str, row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {"noteId": note_id, "status": "missing"}
    status = str(row["status"] or "missing")
    result: dict[str, Any] = {
        "noteId": note_id,
        "status": status,
        "sourceId": row.get("source_legacy_id") or str(row.get("source_id") or ""),
        "scopeType": row.get("scope_type"),
        "scopeValue": row.get("scope_value"),
        "errorMessage": row.get("error_message"),
    }
    if status == "ready":
        result.update({
            "reportMarkdown": row.get("report_markdown") or "",
            "reviewMarkdown": row.get("review_markdown") or "",
            "files": row.get("files") or [],
        })
    elif status == "generating":
        result["message"] = "이미 정리 중입니다. 잠시 후 다시 열어 주세요."
    elif status == "too_broad":
        result["message"] = row.get("message") or "파일을 선택하세요."
        result["files"] = row.get("files") or []
    return result


def _note_key(user_id: int, cohort_code: str, note_id: str) -> str:
    # Globally unique legacy_id without a new unique index. Firestore IDs can
    # still be read via the second lookup in get_note().
    return f"pg:{user_id}:{cohort_code}:{note_id}"


def _read_note(user_id: int, cohort_code: str, note_id: str) -> dict[str, Any] | None:
    with connect(row_factory=dict_row) as conn:
        return conn.execute(
            """SELECT n.*, s.legacy_id AS source_legacy_id
               FROM study_notes n JOIN study_sources s ON s.id = n.source_id
               JOIN cohorts c ON c.id = s.cohort_id
               WHERE n.user_id = %s AND c.code = %s AND n.legacy_id IN (%s, %s)
               ORDER BY CASE WHEN n.legacy_id = %s THEN 0 ELSE 1 END LIMIT 1""",
            (user_id, cohort_code, _note_key(user_id, cohort_code, note_id), note_id,
             _note_key(user_id, cohort_code, note_id)),
        ).fetchone()


def get_note(
    user_pk: int, cohort_code: str, *, note_id: str | None, source_id: str | None,
    scope_type: str | None, scope_value: Any,
) -> dict[str, Any]:
    from study_notes import service

    user_id, _role = _identity(user_pk, cohort_code)
    resolved = (note_id or "").strip()
    if not resolved and source_id and scope_type:
        kind = service.parse_scope_type(scope_type)
        resolved = service.build_note_id(source_id, kind, service.normalize_scope_value(kind, scope_value))
    if not resolved:
        raise StudyNotesError(422, "noteId 또는 sourceId+scope가 필요합니다.")
    return _public_note(resolved, _read_note(user_id, cohort_code, resolved))


def list_tree(user_pk: int, cohort_code: str, source_id: str) -> dict[str, Any]:
    from study_notes import service
    from study_notes.git_tools import GitToolError

    _identity(user_pk, cohort_code)
    _source_id, source = _source(cohort_code, source_id)
    cache = service.repo_cache(cohort_code, source)
    try:
        cache.sync()
        dates = cache.recent_lesson_dates(source.allowed_prefixes)
        entries = cache.list_tree(source.allowed_prefixes)
    except GitToolError as exc:
        raise StudyNotesError(502, str(exc)) from exc
    return {
        "dates": dates,
        "entries": [{"path": path, "type": "blob"} for path in entries],
        "truncated": False,
    }


def _claim(user_id: int, cohort_code: str, source_pk: int, note_id: str, kind: str, value: Any, scope_key: str):
    key = _note_key(user_id, cohort_code, note_id)
    token = uuid.uuid4().hex
    with connect(row_factory=dict_row) as conn:
        conn.execute(
            """INSERT INTO study_notes
               (legacy_id, user_id, source_id, status, scope_type, scope_value,
                scope_key, files, created_at, updated_at, generation_token)
               VALUES (%s, %s, %s, 'generating', %s, %s, %s, '[]'::jsonb,
                       now(), now(), %s)
               ON CONFLICT (legacy_id) DO NOTHING""",
            (key, user_id, source_pk, kind, Jsonb(value), scope_key, token),
        )
        row = conn.execute(
            "SELECT * FROM study_notes WHERE legacy_id = %s FOR UPDATE", (key,)
        ).fetchone()
        assert row is not None
        if row["generation_token"] == token:
            return "start", int(row["id"]), token, row
        if row["status"] == "ready":
            return "ready", int(row["id"]), "", row
        updated = row["updated_at"]
        if updated and updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if row["status"] == "generating" and updated and datetime.now(timezone.utc) - updated < LOCK_AGE:
            return "generating", int(row["id"]), "", row
        row = conn.execute(
            """UPDATE study_notes SET status = 'generating', scope_type = %s,
                      scope_value = %s, scope_key = %s, source_id = %s,
                      error_message = NULL, message = NULL, updated_at = now(),
                      generation_token = %s
               WHERE id = %s RETURNING *""",
            (kind, Jsonb(value), scope_key, source_pk, token, row["id"]),
        ).fetchone()
        return "start", int(row["id"]), token, row


def _finish(note_pk: int, token: str, status: str, **fields: Any) -> None:
    allowed = {"files", "report_markdown", "review_markdown", "error_message", "message"}
    if set(fields) - allowed:
        raise ValueError("unsupported note field")
    assignments = ["status = %s", "updated_at = now()", "generation_token = NULL"]
    values: list[Any] = [status]
    for name, value in fields.items():
        assignments.append(f"{name} = %s")
        values.append(Jsonb(value) if name == "files" else value)
    values.extend((note_pk, token))
    with connect() as conn:
        result = conn.execute(
            f"UPDATE study_notes SET {', '.join(assignments)} WHERE id = %s AND generation_token = %s",
            values,
        )
        if result.rowcount != 1:
            raise StudyNotesError(409, "노트 생성 소유권이 만료되었습니다.")


def generate_note(
    user_pk: int, cohort_code: str, source_id: str, scope_type: str, scope_value: Any,
) -> dict[str, Any]:
    from fastapi import HTTPException
    from study_notes import service
    from study_notes.git_tools import GitToolError

    user_id, _role = _identity(user_pk, cohort_code)
    source_pk, source = _source(cohort_code, source_id)
    kind = service.parse_scope_type(scope_type)
    value = service.normalize_scope_value(kind, scope_value)
    service.assert_scope_allowed(source, kind, value)
    scope_key = service.build_scope_key(kind, value)
    note_id = service.build_note_id(source.id, kind, value)
    state, note_pk, token, row = _claim(user_id, cohort_code, source_pk, note_id, kind, value, scope_key)
    if state != "start":
        row["source_legacy_id"] = source.id
        return _public_note(note_id, row)
    try:
        cache = service.repo_cache(cohort_code, source)
        commits, files, too_broad = service._collect(cache, source, kind, value)
        if too_broad:
            message = f"파일을 선택하세요. 한 번에 최대 {service.MAX_FILES}개까지 정리할 수 있습니다."
            _finish(note_pk, token, "too_broad", files=files, message=message)
            return {"noteId": note_id, "status": "too_broad", "message": message, "files": files}
        if not files:
            raise StudyNotesError(404, "이 범위에서 분석 가능한 .ipynb/.py/.md 파일이 없습니다.")
        materials = service._load_materials(cache, files)
        report, review = service.generate_study_note(
            scope_label=service.scope_label(kind, value), commits=commits, materials=materials,
        )
        _finish(note_pk, token, "ready", files=files, report_markdown=report,
                review_markdown=review, error_message=None, message=None)
        return {
            "noteId": note_id, "status": "ready", "sourceId": source.id,
            "scopeType": kind, "scopeValue": value,
            "reportMarkdown": report, "reviewMarkdown": review, "files": files,
        }
    except Exception as exc:
        detail = str(exc.detail) if isinstance(exc, (HTTPException, StudyNotesError)) else str(exc)[:200]
        _finish(note_pk, token, "failed", error_message=detail[:500])
        if isinstance(exc, (HTTPException, StudyNotesError)):
            raise
        code = 502 if isinstance(exc, GitToolError) else 500
        raise StudyNotesError(code, detail) from exc
