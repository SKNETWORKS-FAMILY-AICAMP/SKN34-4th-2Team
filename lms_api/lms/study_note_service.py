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
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any, Callable

from django.db import connection, transaction
from django.utils import timezone

from lms.permissions import can_access_cohort
from lms.study_scope import SUBJECT_KEY, ScopeError, normalize_scope, same_material, scope_key

GENERATING_LOCK = timedelta(minutes=10)
TREE_TIMEOUT = 120
GENERATE_TIMEOUT = 600
RESOLVE_TIMEOUT = 30  # 저장소 동기화 + 트리 읽기. 처음 받는 저장소면 clone 이 든다
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


def _prefixes(raw: Any) -> list[str]:
    """허용 폴더. 운영 DB 는 jsonb 라 '[]' · '{}' · '["a"]' 글자로 오고, 예전 표(text[])는 '{a,b}'로 온다.

    예전에는 '{a,b}'만 알아서 '[]'를 「[]」라는 폴더 하나로 읽었다. 그러면 허용 폴더가 없는 것이 아니라
    아무 파일도 허용하지 않는 것이 되어, 자동으로 올라간 저장소는 날짜도 파일도 비어 보였다.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("["):
            try:
                raw = json.loads(text)
            except ValueError:
                raw = []
        else:
            raw = [p for p in text.strip("{}").split(",") if p]
    if not isinstance(raw, list):  # jsonb '{}' 가 사전으로 풀린 경우
        return []
    return [str(p).strip().strip('"') for p in raw if str(p).strip().strip('"')]


def _source_payload(source: dict) -> dict:
    prefixes = _prefixes(source.get("allowed_prefixes"))
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


def lesson_file(user: dict, source_key: str, path: str, commit: str) -> dict:
    """수업 파일 하나의 원문 — 노트의 「연습장에서 열기」. 내 기수 저장소만(관리자는 모두)."""
    with connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
    return _call(
        "/proxy/file",
        {"cohortId": source["cohort_code"], "source": _source_payload(source), "path": path, "commit": commit or ""},
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


def delete_note(user: dict, note_key: str) -> dict:
    """내 노트 지우기. 정리 중이던 노트면 뒤에서 도는 스레드가 끝나도 채울 행이 없어 그냥 끝난다.
    같은 범위를 다시 누르면 새로 만든다."""
    with connection.cursor() as cur:
        cur.execute(
            "DELETE FROM study_notes WHERE user_id = %s AND (legacy_id = %s OR id::text = %s) RETURNING id",
            [user["id"], note_key, note_key],
        )
        if not cur.fetchone():
            raise StudyNoteError(404, "노트를 찾을 수 없습니다.")
    return {"ok": True}


# ── 만들기 ────────────────────────────────────────────────────────


def _spawn(work: Callable[[], None]) -> None:
    """테스트가 바꿔 끼운다 — 스레드 없이 바로 돌리도록"""
    threading.Thread(target=work, name="study-note", daemon=True).start()


def _resolve(payload: dict) -> dict | None:
    """범위가 지금 어떤 파일(내용 해시)로 되어 있는지 — AI 서버가 LLM 없이 1~2초에 답한다.

    실패하면 None 이다. 그때는 예전처럼 학생 본인 노트만 보고, 없으면 새로 만든다(만드는 쪽이 이유를 남긴다).
    """
    try:
        return _call("/proxy/resolve", payload, RESOLVE_TIMEOUT)
    except Exception:  # noqa: BLE001 — 나눠 주기는 곁다리다. 안 되면 원래 흐름으로
        return None


def _shared_note(cur, source_id: int, key: str, files: Any, *, except_user: int | None = None) -> dict | None:
    """같은 저장소 · 같은 범위 · 같은 수업 자료로 누군가 이미 만든 노트. 같은 기수 학생이 나눠 본다."""
    cur.execute(
        """SELECT * FROM study_notes
           WHERE source_id = %s AND scope_key = %s AND status IN ('ready', 'done')
             AND COALESCE(report_markdown, '') <> '' AND user_id <> %s
           ORDER BY id DESC LIMIT 30""",
        [source_id, key, except_user if except_user is not None else -1],
    )
    return next((row for row in _dicts(cur) if same_material(row.get("files"), files)), None)


def _put(cur, row_id: int | None, user_id: int, source_id: int, scope_type: str, value: Any, key: str, *,
         status: str, message: str | None = None, report: str | None = None, review: str | None = None,
         files: Any = None, error: str | None = None) -> dict:
    """학생 한 명의 노트 행을 쓴다. 있으면 고치고 없으면 만든다. report · review · files 가 None 이면 그대로 둔다."""
    scope_json = json.dumps(value, ensure_ascii=False)
    files_json = None if files is None else json.dumps(files, ensure_ascii=False)
    if row_id is not None:
        cur.execute(
            """UPDATE study_notes SET status = %s, scope_value = %s::jsonb, message = %s, error_message = %s,
                      report_markdown = COALESCE(%s, report_markdown), review_markdown = COALESCE(%s, review_markdown),
                      files = COALESCE(%s::jsonb, files), created_at = now()
               WHERE id = %s RETURNING *""",
            [status, scope_json, message, error, report, review, files_json, row_id],
        )
    else:
        cur.execute(
            """INSERT INTO study_notes (user_id, source_id, status, scope_type, scope_value, scope_key, message,
                                        error_message, report_markdown, review_markdown, files, created_at)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, COALESCE(%s::jsonb, '[]'::jsonb), now()) RETURNING *""",
            [user_id, source_id, status, scope_type, scope_json, key, message, error, report, review, files_json],
        )
    return _one(cur)


def _own_note(cur, user_id: int, source_id: int, key: str) -> dict | None:
    # 같은 학생이 같은 범위를 두 번 눌러도 한 행만 — 표에 유일 키가 없어 트랜잭션 잠금으로 줄 세운다
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"study_note:{user_id}:{source_id}:{key}"])
    cur.execute(
        """SELECT * FROM study_notes WHERE user_id = %s AND source_id = %s AND scope_key = %s
           ORDER BY id DESC LIMIT 1""",
        [user_id, source_id, key],
    )
    return _one(cur)


def start_note(user: dict, source_key: str, scope_type: str, scope_value: Any) -> dict:
    """범위의 노트를 돌려준다. 있으면 그것, 같은 기수 학생이 같은 자료로 만든 것이 있으면 그 사본,
    정리 중이면 그 행, 아니면 「정리 중」 행을 만들고 뒤에서 만든다.

    노트는 수업 자료로 정해진다. 그래서 같은 저장소 · 같은 범위 · 같은 파일 내용이면 누가 만들었든 같은 노트다.
    한 학생이 만들면 나머지는 기다리지 않고 받는다(LLM 도 한 번). 수업 파일이 나중에 고쳐졌으면
    내 노트라도 다시 만든다 — 예전에는 한 번 만든 노트를 계속 보여 줬다.
    """
    try:
        value = normalize_scope(scope_type, scope_value)
    except ScopeError as exc:
        raise StudyNoteError(422, str(exc)) from exc
    if scope_type == "subject":
        return start_subject_note(user, source_key)
    key = scope_key(scope_type, value)

    with connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
    payload = {
        "cohortId": source["cohort_code"],
        "source": _source_payload(source),
        "scopeType": scope_type,
        "scopeValue": value,
    }
    # 트랜잭션 밖에서 — 저장소 동기화가 1~2초 걸린다
    current = _resolve(payload)
    fresh = current is not None and current.get("status") == "ready"
    public_source = _public_id(source)

    with transaction.atomic(), connection.cursor() as cur:
        row = _own_note(cur, user["id"], source["id"], key)
        row_id = row["id"] if row else None
        if row and row.get("status") in READY and not (fresh and not same_material(row.get("files"), current["files"])):
            return serialize(row, public_source)
        started = row.get("created_at") if row else None
        if row and row.get("status") == "generating" and started and timezone.now() - started < GENERATING_LOCK:
            return serialize(row, public_source)

        if current is not None and current.get("status") == "too_broad":
            # 파일이 너무 많다 — 만들어 볼 것도 없이 학생이 고르게 한다
            row = _put(cur, row_id, user["id"], source["id"], scope_type, value, key, status="too_broad",
                       message=str(current.get("message") or ""), files=current.get("files") or [])
            return serialize(row, public_source)
        if fresh:
            shared = _shared_note(cur, source["id"], key, current["files"], except_user=user["id"])
            if shared is not None:
                row = _put(cur, row_id, user["id"], source["id"], scope_type, value, key, status="ready",
                           message="", report=shared.get("report_markdown") or "", review="",
                           files=current["files"])
                return serialize(row, public_source)

        row = _put(cur, row_id, user["id"], source["id"], scope_type, value, key, status="generating",
                   message="정리 중입니다.")
        note_id = row["id"]
        transaction.on_commit(lambda: _spawn(lambda: _finish(note_id, payload)))
    return serialize(row, public_source)


def publish_lesson_notes(source: dict, dates: list[str]) -> dict:
    """자동 출제 뒤 — 그날 수업 노트를 한 번 만들어 기수 학생 모두의 공부방에 넣는다.

    복습 문제처럼 학생이 누르기 전에 준비해 둔다. 노트는 날짜마다 한 번만 만들고(같은 자료로 만든
    노트가 이미 있으면 그것을 쓴다) 학생마다 사본 행을 둔다. 목록 · 삭제가 학생 행 기준이기 때문이다.
    이미 같은 자료의 노트가 있는 학생은 건너뛴다. 파일이 너무 많은 날은 만들지 않는다(학생이 골라서 만든다).
    """
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id FROM users WHERE cohort_id = %s AND role = 'student' AND is_active ORDER BY id",
            [source["cohort_id"]],
        )
        students = [r[0] for r in cur.fetchall()]
    made: list[str] = []
    skipped: list[str] = []
    for date in dates:
        key = scope_key("date", date)
        payload = {"cohortId": source["cohort_code"], "source": _source_payload(source),
                   "scopeType": "date", "scopeValue": date}
        current = _resolve(payload)
        if current is None or current.get("status") != "ready":
            skipped.append(date)
            continue
        with connection.cursor() as cur:
            shared = _shared_note(cur, source["id"], key, current["files"])
        if shared is not None:
            report = shared.get("report_markdown") or ""
            files = current["files"]
        else:
            try:
                result = _call("/proxy/generate", payload, GENERATE_TIMEOUT)
            except StudyNoteError:
                skipped.append(date)
                continue
            if result.get("status") != "ready" or not result.get("reportMarkdown"):
                skipped.append(date)
                continue
            report = str(result["reportMarkdown"])
            files = result.get("files") or current["files"]
        for student in students:
            with transaction.atomic(), connection.cursor() as cur:
                row = _own_note(cur, student, source["id"], key)
                if row and row.get("status") in READY and same_material(row.get("files"), files):
                    continue
                _put(cur, row["id"] if row else None, student, source["id"], "date", date, key,
                     status="ready", message="", report=report, review="", files=files)
        made.append(date)
    return {"notes": made, "skipped": skipped, "students": len(students)}


# ── 과목 전체 요약 ────────────────────────────────────────────────
# 과목(수업 저장소) 하나를 한 장으로. 파일을 통째로 넣기엔 너무 많아서 날짜별 노트를 모아 한 번 더 정리한다.
# 날짜 노트가 없는 날은 먼저 만든다(같은 기수가 같은 자료로 만든 것이 있으면 그것). 그래서 처음엔 오래 걸린다.

SUBJECT_LOCK = timedelta(minutes=40)  # 날짜 노트를 여럿 만들 수 있어 날짜 노트(10분)보다 길게
SUBJECT_MAX_DAYS = 40
DAY_WORKERS = 3


def _subject_dates(row: dict | None) -> list[str] | None:
    """요약을 만들 때 쓴 수업 날짜들 — 끝난 요약 행의 scope_value 에 적어 둔다."""
    value = _json(row.get("scope_value")) if row else None
    return sorted(value) if isinstance(value, list) else None


def _lesson_dates(source: dict) -> list[str] | None:
    """저장소의 수업 날짜(오래된 순). 못 읽으면 None."""
    try:
        tree = _call("/proxy/tree", {"cohortId": source["cohort_code"], "source": _source_payload(source)}, TREE_TIMEOUT)
    except StudyNoteError:
        return None
    return sorted(tree.get("dates") or [])[-SUBJECT_MAX_DAYS:]


def start_subject_note(user: dict, source_key: str) -> dict:
    """과목 전체 요약. 있으면 그것, 같은 기수가 같은 수업 날짜로 만든 것이 있으면 사본, 아니면 뒤에서 만든다.

    수업 날짜가 늘었으면(새 수업) 다시 만든다. 날짜 안의 파일이 고쳐진 것까지는 보지 않는다 —
    그걸 보려면 날짜마다 저장소를 확인해야 해서 누를 때마다 수십 초가 걸린다.
    """
    with connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
    public_source = _public_id(source)
    dates = _lesson_dates(source)

    with transaction.atomic(), connection.cursor() as cur:
        row = _own_note(cur, user["id"], source["id"], SUBJECT_KEY)
        row_id = row["id"] if row else None
        if row and row.get("status") in READY and (dates is None or _subject_dates(row) == dates):
            return serialize(row, public_source)
        started = row.get("created_at") if row else None
        if row and row.get("status") == "generating" and started and timezone.now() - started < SUBJECT_LOCK:
            return serialize(row, public_source)
        if dates == []:
            row = _put(cur, row_id, user["id"], source["id"], "subject", "all", SUBJECT_KEY, status="failed",
                       error="이 저장소에는 아직 수업 날짜가 없어요.")
            return serialize(row, public_source)
        if dates:
            cur.execute(
                """SELECT * FROM study_notes WHERE source_id = %s AND scope_key = %s AND status IN ('ready', 'done')
                     AND COALESCE(report_markdown, '') <> '' AND user_id <> %s ORDER BY id DESC LIMIT 30""",
                [source["id"], SUBJECT_KEY, user["id"]],
            )
            shared = next((r for r in _dicts(cur) if _subject_dates(r) == dates), None)
            if shared is not None:
                row = _put(cur, row_id, user["id"], source["id"], "subject", dates, SUBJECT_KEY, status="ready",
                           message="", report=shared.get("report_markdown") or "", review="",
                           files=_json(shared.get("files")) or [])
                return serialize(row, public_source)

        row = _put(cur, row_id, user["id"], source["id"], "subject", "all", SUBJECT_KEY, status="generating",
                   message="과목 전체를 정리하고 있어요. 날짜별 노트가 없으면 먼저 만들어서 몇 분 넘게 걸려요.")
        note_id = row["id"]
        transaction.on_commit(lambda: _spawn(lambda: _finish_subject(note_id, user["id"], source, dates)))
    return serialize(row, public_source)


def _day_note(source: dict, date: str) -> tuple[dict | None, dict | None]:
    """(이미 있는 같은 자료의 날짜 노트, 새로 만들 때 넘길 payload). 둘 다 None 이면 그날은 뺀다(파일이 너무 많음 등)."""
    payload = {"cohortId": source["cohort_code"], "source": _source_payload(source), "scopeType": "date", "scopeValue": date}
    current = _resolve(payload)
    if current is None or current.get("status") != "ready":
        return None, None
    with connection.cursor() as cur:
        shared = _shared_note(cur, source["id"], scope_key("date", date), current["files"])
    if shared is not None:
        return {"report": shared.get("report_markdown") or "", "files": _json(shared.get("files")) or current["files"]}, None
    return None, payload


def _finish_subject(note_id: int, user_id: int, source: dict, dates: list[str] | None) -> None:
    """날짜 노트를 모으고(없으면 만들고) AI 서버에 과목 요약을 받는다. 스레드 안이라 DB 연결을 직접 닫는다."""
    try:
        dates = dates if dates is not None else _lesson_dates(source)
        if not dates:
            _save(note_id, "failed", error="수업 날짜를 읽지 못했습니다. 잠시 후 다시 시도하세요.")
            return
        days: dict[str, dict] = {}
        todo: dict[str, dict] = {}
        for date in dates:
            found, payload = _day_note(source, date)
            if found is not None:
                days[date] = found
            elif payload is not None:
                todo[date] = payload

        def make(date: str) -> tuple[str, dict | None]:
            try:
                result = _call("/proxy/generate", todo[date], GENERATE_TIMEOUT)
            except StudyNoteError:
                return date, None
            if result.get("status") != "ready" or not result.get("reportMarkdown"):
                return date, None
            return date, {"report": str(result["reportMarkdown"]), "files": result.get("files") or []}

        with ThreadPoolExecutor(max_workers=DAY_WORKERS) as pool:
            for date, made in pool.map(make, list(todo)):
                if made is None:
                    continue
                days[date] = made
                # 만든 날짜 노트는 이 학생의 날짜 노트로도 남긴다 — 다음에 그 날짜를 열면 기다리지 않는다
                key = scope_key("date", date)
                with transaction.atomic(), connection.cursor() as cur:
                    own = _own_note(cur, user_id, source["id"], key)
                    if not (own and own.get("status") in READY and same_material(own.get("files"), made["files"])):
                        _put(cur, own["id"] if own else None, user_id, source["id"], "date", date, key, status="ready",
                             message="", report=made["report"], review="", files=made["files"])
        if not days:
            _save(note_id, "failed", error="요약할 날짜 노트를 만들지 못했습니다. 날짜마다 파일이 너무 많거나 저장소를 읽지 못했어요.")
            return
        try:
            result = _call(
                "/proxy/subject",
                {"subject": source.get("title") or "과목", "days": [{"date": d, "report": days[d]["report"]} for d in sorted(days)]},
                GENERATE_TIMEOUT,
            )
        except StudyNoteError as exc:
            _save(note_id, "failed", error=exc.detail)
            return
        skipped = [d for d in dates if d not in days]
        files = [f for d in sorted(days) for f in days[d]["files"]]
        with connection.cursor() as cur:
            cur.execute(
                """UPDATE study_notes SET status = 'ready', scope_value = %s::jsonb, error_message = NULL, message = %s,
                          report_markdown = %s, review_markdown = '', files = %s::jsonb WHERE id = %s""",
                [json.dumps(dates), f"{len(skipped)}일은 파일이 너무 많거나 읽지 못해 빠졌어요." if skipped else "",
                 str(result.get("reportMarkdown") or ""), json.dumps(files, ensure_ascii=False), note_id],
            )
    except Exception as exc:  # noqa: BLE001 — 「정리 중」으로 남기지 않는다
        _save(note_id, "failed", error=f"과목 요약을 만들지 못했습니다: {str(exc)[:200]}")
    finally:
        connection.close()


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
