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
from datetime import datetime

from django.db import connection

from lms.attendance_requests import issue_label, load_details
from lms.commands import dispatch
from lms.manager_commands import KST, STUDENT_FILTERS, cohort_students, find_students, parse_day

log = logging.getLogger(__name__)

MAX_TURNS = 6
MAX_HISTORY = 12
MAX_MESSAGE_CHARS = 4000
WEEKDAYS = "월화수목금토일"
ATTENDANCE_REQUEST_PATH = "/attendance-request"

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
        return find_students(cur, self.cohort["id"], parse_day(args.get("date")), list(args.get("filters") or []))

    def _tool_search_students(self, cur, args):
        name = str(args.get("name") or "").strip()
        result = find_students(cur, self.cohort["id"], parse_day(None), [])
        return {"students": [s for s in result["students"] if name and name in (s["name"] or "")]}

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
            response = client.chat.completions.create(model=_model(), messages=convo, tools=TOOLS)
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
    if not reply:
        reply = "아래 내용을 확인하고 실행해 주세요." if session.actions else "답변을 만들지 못했습니다."
    return {"reply": reply, "actions": session.actions}


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
