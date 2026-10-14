"""학생이 만드는 복습 문제 — 자기 노트, 또는 연습장에서 연 .py · .ipynb 로.

- 노트: 그 노트가 정리한 수업 파일(저장소 · 커밋 그대로)을 AI 서버가 다시 읽어 출제한다.
- 연습장: 학생이 연 파일 글을 그대로 보낸다(브라우저에만 있던 코드).
- 만든 세트는 그 학생만 본다(practice_sets.owner_id). 수업 세트 · 18:30 자동 출제와 섞이지 않는다.
- 몇 분 걸려서 study_practice_jobs 줄을 먼저 돌려주고 스레드에서 AI 서버를 기다린다. 화면은 줄을 물어 끝났는지 본다.
- LLM 을 부르므로 한 번에 COUNT 문제, 하루 DAILY_LIMIT 번까지.
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta
from typing import Callable

from django.db import connection, transaction
from django.utils import timezone

from lms.practice_auto import _repo_name
from lms.practice_service import create_personal_set
from lms.study_note_service import StudyNoteError, _call, _one, _source_payload
from lms.study_source_service import StudySourceError

COUNT = 6
DAILY_LIMIT = 5
TIMEOUT = 20 * 60
MAX_FILE_CHARS = 200_000
STALE = timedelta(hours=1)


def _ready(cur) -> None:
    cur.execute("SELECT to_regclass('study_practice_jobs') IS NOT NULL, to_regclass('practice_sets') IS NOT NULL")
    jobs, sets = cur.fetchone()
    if not (jobs and sets):
        raise StudySourceError(503, "문제를 넣을 곳이 없습니다. manage.py migrate 로 lms.0006 까지 적용하세요.")


def _check_limit(cur, user_id: int) -> None:
    cur.execute(
        "SELECT count(*) FROM study_practice_jobs WHERE user_id = %s AND created_at > now() - interval '1 day'",
        [user_id],
    )
    if cur.fetchone()[0] >= DAILY_LIMIT:
        raise StudySourceError(429, f"문제 만들기는 하루 {DAILY_LIMIT}번까지예요. 내일 다시 만들 수 있어요.")


def _spawn(work: Callable[[], None]) -> None:
    """테스트가 바꿔 끼운다"""
    threading.Thread(target=work, name="practice-custom", daemon=True).start()


def _job_json(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "origin": row["origin"],
        "label": row["label"],
        "status": row["status"],
        "setId": row.get("set_legacy_id"),
        "message": row.get("message") or "",
    }


def _start(user: dict, origin: str, label: str, payload: dict, meta: dict) -> dict:
    if not user.get("cohort_id"):
        raise StudySourceError(403, "기수에 속한 학생만 문제를 만들 수 있어요.")
    with transaction.atomic(), connection.cursor() as cur:
        _ready(cur)
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"practice_custom:{user['id']}"])
        _check_limit(cur, user["id"])
        cur.execute(
            """INSERT INTO study_practice_jobs (user_id, cohort_id, origin, label, status, message, created_at)
               VALUES (%s, %s, %s, %s, 'running', '', now()) RETURNING *""",
            [user["id"], user["cohort_id"], origin, label[:200]],
        )
        job = _one(cur)
        job_id = job["id"]
        owner = {"id": user["id"], "cohort_id": user["cohort_id"]}
        transaction.on_commit(lambda: _spawn(lambda: _finish(job_id, owner, origin, payload, meta)))
    return _job_json(job)


def _finish(job_id: int, owner: dict, origin: str, payload: dict, meta: dict) -> None:
    """AI 서버를 기다려 그 학생만 보는 세트로 넣는다. 스레드 안이라 DB 연결을 직접 닫는다."""
    try:
        try:
            result = _call("/proxy/practice/custom", payload, TIMEOUT)
        except StudyNoteError as exc:
            _end(job_id, "failed", message=exc.detail)
            return
        problems = result.get("problems") or []
        if not problems:
            _end(job_id, "failed", message="검증을 통과한 문제가 없어요. 자료를 조금 더 길게 해서 다시 만들어 보세요.")
            return
        legacy = f"pu-{job_id}"
        topics = list(dict.fromkeys(str(p.get("topic") or "").strip() for p in problems if p.get("topic")))
        with transaction.atomic(), connection.cursor() as cur:
            set_id = create_personal_set(
                cur, owner, origin=origin, legacy_id=legacy, source_title=meta["source_title"],
                lesson_date=meta["date"], day_label=meta["day_label"],
                title=" · ".join(topics[:3]) or meta["label"], files=meta["files"],
                generation_model=result.get("model") or "", problems=problems,
            )
            cur.execute(
                """UPDATE study_practice_jobs SET status = 'done', practice_set_id = %s, finished_at = now(),
                          message = %s WHERE id = %s""",
                [set_id, f"{len(problems)}문제를 만들었어요.", job_id],
            )
    except Exception as exc:  # noqa: BLE001 — running 으로 남기지 않는다
        _end(job_id, "failed", message=f"문제를 만들지 못했어요: {str(exc)[:200]}")
    finally:
        connection.close()


def _end(job_id: int, status: str, *, message: str) -> None:
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE study_practice_jobs SET status = %s, message = %s, finished_at = now() WHERE id = %s",
            [status, message[:500], job_id],
        )


# ── 시작 ──────────────────────────────────────────────────────────


def from_note(user: dict, note_key: str) -> dict:
    """내 노트로 — 노트가 정리한 수업 파일을 그대로 다시 읽는다"""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT n.*, s.id AS s_id, s.legacy_id AS s_legacy, s.title AS s_title, s.repo_url, s.branch, s.allowed_prefixes,
                      c.code AS s_cohort
               FROM study_notes n JOIN study_sources s ON s.id = n.source_id JOIN cohorts c ON c.id = s.cohort_id
               WHERE n.user_id = %s AND (n.legacy_id = %s OR n.id::text = %s)""",
            [user["id"], note_key, note_key],
        )
        note = _one(cur)
    if not note:
        raise StudySourceError(404, "노트를 찾을 수 없습니다.")
    if note.get("status") not in ("ready", "done", None, ""):
        raise StudySourceError(409, "다 만든 노트로만 문제를 만들 수 있어요.")
    files = note.get("files")
    files = json.loads(files) if isinstance(files, str) else (files or [])
    files = [f for f in files if isinstance(f, dict) and f.get("path") and f.get("commit")]
    if not files:
        raise StudySourceError(422, "이 노트에는 다시 읽을 수업 파일이 없어요.")
    scope = note.get("scope_value")
    scope = json.loads(scope) if isinstance(scope, str) and scope.startswith(("[", '"')) else scope
    date = scope if note.get("scope_type") == "date" and isinstance(scope, str) else timezone.localdate().isoformat()
    label = f"{date[5:].replace('-', '/')} 수업 노트" if note.get("scope_type") == "date" else f"{note['s_title']} 노트"
    source = {
        "id": note["s_legacy"] or note["s_id"], "legacy_id": note["s_legacy"], "title": note["s_title"],
        "repo_url": note["repo_url"], "branch": note["branch"], "allowed_prefixes": note["allowed_prefixes"],
    }
    payload = {
        "scopeLabel": f"{label} — 학생이 만든 노트의 수업 파일",
        "count": COUNT,
        "cohortId": note["s_cohort"],
        "source": _source_payload(source),
        "files": [{"path": f["path"], "commit": f["commit"]} for f in files[:8]],
    }
    meta = {
        "source_title": _repo_name(note["repo_url"] or ""), "date": date, "day_label": "내 노트로 만든 문제",
        "label": label, "files": [f["path"] for f in files[:8]],
    }
    return _start(user, "note", label, payload, meta)


def from_file(user: dict, name: str, content: str) -> dict:
    """연습장에서 연 파일로 — 브라우저에 있던 글을 그대로"""
    name = (name or "").strip()[:120] or "연습장 노트북.py"
    if not content or not content.strip():
        raise StudySourceError(422, "빈 노트북이에요. 코드를 넣은 뒤 만들어 주세요.")
    if len(content) > MAX_FILE_CHARS:
        raise StudySourceError(422, "파일이 너무 길어요. 필요한 부분만 남겨 주세요.")
    today = timezone.localdate().isoformat()
    payload = {
        "scopeLabel": f"{name} — 학생이 연습장에서 연 파일",
        "count": COUNT,
        "uploads": [{"name": name, "content": content}],
    }
    meta = {"source_title": "내 파일", "date": today, "day_label": "내 파일로 만든 문제", "label": name, "files": [name]}
    return _start(user, "file", name, payload, meta)


def get_job(user: dict, job_id: str) -> dict:
    with connection.cursor() as cur:
        select = """SELECT j.*, s.legacy_id AS set_legacy_id FROM study_practice_jobs j
                      LEFT JOIN practice_sets s ON s.id = j.practice_set_id WHERE j.id = %s"""
        cur.execute(
            "SELECT id FROM study_practice_jobs WHERE id::text = %s AND user_id = %s",
            [str(job_id), user.get("id")],
        )
        found = _one(cur)
        row = None
        if found:
            cur.execute(select, [found["id"]])
            row = _one(cur)
        if row and row["status"] == "running" and timezone.now() - row["created_at"] > STALE:
            # 서버가 도중에 꺼졌다 — 영원히 「만드는 중」으로 두지 않는다
            cur.execute(
                "UPDATE study_practice_jobs SET status = 'failed', message = %s, finished_at = now() WHERE id = %s",
                ["중간에 멈췄어요. 다시 만들어 주세요.", row["id"]],
            )
            cur.execute(select, [row["id"]])
            row = _one(cur)
    if not row:
        raise StudySourceError(404, "문제 만들기를 찾을 수 없습니다.")
    return _job_json(row)


def remaining(user: dict) -> dict:
    """오늘 남은 횟수 — 버튼 옆에 보여 준다"""
    with connection.cursor() as cur:
        _ready(cur)
        cur.execute(
            "SELECT count(*) FROM study_practice_jobs WHERE user_id = %s AND created_at > now() - interval '1 day'",
            [user.get("id")],
        )
        used = cur.fetchone()[0]
    return {"used": used, "limit": DAILY_LIMIT, "count": COUNT}

