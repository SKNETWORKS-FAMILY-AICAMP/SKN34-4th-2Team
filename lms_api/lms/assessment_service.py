"""성취도평가 응시 · 채점 — functions/src/assessments.ts 의 getAssessmentForTake · submitAssessment · getAssessmentReview.

학생에게 정답이 가지 않게 한다.
- 응시(take): 정답 · 해설을 뺀 문항만. 공개된 평가를 응시 기간 안에, 아직 안 낸 학생만 받는다.
- 제출(submit): 채점은 서버가 한다. 화면이 보낸 점수 · 정답 여부는 쓰지 않는다. 한 사람 한 번.
- 결과(review): 낸 뒤에만 정답 · 해설과 내 답을 준다. 강사 · 관리자는 제출 id 로 본다.

평가 · 문항 · 제출을 가리키는 id 는 bootstrap 과 같다(legacy_id, 없으면 숫자 id).
"""

from __future__ import annotations

import json

from django.utils import timezone

from lms.commands import _one, resolve_row
from lms.permissions import can_access_cohort


class AssessmentError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _is_mc(question: dict) -> bool:
    # ETL 로 옮긴 문항은 Firestore 값(mc · sa), 화면에서 만든 문항은 multipleChoice · shortAnswer
    return str(question.get("type") or "mc") in ("mc", "multipleChoice")


def _public_id(row: dict) -> str:
    return str(row.get("legacy_id") or row["id"])


def _json(value, fallback):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return fallback
    return fallback if value is None else value


def normalize_short_answer(value) -> str:
    return " ".join(str(value if value is not None else "").strip().lower().split())


def grade_answer(question: dict, raw) -> dict:
    """문항 하나 — {value, autoScore, finalScore, isCorrect}. 원본 gradeAnswer 와 같은 규칙."""
    points = int(question.get("points") or 0)
    if _is_mc(question):
        selected = None
        if isinstance(raw, bool):
            selected = None
        elif isinstance(raw, int):
            selected = raw
        elif raw is not None and str(raw).strip() != "":
            try:
                selected = int(str(raw).strip())
            except ValueError:
                selected = None
        correct = question.get("correct_index")
        is_correct = selected is not None and correct is not None and selected == int(correct)
        score = points if is_correct else 0
        return {"value": selected, "autoScore": score, "finalScore": score, "isCorrect": is_correct}
    text = str(raw if raw is not None else "").strip()
    accepted = {normalize_short_answer(a) for a in _json(question.get("accepted_answers"), [])}
    is_correct = bool(text) and normalize_short_answer(text) in accepted
    score = points if is_correct else 0
    return {"value": text, "autoScore": score, "finalScore": score, "isCorrect": is_correct}


def _assessment(cur, user: dict, key: str) -> dict:
    row = resolve_row(cur, "assessments", key)
    if not row:
        raise AssessmentError(404, "평가를 찾을 수 없습니다.")
    if not can_access_cohort(user, row["cohort_id"]):
        raise AssessmentError(403, "해당 기수에 접근할 수 없습니다.")
    return row


def _window_error(assessment: dict) -> str | None:
    now = timezone.now()
    if assessment.get("start_at") and now < assessment["start_at"]:
        return "아직 응시 기간이 아닙니다."
    if assessment.get("end_at") and now > assessment["end_at"]:
        return "응시 기간이 종료되었습니다."
    return None


def _questions(cur, assessment_id: int) -> list[dict]:
    cur.execute(
        'SELECT * FROM assessment_questions WHERE assessment_id = %s ORDER BY "order" NULLS LAST, id',
        [assessment_id],
    )
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _my_submission(cur, assessment_id: int, user_id: int) -> dict | None:
    cur.execute(
        "SELECT * FROM assessment_submissions WHERE assessment_id = %s AND user_id = %s",
        [assessment_id, user_id],
    )
    return _one(cur)


def _question_json(q: dict, *, with_answers: bool) -> dict:
    mc = _is_mc(q)
    out = {
        "id": _public_id(q),
        "order": q.get("order") or 0,
        "type": "multipleChoice" if mc else "shortAnswer",
        "prompt": q.get("prompt") or "",
        "points": q.get("points") or 0,
        "choices": [str(c) for c in _json(q.get("choices"), [])] if mc else [],
        "origin": q.get("origin") or "manual",
    }
    if with_answers:
        out.update({
            "correctIndex": q.get("correct_index"),
            "acceptedAnswers": [str(a) for a in _json(q.get("accepted_answers"), [])],
            "explanation": q.get("explanation"),
            "sourceDay": q.get("source_day"),
            "sourceTopic": q.get("source_topic"),
        })
    return out


def take(cur, user: dict, key: str) -> dict:
    """응시할 문항 — 정답 · 해설 없이."""
    assessment = _assessment(cur, user, key)
    if user.get("role") == "student":
        if not assessment.get("published"):
            raise AssessmentError(409, "아직 공개되지 않은 평가입니다.")
        error = _window_error(assessment)
        if error:
            raise AssessmentError(409, error)
        if _my_submission(cur, assessment["id"], user["id"]):
            raise AssessmentError(409, "이미 응시한 평가입니다. 결과만 확인할 수 있습니다.")
    questions = _questions(cur, assessment["id"])
    return {"assessmentId": _public_id(assessment), "questions": [_question_json(q, with_answers=False) for q in questions]}


def submit(cur, user: dict, p: dict) -> dict:
    """학생 제출 + 서버 채점(1회). 화면이 보낸 점수는 쓰지 않는다."""
    if user.get("role") != "student":
        raise PermissionError("학생만 제출할 수 있습니다.")
    assessment = _assessment(cur, user, str(p.get("assessmentId") or ""))
    if not assessment.get("published"):
        raise ValueError("공개되지 않은 평가입니다.")
    if _window_error(assessment):
        raise ValueError("응시 가능 기간이 아닙니다.")
    # 같은 학생이 두 번 눌러도 한 번만 — 평가 · 학생마다 잠근다
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"assessment_submit:{assessment['id']}:{user['id']}"])
    if _my_submission(cur, assessment["id"], user["id"]):
        raise ValueError("이미 응시한 평가입니다.")

    raw_answers = p.get("answers") or {}
    graded: dict[str, dict] = {}
    rows = []
    total = 0
    for q in _questions(cur, assessment["id"]):
        qid = _public_id(q)
        entry = raw_answers.get(qid)
        # 화면은 {value, ...} 로도, 값 그대로도 보낸다
        raw = entry.get("value") if isinstance(entry, dict) else entry
        one = grade_answer(q, raw)
        graded[qid] = one
        rows.append((q["id"], one))
        total += one["finalScore"]

    cur.execute(
        """INSERT INTO assessment_submissions (assessment_id, user_id, auto_total_score, total_score, status, submitted_at)
           VALUES (%s, %s, %s, %s, 'submitted', now()) RETURNING id""",
        [assessment["id"], user["id"], total, total],
    )
    pk = cur.fetchone()[0]
    key = f"{_public_id(assessment)}_{user['firebase_uid']}"
    cur.execute("UPDATE assessment_submissions SET legacy_id = %s WHERE id = %s", [key, pk])
    for question_id, one in rows:
        cur.execute(
            """INSERT INTO assessment_answers (submission_id, question_id, value, auto_score, final_score, is_correct)
               VALUES (%s, %s, %s::jsonb, %s, %s, %s)""",
            [pk, question_id, json.dumps(one["value"], ensure_ascii=False), one["autoScore"], one["finalScore"], one["isCorrect"]],
        )
    return {"id": key, "submissionId": key, "totalScore": total, "autoTotalScore": total, "answers": graded}


def review(cur, user: dict, key: str, submission_key: str | None = None) -> dict:
    """제출 뒤 결과 — 정답 · 해설 + 내 답. 학생은 자기 제출만, 강사 · 관리자는 제출 id 로."""
    assessment = _assessment(cur, user, key)
    staff = user.get("role") in ("admin", "instructor")
    if submission_key and staff:
        submission = resolve_row(cur, "assessment_submissions", submission_key)
    elif not staff:
        submission = _my_submission(cur, assessment["id"], user["id"])
    else:
        raise AssessmentError(400, "제출 id 가 필요합니다.")
    if not submission or submission["assessment_id"] != assessment["id"]:
        raise AssessmentError(404, "제출 기록이 없습니다.")

    questions = _questions(cur, assessment["id"])
    public_by_pk = {q["id"]: _public_id(q) for q in questions}
    cur.execute("SELECT * FROM assessment_answers WHERE submission_id = %s", [submission["id"]])
    cols = [c[0] for c in cur.description]
    answers = {}
    for r in cur.fetchall():
        a = dict(zip(cols, r))
        qid = public_by_pk.get(a["question_id"])
        if qid is None:
            continue
        answers[qid] = {
            "value": _json(a.get("value"), None),
            "autoScore": a.get("auto_score") or 0,
            "finalScore": a.get("final_score") or 0,
            "isCorrect": bool(a.get("is_correct")),
        }
    return {
        "assessmentId": _public_id(assessment),
        "questions": [_question_json(q, with_answers=True) for q in questions],
        "submission": {
            "id": _public_id(submission),
            "totalScore": submission.get("total_score") or 0,
            "autoTotalScore": submission.get("auto_total_score") or 0,
            "submittedAt": submission["submitted_at"].isoformat() if submission.get("submitted_at") else None,
            "answers": answers,
        },
    }
