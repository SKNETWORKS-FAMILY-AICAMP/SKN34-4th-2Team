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
import re
import threading
import urllib.error
import urllib.request
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
    """AI 서버 호출. 폴더 올리기 과목이면 먼저 서버 안 저장소가 있는지 보고 없으면 보관본으로 되살린다(lms/folder_upload.py)."""
    source = payload.get("source")
    if isinstance(source, dict) and str(source.get("repoUrl") or "").startswith("upload://") and payload.get("cohortId"):
        from lms.folder_upload import ensure_repo

        ensure_repo(str(payload["cohortId"]), source)
    return _post(path, payload, timeout)


def _post(path: str, payload: dict, timeout: int) -> dict:
    base = _ai_base()
    if not base:
        raise StudyNoteError(503, "공부방 서버가 연결되어 있지 않습니다(STUDY_NOTES_URL).")
    req = urllib.request.Request(
        f"{base}/api/v1/study-notes{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        # 두 EC2 로 나뉘면 AI 서버가 이 값으로 Django 를 알아본다(웹 채점은 검사문을 실행하므로 확인한다 — study_notes/api.py)
        headers={"Content-Type": "application/json", "X-LMS-AI-Token": os.environ.get("LMS_AI_SHARED_TOKEN") or ""},
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


PREVIOUS_DAYS = 3


def _previous_notes(source_id: int, scope_type: str, value: Any) -> list[dict]:
    """같은 과목의 이전 수업 날짜 노트(최근 PREVIOUS_DAYS 일, 날짜마다 가장 새것) — AI 서버가 「이전 학습과의 연결」을
    이것과만 잇는다. 없으면 이어 쓸 수업이 없다고 적는다(첫날에도 「이전에 배웠다」고 지어내던 것). 날짜 노트만."""
    if scope_type != "date":
        return []
    with connection.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (scope_value #>> '{}') scope_value #>> '{}' AS date, report_markdown
               FROM study_notes
               WHERE source_id = %s AND scope_type = 'date' AND status IN ('ready', 'done')
                 AND COALESCE(report_markdown, '') <> '' AND scope_value #>> '{}' < %s
               ORDER BY scope_value #>> '{}' DESC, id DESC""",
            [source_id, str(value)],
        )
        rows = _dicts(cur)
    return [{"date": r["date"], "report": r["report_markdown"]} for r in rows[:PREVIOUS_DAYS]]


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
        generate = {**payload, "previous": _previous_notes(source["id"], scope_type, value)}
        transaction.on_commit(lambda: _spawn(lambda: _finish(note_id, generate)))
    return serialize(row, public_source)


def publish_lesson_notes(source: dict, dates: list[str]) -> dict:
    """자동 출제 뒤 — 그날 수업 노트를 한 번 만들어 기수 학생 모두의 공부방에 넣는다.

    복습 문제처럼 학생이 누르기 전에 준비해 둔다. 노트는 날짜마다 한 번만 만들고(같은 자료로 만든
    노트가 이미 있으면 그것을 쓴다) 학생마다 사본 행을 둔다. 목록 · 삭제가 학생 행 기준이기 때문이다.
    이미 같은 자료의 노트가 있는 학생은 건너뛴다. 파일이 너무 많은 날은 AI 서버가 묶음으로 나눠 만든다
    (study_notes/pipeline.py). 그래도 넘치면(MAX_DATE_FILES) 만들지 않는다.
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
                result = _call("/proxy/generate", {**payload, "previous": _previous_notes(source["id"], "date", date)},
                               GENERATE_TIMEOUT)
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
# 과목(수업 저장소) 하나를 한 장으로 — AI 서버가 수업 파일을 직접 읽어 주제(맨 위 폴더)별로 정리한다(study_notes/subject.py).
# 예전엔 날짜 노트를 모아 다시 요약했는데, 날짜 노트가 6천 자에서 잘리고 없으면 먼저 만들어야 했다(2026-10-04 바꿈).
# 과목이 끝나면 18:30 자동 출제 뒤에 한 번 만들어 기수 학생 모두에게 넣는다(publish_subject_note).

SUBJECT_LOCK = timedelta(minutes=40)  # 주제 묶음이 많은 과목은 몇 분 걸린다
SUBJECT_MAX_DAYS = 40
SUBJECT_TIMEOUT = 1200
# 파일 직접 · 주제별로 만든 요약에만 있는 소제목 — 예전 방식(날짜 노트를 모아 다시 요약) 요약은 다시 만든다
SUBJECT_FORMAT_MARK = "## 주제별 핵심 정리"


def _subject_dates(row: dict | None) -> list[str] | None:
    """요약을 만들 때 쓴 수업 날짜들 — 끝난 요약 행의 scope_value 에 적어 둔다."""
    value = _json(row.get("scope_value")) if row else None
    return sorted(value) if isinstance(value, list) else None


def _current_subject(row: dict | None, dates: list[str] | None) -> bool:
    """지금 쓸 수 있는 과목 요약인가 — 다 만들어졌고, 새 형식이고, 수업 날짜가 그대로(새 수업이 없음)"""
    return bool(
        row and row.get("status") in READY and SUBJECT_FORMAT_MARK in (row.get("report_markdown") or "")
        and (dates is None or _subject_dates(row) == dates)
    )


def _lesson_dates(source: dict) -> list[str] | None:
    """저장소의 수업 날짜(오래된 순). 못 읽으면 None."""
    try:
        tree = _call("/proxy/tree", {"cohortId": source["cohort_code"], "source": _source_payload(source)}, TREE_TIMEOUT)
    except StudyNoteError:
        return None
    return sorted(tree.get("dates") or [])[-SUBJECT_MAX_DAYS:]


SUBJECT_NOT_FINISHED = "과목이 끝나면 전체 요약을 만들 수 있어요. 다음 과목 수업이 시작되면 열려요."


def _repo_title(repo_url: str) -> str:
    """세트의 과목 이름(practice_sets.source_title) — 저장소 이름 소문자(practice_auto._repo_name 과 같은 값).
    study_source_service._repo_key 를 쓰면 서로 불러와 순환이 된다."""
    return re.sub(r"\.git$", "", repo_url.strip().rstrip("/")).lower().rsplit("/", 1)[-1]


def subject_finished(cur, source: dict, dates: list[str] | None = None) -> bool:
    """과목이 끝났는지 — 과목 전체 요약은 끝난 과목만 만든다(화면 lessonDays.subjectFinished 와 같은 규칙).

    같은 기수의 다른 과목이 이 과목 마지막 수업 **뒤에 처음 시작했으면**(다음 과목이 시작됨), 또는 기수 수료일이
    지났으면 끝난 것. 다른 과목에 늦은 수업이 「있기만」 한 것으로 보면 번갈아 하는 두 과목이 서로 끝난 걸로 보여서
    첫 수업일로 견준다. 수업 날짜는 복습 세트(자동 출제가 날마다 만든다)와 저장소 날짜(dates)를 함께 본다.
    """
    title = _repo_title(source.get("repo_url") or "")
    cur.execute(
        "SELECT max(lesson_date)::text FROM practice_sets WHERE cohort_id = %s AND origin = 'lesson' AND lower(source_title) = %s",
        [source["cohort_id"], title],
    )
    last = max([d for d in [cur.fetchone()[0], *(dates or [])] if d] or [""])
    if not last:
        return False
    cur.execute("SELECT end_date FROM cohorts WHERE id = %s", [source["cohort_id"]])
    row = cur.fetchone()
    if row and row[0] and row[0] < timezone.localdate():
        return True
    cur.execute(
        """SELECT 1 FROM practice_sets WHERE cohort_id = %s AND origin = 'lesson' AND lower(source_title) <> %s
           GROUP BY lower(source_title) HAVING min(lesson_date) > %s LIMIT 1""",
        [source["cohort_id"], title, last],
    )
    return cur.fetchone() is not None


def _shared_subject(cur, source_id: int, dates: list[str] | None, except_user: int | None = None) -> dict | None:
    """같은 기수가 같은 수업 날짜로 이미 만든 새 형식 과목 요약"""
    cur.execute(
        """SELECT * FROM study_notes WHERE source_id = %s AND scope_key = %s AND status IN ('ready', 'done')
             AND COALESCE(report_markdown, '') <> '' AND user_id <> %s ORDER BY id DESC LIMIT 30""",
        [source_id, SUBJECT_KEY, except_user or 0],
    )
    return next((r for r in _dicts(cur) if _current_subject(r, dates)), None)


def start_subject_note(user: dict, source_key: str) -> dict:
    """과목 전체 요약 — 수업 파일을 직접 읽어 주제(맨 위 폴더)별로(AI 서버 study_notes/subject.py).
    있으면 그것, 같은 기수가 같은 수업 날짜로 만든 것이 있으면 사본, 아니면 뒤에서 만든다.

    끝난 과목만(subject_finished) — 진행 중인 과목은 409. 반쯤 배운 상태의 「전체」 요약은 헷갈리게 하고,
    수업이 늘 때마다 다시 만들어 비용만 든다. 수업 날짜가 아예 없는 과목(폴더로 올린 지난 자료뿐)은 파일만으로 만든다.
    수업 날짜가 늘었으면(새 수업) 다시 만든다.
    """
    with connection.cursor() as cur:
        source = _load_source(cur, user, source_key)
    public_source = _public_id(source)
    dates = _lesson_dates(source)
    if dates:
        with connection.cursor() as cur:
            if not subject_finished(cur, source, dates):
                raise StudyNoteError(409, SUBJECT_NOT_FINISHED)

    with transaction.atomic(), connection.cursor() as cur:
        row = _own_note(cur, user["id"], source["id"], SUBJECT_KEY)
        row_id = row["id"] if row else None
        if _current_subject(row, dates):
            return serialize(row, public_source)
        started = row.get("created_at") if row else None
        if row and row.get("status") == "generating" and started and timezone.now() - started < SUBJECT_LOCK:
            return serialize(row, public_source)
        shared = _shared_subject(cur, source["id"], dates, except_user=user["id"]) if dates else None
        if shared is not None:
            row = _put(cur, row_id, user["id"], source["id"], "subject", dates, SUBJECT_KEY, status="ready",
                       message="", report=shared.get("report_markdown") or "", review="",
                       files=_json(shared.get("files")) or [])
            return serialize(row, public_source)
        row = _put(cur, row_id, user["id"], source["id"], "subject", "all", SUBJECT_KEY, status="generating",
                   message="과목의 수업 파일을 모두 읽어 주제별로 정리하고 있어요. 몇 분 걸려요.")
        note_id = row["id"]
        transaction.on_commit(lambda: _spawn(lambda: _finish_subject(note_id, source)))
    return serialize(row, public_source)


def _subject_from_files(source: dict) -> dict:
    """AI 서버가 수업 파일을 직접 읽어 만든 과목 요약 {status, reportMarkdown, dates, files} — 몇 분 걸린다"""
    return _call("/proxy/subject-files", {"cohortId": source["cohort_code"], "source": _source_payload(source)}, SUBJECT_TIMEOUT)


def _finish_subject(note_id: int, source: dict) -> None:
    """AI 서버에 과목 요약을 받아 행을 채운다. 스레드 안이라 DB 연결을 직접 닫는다."""
    try:
        try:
            result = _subject_from_files(source)
        except StudyNoteError as exc:
            _save(note_id, "failed", error=exc.detail)
            return
        if result.get("status") != "ready" or not result.get("reportMarkdown"):
            _save(note_id, "failed", error=str(result.get("message") or "요약할 수업 파일이 없어요."))
            return
        dates = sorted(result.get("dates") or [])[-SUBJECT_MAX_DAYS:]
        with connection.cursor() as cur:
            cur.execute(
                """UPDATE study_notes SET status = 'ready', scope_value = %s::jsonb, error_message = NULL, message = '',
                          report_markdown = %s, review_markdown = '', files = %s::jsonb WHERE id = %s""",
                [json.dumps(dates), str(result["reportMarkdown"]), json.dumps(result.get("files") or [], ensure_ascii=False), note_id],
            )
    except Exception as exc:  # noqa: BLE001 — 「정리 중」으로 남기지 않는다
        _save(note_id, "failed", error=f"과목 요약을 만들지 못했습니다: {str(exc)[:200]}")
    finally:
        connection.close()


def publish_subject_note(source: dict) -> str:
    """과목이 끝나면 전체 요약을 한 번 만들어 기수 학생 모두의 공부방에 넣는다(18:30 자동 출제 뒤).
    이미 같은 수업 날짜 · 새 형식 요약이 있으면 LLM 없이 없는 학생에게만 넣는다. 돌려주는 값: made · copied · running · skip"""
    dates = _lesson_dates(source)
    if not dates:
        return "skip"
    with connection.cursor() as cur:
        if not subject_finished(cur, source, dates):
            return "running"
        shared = _shared_subject(cur, source["id"], dates)
        cur.execute(
            "SELECT id FROM users WHERE cohort_id = %s AND role = 'student' AND is_active ORDER BY id",
            [source["cohort_id"]],
        )
        students = [r[0] for r in cur.fetchall()]
    if shared is not None:
        report, files, how = shared.get("report_markdown") or "", _json(shared.get("files")) or [], "copied"
    else:
        result = _subject_from_files(source)
        if result.get("status") != "ready" or not result.get("reportMarkdown"):
            return "skip"
        report, files, how = str(result["reportMarkdown"]), result.get("files") or [], "made"
        dates = sorted(result.get("dates") or [])[-SUBJECT_MAX_DAYS:]
    for student in students:
        with transaction.atomic(), connection.cursor() as cur:
            row = _own_note(cur, student, source["id"], SUBJECT_KEY)
            if _current_subject(row, dates):
                continue
            _put(cur, row["id"] if row else None, student, source["id"], "subject", dates, SUBJECT_KEY,
                 status="ready", message="", report=report, review="", files=files)
    return how


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
