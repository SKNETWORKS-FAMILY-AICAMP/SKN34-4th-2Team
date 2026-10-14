"""매니저 업무 — 불시 자리 점검 · 지정 알림 대상 · 학생 조건 조회(빠른 필터 · AI 어시스턴트 공용)."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from lms.commands import _require_staff, resolve_cohort, resolve_row
from lms.permissions import can_access_cohort

KST = ZoneInfo("Asia/Seoul")
PRESENCE_STATES = ("present", "absent")
PERIODS = ("am", "pm")
REASON_MAX = 100


def _cohort_for(cur, user, cohort_key) -> int:
    cohort_id = resolve_cohort(cur, cohort_key, user)
    if cohort_id is None:
        raise ValueError("cohort required")
    if not can_access_cohort(user, cohort_id):
        raise PermissionError("cohort only")
    return cohort_id


def _parse_datetime(value) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("checkedAt required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid checkedAt") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


def parse_day(value) -> date:
    if value in (None, ""):
        return datetime.now(KST).date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise ValueError("invalid date") from exc


def cohort_students(cur, cohort_id: int, uids: list[str] | None = None) -> dict[str, int]:
    """firebase_uid → users.id — 이 기수의 재학 중인 학생만."""
    if uids is None:
        cur.execute(
            "SELECT firebase_uid, id FROM users WHERE cohort_id = %s AND role = 'student' AND is_active = true",
            [cohort_id],
        )
    else:
        cur.execute(
            """SELECT firebase_uid, id FROM users
               WHERE cohort_id = %s AND role = 'student' AND is_active = true AND firebase_uid = ANY(%s)""",
            [cohort_id, uids],
        )
    return {uid: pk for uid, pk in cur.fetchall()}


# ── 불시 자리 점검 ─────────────────────────────────────


def op_save_presence_check(cur, user, p):
    """점검 한 번을 통째로 저장한다. id 가 있으면 그 점검을 고쳐 쓴다(학생 줄은 모두 새로)."""
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    checked_at = _parse_datetime(p.get("checkedAt"))
    period = p.get("period") or ("am" if checked_at.astimezone(KST).hour < 13 else "pm")
    if period not in PERIODS:
        raise ValueError("invalid period")
    note = (str(p.get("note") or "").strip() or None)

    items = p.get("items") or []
    if not isinstance(items, list) or not items:
        raise ValueError("점검한 학생이 없습니다.")
    parsed: dict[str, tuple[str, str | None]] = {}
    for item in items:
        uid = str((item or {}).get("userId") or "")
        state = (item or {}).get("state")
        if not uid or state not in PRESENCE_STATES:
            raise ValueError("invalid presence check item")
        reason = str(item.get("reason") or "").strip()[:REASON_MAX] or None
        parsed[uid] = (state, reason if state == "absent" else None)
    students = cohort_students(cur, cohort_id, list(parsed))
    unknown = [uid for uid in parsed if uid not in students]
    if unknown:
        raise ValueError("이 기수 학생이 아닌 항목이 있습니다.")

    row_id = p.get("id")
    if row_id:
        row = resolve_row(cur, "presence_checks", row_id)
        if not row:
            raise KeyError("presence_check")
        if row["cohort_id"] != cohort_id:
            raise PermissionError("cohort only")
        pk = row["id"]
        cur.execute(
            """UPDATE presence_checks SET checked_at = %s, period = %s, note = %s, checked_by = %s,
                      updated_at = now() WHERE id = %s""",
            [checked_at, period, note, user["id"], pk],
        )
        cur.execute("DELETE FROM presence_check_items WHERE presence_check_id = %s", [pk])
    else:
        cur.execute(
            """INSERT INTO presence_checks (cohort_id, checked_at, period, note, checked_by, created_at, updated_at)
               VALUES (%s, %s, %s, %s, %s, now(), now()) RETURNING id""",
            [cohort_id, checked_at, period, note, user["id"]],
        )
        pk = cur.fetchone()[0]
    for uid, (state, reason) in parsed.items():
        cur.execute(
            """INSERT INTO presence_check_items (presence_check_id, user_id, state, reason)
               VALUES (%s, %s, %s, %s)""",
            [pk, students[uid], state, reason],
        )
    return {"id": str(pk)}


def op_delete_presence_check(cur, user, p):
    _require_staff(user)
    row = resolve_row(cur, "presence_checks", p.get("id"))
    if not row:
        return {"ok": True}
    if not can_access_cohort(user, row["cohort_id"]):
        raise PermissionError("cohort only")
    cur.execute("DELETE FROM presence_check_items WHERE presence_check_id = %s", [row["id"]])
    cur.execute("DELETE FROM presence_checks WHERE id = %s", [row["id"]])
    return {"ok": True}


# ── 지정 알림 대상 ─────────────────────────────────────


def set_alert_targets(cur, popup_id: int, cohort_id: int, uids) -> int:
    """대상을 통째로 바꾼다. 빈 목록이면 기수 전체 알림이 된다."""
    wanted = [str(uid) for uid in (uids or []) if uid]
    students = cohort_students(cur, cohort_id, wanted) if wanted else {}
    if len(students) != len(set(wanted)):
        raise ValueError("이 기수 학생만 알림 대상으로 고를 수 있습니다.")
    cur.execute("DELETE FROM alert_popup_targets WHERE popup_id = %s", [popup_id])
    for pk in students.values():
        cur.execute(
            "INSERT INTO alert_popup_targets (popup_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            [popup_id, pk],
        )
    return len(students)


# ── 학생 조건 조회 ─────────────────────────────────────
# 관리자 화면의 빠른 필터(lms_react/src/features/manager/studentFilters.ts)와 같은 기준이다.

STUDENT_FILTERS = ("missing_check_in", "missing_attendance_form", "absent_in_spot_check")


def _student_rows(cur, cohort_id: int) -> list[dict]:
    cur.execute(
        """SELECT id, firebase_uid, display_name, email, seat_number FROM users
           WHERE cohort_id = %s AND role = 'student' AND is_active = true
           ORDER BY display_name""",
        [cohort_id],
    )
    return [
        {"pk": pk, "uid": uid, "name": name, "email": email, "seatNumber": seat}
        for pk, uid, name, email, seat in cur.fetchall()
    ]


def _checked_in(cur, cohort_id: int, day: date) -> set[int]:
    """입실 시각이 찍혔거나 출석 · 지각으로 처리된 학생."""
    cur.execute(
        """SELECT user_id FROM attendances
           WHERE cohort_id = %s AND attendance_date = %s
             AND (check_in_at IS NOT NULL OR status IN ('present', 'late'))""",
        [cohort_id, day],
    )
    return {row[0] for row in cur.fetchall()}


def _form_submitted(cur, cohort_id: int, day: date) -> set[int]:
    cur.execute(
        "SELECT user_id FROM attendance_issue_reports WHERE cohort_id = %s AND attendance_date = %s",
        [cohort_id, day],
    )
    return {row[0] for row in cur.fetchall()}


def _absent_in_latest_check(cur, cohort_id: int, day: date) -> tuple[set[int], dict | None]:
    cur.execute(
        """SELECT id, checked_at, period FROM presence_checks
           WHERE cohort_id = %s AND (checked_at AT TIME ZONE 'Asia/Seoul')::date = %s
           ORDER BY checked_at DESC LIMIT 1""",
        [cohort_id, day],
    )
    row = cur.fetchone()
    if not row:
        return set(), None
    cur.execute(
        "SELECT user_id FROM presence_check_items WHERE presence_check_id = %s AND state = 'absent'",
        [row[0]],
    )
    check = {"id": str(row[0]), "checkedAt": row[1].astimezone(KST).isoformat(), "period": row[2]}
    return {r[0] for r in cur.fetchall()}, check


def find_students(cur, cohort_id: int, day: date, filters: list[str]) -> dict:
    """고른 조건을 모두 만족하는(교집합) 학생. 조건이 없으면 기수 학생 전체."""
    unknown = [f for f in filters if f not in STUDENT_FILTERS]
    if unknown:
        raise ValueError(f"unknown filter {unknown[0]}")
    students = _student_rows(cur, cohort_id)
    keep = {s["pk"] for s in students}
    spot_check = None
    if "missing_check_in" in filters:
        keep -= _checked_in(cur, cohort_id, day)
    if "missing_attendance_form" in filters:
        keep -= _form_submitted(cur, cohort_id, day)
    if "absent_in_spot_check" in filters:
        absent, spot_check = _absent_in_latest_check(cur, cohort_id, day)
        keep &= absent
    matched = [{k: v for k, v in s.items() if k != "pk"} for s in students if s["pk"] in keep]
    return {"date": day.isoformat(), "filters": filters, "students": matched, "spotCheck": spot_check}


def op_find_students(cur, user, p):
    _require_staff(user)
    cohort_id = _cohort_for(cur, user, p.get("cohortId"))
    filters = [str(f) for f in (p.get("filters") or [])]
    return find_students(cur, cohort_id, parse_day(p.get("date")), filters)


MANAGER_OPS = {
    "savePresenceCheck": op_save_presence_check,
    "deletePresenceCheck": op_delete_presence_check,
    "findStudents": op_find_students,
}
