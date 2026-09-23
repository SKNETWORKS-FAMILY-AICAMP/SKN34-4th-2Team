"""공부방 노트 — 학생이 고른 범위(날짜·폴더·파일)로 AI 서버가 수업 저장소를 읽어 노트를 만든다.

원래(Flutter)는 앱이 AI 서버(study_notes/api.py)를 Firebase 토큰으로 바로 불렀고, AI 서버가 Firestore 에서
저장소를 읽고 노트도 Firestore 에 저장했다. 지금은 Django 가 JWT 로 학생을 확인하고, DB(study_sources)의
저장소 정보를 AI 서버의 /proxy/* 로 넘긴 뒤 결과를 study_notes 에 저장한다.

노트 하나에 몇 분 걸린다. gunicorn · nginx 는 120초에 끊으므로 요청은 곧바로 「정리 중」 행을 돌려주고,
같은 프로세스의 스레드가 AI 서버를 기다려 그 행을 채운다. 화면은 GET /study-notes/{id} 로 끝났는지 본다.
프로세스가 중간에 죽으면 행이 「정리 중」으로 남는데, 10분이 지나면 같은 범위를 다시 만들 수 있다(원래 잠금과 같다).
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import timedelta
from typing import Any, Callable

from django.db import connection, transaction
from django.utils import timezone

from lms.permissions import can_access_cohort
from lms.study_scope import ScopeError, normalize_scope, scope_key

GENERATING_LOCK = timedelta(minutes=10)
TREE_TIMEOUT = 120
GENERATE_TIMEOUT = 600
READY = ("ready", "done")


class StudyNoteError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _ai_base() -> str:
    """AI 서버 주소 — 챗봇 · 공고 추천과 같은 통합 서버다(배포에선 http://ai:8000)."""
    for key in ("STUDY_NOTES_URL", "JOBS_URL", "CHATBOT_URL"):
        value = (os.environ.get(key) or "").rstrip("/")
        if value:
            return value
    return ""


def _call(path: str, payload: dict, timeout: int) -> dict:
    base = _ai_base()
    if not base:
        raise StudyNoteError(503, "공부방 서버가 연결되어 있지 않습니다(STUDY_NOTES_URL).")
    req = urllib.request.Request(
        f"{base}/api/v1/study-notes{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        raise StudyNoteError(exc.code, str(detail or "공부방 서버가 노트를 만들지 못했습니다.")) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise StudyNoteError(503, "공부방 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.") from exc


def _dicts(cur) -> list[dict]:
    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(cur) -> dict | None:
    rows = _dicts(cur)
    return rows[0] if rows else None


# ── 저장소 ─────────────────────────────────────────────────────────


def _load_source(cur, user: dict, source_key: str) -> dict:
    """화면의 소스 id(legacy_id, 없으면 숫자 id)로 찾는다. 내 기수 것만(관리자는 모두)."""
    cur.execute(
        """SELECT s.*, c.code AS cohort_code FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
           WHERE s.legacy_id = %s OR s.id::text = %s
           ORDER BY (s.legacy_id = %s) DESC NULLS LAST LIMIT 1""",
        [source_key, source_key, source_key],
    )
    row = _one(cur)
    if not row:
        raise StudyNoteError(404, "공부 소스를 찾을 수 없습니다.")
    if not can_access_cohort(user, row["cohort_id"]):
        raise StudyNoteError(403, "해당 기수에 접근할 수 없습니다.")
    if row.get("is_active") is False:
        raise StudyNoteError(409, "비활성 수업 저장소입니다.")
    return row


def _public_id(source: dict) -> str:
    return str(source.get("legacy_id") or source["id"])


def _source_payload(source: dict) -> dict:
    prefixes = source.get("allowed_prefixes") or []
    if isinstance(prefixes, str):  # text[] 가 드라이버에 따라 '{a,b}' 문자열로 올 때
        prefixes = [p for p in prefixes.strip("{}").split(",") if p]
    return {
        "id": _public_id(source),
        "title": source.get("title") or "",
        "repoUrl": source.get("repo_url") or "",
        "branch": source.get("branch") or "main",
        "allowedPrefixes": list(prefixes),
    }


# ── 화면에 돌려줄 모양 — bootstrap 의 studyNotes 행과 같다 ──────────────


def _json(value: Any) -> Any:
    """Django 의 psycopg 설정은 jsonb 를 풀지 않고 JSON 글자로 준다(JSONField 가 직접 풀게)"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def serialize(row: dict, source_id: str) -> dict:
    created = row.get("created_at")
    return {
        "id": str(row.get("legacy_id") or row["id"]),
        "pk": row["id"],
        "sourceId": source_id,
        "status": row.get("status") or "",
        "scopeType": row.get("scope_type"),
        "scopeValue": _json(row.get("scope_value")),
        "scopeKey": row.get("scope_key"),
        "reportMarkdown": row.get("report_markdown") or "",
        "reviewMarkdown": row.get("review_markdown") or "",
        "errorMessage": row.get("error_message"),
        "message": row.get("message"),
        "files": _json(row.get("files")) or [],
        "createdAt": created.isoformat() if created else None,
    }


# ── 조회 ──────────────────────────────────────────────────────────


def source_tree(user: dict, source_key: str) -> dict:
    with connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
    return _call(
        "/proxy/tree",
        {"cohortId": source["cohort_code"], "source": _source_payload(source)},
        TREE_TIMEOUT,
    )


def get_note(user: dict, note_key: str) -> dict:
    with connection.cursor() as cur:
        cur.execute(
            """SELECT n.*, COALESCE(s.legacy_id, s.id::text) AS source_key
               FROM study_notes n LEFT JOIN study_sources s ON s.id = n.source_id
               WHERE n.user_id = %s AND (n.legacy_id = %s OR n.id::text = %s)""",
            [user["id"], note_key, note_key],
        )
        row = _one(cur)
    if not row:
        raise StudyNoteError(404, "노트를 찾을 수 없습니다.")
    return serialize(row, row.get("source_key") or "")


# ── 만들기 ────────────────────────────────────────────────────────


def _spawn(work: Callable[[], None]) -> None:
    """테스트가 바꿔 끼운다 — 스레드 없이 바로 돌리도록"""
    threading.Thread(target=work, name="study-note", daemon=True).start()


def start_note(user: dict, source_key: str, scope_type: str, scope_value: Any) -> dict:
    """같은 범위의 노트가 있으면 그것을, 정리 중이면 그 행을, 아니면 「정리 중」 행을 만들어 돌려준다."""
    try:
        value = normalize_scope(scope_type, scope_value)
    except ScopeError as exc:
        raise StudyNoteError(422, str(exc)) from exc
    key = scope_key(scope_type, value)

    with transaction.atomic(), connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
        # 같은 학생이 같은 범위를 두 번 눌러도 한 행만 — 표에 유일 키가 없어 트랜잭션 잠금으로 줄 세운다
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"study_note:{user['id']}:{source['id']}:{key}"])
        cur.execute(
            """SELECT * FROM study_notes WHERE user_id = %s AND source_id = %s AND scope_key = %s
               ORDER BY id DESC LIMIT 1""",
            [user["id"], source["id"], key],
        )
        row = _one(cur)
        public_source = _public_id(source)
        if row and row.get("status") in READY:
            return serialize(row, public_source)
        started = row.get("created_at") if row else None
        if row and row.get("status") == "generating" and started and timezone.now() - started < GENERATING_LOCK:
            return serialize(row, public_source)

        params = [json.dumps(value, ensure_ascii=False)]
        if row:
            cur.execute(
                """UPDATE study_notes SET status = 'generating', scope_value = %s::jsonb, message = '정리 중입니다.',
                          error_message = NULL, created_at = now()
                   WHERE id = %s RETURNING *""",
                [*params, row["id"]],
            )
        else:
            cur.execute(
                """INSERT INTO study_notes (user_id, source_id, status, scope_type, scope_value, scope_key, message, files, created_at)
                   VALUES (%s, %s, 'generating', %s, %s::jsonb, %s, '정리 중입니다.', '[]'::jsonb, now()) RETURNING *""",
                [user["id"], source["id"], scope_type, *params, key],
            )
        row = _one(cur)
        payload = {
            "cohortId": source["cohort_code"],
            "source": _source_payload(source),
            "scopeType": scope_type,
            "scopeValue": value,
        }
        note_id = row["id"]
        transaction.on_commit(lambda: _spawn(lambda: _finish(note_id, payload)))
    return serialize(row, public_source)


def _finish(note_id: int, payload: dict) -> None:
    """AI 서버를 기다려 행을 채운다. 스레드 안이라 DB 연결을 직접 닫는다."""
    try:
        try:
            result = _call("/proxy/generate", payload, GENERATE_TIMEOUT)
        except StudyNoteError as exc:
            _save(note_id, "failed", error=exc.detail)
            return
        except Exception as exc:  # noqa: BLE001 — 무엇이든 「정리 중」으로 남기지 않는다
            _save(note_id, "failed", error=f"노트를 만들지 못했습니다: {str(exc)[:200]}")
            return
        if result.get("status") == "too_broad":
            _save(note_id, "too_broad", message=str(result.get("message") or ""), files=result.get("files") or [])
        else:
            _save(
                note_id,
                "ready",
                report=str(result.get("reportMarkdown") or ""),
                review=str(result.get("reviewMarkdown") or ""),
                files=result.get("files") or [],
            )
    finally:
        connection.close()


def _save(note_id: int, status: str, *, error: str | None = None, message: str | None = None,
          report: str | None = None, review: str | None = None, files: list | None = None) -> None:
    with connection.cursor() as cur:
        cur.execute(
            """UPDATE study_notes SET status = %s, error_message = %s, message = %s,
                      report_markdown = COALESCE(%s, report_markdown), review_markdown = COALESCE(%s, review_markdown),
                      files = COALESCE(%s::jsonb, files)
               WHERE id = %s""",
            [status, (error or None) and error[:500], message, report, review,
             json.dumps(files, ensure_ascii=False) if files is not None else None, note_id],
        )
