"""복습 문제(practice 스키마) — bootstrap 에 싣는 스냅샷과 /command 쓰기.

표는 scripts/firestore_to_postgres/practice_schema.sql, 세트 적재는 load_practice.py.
사용자는 users.firebase_uid, 기수는 cohorts.code 로 가리킨다(ETL 이 public 을 다시 만들어도 이어지게).

스냅샷은 화면(lms_react)의 모양 그대로 보낸다: practiceSets · practiceAttempts · practiceReports · practiceReviews.
- 학생: 내 풀이 기록, 내 신고는 그대로, 다른 학생의 신고는 누구인지 가린다(숨김 판단에 「서로 다른 학생 수」만 필요하다).
- 강사 · 관리자: 신고를 모두 본다(누가 신고했는지 강사 화면에 이름이 나온다).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime


REASONS = {"unclear", "answer", "tests", "offtopic", "other"}


def _require_staff(user):
    # commands.py 의 것과 같다. 여기서 commands 를 불러오면 서로 부르는 고리가 생겨 따로 둔다
    if user.get("role") not in ("admin", "instructor"):
        raise PermissionError("staff only")


def _iso(value) -> str | None:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None if value is None else str(value)


def _has_schema(cur) -> bool:
    cur.execute("SELECT to_regclass('practice.sets')")
    return cur.fetchone()[0] is not None


def _rows(cur, sql: str, args) -> list[dict]:
    cur.execute(sql, args)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _j(value):
    """jsonb 칸 — 이 연결은 jsonb 를 JSON 글자로 돌려준다. 객체로 풀어서 보낸다"""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _anon(uid: str) -> str:
    return "anon-" + hashlib.sha1(uid.encode("utf-8")).hexdigest()[:10]


def practice_snapshot(cur, user: dict, cohort_codes: list[str]) -> dict:
    """bootstrap 에 더할 조각. practice 스키마가 없으면(아직 SQL 을 안 돌렸으면) 빈 목록."""
    empty = {"practiceSets": [], "practiceAttempts": [], "practiceReports": [], "practiceReviews": []}
    if not cohort_codes or not _has_schema(cur):
        return empty
    uid = user.get("firebase_uid") or ""
    staff = user.get("role") in ("admin", "instructor")

    # 학생이 자기 노트 · 연습장 파일로 만든 세트(owner_uid)는 만든 학생에게만 — 강사 · 관리자에게도 안 보인다
    if sets_have_owner(cur):
        sets = _rows(
            cur,
            """SELECT * FROM practice.sets WHERE cohort_code = ANY(%s) AND (owner_uid IS NULL OR owner_uid = %s)
               ORDER BY lesson_date, id""",
            [cohort_codes, uid],
        )
    else:
        sets = _rows(cur, "SELECT * FROM practice.sets WHERE cohort_code = ANY(%s) ORDER BY lesson_date", [cohort_codes])
    set_ids = [s["id"] for s in sets] or [-1]
    problems = _rows(cur, "SELECT * FROM practice.problems WHERE set_id = ANY(%s) ORDER BY set_id, idx", [set_ids])
    key_of = {s["id"]: s["legacy_id"] for s in sets}
    where = {p["id"]: (key_of[p["set_id"]], p["idx"]) for p in problems}
    problem_ids = list(where) or [-1]

    out_sets = []
    for s in sets:
        out_sets.append({
            "id": s["legacy_id"],
            "cohortId": s["cohort_code"],
            "sourceTitle": s["source_title"],
            "lessonDate": _iso(s["lesson_date"]),
            "dayLabel": s["day_label"],
            "title": s["title"],
            "files": _j(s["files"]),
            "model": s["model"],
            # lesson(수업 · 반 전체) · note · file(학생이 만든 것 — 만든 학생에게만 온다)
            "origin": s.get("origin") or "lesson",
            "problems": [
                {
                    "kind": p["kind"], "topic": p["topic"], "prompt": p["prompt"], "sourceFiles": _j(p["source_files"]),
                    "explanation": p["explanation"], "choices": _j(p["choices"]), "answerIndex": p["answer_index"],
                    "starterCode": p["starter_code"], "expectedStdout": p["expected_stdout"],
                    "blankAnswers": _j(p["blank_answers"]), "referenceSolution": p["reference_solution"],
                    "hiddenTests": p["hidden_tests"], "packages": _j(p["packages"]),
                }
                for p in problems
                if p["set_id"] == s["id"]
            ],
        })

    attempts = _rows(
        cur,
        "SELECT * FROM practice.attempts WHERE user_uid = %s AND problem_id = ANY(%s)",
        [uid, problem_ids],
    )
    reports = _rows(cur, "SELECT * FROM practice.reports WHERE problem_id = ANY(%s)", [problem_ids])
    reviews = _rows(cur, "SELECT * FROM practice.reviews WHERE problem_id = ANY(%s)", [problem_ids])

    return {
        "practiceSets": out_sets,
        "practiceAttempts": [
            {
                "id": f"{a['user_uid']}#{a['problem_id']}", "uid": a["user_uid"],
                "setId": where[a["problem_id"]][0], "index": where[a["problem_id"]][1],
                "passed": a["passed"], "tries": a["tries"], "answeredAt": _iso(a["answered_at"]),
            }
            for a in attempts
        ],
        "practiceReports": [
            {
                "id": str(r["id"]),
                "uid": r["user_uid"] if staff or r["user_uid"] == uid else _anon(r["user_uid"]),
                "setId": where[r["problem_id"]][0], "index": where[r["problem_id"]][1],
                "reason": r["reason"], "note": r["note"] if staff or r["user_uid"] == uid else "",
                "createdAt": _iso(r["created_at"]),
            }
            for r in reports
        ],
        "practiceReviews": [
            {
                "setId": where[v["problem_id"]][0], "index": where[v["problem_id"]][1],
                "decision": v["decision"], "decidedBy": v["decided_by_uid"], "decidedAt": _iso(v["decided_at"]),
            }
            for v in reviews
        ],
    }


def sets_have_owner(cur) -> bool:
    """practice_schema.sql 을 다시 돌리기 전 DB 에는 owner_uid 칸이 없다"""
    cur.execute(
        """SELECT 1 FROM information_schema.columns
           WHERE table_schema = 'practice' AND table_name = 'sets' AND column_name = 'owner_uid'"""
    )
    return cur.fetchone() is not None


def _problem_id(cur, user: dict, set_key, index) -> int:
    """세트 id · 문제 번호 → practice.problems.id. 내 기수의 세트만(관리자는 모두)."""
    cur.execute(
        """SELECT p.id, s.cohort_code FROM practice.problems p JOIN practice.sets s ON s.id = p.set_id
           WHERE s.legacy_id = %s AND p.idx = %s""",
        [str(set_key), int(index)],
    )
    row = cur.fetchone()
    if not row:
        raise KeyError("problem")
    if user.get("role") != "admin" and row[1] != user.get("cohort_code"):
        raise PermissionError("cohort")
    return row[0]


def op_record_practice_attempt(cur, user, p):
    """풀이 한 번 — 시도 수를 늘리고 통과 여부를 바꾼다. 한 번 통과한 문제는 틀려도 통과로 남긴다(화면과 같게)."""
    problem_id = _problem_id(cur, user, p.get("setId"), p.get("index"))
    cur.execute(
        """INSERT INTO practice.attempts (user_uid, problem_id, passed, tries, answered_at)
           VALUES (%s, %s, %s, 1, now())
           ON CONFLICT (user_uid, problem_id) DO UPDATE SET
             passed = practice.attempts.passed OR EXCLUDED.passed,
             tries = practice.attempts.tries + 1,
             answered_at = now()""",
        [user["firebase_uid"], problem_id, bool(p.get("passed"))],
    )


def op_report_practice_problem(cur, user, p):
    reason = str(p.get("reason") or "")
    if reason not in REASONS:
        raise ValueError("reason")
    problem_id = _problem_id(cur, user, p.get("setId"), p.get("index"))
    cur.execute(
        """INSERT INTO practice.reports (user_uid, problem_id, reason, note, created_at) VALUES (%s, %s, %s, %s, now())
           ON CONFLICT (user_uid, problem_id) DO UPDATE SET reason = EXCLUDED.reason, note = EXCLUDED.note, created_at = now()""",
        [user["firebase_uid"], problem_id, reason, str(p.get("note") or "")[:500]],
    )


def op_review_practice_problem(cur, user, p):
    _require_staff(user)
    decision = str(p.get("decision") or "")
    if decision not in ("hidden", "kept"):
        raise ValueError("decision")
    problem_id = _problem_id(cur, user, p.get("setId"), p.get("index"))
    cur.execute(
        """INSERT INTO practice.reviews (problem_id, decision, decided_by_uid, decided_at) VALUES (%s, %s, %s, now())
           ON CONFLICT (problem_id) DO UPDATE SET decision = EXCLUDED.decision,
             decided_by_uid = EXCLUDED.decided_by_uid, decided_at = now()""",
        [problem_id, decision, user["firebase_uid"]],
    )


PRACTICE_OPS = {
    "recordPracticeAttempt": op_record_practice_attempt,
    "reportPracticeProblem": op_report_practice_problem,
    "reviewPracticeProblem": op_review_practice_problem,
}
