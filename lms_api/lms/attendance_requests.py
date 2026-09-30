"""출결 신청 — 예전 구글폼(예외 출결)을 LMS 안으로 옮긴 것. attendance_issue_reports 에 쌓는다.

학생이 지각 · 조퇴 · 외출 · 결석(공가 포함)을 신청하고, 매니저가 승인하면 그날 출석부 상태에 반영된다.
옛 데이터(구글폼 ETL)는 issue_type 에 공가 종류(vacation · sick …)가 들어 있고 details 가 JSON 문자열일 수 있다.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")

ISSUE_TYPES = {"late": "지각", "earlyLeave": "조퇴", "outing": "외출", "absent": "결석"}
LEAVE_TYPES = {
    "vacation": "휴가", "sick": "병가", "interview": "면접",
    "reserve": "예비군·민방위", "cert": "자격증", "other": "기타",
}
STATUSES = ("submitted", "approved", "rejected")
# 한 사람이 같은 날 여러 건을 승인받으면 출석부에는 가장 무거운 것 하나를 남긴다
STATUS_WEIGHT = {"officialLeave": 5, "absent": 4, "earlyLeave": 3, "late": 2, "outing": 1}

PAST_DAYS = 31
FUTURE_DAYS = 62
REASON_MAX = 1000
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


# commands 가 맨 아래에서 이 모듈의 OPS 를 가져가므로, commands 쪽 도움 함수는 쓸 때 가져온다
def parse_day(value) -> date:
    from lms.manager_commands import parse_day as parse

    return parse(value)


def _require_staff(user: dict) -> None:
    from lms.commands import _require_staff as require

    require(user)


def can_access_cohort(user: dict, cohort_id: int) -> bool:
    from lms.commands import can_access_cohort as can_access

    return can_access(user, cohort_id)


def load_details(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _leave_name(issue_type: str, details: dict) -> str | None:
    if issue_type in LEAVE_TYPES and issue_type not in ISSUE_TYPES:
        kind = issue_type
    elif details.get("officialLeaveUsed"):
        kind = details.get("officialLeaveType") or "other"
    else:
        return None
    if kind == "other":
        return str(details.get("officialLeaveOther") or "기타")
    return LEAVE_TYPES.get(kind, str(kind))


def issue_label(issue_type: str, details: dict) -> str:
    """목록에 보일 한 줄 — 「조퇴 15:00 · 공가(병가)」"""
    leave = _leave_name(issue_type, details)
    if issue_type not in ISSUE_TYPES:
        if leave:
            return f"공가({leave})"
        return str(details.get("label") or issue_type)
    parts = [ISSUE_TYPES[issue_type]]
    start, end = details.get("timeFrom"), details.get("timeTo")
    if start and end:
        parts[0] += f" {start}~{end}"
    elif start:
        parts[0] += f" {start}"
    if leave:
        parts.append(f"공가({leave})")
    return " · ".join(parts)


def resulting_status(issue_type: str, details: dict) -> str | None:
    """승인하면 출석부에 넣을 상태"""
    if _leave_name(issue_type, details):
        return "officialLeave"
    return issue_type if issue_type in ISSUE_TYPES else None


def _time(value, label: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not _HHMM.match(text):
        raise ValueError(f"{label}은 00:00 형식으로 적어 주세요.")
    return text


def _clean(user: dict, p: dict) -> tuple[date, str, dict, str | None]:
    day = parse_day(p.get("dateKey") or p.get("date"))
    today = parse_day(None)
    if day < today - timedelta(days=PAST_DAYS) or day > today + timedelta(days=FUTURE_DAYS):
        raise ValueError(f"발생일은 {PAST_DAYS}일 전부터 {FUTURE_DAYS}일 뒤까지만 고를 수 있습니다.")
    issue_type = str(p.get("issueType") or "")
    if issue_type not in ISSUE_TYPES:
        raise ValueError("출결 유형을 골라 주세요.")
    reason = str(p.get("reason") or "").strip()
    if not reason:
        raise ValueError("사유를 적어 주세요.")
    if len(reason) > REASON_MAX:
        raise ValueError(f"사유는 {REASON_MAX}자까지 적을 수 있습니다.")

    time_from = _time(p.get("timeFrom"), "시각")
    time_to = _time(p.get("timeTo"), "복귀 시각")
    if issue_type in ("late", "earlyLeave") and not time_from:
        raise ValueError("입실 예정 시각을 적어 주세요." if issue_type == "late" else "퇴실 시각을 적어 주세요.")
    if issue_type == "outing":
        if not time_from or not time_to:
            raise ValueError("외출 시각과 복귀 시각을 적어 주세요.")
        if time_to <= time_from:
            raise ValueError("복귀 시각은 외출 시각보다 늦어야 합니다.")
    if issue_type != "outing":
        time_to = None
    if issue_type == "absent":
        time_from = None

    leave_used = bool(p.get("officialLeaveUsed"))
    leave_type = str(p.get("officialLeaveType") or "") if leave_used else ""
    leave_other = str(p.get("officialLeaveOther") or "").strip()[:100] if leave_used else ""
    if leave_used and leave_type not in LEAVE_TYPES:
        raise ValueError("공가 유형을 골라 주세요.")
    if leave_type == "other" and not leave_other:
        raise ValueError("기타 공가 내용을 적어 주세요.")

    evidence = p.get("evidence") or None
    evidence_key = None
    details = {
        "reason": reason,
        "timeFrom": time_from,
        "timeTo": time_to,
        "officialLeaveUsed": leave_used,
        "officialLeaveType": leave_type or None,
        "officialLeaveOther": leave_other or None,
    }
    if evidence:
        evidence_key = str(evidence.get("key") or "")
        parts = evidence_key.split("/")
        if len(parts) != 4 or parts[0] != "records" or parts[2] != user.get("firebase_uid") or ".." in parts:
            raise PermissionError("본인이 올린 증빙만 붙일 수 있습니다.")
        details["evidenceName"] = str(evidence.get("name") or parts[-1])[:255]
    details["label"] = issue_label(issue_type, details)
    return day, issue_type, details, evidence_key


def _row(cur, request_id) -> dict | None:
    try:
        pk = int(request_id)
    except (TypeError, ValueError):
        return None
    cur.execute(
        """SELECT id, user_id, cohort_id, attendance_date, issue_type, status, details, evidence_storage_key
           FROM attendance_issue_reports WHERE id = %s""",
        [pk],
    )
    found = cur.fetchone()
    if not found:
        return None
    keys = ("id", "user_id", "cohort_id", "attendance_date", "issue_type", "status", "details", "evidence_storage_key")
    row = dict(zip(keys, found))
    row["details"] = load_details(row["details"])
    return row


def op_submit_attendance_request(cur, user, p):
    """학생 신청 · 고치기. 승인된 신청은 고칠 수 없다. 반려된 것을 고치면 다시 검토 대기로 돌아간다."""
    if user.get("role") != "student":
        raise PermissionError("student only")
    if not user.get("cohort_id"):
        raise ValueError("기수가 없는 계정입니다.")
    day, issue_type, details, evidence_key = _clean(user, p)

    existing = _row(cur, p.get("id")) if p.get("id") else None
    if p.get("id") and existing is None:
        raise KeyError("attendance_request")
    if existing is not None:
        if existing["user_id"] != user["id"]:
            raise PermissionError("owner only")
        if existing["status"] == "approved":
            raise ValueError("승인된 신청은 고칠 수 없습니다. 매니저에게 문의해 주세요.")

    cur.execute(
        """SELECT id FROM attendance_issue_reports
           WHERE user_id = %s AND attendance_date = %s AND issue_type = %s AND id <> %s""",
        [user["id"], day, issue_type, existing["id"] if existing else 0],
    )
    if cur.fetchone():
        raise ValueError(f"{day.isoformat()} {ISSUE_TYPES[issue_type]} 신청이 이미 있습니다. 그 신청을 고쳐 주세요.")

    if existing is not None:
        if not evidence_key and not p.get("removeEvidence"):
            evidence_key = existing["evidence_storage_key"]
            if existing["details"].get("evidenceName") and evidence_key:
                details["evidenceName"] = existing["details"]["evidenceName"]
        if "previousAttendance" in existing["details"]:
            details["previousAttendance"] = existing["details"]["previousAttendance"]
        cur.execute(
            """UPDATE attendance_issue_reports
               SET attendance_date = %s, issue_type = %s, details = %s::jsonb, evidence_storage_key = %s,
                   status = 'submitted', reviewed_by_id = NULL, reviewed_at = NULL, updated_at = now()
               WHERE id = %s""",
            [day, issue_type, json.dumps(details, ensure_ascii=False), evidence_key, existing["id"]],
        )
        return {"id": str(existing["id"])}

    cur.execute(
        """INSERT INTO attendance_issue_reports
               (user_id, cohort_id, attendance_date, issue_type, details, evidence_storage_key, status,
                created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s::jsonb, %s, 'submitted', now(), now()) RETURNING id""",
        [user["id"], user["cohort_id"], day, issue_type, json.dumps(details, ensure_ascii=False), evidence_key],
    )
    return {"id": str(cur.fetchone()[0])}


def op_cancel_attendance_request(cur, user, p):
    """학생은 승인 전 자기 신청만, 매니저 · 강사는 자기 기수 신청을 지운다"""
    row = _row(cur, p.get("id"))
    if row is None:
        raise KeyError("attendance_request")
    if user.get("role") == "student":
        if row["user_id"] != user["id"]:
            raise PermissionError("owner only")
        if row["status"] == "approved":
            raise ValueError("승인된 신청은 취소할 수 없습니다. 매니저에게 문의해 주세요.")
    else:
        _require_staff(user)
        if user["role"] != "admin" and not can_access_cohort(user, row["cohort_id"]):
            raise PermissionError("cohort")
    cur.execute("DELETE FROM attendance_issue_reports WHERE id = %s", [row["id"]])
    if row["status"] == "approved":
        _release_attendance(cur, user["id"], row["user_id"], row["cohort_id"], row["attendance_date"], row["details"])
    return {"ok": True}


def _attendance_now(cur, user_id: int, day: date) -> dict | None:
    cur.execute(
        "SELECT status, data_source, finalized_by_id FROM attendances WHERE user_id = %s AND attendance_date = %s",
        [user_id, day],
    )
    found = cur.fetchone()
    if not found:
        return None
    return {"status": found[0], "dataSource": found[1], "finalizedById": found[2]}


def _snapshot_before_approval(cur, user_id: int, day: date) -> tuple[bool, dict | None]:
    """출결 신청이 덮어쓰기 전 출석부 상태. 이미 신청이 반영된 상태면 (False, None) — 원래 값은 앞선 신청이 들고 있다"""
    current = _attendance_now(cur, user_id, day)
    if current is not None and current["dataSource"] == "form":
        return False, None
    return True, current


def _find_snapshot(cur, user_id: int, day: date, fallback: dict | None = None) -> dict | None:
    cur.execute(
        """SELECT details FROM attendance_issue_reports
           WHERE user_id = %s AND attendance_date = %s ORDER BY updated_at DESC NULLS LAST""",
        [user_id, day],
    )
    for (raw,) in cur.fetchall():
        details = load_details(raw)
        if "previousAttendance" in details:
            return details["previousAttendance"]
    if fallback and "previousAttendance" in fallback:
        return fallback["previousAttendance"]
    return None


def _release_attendance(cur, reviewer_id: int, user_id: int, cohort_id: int, day: date,
                        fallback: dict | None = None) -> dict | None:
    """승인이 빠졌을 때 — 남은 승인 건으로 다시 매기고, 하나도 없으면 신청 전 상태로 돌린다.
    그 사이 매니저가 출석부를 직접 고쳤으면(data_source 가 form 이 아니면) 건드리지 않는다."""
    status = _apply_to_attendance(cur, reviewer_id, user_id, cohort_id, day)
    if status:
        return {"status": status}
    current = _attendance_now(cur, user_id, day)
    if current is None or current["dataSource"] != "form":
        return None
    snapshot = _find_snapshot(cur, user_id, day, fallback) or {}
    cur.execute(
        """UPDATE attendances
           SET status = %s, data_source = %s, finalized_by_id = %s,
               finalized_at = CASE WHEN %s THEN NULL ELSE finalized_at END, updated_at = now()
           WHERE user_id = %s AND attendance_date = %s""",
        [snapshot.get("status"), snapshot.get("dataSource"), snapshot.get("finalizedById"),
         snapshot.get("finalizedById") is None, user_id, day],
    )
    return {"status": snapshot.get("status"), "restored": True}


def _apply_to_attendance(cur, reviewer_id: int, user_id: int, cohort_id: int, day: date) -> str | None:
    """그날 승인된 신청 중 가장 무거운 상태를 출석부에 넣는다"""
    cur.execute(
        """SELECT issue_type, details FROM attendance_issue_reports
           WHERE user_id = %s AND attendance_date = %s AND status = 'approved'""",
        [user_id, day],
    )
    statuses = [resulting_status(t, load_details(d)) for t, d in cur.fetchall()]
    statuses = [s for s in statuses if s]
    if not statuses:
        return None
    status = max(statuses, key=lambda s: STATUS_WEIGHT.get(s, 0))
    cur.execute(
        """INSERT INTO attendances
               (cohort_id, user_id, attendance_date, status, data_source, finalized_by_id, finalized_at,
                created_at, updated_at)
           VALUES (%s, %s, %s, %s, 'form', %s, now(), now(), now())
           ON CONFLICT (user_id, attendance_date) DO UPDATE
               SET status = EXCLUDED.status, data_source = 'form', finalized_by_id = EXCLUDED.finalized_by_id,
                   finalized_at = now(), updated_at = now()""",
        [cohort_id, user_id, day, status, reviewer_id],
    )
    return status


def op_review_attendance_request(cur, user, p):
    """승인 · 반려 — 여러 건을 한 번에. 승인하면 그날 출석부 상태도 바꾼다(applyStatus=false 면 두기만)"""
    _require_staff(user)
    decision = p.get("decision")
    if decision not in ("approved", "rejected", "submitted"):
        raise ValueError("decision")
    ids = p.get("ids") or ([p["id"]] if p.get("id") else [])
    if not ids:
        raise ValueError("ids required")
    comment = str(p.get("comment") or "").strip()[:500] or None
    apply_status = p.get("applyStatus", True) is not False
    applied = []
    for request_id in ids:
        row = _row(cur, request_id)
        if row is None:
            raise KeyError("attendance_request")
        if user["role"] != "admin" and not can_access_cohort(user, row["cohort_id"]):
            raise PermissionError("cohort")
        was_approved = row["status"] == "approved"
        details = {**row["details"], "reviewComment": comment}
        if decision == "approved" and not was_approved and apply_status:
            fresh, snapshot = _snapshot_before_approval(cur, row["user_id"], row["attendance_date"])
            if fresh:
                details["previousAttendance"] = snapshot
        cur.execute(
            """UPDATE attendance_issue_reports
               SET status = %s, details = %s::jsonb, reviewed_by_id = %s,
                   reviewed_at = CASE WHEN %s = 'submitted' THEN NULL ELSE now() END, updated_at = now()
               WHERE id = %s""",
            [decision, json.dumps(details, ensure_ascii=False),
             None if decision == "submitted" else user["id"], decision, row["id"]],
        )
        if not apply_status:
            continue
        if decision == "approved":
            status = _apply_to_attendance(cur, user["id"], row["user_id"], row["cohort_id"], row["attendance_date"])
            if status:
                applied.append({"id": str(row["id"]), "status": status})
        elif was_approved:
            released = _release_attendance(
                cur, user["id"], row["user_id"], row["cohort_id"], row["attendance_date"], details,
            )
            if released is not None:
                applied.append({"id": str(row["id"]), **released})
    return {"ok": True, "count": len(ids), "applied": applied}


ATTENDANCE_REQUEST_OPS = {
    "submitAttendanceRequest": op_submit_attendance_request,
    "cancelAttendanceRequest": op_cancel_attendance_request,
    "reviewAttendanceRequest": op_review_attendance_request,
}


def public_request(row: dict, uid_by_pk: dict, read_url) -> dict:
    """bootstrap 에 싣는 모양 — 옛 데이터도 같은 칸으로 풀어 준다"""
    details = load_details(row.get("details"))
    issue_type = row.get("issue_type") or "other"
    leave = _leave_name(issue_type, details)
    legacy_leave = issue_type in LEAVE_TYPES and issue_type not in ISSUE_TYPES
    submitted = row.get("created_at")
    reviewed = row.get("reviewed_at")
    return {
        "id": str(row["id"]),
        "pk": row["id"],
        "userId": uid_by_pk.get(row["user_id"]),
        "attendanceDate": row["attendance_date"].isoformat() if row.get("attendance_date") else None,
        "issueType": "absent" if legacy_leave else issue_type,
        "status": row.get("status") or "submitted",
        "label": issue_label(issue_type, details),
        "reason": details.get("reason"),
        "timeFrom": details.get("timeFrom"),
        "timeTo": details.get("timeTo"),
        "officialLeaveUsed": bool(leave),
        "officialLeaveType": issue_type if legacy_leave else details.get("officialLeaveType"),
        "officialLeaveOther": details.get("officialLeaveOther"),
        "evidenceName": details.get("evidenceName") if row.get("evidence_storage_key") else None,
        "evidenceUrl": read_url(row.get("evidence_storage_key")) if row.get("evidence_storage_key") else None,
        "reviewComment": details.get("reviewComment"),
        "reviewedBy": uid_by_pk.get(row.get("reviewed_by_id")),
        "reviewedAt": reviewed.astimezone(KST).isoformat() if reviewed else None,
        "submittedAt": submitted.astimezone(KST).isoformat() if submitted else None,
    }
