"""관리자 AI 어시스턴트.

모델은 조회 도구로 대상을 찾고, 알림 발송 · 공지 등록 같은 쓰기는 「제안」 도구로만 만든다.
제안은 화면에 확인 카드로 뜨고, 관리자가 누를 때 execute_action 이 기존 커맨드로 실행한다.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta

from django.db import connection

from lms.attendance_requests import issue_label, load_details
from lms.commands import dispatch
from lms.manager_commands import KST, STUDENT_FILTERS, cohort_students, find_students, parse_day

log = logging.getLogger(__name__)

MAX_TURNS = 8
MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 4000
WEEKDAYS = "월화수목금토일"
ATTENDANCE_REQUEST_PATH = "/attendance-request"
ATTENDANCE_STATUSES = ("late", "absent", "earlyLeave", "outing", "officialLeave")
MAX_STATS_DAYS = 120
MAX_LISTED = 30
MAX_REMEMBERED = 80

FILTER_HELP = (
    "missing_check_in: 그 날짜 출석부에 입실 시각도 출석 · 지각 처리도 없는 학생 / "
    "missing_attendance_form: 그 날짜로 LMS 출결 신청(지각 · 조퇴 · 외출 · 결석 · 공가)을 내지 않은 학생 / "
    "absent_in_spot_check: 그 날짜 마지막 불시 자리 점검에서 '무'였던 학생"
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_students",
            "description": "조건을 모두 만족하는(교집합) 학생을 찾는다. 조건이 없으면 기수 학생 전체. " + FILTER_HELP,
            "parameters": {
                "type": "object",
                "properties": {
                    "filters": {"type": "array", "items": {"type": "string", "enum": list(STUDENT_FILTERS)}},
                    "date": {"type": "string", "description": "YYYY-MM-DD. 비우면 오늘"},
                },
                "required": ["filters"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_students",
            "description": "이름 일부로 이 기수 학생을 찾는다. 특정 학생에게 알림을 보낼 때 uid 를 얻는 데 쓴다.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attendance_summary",
            "description": "그 날짜의 출결 요약 — 학생 수, 입실 기록 수, 출결 신청 목록(유형 · 사유 · 처리 상태), 불시 점검 결과.",
            "parameters": {
                "type": "object",
                "properties": {"date": {"type": "string", "description": "YYYY-MM-DD. 비우면 오늘"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "attendance_stats",
            "description": (
                "기간 동안 학생별 출결 상태 횟수(지각 · 결석 · 조퇴 · 외출 · 공가)를 센다. "
                "'이번 달 지각 3번 이상', '결석 많은 학생' 같은 질문에 쓴다."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_date": {"type": "string", "description": "YYYY-MM-DD. 비우면 오늘부터 30일 전"},
                    "to_date": {"type": "string", "description": "YYYY-MM-DD. 비우면 오늘"},
                    "status": {"type": "string", "enum": list(ATTENDANCE_STATUSES), "description": "이 상태만 센다"},
                    "min_count": {"type": "integer", "description": "status 를 이 횟수 이상 받은 학생만. 기본 1"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "student_profile",
            "description": (
                "학생 한 명의 최근 상황 — 최근 2주 출결, 출결 신청, 기록 제출, 안 낸 설문, 마일리지 잔액 · 대기 중인 구매 요청."
                " uid 를 알면 uid, 모르면 name 으로 찾는다. 이름이 겹치면 후보를 돌려준다."
            ),
            "parameters": {
                "type": "object",
                "properties": {"uid": {"type": "string"}, "name": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "form_status",
            "description": (
                "이 기수에 올린 설문 · 제출 과제의 제출 현황. title 을 주면 제목이 맞는 과제의 미제출 학생 목록까지 준다."
            ),
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string", "description": "과제 제목 일부. 비우면 최근 과제 요약만"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pending_reviews",
            "description": "관리자가 처리해야 할 대기 건 — 확인 대기 출결 신청, 승인 대기 기록 제출, 대기 중인 마일리지 구매 요청.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notices",
            "description": "최근 게시판 공지 목록(제목 · 중요 여부 · 올린 날).",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "기본 10, 최대 30"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alerts",
            "description": "최근 알림 팝업 목록 — 대상 수 · 읽은 학생 수 · 노출 마감일 · 켜짐 여부.",
            "parameters": {
                "type": "object",
                "properties": {"active_only": {"type": "boolean", "description": "지금 켜진 알림만"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_alert",
            "description": (
                "알림 팝업 발송을 제안한다. 바로 보내지지 않고 관리자가 확인 카드에서 눌러야 발송된다. "
                "target_user_ids 는 조회 도구가 돌려준 uid 만 쓴다. 기수 전체에게 보낼 때만 all_students=true."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "target_user_ids": {"type": "array", "items": {"type": "string"}},
                    "all_students": {"type": "boolean"},
                    "link_url": {"type": "string"},
                    "end_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD. 이 날까지 보인다. 비우면 오늘 하루만. 계속 띄울 알림이면 'none'",
                    },
                },
                "required": ["title", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_notice",
            "description": "게시판 공지 등록을 제안한다. 관리자가 확인 카드에서 눌러야 등록된다.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "important": {"type": "boolean", "description": "중요 공지로 올릴지"},
                },
                "required": ["title", "content"],
            },
        },
    },
]


class AssistantError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _model() -> str:
    return os.environ.get("ADMIN_ASSISTANT_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"


def _effort_kwargs(model: str) -> dict:
    """추론 모델은 chat completions 에서 도구를 쓰려면 reasoning_effort='none' 이어야 한다. gpt-4 계열에 보내면 400"""
    if model.startswith(("gpt-4", "gpt-3")):
        return {}
    return {"reasoning_effort": "none"}


def _client():
    if not os.environ.get("OPENAI_API_KEY"):
        raise AssistantError("AI 키(OPENAI_API_KEY)가 설정되지 않았습니다.", 503)
    from openai import OpenAI

    return OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def _cohort(cohort_id: int) -> dict:
    with connection.cursor() as cur:
        cur.execute("SELECT code, name FROM cohorts WHERE id = %s", [cohort_id])
        row = cur.fetchone()
    if not row:
        raise AssistantError("기수를 찾을 수 없습니다.", 404)
    return {"id": cohort_id, "code": row[0], "name": row[1]}


def _system_prompt(cohort: dict, today) -> str:
    return (
        "너는 부트캠프 LMS 운영 매니저를 돕는 업무 어시스턴트다. 한국어로 짧고 분명하게 답한다.\n"
        f"- 오늘: {today.isoformat()} ({WEEKDAYS[today.weekday()]}요일), 대상 기수: {cohort['name']} ({cohort['code']})\n"
        "- 학생 정보 · 출결은 반드시 도구로 조회한 결과만 말한다. 추측하지 않는다.\n"
        "- 기간 출결 통계는 attendance_stats, 학생 한 명의 상황은 student_profile, 설문 · 과제 미제출은 form_status, "
        "처리할 대기 건은 pending_reviews, 최근 공지 · 알림은 list_notices · list_alerts 로 조회한다. "
        "'이번 주'는 월요일부터, '이번 달'은 1일부터 오늘까지로 계산한다.\n"
        "- 앞선 답 끝의 '[조회한 학생 N명] 이름(uid), …' 는 이전에 조회한 결과다. '아까 그 학생들'처럼 가리키면 "
        "그 uid 를 그대로 target_user_ids 에 쓴다. 조건이 바뀌었으면 다시 조회한다.\n"
        "- 도구 결과의 uid 는 답에 적지 말고 이름으로 말한다. 목록이 길면 몇 명만 적고 총 인원을 말한다.\n"
        "- 알림 발송 · 공지 등록은 propose_* 도구로 제안만 한다. 제안했다고 말하되 '보냈다 · 등록했다'고 하지 않는다. "
        "관리자가 아래 확인 카드에서 실행해야 반영된다.\n"
        "- 조건에 맞는 학생이 없으면 제안하지 말고 없다고 알린다.\n"
        "- 알림 · 공지 문구는 학생에게 보내는 존댓말로, 핵심만 담아 쓴다.\n"
        f"- 출결 신청은 LMS 왼쪽 메뉴 「출결 신청」에서 한다. 출결 신청을 안내하는 알림은 link_url 을 '{ATTENDANCE_REQUEST_PATH}' 로 둔다.\n"
        "- 이 업무 밖의 요청(코드 작성, 잡담 등)은 정중히 거절한다."
    )


def _end_date_arg(value) -> str | None:
    """알림 노출 마지막 날 — 비우면 오늘, 'none' 이면 끌 때까지"""
    text = str(value or "").strip().lower()
    if text in ("none", "null", "없음"):
        return None
    if not text:
        return datetime.now(KST).date().isoformat()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return datetime.now(KST).date().isoformat()


def _clean_history(messages) -> list[dict]:
    out = []
    for message in (messages or [])[-MAX_HISTORY:]:
        role = (message or {}).get("role")
        content = str((message or {}).get("content") or "").strip()[:MAX_MESSAGE_CHARS]
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    if not out or out[-1]["role"] != "user":
        raise AssistantError("message required")
    return out


class _Session:
    """한 번의 대화 요청 — 도구 실행과 제안 카드를 모은다."""

    def __init__(self, user: dict, cohort: dict):
        self.user = user
        self.cohort = cohort
        self.actions: list[dict] = []
        self.seen: dict[str, str] = {}

    def remember(self, students) -> None:
        for s in students or []:
            if s.get("uid") and len(self.seen) < MAX_REMEMBERED:
                self.seen.setdefault(s["uid"], s.get("name") or "")

    def memo(self) -> str:
        """다음 질문에서 '아까 그 학생들'을 알아듣도록 답 뒤에 붙여 둘 조회 결과"""
        if not self.seen:
            return ""
        names = ", ".join(f"{name}({uid})" for uid, name in self.seen.items())
        return f"[조회한 학생 {len(self.seen)}명] {names}"

    def run_tool(self, name: str, args: dict):
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return {"error": f"unknown tool {name}"}
        try:
            with connection.cursor() as cur:
                return handler(cur, args)
        except ValueError as exc:
            return {"error": str(exc)}

    def _tool_find_students(self, cur, args):
        result = find_students(cur, self.cohort["id"], parse_day(args.get("date")), list(args.get("filters") or []))
        self.remember(result.get("students"))
        return result

    def _tool_search_students(self, cur, args):
        name = str(args.get("name") or "").strip()
        result = find_students(cur, self.cohort["id"], parse_day(None), [])
        students = [s for s in result["students"] if name and name in (s["name"] or "")]
        self.remember(students)
        return {"students": students}

    def _tool_attendance_stats(self, cur, args):
        today = datetime.now(KST).date()
        end = parse_day(args.get("to_date")) if args.get("to_date") else today
        start = parse_day(args.get("from_date")) if args.get("from_date") else end - timedelta(days=30)
        if start > end:
            start, end = end, start
        if (end - start).days > MAX_STATS_DAYS:
            raise ValueError(f"기간은 {MAX_STATS_DAYS}일 이내로 좁혀 주세요.")
        status = args.get("status") or None
        if status is not None and status not in ATTENDANCE_STATUSES:
            raise ValueError(f"unknown status {status}")
        try:
            min_count = max(1, int(args.get("min_count") or 1))
        except (TypeError, ValueError):
            min_count = 1
        cur.execute(
            """SELECT u.firebase_uid, u.display_name, a.status, COUNT(*)
               FROM attendances a JOIN users u ON u.id = a.user_id
               WHERE a.cohort_id = %s AND a.attendance_date BETWEEN %s AND %s
                 AND u.role = 'student' AND u.is_active = true
               GROUP BY u.firebase_uid, u.display_name, a.status""",
            [self.cohort["id"], start, end],
        )
        per_student: dict[str, dict] = {}
        totals = {s: 0 for s in ATTENDANCE_STATUSES}
        for uid, name, code, count in cur.fetchall():
            if code not in ATTENDANCE_STATUSES:
                continue
            row = per_student.setdefault(uid, {"uid": uid, "name": name, **{s: 0 for s in ATTENDANCE_STATUSES}})
            row[code] += count
            totals[code] += count
        if status:
            rows = [r for r in per_student.values() if r[status] >= min_count]
            rows.sort(key=lambda r: (-r[status], r["name"] or ""))
        else:
            rows = [r for r in per_student.values() if sum(r[s] for s in ATTENDANCE_STATUSES) >= min_count]
            rows.sort(key=lambda r: (-r["absent"], -r["late"], -r["earlyLeave"], r["name"] or ""))
        self.remember(rows[:MAX_LISTED])
        return {
            "from": start.isoformat(), "to": end.isoformat(), "status": status, "minCount": min_count,
            "totals": totals, "matchedCount": len(rows), "students": rows[:MAX_LISTED],
        }

    def _find_student(self, cur, args) -> dict:
        uid = str(args.get("uid") or "").strip()
        name = str(args.get("name") or "").strip()
        if not uid and not name:
            raise ValueError("uid 나 name 이 필요합니다.")
        where, value = ("firebase_uid = %s", uid) if uid else ("display_name ILIKE %s", f"%{name}%")
        cur.execute(
            f"""SELECT id, firebase_uid, display_name, email, seat_number, mileage_balance FROM users
                WHERE cohort_id = %s AND role = 'student' AND is_active = true AND {where}
                ORDER BY display_name LIMIT 10""",
            [self.cohort["id"], value],
        )
        rows = cur.fetchall()
        if not rows:
            raise ValueError("이 기수에서 그 학생을 찾지 못했습니다.")
        people = [
            {"pk": pk, "uid": u, "name": n, "email": e, "seatNumber": seat, "mileageBalance": balance}
            for pk, u, n, e, seat, balance in rows
        ]
        exact = [p for p in people if p["name"] == name]
        if len(people) > 1 and len(exact) != 1:
            self.remember(people)
            return {"candidates": [{k: p[k] for k in ("uid", "name", "seatNumber")} for p in people]}
        return exact[0] if len(people) > 1 else people[0]

    def _tool_student_profile(self, cur, args):
        student = self._find_student(cur, args)
        if "candidates" in student:
            return {"ambiguous": True, **student}
        pk = student.pop("pk")
        self.remember([student])
        since = datetime.now(KST).date() - timedelta(days=13)
        cur.execute(
            """SELECT attendance_date, status, check_in_at, check_out_at FROM attendances
               WHERE user_id = %s AND attendance_date >= %s ORDER BY attendance_date DESC""",
            [pk, since],
        )
        attendance = [
            {
                "date": day.isoformat(), "status": code,
                "checkIn": check_in.astimezone(KST).strftime("%H:%M") if check_in else None,
                "checkOut": check_out.astimezone(KST).strftime("%H:%M") if check_out else None,
            }
            for day, code, check_in, check_out in cur.fetchall()
        ]
        cur.execute(
            """SELECT attendance_date, issue_type, details, status FROM attendance_issue_reports
               WHERE user_id = %s ORDER BY attendance_date DESC LIMIT 10""",
            [pk],
        )
        requests = []
        for day, issue_type, raw, code in cur.fetchall():
            details = load_details(raw)
            requests.append({
                "date": day.isoformat(), "label": issue_label(issue_type, details),
                "reason": details.get("reason"), "status": code,
            })
        cur.execute(
            """SELECT type, status, title, submitted_at FROM record_submissions
               WHERE user_id = %s ORDER BY submitted_at DESC NULLS LAST LIMIT 10""",
            [pk],
        )
        records = [
            {"type": kind, "status": code, "title": title,
             "submittedAt": at.astimezone(KST).date().isoformat() if at else None}
            for kind, code, title, at in cur.fetchall()
        ]
        cur.execute(
            """SELECT st.title, st.due_at FROM submission_tasks st
               JOIN submission_task_cohorts stc ON stc.task_id = st.id
               WHERE stc.cohort_id = %s AND st.published = true
                 AND NOT EXISTS (SELECT 1 FROM submission_responses r WHERE r.task_id = st.id AND r.user_id = %s)
               ORDER BY st.due_at DESC NULLS LAST LIMIT 10""",
            [self.cohort["id"], pk],
        )
        missing_forms = [
            {"title": title, "dueAt": due.astimezone(KST).isoformat() if due else None}
            for title, due in cur.fetchall()
        ]
        cur.execute(
            "SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM purchase_requests WHERE user_id = %s AND status = 'pending'",
            [pk],
        )
        pending_count, pending_amount = cur.fetchone() or (0, 0)
        return {
            **student,
            "recentAttendance": attendance,
            "attendanceRequests": requests,
            "recordSubmissions": records,
            "missingForms": missing_forms,
            "pendingPurchases": {"count": pending_count, "amount": int(pending_amount or 0)},
        }

    def _tool_form_status(self, cur, args):
        title = str(args.get("title") or "").strip()
        params: list = [self.cohort["id"]]
        where = ""
        if title:
            where = "AND st.title ILIKE %s"
            params.append(f"%{title}%")
        cur.execute(
            f"""SELECT st.id, st.title, st.submission_type, st.due_at, st.published,
                       (SELECT COUNT(*) FROM submission_responses r
                          JOIN users u ON u.id = r.user_id
                         WHERE r.task_id = st.id AND u.cohort_id = stc.cohort_id AND u.role = 'student')
                FROM submission_tasks st JOIN submission_task_cohorts stc ON stc.task_id = st.id
                WHERE stc.cohort_id = %s {where}
                ORDER BY st.due_at DESC NULLS LAST, st.id DESC LIMIT 10""",
            params,
        )
        tasks = cur.fetchall()
        students = find_students(cur, self.cohort["id"], parse_day(None), [])["students"]
        out = []
        for pk, task_title, kind, due, published, submitted in tasks:
            item = {
                "title": task_title,
                "mode": "builtin" if kind == "builtin" else "external",
                "dueAt": due.astimezone(KST).isoformat() if due else None,
                "published": bool(published),
                "submitted": submitted,
                "total": len(students),
            }
            if title:
                cur.execute(
                    """SELECT u.firebase_uid FROM submission_responses r JOIN users u ON u.id = r.user_id
                       WHERE r.task_id = %s""",
                    [pk],
                )
                done = {row[0] for row in cur.fetchall()}
                missing = [{"uid": s["uid"], "name": s["name"]} for s in students if s["uid"] not in done]
                self.remember(missing)
                item["missing"] = missing
            out.append(item)
        if title and not out:
            raise ValueError(f"제목에 '{title}'이 들어간 과제가 없습니다.")
        return {"tasks": out}

    def _tool_pending_reviews(self, cur, args):
        cohort_id = self.cohort["id"]
        cur.execute(
            """SELECT u.display_name, r.attendance_date, r.issue_type, r.details
               FROM attendance_issue_reports r JOIN users u ON u.id = r.user_id
               WHERE r.cohort_id = %s AND r.status = 'submitted'
               ORDER BY r.attendance_date DESC, u.display_name""",
            [cohort_id],
        )
        requests = [
            {"name": name, "date": day.isoformat(), "label": issue_label(issue_type, load_details(raw))}
            for name, day, issue_type, raw in cur.fetchall()
        ]
        cur.execute(
            """SELECT u.display_name, s.type, s.title, s.submitted_at
               FROM record_submissions s JOIN users u ON u.id = s.user_id
               WHERE s.cohort_id = %s AND s.status = 'pending'
               ORDER BY s.submitted_at DESC NULLS LAST""",
            [cohort_id],
        )
        records = [
            {"name": name, "type": kind, "title": title,
             "submittedAt": at.astimezone(KST).date().isoformat() if at else None}
            for name, kind, title, at in cur.fetchall()
        ]
        cur.execute(
            """SELECT u.display_name, p.total_amount, p.created_at
               FROM purchase_requests p JOIN users u ON u.id = p.user_id
               WHERE p.cohort_id = %s AND p.status = 'pending'
               ORDER BY p.created_at DESC NULLS LAST""",
            [cohort_id],
        )
        purchases = [
            {"name": name, "amount": int(amount or 0),
             "requestedAt": at.astimezone(KST).date().isoformat() if at else None}
            for name, amount, at in cur.fetchall()
        ]
        return {
            "attendanceRequests": {"count": len(requests), "items": requests[:MAX_LISTED]},
            "recordSubmissions": {"count": len(records), "items": records[:MAX_LISTED]},
            "purchaseRequests": {"count": len(purchases), "items": purchases[:MAX_LISTED]},
        }

    def _tool_list_notices(self, cur, args):
        try:
            limit = min(30, max(1, int(args.get("limit") or 10)))
        except (TypeError, ValueError):
            limit = 10
        cur.execute(
            """SELECT title, is_favorite, created_at FROM notices
               WHERE cohort_id = %s ORDER BY created_at DESC NULLS LAST LIMIT %s""",
            [self.cohort["id"], limit],
        )
        return {"notices": [
            {"title": title, "important": bool(important),
             "createdAt": at.astimezone(KST).date().isoformat() if at else None}
            for title, important, at in cur.fetchall()
        ]}

    def _tool_list_alerts(self, cur, args):
        active = "AND p.is_active = true AND (p.end_date IS NULL OR p.end_date >= %s)" if args.get("active_only") else ""
        params: list = [self.cohort["id"]]
        if active:
            params.append(datetime.now(KST).date())
        cur.execute(
            f"""SELECT p.title, p.is_active, p.end_date, p.created_at,
                       (SELECT COUNT(*) FROM alert_popup_targets t WHERE t.popup_id = p.id),
                       (SELECT COUNT(*) FROM alert_popup_reads r WHERE r.popup_id = p.id)
                FROM alert_popups p
                WHERE p.cohort_id = %s {active}
                ORDER BY p.created_at DESC NULLS LAST LIMIT 15""",
            params,
        )
        rows = cur.fetchall()
        everyone = len(find_students(cur, self.cohort["id"], parse_day(None), [])["students"])
        return {"alerts": [
            {
                "title": title, "active": bool(is_active),
                "endDate": end.isoformat() if end else None,
                "createdAt": at.astimezone(KST).date().isoformat() if at else None,
                "targetCount": targets or everyone,
                "targetsAllStudents": not targets,
                "readCount": reads,
            }
            for title, is_active, end, at, targets, reads in rows
        ]}

    def _tool_attendance_summary(self, cur, args):
        day = parse_day(args.get("date"))
        everyone = find_students(cur, self.cohort["id"], day, [])["students"]
        no_check_in = find_students(cur, self.cohort["id"], day, ["missing_check_in"])["students"]
        absent = find_students(cur, self.cohort["id"], day, ["absent_in_spot_check"])
        cur.execute(
            """SELECT u.display_name, r.issue_type, r.details, r.status
               FROM attendance_issue_reports r JOIN users u ON u.id = r.user_id
               WHERE r.cohort_id = %s AND r.attendance_date = %s ORDER BY u.display_name""",
            [self.cohort["id"], day],
        )
        forms = []
        for name, issue_type, raw, status in cur.fetchall():
            details = load_details(raw)
            forms.append({
                "name": name, "label": issue_label(issue_type, details),
                "reason": details.get("reason"), "status": status,
            })
        return {
            "date": day.isoformat(),
            "studentCount": len(everyone),
            "checkedInCount": len(everyone) - len(no_check_in),
            "attendanceRequests": forms,
            "latestSpotCheck": absent["spotCheck"],
            "spotCheckAbsent": [s["name"] for s in absent["students"]],
        }

    def _targets(self, cur, uids) -> list[dict]:
        wanted = [str(u) for u in uids or [] if u]
        found = cohort_students(cur, self.cohort["id"], wanted) if wanted else {}
        missing = [u for u in wanted if u not in found]
        if missing:
            raise ValueError(f"이 기수 학생이 아닌 uid: {', '.join(missing[:5])}")
        cur.execute(
            "SELECT firebase_uid, display_name FROM users WHERE firebase_uid = ANY(%s) ORDER BY display_name",
            [list(found)],
        )
        return [{"uid": uid, "name": name} for uid, name in cur.fetchall()]

    def _tool_propose_alert(self, cur, args):
        title = str(args.get("title") or "").strip()
        content = str(args.get("content") or "").strip()
        if not title:
            raise ValueError("title required")
        everyone = bool(args.get("all_students"))
        targets = [] if everyone else self._targets(cur, args.get("target_user_ids"))
        if not everyone and not targets:
            raise ValueError("대상 학생이 없습니다. 조회 도구로 uid 를 먼저 찾거나 all_students=true 로 제안하세요.")
        action = {
            "id": uuid.uuid4().hex,
            "type": "send_alert",
            "title": title,
            "content": content,
            "linkUrl": str(args.get("link_url") or "").strip() or None,
            "endDate": _end_date_arg(args.get("end_date")),
            "allStudents": everyone,
            "targets": targets,
        }
        self.actions.append(action)
        return {"ok": True, "proposed": "send_alert", "targetCount": len(targets) if not everyone else "all"}

    def _tool_propose_notice(self, cur, args):
        title = str(args.get("title") or "").strip()
        if not title:
            raise ValueError("title required")
        action = {
            "id": uuid.uuid4().hex,
            "type": "create_notice",
            "title": title,
            "content": str(args.get("content") or "").strip(),
            "important": bool(args.get("important")),
        }
        self.actions.append(action)
        return {"ok": True, "proposed": "create_notice"}


def _log(user: dict, cohort_id: int, status: str, latency_ms: int, details: dict, error: str | None = None):
    try:
        with connection.cursor() as cur:
            cur.execute(
                """INSERT INTO ai_generation_logs
                       (type, cohort_id, created_by, prompt_version, model, status, error_message,
                        latency_ms, details, created_at)
                   VALUES ('admin_assistant', %s, %s, 'v1', %s, %s, %s, %s, %s::jsonb, now())""",
                [cohort_id, user["id"], _model(), status, error, latency_ms,
                 json.dumps(details, ensure_ascii=False)],
            )
    except Exception:  # 로그를 못 남겨도 대화는 이어 간다
        log.exception("admin assistant log failed")


def run_assistant(user: dict, cohort_id: int, messages, client=None) -> dict:
    if user.get("role") not in ("admin", "instructor"):
        raise AssistantError("forbidden", 403)
    cohort = _cohort(cohort_id)
    history = _clean_history(messages)
    session = _Session(user, cohort)
    client = client or _client()
    today = datetime.now(KST).date()
    convo: list[dict] = [{"role": "system", "content": _system_prompt(cohort, today)}, *history]
    started = time.perf_counter()
    tools_used: list[str] = []
    reply = ""
    try:
        for _ in range(MAX_TURNS):
            response = client.chat.completions.create(
                model=_model(), messages=convo, tools=TOOLS, **_effort_kwargs(_model()),
            )
            message = response.choices[0].message
            calls = message.tool_calls or []
            if not calls:
                reply = (message.content or "").strip()
                break
            convo.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            })
            for call in calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                tools_used.append(call.function.name)
                result = session.run_tool(call.function.name, args if isinstance(args, dict) else {})
                convo.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False, default=str)})
        else:
            reply = "요청을 끝까지 처리하지 못했습니다. 조금 더 구체적으로 말씀해 주세요."
    except AssistantError:
        raise
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        _log(user, cohort_id, "error", latency, {"tools": tools_used}, str(exc)[:500])
        log.exception("admin assistant failed")
        raise AssistantError("AI 어시스턴트에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.", 503) from exc
    latency = int((time.perf_counter() - started) * 1000)
    _log(user, cohort_id, "success", latency, {"tools": tools_used, "proposed": [a["type"] for a in session.actions]})
    reply = "\n".join(line for line in reply.splitlines() if not line.strip().startswith("[조회한 학생")).strip()
    if not reply:
        reply = "아래 내용을 확인하고 실행해 주세요." if session.actions else "답변을 만들지 못했습니다."
    return {"reply": reply, "actions": session.actions, "context": session.memo()}


def execute_action(user: dict, cohort_id: int, action: dict) -> dict:
    """확인 카드의 실행 — 기존 커맨드를 그대로 써서 권한 · 검증도 같게 한다."""
    if user.get("role") not in ("admin", "instructor"):
        raise AssistantError("forbidden", 403)
    cohort = _cohort(cohort_id)
    kind = (action or {}).get("type")
    title = str(action.get("title") or "").strip()
    if not title:
        raise AssistantError("title required")
    started = time.perf_counter()
    if kind == "send_alert":
        targets = [str(t.get("uid") if isinstance(t, dict) else t) for t in action.get("targets") or []]
        if not action.get("allStudents") and not targets:
            raise AssistantError("대상 학생이 없습니다.")
        result = dispatch(user, "upsertAlertPopup", {
            "action": "insert",
            "cohortId": cohort["code"],
            "title": title,
            "content": str(action.get("content") or ""),
            "linkUrl": action.get("linkUrl") or None,
            "endDate": action.get("endDate") or None,
            "isActive": True,
            "targetUserIds": [] if action.get("allStudents") else targets,
        })
        details = {"action": kind, "popupId": result.get("id"), "targetCount": len(targets)}
    elif kind == "create_notice":
        result = dispatch(user, "createNotice", {
            "cohortId": cohort["code"],
            "title": title,
            "content": str(action.get("content") or ""),
            "isFavorite": bool(action.get("important")),
            "priority": 1 if action.get("important") else 0,
        })
        details = {"action": kind, "noticeId": result.get("id")}
    else:
        raise AssistantError("unknown action")
    _log(user, cohort_id, "success", int((time.perf_counter() - started) * 1000), {"executed": details})
    return {"ok": True, **details}
