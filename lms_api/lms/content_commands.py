"""기록실 · 평가 · 설문 · 마일리지 · 학습실 · 자리 확인 쓰기.

React 가 화면 캐시에만 저장하던 것들을 서버로 옮긴 것이다(새로고침하면 사라지던 문제).
표 하나로 끝나는 것은 commands 의 범용 `upsert` 를 그대로 쓰고, 여기에는 **여러 표를
한꺼번에 고쳐야 하는 것**만 둔다.

- 평가: assessments + assessment_questions
- 평가 응시 · 채점: assessment_submissions + assessment_answers
- 구매 요청: purchase_requests + purchase_request_items (+ 승인 시 mileage_transactions · 잔액)
- 커리큘럼: curriculum_sheets + curriculum_rows
- 자리 확인: roll_calls + roll_call_entries
- 설문 응답 · 마일리지 설정: id 칸이 없어 범용 upsert 가 다루지 못한다
"""

from __future__ import annotations

import json

from lms.commands import _one, _require_staff, resolve_cohort, resolve_row, resolve_user
from lms.permissions import can_access_cohort


def _cohort_for(cur, user, cohort_key) -> int:
    cohort_id = resolve_cohort(cur, cohort_key, user)
    if cohort_id is None or not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    return cohort_id


def _js(value):
    return json.dumps(value if value is not None else [])


def _arr(value):
    """text[] 칸 — 목록 그대로 넣는다(JSON 글자로 바꾸면 배열이 깨진다)."""
    return [str(v) for v in (value or [])]


def _dt(value):
    """화면이 보내는 ISO 글자 — 빈 값은 NULL 로."""
    return value or None


# ── 기록실 ────────────────────────────────────────────


def op_review_record(cur, user, p):
    """승인 · 반려. 승인하면 적립 표시를 남긴다(마일리지 적립은 관리자가 따로 지급한다)."""
    _require_staff(user)
    row = resolve_row(cur, "record_submissions", p["id"])
    if not row:
        raise KeyError("record")
    if not can_access_cohort(user, row["cohort_id"]):
        raise PermissionError("cohort")
    status = p.get("status") or "pending"
    cur.execute(
        """UPDATE record_submissions
           SET status = %s, review_comment = %s, reviewed_by = %s, reviewed_at = now(),
               mileage_granted = %s
           WHERE id = %s""",
        [
            status,
            p.get("reviewComment") or None,
            user["id"],
            bool(row.get("mileage_granted")) or status == "approved",
            row["id"],
        ],
    )
    return {"id": str(p["id"])}


# ── 성취도 평가 ────────────────────────────────────────


def _assessment_row(cur, user, p, cohort_id):
    return [
        cohort_id,
        p.get("title") or "",
        _arr(p.get("tags")),
        int(p.get("maxScore") or 0),
        _dt(p.get("startAt")),
        _dt(p.get("endAt")),
        p.get("thumbnailUrl") or None,
        bool(p.get("published")),
        user["id"],
    ]


def op_save_assessment(cur, user, p):
    """평가 + 문항을 함께 저장한다. 문항은 통째로 갈아 끼운다(화면이 목록 전체를 보낸다)."""
    _require_staff(user)
    key = str(p.get("id") or "")
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    row = resolve_row(cur, "assessments", key) if key else None
    if row:
        cur.execute(
            """UPDATE assessments SET cohort_id=%s, title=%s, tags=%s, max_score=%s, start_at=%s,
                   end_at=%s, thumbnail_url=%s, published=%s, updated_at=now()
               WHERE id=%s""",
            [*_assessment_row(cur, user, p, cohort_id)[:-1], row["id"]],
        )
        pk = row["id"]
    else:
        cur.execute(
            """INSERT INTO assessments (legacy_id, cohort_id, title, tags, max_score, start_at, end_at,
                   thumbnail_url, published, created_by, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
            [key or None, *_assessment_row(cur, user, p, cohort_id)],
        )
        pk = cur.fetchone()[0]
        if not key:
            key = str(pk)
            cur.execute("UPDATE assessments SET legacy_id = %s WHERE id = %s", [key, pk])

    questions = p.get("questions")
    if questions is not None:
        cur.execute("DELETE FROM assessment_questions WHERE assessment_id = %s", [pk])
        for order, q in enumerate(questions):
            cur.execute(
                """INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt,
                       points, choices, correct_index, accepted_answers, explanation, origin,
                       source_day, source_topic)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                [
                    str(q.get("id") or "") or None,
                    pk,
                    int(q.get("order", order) or order),
                    q.get("type") or "multipleChoice",
                    q.get("prompt") or "",
                    int(q.get("points") or 0),
                    _arr(q.get("choices")),
                    q.get("correctIndex"),
                    _arr(q.get("acceptedAnswers")),
                    q.get("explanation") or None,
                    q.get("origin") or None,
                    q.get("sourceDay"),
                    q.get("sourceTopic") or None,
                ],
            )
    return {"id": key}


def op_submit_assessment(cur, user, p):
    """응시 제출 — 학생 본인, 한 번. 채점은 서버가 한다(assessment_service.submit)."""
    from lms.assessment_service import AssessmentError, submit

    try:
        return submit(cur, user, p)
    except AssessmentError as exc:
        # 명령 창구는 403 · 404 · 400 만 안다
        if exc.status == 403:
            raise PermissionError(exc.detail) from exc
        if exc.status == 404:
            raise KeyError(exc.detail) from exc
        raise ValueError(exc.detail) from exc


def op_grade_answer(cur, user, p):
    """단답형 채점 — 점수를 고치고 총점을 다시 더한다."""
    _require_staff(user)
    submission = resolve_row(cur, "assessment_submissions", p["submissionId"])
    if not submission:
        raise KeyError("submission")
    question = resolve_row(cur, "assessment_questions", p["questionId"])
    if not question or question["assessment_id"] != submission["assessment_id"]:
        raise KeyError("question")
    cur.execute("SELECT cohort_id FROM assessments WHERE id = %s", [submission["assessment_id"]])
    if not can_access_cohort(user, cur.fetchone()[0]):
        raise PermissionError("cohort")
    # 0 ~ 배점 사이로만
    score = max(0, min(int(p.get("score") or 0), int(question.get("points") or 0)))
    cur.execute(
        "UPDATE assessment_answers SET final_score = %s, is_correct = %s WHERE submission_id = %s AND question_id = %s",
        [score, score > 0, submission["id"], question["id"]],
    )
    cur.execute(
        "SELECT COALESCE(SUM(final_score), 0) FROM assessment_answers WHERE submission_id = %s",
        [submission["id"]],
    )
    total = cur.fetchone()[0]
    cur.execute(
        "UPDATE assessment_submissions SET total_score = %s, status = 'graded' WHERE id = %s",
        [total, submission["id"]],
    )
    return {"id": str(p["submissionId"]), "totalScore": int(total)}


# ── 설문 · 제출 ────────────────────────────────────────


def op_mark_form_responded(cur, user, p):
    """제출함 표시 — form_responses 는 (task_id, user_id) 가 열쇠라 범용 upsert 가 못 다룬다."""
    task = resolve_row(cur, "form_tasks", p["taskId"])
    if not task:
        raise KeyError("form")
    if not can_access_cohort(user, task["cohort_id"]):
        raise PermissionError("cohort")
    target = user["id"]
    if p.get("uid") and user["role"] in ("admin", "instructor"):
        target = resolve_user(cur, str(p["uid"])) or target
    cur.execute(
        """INSERT INTO form_responses (task_id, user_id, source, submitted_at)
           VALUES (%s,%s,%s, now())
           ON CONFLICT (task_id, user_id) DO UPDATE SET source = EXCLUDED.source, submitted_at = now()""",
        [task["id"], target, p.get("source") or "manual"],
    )
    return {"ok": True}


# ── 마일리지 ──────────────────────────────────────────


def op_save_purchase_request(cur, user, p):
    """구매 요청 — 요청 + 담은 상품."""
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    key = str(p.get("id") or "")
    items = p.get("items") or []
    total = int(p.get("totalAmount") or 0)
    cur.execute(
        """INSERT INTO purchase_requests (legacy_id, cohort_id, user_id, total_amount, status,
               student_note, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
        [key or None, cohort_id, user["id"], total, p.get("status") or "pending", p.get("studentNote") or None],
    )
    pk = cur.fetchone()[0]
    if not key:
        key = str(pk)
        cur.execute("UPDATE purchase_requests SET legacy_id = %s WHERE id = %s", [key, pk])
    for item in items:
        product = resolve_row(cur, "mileage_products", item.get("productId")) if item.get("productId") else None
        cur.execute(
            """INSERT INTO purchase_request_items (request_id, product_id, product_name, category,
                   pricing_type, unit_price, quantity, purchase_link)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            [
                pk,
                product["id"] if product else None,
                item.get("productName") or item.get("name") or "",
                item.get("category") or None,
                item.get("pricingType") or "fixed",
                int(item.get("unitPrice") or 0),
                int(item.get("quantity") or 1),
                item.get("purchaseLink") or None,
            ],
        )
    cur.execute("DELETE FROM mileage_cart_items WHERE user_id = %s", [user["id"]])
    return {"id": key}


def op_review_purchase_request(cur, user, p):
    """승인 · 반려 · 수정 요청. 승인하면 마일리지를 차감하고 내역을 남긴다."""
    _require_staff(user)
    row = resolve_row(cur, "purchase_requests", p["id"])
    if not row:
        raise KeyError("request")
    if not can_access_cohort(user, row["cohort_id"]):
        raise PermissionError("cohort")
    status = p.get("status") or "pending"
    was_approved = row["status"] == "approved"
    cur.execute(
        """UPDATE purchase_requests SET status=%s, manager_memo=%s, manager_purchase_link=%s,
               processed_by=%s, processed_at=now(), updated_at=now()
           WHERE id=%s""",
        [status, p.get("managerMemo") or None, p.get("purchaseLink") or None, user["id"], row["id"]],
    )
    if status == "approved" and not was_approved:
        amount = -int(row["total_amount"] or 0)
        cur.execute(
            """INSERT INTO mileage_transactions (cohort_id, user_id, amount, type, reason, related_id,
                   adjusted_by, created_at)
               VALUES (%s,%s,%s,'purchase',%s,%s,%s, now())""",
            [row["cohort_id"], row["user_id"], amount, "상품 구매 승인", str(row["id"]), user["id"]],
        )
        cur.execute(
            "UPDATE users SET mileage_balance = mileage_balance + %s WHERE id = %s", [amount, row["user_id"]]
        )
    return {"id": str(p["id"])}


def op_save_mileage_settings(cur, user, p):
    """기수 설정 — 열쇠가 cohort_id 라 범용 upsert 가 못 다룬다."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    cur.execute(
        """INSERT INTO mileage_settings (cohort_id, category_limits, accrual_rules, updated_by, updated_at)
           VALUES (%s,%s,%s,%s, now())
           ON CONFLICT (cohort_id) DO UPDATE SET category_limits = EXCLUDED.category_limits,
             accrual_rules = EXCLUDED.accrual_rules, updated_by = EXCLUDED.updated_by, updated_at = now()""",
        [cohort_id, json.dumps(p.get("categoryLimits") or {}), json.dumps(p.get("accrualRules") or {}), user["id"]],
    )
    return {"ok": True}


# ── 학습실 ────────────────────────────────────────────


def op_replace_curriculum_sheet(cur, user, p):
    """CSV 교체 — 기수에 표는 하나다. 옛 표를 지우고 새로 넣는다."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    cur.execute("DELETE FROM curriculum_sheets WHERE cohort_id = %s", [cohort_id])
    key = str(p.get("id") or "")
    cur.execute(
        """INSERT INTO curriculum_sheets (legacy_id, cohort_id, title, file_name, source, uploaded_by, uploaded_at)
           VALUES (%s,%s,%s,%s,%s,%s, now()) RETURNING id""",
        [key or None, cohort_id, p.get("title") or "", p.get("fileName") or "", "csv", user["id"]],
    )
    pk = cur.fetchone()[0]
    if not key:
        key = str(pk)
        cur.execute("UPDATE curriculum_sheets SET legacy_id = %s WHERE id = %s", [key, pk])
    for order, row in enumerate(p.get("rows") or []):
        cur.execute(
            """INSERT INTO curriculum_rows (sheet_id, day_index, date_label, subject, topic, detail, "order")
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            [
                pk,
                int(row.get("dayIndex") or 0),
                row.get("dateLabel") or "",
                row.get("subject") or "",
                row.get("topic") or "",
                row.get("detail") or "",
                int(row.get("order", order) or order),
            ],
        )
    return {"id": key}


# ── 자리 확인 ─────────────────────────────────────────


def op_set_seat_presence(cur, user, p):
    """교시마다 학생이 자리에 있는지 — roll_calls(날짜 · 교시) 밑에 학생별로 남긴다."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    date_key = str(p.get("dateKey") or "")[:10]
    period = str(p.get("period") or "")
    cur.execute(
        """INSERT INTO roll_calls (cohort_id, date_key, period_id, updated_by, updated_at)
           VALUES (%s,%s,%s,%s, now())
           ON CONFLICT (cohort_id, date_key, period_id) DO UPDATE SET updated_by = EXCLUDED.updated_by,
             updated_at = now()
           RETURNING id""",
        [cohort_id, date_key, period, user["id"]],
    )
    fetched = cur.fetchone()
    if fetched:
        roll_call_id = fetched[0]
    else:
        cur.execute(
            "SELECT id FROM roll_calls WHERE cohort_id=%s AND date_key=%s AND period_id=%s",
            [cohort_id, date_key, period],
        )
        roll_call_id = cur.fetchone()[0]
    target = resolve_user(cur, str(p.get("uid") or ""))
    if not target:
        raise KeyError("user")
    state = p.get("state") or "none"
    if state == "none":
        cur.execute(
            "DELETE FROM roll_call_entries WHERE roll_call_id = %s AND user_id = %s", [roll_call_id, target]
        )
    else:
        cur.execute(
            """INSERT INTO roll_call_entries (roll_call_id, user_id, state) VALUES (%s,%s,%s)
               ON CONFLICT (roll_call_id, user_id) DO UPDATE SET state = EXCLUDED.state""",
            [roll_call_id, target, state],
        )
    return {"ok": True}


# ── 학생 상담 ─────────────────────────────────────────

INTAKE_FIELDS = [
    "education_major", "current_status", "weekly_study_hours", "programming_level",
    "collaboration_tools", "ai_llm_experience", "motivation", "desired_role",
    "post_completion_goal", "awards", "project_links", "team_role",
    "self_learning_style", "slump_overcome_experience",
]


def op_save_student_intake(cur, user, p):
    """학생 상담 내용 — 열쇠가 user_id 라 범용 upsert 가 못 다룬다."""
    _require_staff(user)
    target = resolve_user(cur, str(p.get("uid") or ""))
    if not target:
        raise KeyError("user")
    values = [p.get(_camel(f)) or "" for f in INTAKE_FIELDS]
    cols = ", ".join(INTAKE_FIELDS)
    marks = ", ".join(["%s"] * len(INTAKE_FIELDS))
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in INTAKE_FIELDS)
    cur.execute(
        f"""INSERT INTO student_intakes (user_id, {cols}, is_active, created_by, created_at)
            VALUES (%s, {marks}, true, %s, now())
            ON CONFLICT (user_id) DO UPDATE SET {updates}""",
        [target, *values, user["id"]],
    )
    return {"ok": True}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


CONTENT_OPS = {
    "saveStudentIntake": op_save_student_intake,
    "reviewRecord": op_review_record,
    "saveAssessment": op_save_assessment,
    "submitAssessment": op_submit_assessment,
    "gradeAssessmentAnswer": op_grade_answer,
    "markFormResponded": op_mark_form_responded,
    "savePurchaseRequest": op_save_purchase_request,
    "reviewPurchaseRequest": op_review_purchase_request,
    "saveMileageSettings": op_save_mileage_settings,
    "replaceCurriculumSheet": op_replace_curriculum_sheet,
    "setSeatPresence": op_set_seat_presence,
}
