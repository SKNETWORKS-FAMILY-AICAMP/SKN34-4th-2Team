"""Relational storage for the five study/practice features added after feature/test.

External cohort codes, source keys and practice legacy IDs are resolved here;
none is used as an internal relationship in the new tables.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from lms.permissions import can_access_cohort


OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
RUN_STALE_AFTER = timedelta(hours=1)
PERSONAL_DAILY_LIMIT = 5


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    columns = [column[0] for column in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _cohort(cur, user: dict, code: str):
    cohort_code = str(code or user.get("cohort_code") or "").strip()
    rows = _rows(cur, "SELECT id, code FROM cohorts WHERE code = %s", [cohort_code])
    if not rows:
        raise KeyError("cohort")
    cohort = rows[0]
    if not can_access_cohort(user, cohort["id"]):
        raise PermissionError("cohort")
    return cohort


def _source(cur, user: dict, key: str):
    rows = _rows(
        cur,
        """SELECT s.*, c.code AS cohort_code FROM study_sources s
           JOIN cohorts c ON c.id = s.cohort_id
           WHERE s.legacy_id = %s OR s.id::text = %s
           ORDER BY (s.legacy_id = %s) DESC NULLS LAST LIMIT 1""",
        [str(key), str(key), str(key)],
    )
    if not rows:
        raise KeyError("study source")
    source = rows[0]
    if not can_access_cohort(user, source["cohort_id"]):
        raise PermissionError("cohort")
    return source


def _staff(user):
    if user.get("role") not in ("admin", "instructor"):
        raise PermissionError("staff only")


def list_github_owners(user: dict, cohort_code: str):
    _staff(user)
    with connection.cursor() as cur:
        cohort = _cohort(cur, user, cohort_code)
        rows = _rows(
            cur,
            """SELECT id, owner, last_synced_at, last_error FROM study_github_owners
               WHERE cohort_id = %s ORDER BY id""",
            [cohort["id"]],
        )
    return {"cohortId": cohort["code"], "owners": [
        {"id": str(row["id"]), "owner": row["owner"],
         "lastSyncedAt": row["last_synced_at"].isoformat() if row["last_synced_at"] else None,
         "lastError": row["last_error"]} for row in rows
    ]}


def add_github_owner(user: dict, cohort_code: str, owner: str):
    _staff(user)
    owner = str(owner or "").strip().removeprefix("https://github.com/").strip("/")
    if not OWNER_RE.fullmatch(owner):
        raise ValueError("owner")
    with transaction.atomic(), connection.cursor() as cur:
        cohort = _cohort(cur, user, cohort_code)
        cur.execute(
            """INSERT INTO study_github_owners
               (cohort_id, owner, added_by_id, last_error, created_at)
               VALUES (%s, %s, %s, '', now()) ON CONFLICT DO NOTHING""",
            [cohort["id"], owner, user["id"]],
        )
    return list_github_owners(user, cohort_code)


def remove_github_owner(user: dict, owner_id: int):
    _staff(user)
    with transaction.atomic(), connection.cursor() as cur:
        rows = _rows(cur, "SELECT cohort_id FROM study_github_owners WHERE id = %s", [owner_id])
        if not rows:
            raise KeyError("owner")
        cohort_id = rows[0]["cohort_id"]
        if not can_access_cohort(user, cohort_id):
            raise PermissionError("cohort")
        cur.execute("DELETE FROM study_github_owners WHERE id = %s", [owner_id])
        rows = _rows(cur, "SELECT code FROM cohorts WHERE id = %s", [cohort_id])
        code = rows[0]["code"]
    return list_github_owners(user, code)


def practice_setting(user: dict, source_key: str):
    with connection.cursor() as cur:
        source = _source(cur, user, source_key)
        rows = _rows(cur, "SELECT enabled FROM study_practice_settings WHERE source_id = %s", [source["id"]])
    return {"sourceId": str(source["legacy_id"] or source["id"]),
            "enabled": rows[0]["enabled"] if rows else True}


def set_practice_setting(user: dict, source_key: str, enabled: bool):
    _staff(user)
    with transaction.atomic(), connection.cursor() as cur:
        source = _source(cur, user, source_key)
        cur.execute(
            """INSERT INTO study_practice_settings (source_id, enabled, updated_by_id, updated_at)
               VALUES (%s, %s, %s, now()) ON CONFLICT (source_id) DO UPDATE SET
                 enabled = EXCLUDED.enabled, updated_by_id = EXCLUDED.updated_by_id,
                 updated_at = now()""",
            [source["id"], bool(enabled), user["id"]],
        )
    return practice_setting(user, source_key)


def claim_practice_run(user: dict, source_key: str, trigger: str = "schedule"):
    if trigger not in ("schedule", "manual"):
        raise ValueError("trigger")
    if trigger == "manual":
        _staff(user)
    with transaction.atomic(), connection.cursor() as cur:
        source = _source(cur, user, source_key)
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [source["id"]])
        cur.execute(
            """SELECT id FROM study_practice_runs WHERE source_id = %s
               AND status = 'running' AND started_at > now() - %s LIMIT 1""",
            [source["id"], RUN_STALE_AFTER],
        )
        if cur.fetchone():
            return None
        cur.execute(
            """INSERT INTO study_practice_runs
               (source_id, trigger, status, problems, dates, message, started_at)
               VALUES (%s, %s, 'running', 0, '[]'::jsonb, '', now()) RETURNING id""",
            [source["id"], trigger],
        )
        return cur.fetchone()[0]


def finish_practice_run(run_id: int, *, status: str, problems: int = 0,
                        dates: list[str] | None = None, message: str = ""):
    if status not in ("done", "failed"):
        raise ValueError("status")
    with connection.cursor() as cur:
        cur.execute(
            """UPDATE study_practice_runs SET status = %s, problems = %s,
               dates = %s::jsonb, message = %s, finished_at = now() WHERE id = %s""",
            [status, problems, json.dumps(dates or []), message[:1000], run_id],
        )


def start_practice_job(user: dict, *, origin: str, label: str):
    if user.get("role") != "student" or origin not in ("note", "file"):
        raise PermissionError("student practice only")
    if not user.get("cohort_id"):
        raise ValueError("cohort")
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(%s)", [user["id"]])
        cur.execute(
            "SELECT count(*) FROM study_practice_jobs WHERE user_id = %s AND created_at > now() - interval '1 day'",
            [user["id"]],
        )
        if cur.fetchone()[0] >= PERSONAL_DAILY_LIMIT:
            raise ValueError("daily limit")
        cur.execute(
            """INSERT INTO study_practice_jobs
               (user_id, cohort_id, origin, label, status, message, created_at)
               VALUES (%s, %s, %s, %s, 'running', '', now()) RETURNING id""",
            [user["id"], user["cohort_id"], origin, label[:200]],
        )
        return cur.fetchone()[0]


def finish_practice_job(job_id: int, *, status: str, set_id: int | None = None, message: str = ""):
    if status not in ("done", "failed"):
        raise ValueError("status")
    with connection.cursor() as cur:
        cur.execute(
            """UPDATE study_practice_jobs SET status = %s, practice_set_id = %s,
               message = %s, finished_at = now() WHERE id = %s""",
            [status, set_id, message[:500], job_id],
        )


def practice_job(user: dict, job_id: int):
    with connection.cursor() as cur:
        rows = _rows(
            cur,
            """SELECT j.*, s.legacy_id AS set_legacy_id FROM study_practice_jobs j
               LEFT JOIN practice_sets s ON s.id = j.practice_set_id
               WHERE j.id = %s AND j.user_id = %s""",
            [job_id, user["id"]],
        )
    if not rows:
        raise KeyError("job")
    row = rows[0]
    return {"id": str(row["id"]), "origin": row["origin"], "label": row["label"],
            "status": row["status"], "setId": row["set_legacy_id"], "message": row["message"]}


def tutor_turns(user: dict, thread_key: str, limit: int = 30):
    with connection.cursor() as cur:
        rows = _rows(
            cur,
            """SELECT role, text, kind, hint_level, lines, llm, created_at
               FROM study_tutor_turns WHERE user_id = %s AND thread_key = %s
               ORDER BY id DESC LIMIT %s""",
            [user["id"], thread_key, min(max(limit, 1), 100)],
        )
    return [
        {"role": row["role"], "text": row["text"], "kind": row["kind"],
         "hintLevel": row["hint_level"],
         "lines": json.loads(row["lines"]) if isinstance(row["lines"], str) else row["lines"],
         "llm": row["llm"], "at": row["created_at"].isoformat()}
        for row in reversed(rows)
    ]


def add_tutor_turn(user: dict, *, thread_key: str, role: str, text: str,
                   kind: str = "", hint_level: int | None = None,
                   lines: list | None = None, llm: bool = False, problem_id: int | None = None):
    if role not in ("user", "assistant"):
        raise ValueError("role")
    with connection.cursor() as cur:
        if problem_id is not None:
            rows = _rows(
                cur,
                """SELECT s.cohort_id, s.owner_id FROM practice_problems p
                   JOIN practice_sets s ON s.id = p.problem_set_id WHERE p.id = %s""",
                [problem_id],
            )
            if not rows or rows[0]["cohort_id"] != user.get("cohort_id") or (
                rows[0]["owner_id"] is not None and rows[0]["owner_id"] != user["id"]
            ):
                raise PermissionError("problem")
        cur.execute(
            """INSERT INTO study_tutor_turns
               (user_id, problem_id, thread_key, role, text, kind, hint_level, lines, llm, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, now()) RETURNING id""",
            [user["id"], problem_id, thread_key, role, text, kind, hint_level,
             json.dumps(lines or [], ensure_ascii=False), bool(llm)],
        )
        return cur.fetchone()[0]
