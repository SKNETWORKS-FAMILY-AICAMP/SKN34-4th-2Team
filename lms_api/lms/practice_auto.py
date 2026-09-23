"""복습 문제 자동 출제 — 매일 18:30(수업 끝) 공개된 수업 저장소마다 그날 새로 올라온 내용으로 문제를 낸다.

- 언제: Celery beat 매일 18:30(Asia/Seoul) · 강사 「지금 만들기」.
- 어느 저장소: 공개(study_sources.is_active)이고 자동 출제가 켜진 것. 켜짐이 기본이다(study.practice_settings 에 줄이 없으면 켜짐).
- 무엇을: AI 서버(/api/v1/study-notes/proxy/practice)가 마지막으로 출제한 날부터 오늘까지 새로 생긴 셀로만 출제·검증한다.
  여기서는 그 결과를 practice.sets · problems 에 넣고, 출제 범위 기록(practice.coverage)을 이어 간다.
- 같은 날짜의 세트가 이미 있으면(손으로 넣은 세트 포함) 새 세트를 만들지 않고 그 세트 뒤에 문제를 붙인다.
- 같은 저장소를 두 번 동시에 돌리지 않는다(study.practice_runs 의 running 줄 + 트랜잭션 잠금).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import timedelta
from typing import Any

from django.db import connection, transaction
from django.utils import timezone

from lms.study_note_service import StudyNoteError, _call, _dicts, _one, _source_payload
from lms.study_source_service import StudySourceError, _check_schema, _cohort, _repo_key

logger = logging.getLogger(__name__)

PRACTICE_TIMEOUT = 30 * 60  # 저장소 하나 — LLM 출제 + 고치기 + Pyodide 검증, 며칠 치가 밀렸으면 더 걸린다
STALE_RUN = timedelta(hours=1)  # running 으로 남은 줄이 이보다 오래면 죽은 것으로 본다


def _repo_name(url: str) -> str:
    """출제 범위 기록 · 세트의 저장소 이름 — 손으로 넣던 기록(예: multimodal)과 같은 값"""
    return _repo_key(url).rsplit("/", 1)[-1]


def _practice_ready(cur) -> bool:
    cur.execute("SELECT to_regclass('practice.sets') IS NOT NULL")
    return bool(cur.fetchone()[0])


def _sources(cur, cohort_code: str | None = None) -> list[dict]:
    """공개된 수업 저장소와 자동 출제 여부"""
    cur.execute(
        f"""SELECT s.*, c.code AS cohort_code, COALESCE(ps.enabled, true) AS practice_enabled
            FROM study_sources s JOIN cohorts c ON c.id = s.cohort_id
            LEFT JOIN study.practice_settings ps
              ON ps.cohort_code = c.code AND ps.repo_key = lower(regexp_replace(rtrim(s.repo_url, '/'), '\\.git$', ''))
            WHERE s.is_active {'AND c.code = %s' if cohort_code else ''}
            ORDER BY c.code, s.sort_order NULLS LAST, s.id""",
        [cohort_code] if cohort_code else [],
    )
    return _dicts(cur)


# ── 한 저장소 출제 ─────────────────────────────────────────


def _claim_run(source: dict, trigger: str) -> int | None:
    """running 줄을 만든다. 이미 돌고 있으면 None."""
    key = _repo_key(source["repo_url"])
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"practice_auto:{source['cohort_code']}:{key}"])
        cur.execute(
            """SELECT id FROM study.practice_runs
               WHERE cohort_code = %s AND repo_key = %s AND status = 'running' AND started_at > now() - %s""",
            [source["cohort_code"], key, STALE_RUN],
        )
        if cur.fetchone():
            return None
        cur.execute(
            """INSERT INTO study.practice_runs (cohort_code, repo_key, trigger) VALUES (%s, %s, %s) RETURNING id""",
            [source["cohort_code"], key, trigger],
        )
        return cur.fetchone()[0]


def _finish_run(run_id: int, status: str, *, problems: int = 0, dates: list[str] | None = None, message: str = "") -> None:
    with connection.cursor() as cur:
        cur.execute(
            """UPDATE study.practice_runs SET status = %s, problems = %s, dates = %s::jsonb, message = %s, finished_at = now()
               WHERE id = %s""",
            [status, problems, json.dumps(dates or []), message[:1000], run_id],
        )


def _save_sets(cur, cohort_code: str, name: str, sets: list[dict]) -> int:
    """같은 날짜 세트가 있으면 뒤에 붙이고, 없으면 새로 만든다. 넣은 문제 수."""
    added = 0
    for s in sets:
        cur.execute(
            """SELECT id, files, title FROM practice.sets WHERE cohort_code = %s AND source_title = %s AND lesson_date = %s
               ORDER BY id LIMIT 1""",
            [cohort_code, name, s["lessonDate"]],
        )
        row = _one(cur)
        if row:
            set_id = row["id"]
            old_files = row["files"] if isinstance(row["files"], list) else json.loads(row["files"] or "[]")
            files = old_files + [f for f in s["files"] if f not in old_files]
            cur.execute(
                "UPDATE practice.sets SET files = %s::jsonb, title = COALESCE(NULLIF(title, ''), %s) WHERE id = %s",
                [json.dumps(files, ensure_ascii=False), s["title"], set_id],
            )
        else:
            cur.execute(
                """INSERT INTO practice.sets (legacy_id, cohort_code, source_title, lesson_date, day_label, title, files, model)
                   VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING id""",
                [f"ps-{name}-{s['lessonDate']}", cohort_code, name, s["lessonDate"], s["dayLabel"], s["title"],
                 json.dumps(s["files"], ensure_ascii=False), s["model"]],
            )
            set_id = cur.fetchone()[0]
        cur.execute("SELECT COALESCE(max(idx) + 1, 0) FROM practice.problems WHERE set_id = %s", [set_id])
        start = cur.fetchone()[0]
        for offset, p in enumerate(s["problems"]):
            cur.execute(
                """INSERT INTO practice.problems (set_id, idx, kind, topic, prompt, source_files, explanation, choices,
                     answer_index, starter_code, expected_stdout, blank_answers, reference_solution, hidden_tests, packages)
                   VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)""",
                [set_id, start + offset, p["kind"], p.get("topic", ""), p.get("prompt", ""),
                 json.dumps(p.get("sourceFiles") or [], ensure_ascii=False), p.get("explanation", ""),
                 json.dumps(p.get("choices") or [], ensure_ascii=False), p.get("answerIndex"),
                 p.get("starterCode", ""), p.get("expectedStdout", ""),
                 json.dumps(p.get("blankAnswers") or [], ensure_ascii=False), p.get("referenceSolution", ""),
                 p.get("hiddenTests", ""), json.dumps(p.get("packages") or [], ensure_ascii=False)],
            )
            added += 1
    return added


def run_source(source: dict, *, trigger: str = "schedule", today: str | None = None) -> dict:
    """저장소 하나를 출제한다. {status, problems, dates, message}. 이미 돌고 있으면 status=busy."""
    run_id = _claim_run(source, trigger)
    if run_id is None:
        return {"status": "busy", "problems": 0, "dates": [], "message": "이미 출제 중입니다."}
    name = _repo_name(source["repo_url"])
    code = source["cohort_code"]
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT data FROM practice.coverage WHERE cohort_code = %s AND source_title = %s", [code, name])
            row = cur.fetchone()
        coverage = (json.loads(row[0]) if isinstance(row[0], str) else row[0]) if row else None
        payload = _source_payload(source)
        payload["title"] = source.get("title") or name
        result = _call(
            "/proxy/practice",
            {"cohortId": code, "source": payload, "coverage": coverage,
             "today": today or timezone.localdate().isoformat()},
            PRACTICE_TIMEOUT,
        )
        with transaction.atomic(), connection.cursor() as cur:
            added = _save_sets(cur, code, name, result.get("sets") or [])
            cur.execute(
                """INSERT INTO practice.coverage (cohort_code, source_title, data, updated_at) VALUES (%s, %s, %s::jsonb, now())
                   ON CONFLICT (cohort_code, source_title) DO UPDATE SET data = EXCLUDED.data, updated_at = now()""",
                [code, name, json.dumps(result.get("coverage") or {}, ensure_ascii=False)],
            )
        dates = [s["lessonDate"] for s in result.get("sets") or []]
        error = str(result.get("error") or "")
        _finish_run(run_id, "failed" if error and not added else "done", problems=added, dates=dates, message=error)
        return {"status": "done", "problems": added, "dates": dates, "message": error}
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
        cur.execute("SELECT to_regnamespace('study') IS NOT NULL")
        if not cur.fetchone()[0] or not _practice_ready(cur):
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
        cur.execute("SELECT to_regclass('study.practice_runs') IS NOT NULL")
        if not cur.fetchone()[0]:
            raise StudySourceError(503, "study 스키마가 오래됐습니다. study_schema.sql 을 다시 실행하세요.")
        cur.execute(
            f"""SELECT s.id, s.legacy_id, COALESCE(ps.enabled, true) AS enabled,
                       r.status, r.problems, r.dates, r.message, r.started_at, r.finished_at
                FROM study_sources s
                LEFT JOIN study.practice_settings ps
                  ON ps.cohort_code = %s AND ps.repo_key = lower(regexp_replace(rtrim(s.repo_url, '/'), '\\.git$', ''))
                LEFT JOIN LATERAL (
                  SELECT * FROM study.practice_runs r
                  WHERE r.cohort_code = %s AND r.repo_key = lower(regexp_replace(rtrim(s.repo_url, '/'), '\\.git$', ''))
                  ORDER BY r.started_at DESC LIMIT 1) r ON true
                WHERE s.cohort_id = %s""",
            [cohort["code"], cohort["code"], cohort["id"]],
        )
        rows = _dicts(cur)
        ready = _practice_ready(cur)
    return {
        "cohortId": cohort["code"],
        # practice 스키마가 없으면 출제해도 넣을 곳이 없다 — 화면이 알려 준다
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
            """INSERT INTO study.practice_settings (cohort_code, repo_key, enabled, updated_by_uid, updated_at)
               VALUES (%s, %s, %s, %s, now())
               ON CONFLICT (cohort_code, repo_key) DO UPDATE SET enabled = EXCLUDED.enabled,
                 updated_by_uid = EXCLUDED.updated_by_uid, updated_at = now()""",
            [source["cohort_code"], _repo_key(source["repo_url"]), enabled, user.get("firebase_uid") or ""],
        )
    return {"id": str(source["legacy_id"] or source["id"]), "enabled": enabled}


def _spawn(work) -> None:
    """테스트가 바꿔 끼운다"""
    threading.Thread(target=work, name="practice-auto", daemon=True).start()


def run_now(user: dict, source_key: str) -> dict:
    """「지금 만들기」 — 몇 분 걸려서 바로 돌려주고 뒤에서 돈다. 화면은 status 로 끝났는지 본다."""
    with connection.cursor() as cur:
        _check_schema(cur)
        if not _practice_ready(cur):
            raise StudySourceError(503, "practice 스키마가 없습니다. practice_schema.sql 을 실행하세요.")
        source = _source_for(cur, user, source_key)
    if not source.get("is_active"):
        raise StudySourceError(409, "숨긴 저장소입니다. 공개한 뒤 출제하세요.")

    def work() -> None:
        try:
            run_source(source, trigger="manual")
        except Exception:  # noqa: BLE001 — run_source 가 기록을 남겼다
            pass
        finally:
            connection.close()

    _spawn(work)
    return {"id": str(source["legacy_id"] or source["id"]), "started": True}
