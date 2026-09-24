"""TO-BE practice tables with the existing React practice payload contract."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime


REASONS = {"unclear", "answer", "tests", "offtopic", "other"}
KINDS = {"concept", "code_output", "code_blank", "code_fix", "code_write", "code_scratch"}


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    names = [column[0] for column in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _iso(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _uid(row):
    return row.get("firebase_uid") or str(row["user_id"])


def _anon(uid):
    return "anon-" + hashlib.sha1(uid.encode()).hexdigest()[:10]


def practice_snapshot(cur, user: dict, cohort_codes: list[str]) -> dict:
    """Read sets and learner activity; convert relational IDs at the API boundary."""
    empty = {"practiceSets": [], "practiceAttempts": [], "practiceReports": [], "practiceReviews": []}
    if not cohort_codes:
        return empty
    staff = user.get("role") in ("admin", "instructor")
    user_id = user["id"]
    sets = _rows(
        cur,
        """SELECT s.*, c.code AS cohort_code FROM practice_sets s
           JOIN cohorts c ON c.id = s.cohort_id
           WHERE c.code = ANY(%s) AND (s.owner_id IS NULL OR s.owner_id = %s)
           ORDER BY s.lesson_date, s.id""",
        [cohort_codes, user_id],
    )
    set_ids = [row["id"] for row in sets] or [-1]
    problems = _rows(
        cur,
        "SELECT * FROM practice_problems WHERE problem_set_id = ANY(%s) ORDER BY problem_set_id, position",
        [set_ids],
    )
    set_keys = {row["id"]: row["legacy_id"] for row in sets}
    problem_keys = {row["id"]: (set_keys[row["problem_set_id"]], row["position"]) for row in problems}
    problem_ids = list(problem_keys) or [-1]
    attempts = _rows(
        cur,
        """SELECT a.*, u.firebase_uid FROM practice_attempts a
           JOIN users u ON u.id = a.user_id
           WHERE a.user_id = %s AND a.problem_id = ANY(%s)""",
        [user_id, problem_ids],
    )
    reports = _rows(
        cur,
        """SELECT r.*, u.firebase_uid FROM practice_reports r
           JOIN users u ON u.id = r.user_id WHERE r.problem_id = ANY(%s)""",
        [problem_ids],
    )
    reviews = _rows(
        cur,
        """SELECT r.*, u.firebase_uid AS decided_by_uid FROM practice_reviews r
           JOIN users u ON u.id = r.decided_by_id WHERE r.problem_id = ANY(%s)""",
        [problem_ids],
    )
    return {
        "practiceSets": [
            {
                "id": s["legacy_id"], "cohortId": s["cohort_code"],
                "sourceTitle": s["source_title"], "lessonDate": _iso(s["lesson_date"]),
                "dayLabel": s["day_label"], "title": s["title"],
                "files": _json(s["source_files"]), "model": s["generation_model"],
                "origin": s["origin"],
                "problems": [
                    {
                        "kind": p["kind"], "topic": p["topic"], "prompt": p["prompt"],
                        "sourceFiles": _json(p["source_files"]), "explanation": p["explanation"],
                        "choices": _json(p["choices"]), "answerIndex": p["answer_index"],
                        "starterCode": p["starter_code"], "expectedStdout": p["expected_stdout"],
                        "blankAnswers": _json(p["blank_answers"]),
                        "referenceSolution": p["reference_solution"], "hiddenTests": p["hidden_tests"],
                        "packages": _json(p["packages"]),
                    }
                    for p in problems if p["problem_set_id"] == s["id"]
                ],
            }
            for s in sets
        ],
        "practiceAttempts": [
            {"id": f"{_uid(a)}#{a['problem_id']}", "uid": _uid(a),
             "setId": problem_keys[a["problem_id"]][0], "index": problem_keys[a["problem_id"]][1],
             "passed": a["passed"], "tries": a["tries"], "answeredAt": _iso(a["answered_at"])}
            for a in attempts
        ],
        "practiceReports": [
            {"id": str(r["id"]),
             "uid": _uid(r) if staff or r["user_id"] == user_id else _anon(_uid(r)),
             "setId": problem_keys[r["problem_id"]][0], "index": problem_keys[r["problem_id"]][1],
             "reason": r["reason"], "note": r["note"] if staff or r["user_id"] == user_id else "",
             "createdAt": _iso(r["created_at"])}
            for r in reports
        ],
        "practiceReviews": [
            {"setId": problem_keys[r["problem_id"]][0], "index": problem_keys[r["problem_id"]][1],
             "decision": r["decision"], "decidedBy": r["decided_by_uid"] or str(r["decided_by_id"]),
             "decidedAt": _iso(r["decided_at"])}
            for r in reviews
        ],
    }


def _problem_id(cur, user, set_key, index):
    try:
        position = int(index)
    except (TypeError, ValueError) as exc:
        raise ValueError("index") from exc
    rows = _rows(
        cur,
        """SELECT p.id, s.cohort_id, s.owner_id FROM practice_problems p
           JOIN practice_sets s ON s.id = p.problem_set_id
           WHERE s.legacy_id = %s AND p.position = %s""",
        [str(set_key), position],
    )
    if not rows:
        raise KeyError("problem")
    row = rows[0]
    if user.get("role") != "admin" and row["cohort_id"] != user.get("cohort_id"):
        raise PermissionError("cohort")
    if row["owner_id"] is not None and row["owner_id"] != user["id"]:
        raise PermissionError("personal set")
    return row["id"]


def record_attempt(cur, user, payload):
    problem_id = _problem_id(cur, user, payload.get("setId"), payload.get("index"))
    cur.execute(
        """INSERT INTO practice_attempts (user_id, problem_id, passed, tries, answered_at)
           VALUES (%s, %s, %s, 1, now())
           ON CONFLICT (user_id, problem_id) DO UPDATE SET
             passed = practice_attempts.passed OR EXCLUDED.passed,
             tries = practice_attempts.tries + 1, answered_at = now()""",
        [user["id"], problem_id, bool(payload.get("passed"))],
    )


def report_problem(cur, user, payload):
    reason = str(payload.get("reason") or "")
    if reason not in REASONS:
        raise ValueError("reason")
    problem_id = _problem_id(cur, user, payload.get("setId"), payload.get("index"))
    cur.execute(
        """INSERT INTO practice_reports (user_id, problem_id, reason, note, created_at, updated_at)
           VALUES (%s, %s, %s, %s, now(), now())
           ON CONFLICT (user_id, problem_id) DO UPDATE SET
             reason = EXCLUDED.reason, note = EXCLUDED.note, updated_at = now()""",
        [user["id"], problem_id, reason, str(payload.get("note") or "")[:500]],
    )


def review_problem(cur, user, payload):
    if user.get("role") not in ("admin", "instructor"):
        raise PermissionError("staff only")
    decision = str(payload.get("decision") or "")
    if decision not in ("hidden", "kept"):
        raise ValueError("decision")
    problem_id = _problem_id(cur, user, payload.get("setId"), payload.get("index"))
    cur.execute(
        """INSERT INTO practice_reviews (problem_id, decision, decided_by_id, decided_at)
           VALUES (%s, %s, %s, now())
           ON CONFLICT (problem_id) DO UPDATE SET
             decision = EXCLUDED.decision, decided_by_id = EXCLUDED.decided_by_id, decided_at = now()""",
        [problem_id, decision, user["id"]],
    )


def get_coverage(cur, cohort_id: int, source_title: str):
    rows = _rows(cur, "SELECT data FROM practice_coverage WHERE cohort_id = %s AND source_title = %s",
                 [cohort_id, source_title])
    return _json(rows[0]["data"]) if rows else None


def save_coverage(cur, cohort_id: int, source_title: str, data: dict):
    cur.execute(
        """INSERT INTO practice_coverage (cohort_id, source_title, data, updated_at)
           VALUES (%s, %s, %s::jsonb, now())
           ON CONFLICT (cohort_id, source_title) DO UPDATE SET
             data = EXCLUDED.data, updated_at = now()""",
        [cohort_id, source_title, json.dumps(data, ensure_ascii=False)],
    )


def insert_problems(cur, set_id: int, problems: list[dict]):
    cur.execute("SELECT COALESCE(max(position) + 1, 0) FROM practice_problems WHERE problem_set_id = %s", [set_id])
    start = cur.fetchone()[0]
    for offset, problem in enumerate(problems):
        kind = problem.get("kind")
        if kind not in KINDS:
            raise ValueError("kind")
        cur.execute(
            """INSERT INTO practice_problems
               (problem_set_id, position, kind, topic, prompt, source_files, explanation, choices,
                answer_index, starter_code, expected_stdout, blank_answers, reference_solution, hidden_tests, packages)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)""",
            [set_id, start + offset, kind, problem.get("topic") or "", problem.get("prompt") or "",
             json.dumps(problem.get("sourceFiles") or [], ensure_ascii=False), problem.get("explanation") or "",
             json.dumps(problem.get("choices") or [], ensure_ascii=False), problem.get("answerIndex"),
             problem.get("starterCode") or "", problem.get("expectedStdout") or "",
             json.dumps(problem.get("blankAnswers") or [], ensure_ascii=False),
             problem.get("referenceSolution") or "", problem.get("hiddenTests") or "",
             json.dumps(problem.get("packages") or [], ensure_ascii=False)],
        )
    return len(problems)


def create_personal_set(cur, user, *, origin: str, legacy_id: str, source_title: str,
                        lesson_date: date, day_label: str, title: str, files: list,
                        generation_model: str, problems: list[dict]):
    if origin not in ("note", "file"):
        raise ValueError("origin")
    if not user.get("cohort_id"):
        raise ValueError("cohort")
    cur.execute(
        """INSERT INTO practice_sets
           (legacy_id, cohort_id, owner_id, origin, source_title, lesson_date, day_label,
            title, source_files, generation_model, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, now()) RETURNING id""",
        [legacy_id, user["cohort_id"], user["id"], origin, source_title, lesson_date,
         day_label, title, json.dumps(files, ensure_ascii=False), generation_model],
    )
    set_id = cur.fetchone()[0]
    insert_problems(cur, set_id, problems)
    return set_id


PRACTICE_OPS = {
    "recordPracticeAttempt": record_attempt,
    "reportPracticeProblem": report_problem,
    "reviewPracticeProblem": review_problem,
}
