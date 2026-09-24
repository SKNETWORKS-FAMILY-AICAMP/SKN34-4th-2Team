"""복습 문제 자동 출제 — 매일 18:30(수업 끝) 공개된 수업 저장소마다 그날 새로 올라온 내용으로 문제를 낸다.

- 언제: Celery beat 매일 18:30(Asia/Seoul) · 강사 「지금 만들기」.
- 어느 저장소: 공개(study_sources.is_active)이고 자동 출제가 켜진 것. 켜짐이 기본이다(study_practice_settings 에 줄이 없으면 켜짐).
- 무엇을: AI 서버(/api/v1/study-notes/proxy/practice)가 마지막으로 출제한 날부터 오늘까지 새로 생긴 셀로만 출제·검증한다.
  여기서는 그 결과를 practice_sets · practice_problems 에 넣고, 출제 범위 기록(practice_coverage)을 이어 간다.
- 같은 날짜의 세트가 이미 있으면(손으로 넣은 세트 포함) 새 세트를 만들지 않고 그 세트 뒤에 문제를 붙인다.
- 같은 저장소를 두 번 동시에 돌리지 않는다(study_practice_runs 의 running 줄 + 트랜잭션 잠금).
"""

from __future__ import annotations

import json
import logging
import re
import threading
from datetime import timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from lms.practice_service import get_coverage, insert_problems, save_coverage
from lms.study_note_service import StudyNoteError, _call, _dicts, _one, _source_payload
from lms.study_source_service import StudySourceError, _check_schema, _cohort, _repo_key

logger = logging.getLogger(__name__)

PRACTICE_TIMEOUT = 30 * 60  # 저장소 하나 — LLM 출제 + 고치기 + Pyodide 검증, 며칠 치가 밀렸으면 더 걸린다
STALE_RUN = timedelta(hours=1)  # running 으로 남은 줄이 이보다 오래면 죽은 것으로 본다


def _repo_name(url: str) -> str:
    """출제 범위 기록 · 세트의 저장소 이름 — 손으로 넣던 기록(예: multimodal)과 같은 값"""
    return _repo_key(url).rsplit("/", 1)[-1]


def _practice_ready(cur) -> bool:
    cur.execute("SELECT to_regclass('practice_sets') IS NOT NULL AND to_regclass('study_practice_runs') IS NOT NULL")
    return bool(cur.fetchone()[0])


def _sources(cur, cohort_code: str | None = None) -> list[dict]:
    """공개된 수업 저장소와 자동 출제 여부"""
    cur.execute(
        f"""SELECT s.*, c.code AS cohort_code, COALESCE(ps.enabled, true) AS practice_enabled
            FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
            LEFT JOIN study_practice_settings ps ON ps.source_id = s.id
            WHERE s.is_active {'AND c.code = %s' if cohort_code else ''}
            ORDER BY c.code, s.sort_order NULLS LAST, s.id""",
        [cohort_code] if cohort_code else [],
    )
    return _dicts(cur)


# ── 한 저장소 출제 ─────────────────────────────────────────


def _claim_run(source: dict, trigger: str) -> int | None:
    """running 줄을 만든다. 이미 돌고 있으면 None."""
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"practice_auto:{source['id']}"])
        cur.execute(
            """SELECT id FROM study_practice_runs
               WHERE source_id = %s AND status = 'running' AND started_at > now() - %s""",
            [source["id"], STALE_RUN],
        )
        if cur.fetchone():
            return None
        cur.execute(
            """INSERT INTO study_practice_runs (source_id, trigger, status, problems, dates, message, started_at)
               VALUES (%s, %s, 'running', 0, '[]'::jsonb, '', now()) RETURNING id""",
            [source["id"], trigger],
        )
        return cur.fetchone()[0]


def _finish_run(run_id: int, status: str, *, problems: int = 0, dates: list[str] | None = None, message: str = "") -> None:
    with connection.cursor() as cur:
        cur.execute(
            """UPDATE study_practice_runs SET status = %s, problems = %s, dates = %s::jsonb, message = %s, finished_at = now()
               WHERE id = %s""",
            [status, problems, json.dumps(dates or []), message[:1000], run_id],
        )


def _save_sets(cur, cohort_id: int, name: str, sets: list[dict]) -> int:
    """같은 날짜 세트가 있으면 뒤에 붙이고, 없으면 새로 만든다. 넣은 문제 수. 학생이 만든 세트는 건드리지 않는다."""
    added = 0
    for s in sets:
        cur.execute(
            """SELECT id, source_files, title FROM practice_sets
               WHERE cohort_id = %s AND source_title = %s AND lesson_date = %s AND owner_id IS NULL
               ORDER BY id LIMIT 1""",
            [cohort_id, name, s["lessonDate"]],
        )
        row = _one(cur)
        if row:
            set_id = row["id"]
            old = row["source_files"]
            old_files = old if isinstance(old, list) else json.loads(old or "[]")
            files = old_files + [f for f in s["files"] if f not in old_files]
            cur.execute(
                "UPDATE practice_sets SET source_files = %s::jsonb, title = COALESCE(NULLIF(title, ''), %s) WHERE id = %s",
                [json.dumps(files, ensure_ascii=False), s["title"], set_id],
            )
        else:
            cur.execute(
                """INSERT INTO practice_sets (legacy_id, cohort_id, owner_id, origin, source_title, lesson_date, day_label,
                                             title, source_files, generation_model, created_at)
                   VALUES (%s, %s, NULL, 'lesson', %s, %s, %s, %s, %s::jsonb, %s, now()) RETURNING id""",
                [f"ps-{name}-{s['lessonDate']}", cohort_id, name, s["lessonDate"], s["dayLabel"] or "", s["title"] or "",
                 json.dumps(s["files"], ensure_ascii=False), s["model"] or ""],
            )
            set_id = cur.fetchone()[0]
        added += insert_problems(cur, set_id, s["problems"])
    return added


def run_source(source: dict, *, trigger: str = "schedule", today: str | None = None, dates: list[str] | None = None) -> dict:
    """저장소 하나를 출제한다. {status, problems, dates, message}. 이미 돌고 있으면 status=busy.
    dates — 강사가 고른 수업 날짜(「지금 만들기」). 없으면 자동: 최근 14일 안에서 마지막으로 출제한 날부터."""
    run_id = _claim_run(source, trigger)
    if run_id is None:
        return {"status": "busy", "problems": 0, "dates": [], "message": "이미 출제 중입니다."}
    name = _repo_name(source["repo_url"])
    code = source["cohort_code"]
    try:
        with connection.cursor() as cur:
            coverage = get_coverage(cur, source["cohort_id"], name)
        payload = _source_payload(source)
        payload["title"] = source.get("title") or name
        result = _call(
            "/proxy/practice",
            {"cohortId": code, "source": payload, "coverage": coverage,
             "today": today or timezone.localdate().isoformat(), "dates": dates or None},
            PRACTICE_TIMEOUT,
        )
        with transaction.atomic(), connection.cursor() as cur:
            added = _save_sets(cur, source["cohort_id"], name, result.get("sets") or [])
            save_coverage(cur, source["cohort_id"], name, result.get("coverage") or {})
        made = [s["lessonDate"] for s in result.get("sets") or []]
        error = str(result.get("error") or "")
        # 새로 낸 문제가 없으면 왜 없는지(끝난 과목 · 이미 출제함 · 새 내용 없음)를 남긴다 — 강사 화면이 그대로 보여 준다
        message = error or str(result.get("note") or "")
        _finish_run(run_id, "failed" if error and not added else "done", problems=added, dates=made, message=message)
        return {"status": "done", "problems": added, "dates": made, "message": message}
    except StudyNoteError as exc:
        _finish_run(run_id, "failed", message=exc.detail)
        return {"status": "failed", "problems": 0, "dates": [], "message": exc.detail}
    except Exception as exc:  # noqa: BLE001 — running 으로 남기지 않는다
        logger.exception("practice auto failed: %s", source.get("repo_url"))
        _finish_run(run_id, "failed", message=f"출제하지 못했습니다: {str(exc)[:300]}")
        raise


def run_daily(today: str | None = None) -> dict:
    """Celery beat 18:30 — 모든 기수의 공개 · 자동 출제 켜진 저장소. 저장소 하나가 실패해도 나머지는 돈다."""
    with connection.cursor() as cur:
        if not _practice_ready(cur):
            return {}
        sources = [s for s in _sources(cur) if s["practice_enabled"]]
    out: dict[str, Any] = {}
    for source in sources:
        try:
            out[source["repo_url"]] = run_source(source, today=today)
        except Exception as exc:  # noqa: BLE001
            out[source["repo_url"]] = {"status": "failed", "message": str(exc)[:200]}
    return out


# ── 강사 · 관리자 화면 ──────────────────────────────────────


def _source_for(cur, user: dict, source_key: str) -> dict:
    cur.execute(
        """SELECT s.*, c.code AS cohort_code FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
           WHERE s.legacy_id = %s OR s.id::text = %s ORDER BY (s.legacy_id = %s) DESC NULLS LAST LIMIT 1""",
        [source_key, source_key, source_key],
    )
    row = _one(cur)
    if not row:
        raise StudySourceError(404, "저장소를 찾을 수 없습니다.")
    _cohort(cur, user, row["cohort_code"])
    return row


def status(user: dict, cohort_code: str) -> dict:
    """저장소마다 자동 출제 여부와 마지막 출제"""
    with connection.cursor() as cur:
        _check_schema(cur)
        cohort = _cohort(cur, user, cohort_code)
        cur.execute(
            """SELECT s.id, s.legacy_id, COALESCE(ps.enabled, true) AS enabled,
                      r.status, r.problems, r.dates, r.message, r.started_at, r.finished_at
               FROM study_sources s
               LEFT JOIN study_practice_settings ps ON ps.source_id = s.id
               LEFT JOIN LATERAL (
                 SELECT * FROM study_practice_runs r WHERE r.source_id = s.id
                 ORDER BY r.started_at DESC LIMIT 1) r ON true
               WHERE s.cohort_id = %s""",
            [cohort["id"]],
        )
        rows = _dicts(cur)
        ready = _practice_ready(cur)
    return {
        "cohortId": cohort["code"],
        # 문제 표가 없으면 출제해도 넣을 곳이 없다 — 화면이 알려 준다
        "practiceReady": ready,
        "sources": {
            str(r["legacy_id"] or r["id"]): {
                "enabled": r["enabled"],
                "lastRun": None if r["status"] is None else {
                    "status": r["status"],
                    "problems": r["problems"],
                    "dates": r["dates"] if isinstance(r["dates"], list) else json.loads(r["dates"] or "[]"),
                    "message": r["message"],
                    "startedAt": r["started_at"].isoformat() if r["started_at"] else None,
                    "finishedAt": r["finished_at"].isoformat() if r["finished_at"] else None,
                },
            }
            for r in rows
        },
    }


def set_enabled(user: dict, source_key: str, enabled: bool) -> dict:
    with transaction.atomic(), connection.cursor() as cur:
        _check_schema(cur)
        source = _source_for(cur, user, source_key)
        cur.execute(
            """INSERT INTO study_practice_settings (source_id, enabled, updated_by_id, updated_at)
               VALUES (%s, %s, %s, now())
               ON CONFLICT (source_id) DO UPDATE SET enabled = EXCLUDED.enabled,
                 updated_by_id = EXCLUDED.updated_by_id, updated_at = now()""",
            [source["id"], enabled, user.get("id")],
        )
    return {"id": str(source["legacy_id"] or source["id"]), "enabled": enabled}


def _spawn(work) -> None:
    """테스트가 바꿔 끼운다"""
    threading.Thread(target=work, name="practice-auto", daemon=True).start()


MAX_PICK = 5  # 한 번에 고를 수 있는 날짜 — 날짜마다 LLM 을 부른다


def run_now(user: dict, source_key: str, dates: list[str] | None = None) -> dict:
    """「지금 만들기」 — 몇 분 걸려서 바로 돌려주고 뒤에서 돈다. 화면은 status 로 끝났는지 본다.
    dates 를 주면 그 수업 날짜들로(지난 과목도), 없으면 자동과 같은 규칙으로."""
    picked = sorted({str(d) for d in dates or []})
    if any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in picked):
        raise StudySourceError(422, "날짜는 YYYY-MM-DD 형식이어야 합니다.")
    if len(picked) > MAX_PICK:
        raise StudySourceError(422, f"한 번에 {MAX_PICK}일까지 고를 수 있어요.")
    with connection.cursor() as cur:
        _check_schema(cur)
        if not _practice_ready(cur):
            raise StudySourceError(503, "문제 표가 없습니다. manage.py migrate 로 lms.0006 까지 적용하세요.")
        source = _source_for(cur, user, source_key)
    if not source.get("is_active"):
        raise StudySourceError(409, "숨긴 저장소입니다. 공개한 뒤 출제하세요.")

    def work() -> None:
        try:
            run_source(source, trigger="manual", dates=picked or None)
        except Exception:  # noqa: BLE001 — run_source 가 기록을 남겼다
            pass
        finally:
            connection.close()

    _spawn(work)
    return {"id": str(source["legacy_id"] or source["id"]), "started": True}
