"""설문 · 제출 — 구글폼 링크 대신 LMS 안에서 질문을 만들고 응답을 받는다.

submission_tasks.submission_type 이 'builtin' 이면 LMS 설문, 'external_form' 이면 예전처럼 외부 폼 링크다.
질문은 submission_tasks.questions(jsonb 목록), 응답은 submission_responses.response = {"answers": {질문 id: 값}}.
외부 폼은 링크를 열면 제출로 치지만(content_commands.op_mark_form_responded), LMS 설문은 실제로 내야 제출이다.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timezone

QUESTION_TYPES = ("short", "long", "single", "multi", "scale", "date")
MODES = ("builtin", "external_form")
MAX_QUESTIONS = 50
MAX_OPTIONS = 30
TITLE_MAX = 200
SHORT_MAX = 300
LONG_MAX = 5000
_QID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# commands 가 맨 아래에서 이 모듈의 OPS 를 가져가므로, commands 쪽 도움 함수는 쓸 때 가져온다
def _commands():
    from lms import commands

    return commands


def _text(value, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _load(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def clean_questions(raw) -> list[dict]:
    """관리자가 보낸 질문 목록을 정리한다. 모양이 틀리면 ValueError(화면에 그대로 보인다)."""
    if not isinstance(raw, list):
        raise ValueError("질문 목록이 올바르지 않습니다.")
    if len(raw) > MAX_QUESTIONS:
        raise ValueError(f"질문은 {MAX_QUESTIONS}개까지 넣을 수 있습니다.")
    out: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError("질문 목록이 올바르지 않습니다.")
        qtype = item.get("type")
        if qtype not in QUESTION_TYPES:
            raise ValueError(f"{index}번 질문의 종류가 올바르지 않습니다.")
        title = _text(item.get("title"), TITLE_MAX)
        if not title:
            raise ValueError(f"{index}번 질문 내용을 입력해 주세요.")
        qid = str(item.get("id") or "")
        if not _QID.match(qid) or qid in seen:
            qid = uuid.uuid4().hex[:8]
        seen.add(qid)
        question = {"id": qid, "type": qtype, "title": title, "required": bool(item.get("required"))}
        description = _text(item.get("description"), 500)
        if description:
            question["description"] = description
        if qtype in ("single", "multi"):
            options: list[str] = []
            for option in item.get("options") or []:
                text = _text(option, TITLE_MAX)
                if text and text not in options:
                    options.append(text)
            if len(options) < 2:
                raise ValueError(f"{index}번 질문에 보기를 두 개 이상 넣어 주세요.")
            if len(options) > MAX_OPTIONS:
                raise ValueError(f"{index}번 질문의 보기는 {MAX_OPTIONS}개까지입니다.")
            question["options"] = options
        if qtype == "scale":
            try:
                scale_max = int(item.get("scaleMax") or 5)
            except (TypeError, ValueError):
                scale_max = 5
            question["scaleMax"] = min(10, max(2, scale_max))
            for key in ("minLabel", "maxLabel"):
                label = _text(item.get(key), 30)
                if label:
                    question[key] = label
        out.append(question)
    return out


def _is_empty(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip()) or (isinstance(value, list) and not value)


def validate_answers(questions: list[dict], raw) -> dict:
    """학생 답을 질문에 맞춰 정리한다. 필수 누락 · 없는 보기 · 범위 밖 값은 ValueError."""
    answers = raw if isinstance(raw, dict) else {}
    out: dict = {}
    for q in questions:
        value = answers.get(q["id"])
        title = q["title"]
        if _is_empty(value):
            if q.get("required"):
                raise ValueError(f"「{title}」에 답해 주세요.")
            continue
        qtype = q["type"]
        if qtype in ("short", "long"):
            if not isinstance(value, str):
                raise ValueError(f"「{title}」 답이 올바르지 않습니다.")
            limit = SHORT_MAX if qtype == "short" else LONG_MAX
            text = value.strip()
            if len(text) > limit:
                raise ValueError(f"「{title}」은(는) {limit}자까지 쓸 수 있습니다.")
            out[q["id"]] = text
        elif qtype == "single":
            if value not in q.get("options", []):
                raise ValueError(f"「{title}」 보기에서 골라 주세요.")
            out[q["id"]] = value
        elif qtype == "multi":
            if not isinstance(value, list) or any(v not in q.get("options", []) for v in value):
                raise ValueError(f"「{title}」 보기에서 골라 주세요.")
            out[q["id"]] = [o for o in q["options"] if o in value]
        elif qtype == "scale":
            try:
                score = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"「{title}」 점수가 올바르지 않습니다.") from None
            if not 1 <= score <= int(q.get("scaleMax") or 5):
                raise ValueError(f"「{title}」 점수가 올바르지 않습니다.")
            out[q["id"]] = score
        elif qtype == "date":
            if not isinstance(value, str) or not _DAY.match(value):
                raise ValueError(f"「{title}」 날짜가 올바르지 않습니다.")
            try:
                date.fromisoformat(value)
            except ValueError:
                raise ValueError(f"「{title}」 날짜가 올바르지 않습니다.") from None
            out[q["id"]] = value
    return out


def _parse_due(value) -> datetime:
    if not value:
        raise ValueError("마감 일시를 입력해 주세요.")
    try:
        due = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("마감 일시가 올바르지 않습니다.") from None
    return due if due.tzinfo else due.replace(tzinfo=timezone.utc)


def _task_cohorts(cur, task_id: int) -> list[int]:
    cur.execute("SELECT cohort_id FROM submission_task_cohorts WHERE task_id = %s", [task_id])
    return [r[0] for r in cur.fetchall()]


def _require_task_access(cur, user: dict, task: dict) -> None:
    cmd = _commands()
    if not any(cmd.can_access_cohort(user, c) for c in _task_cohorts(cur, task["id"])):
        raise PermissionError("cohort")


def _public_id(task: dict) -> str:
    return str(task.get("legacy_id") or task["id"])


def op_save_form_task(cur, user, p):
    """설문 등록 · 수정(강사 · 관리자). mode='builtin' 이면 질문, 'external_form' 이면 폼 주소가 있어야 한다."""
    cmd = _commands()
    cmd._require_staff(user)
    title = _text(p.get("title"), TITLE_MAX)
    if not title:
        raise ValueError("제목을 입력해 주세요.")
    mode = p.get("mode") if p.get("mode") in MODES else "external_form"
    url = _text(p.get("formUrl"), 1000)
    questions = clean_questions(p.get("questions") or []) if mode == "builtin" else []
    if mode == "builtin" and not questions:
        raise ValueError("질문을 하나 이상 넣어 주세요.")
    if mode == "external_form" and not url.startswith(("https://", "http://")):
        raise ValueError("폼 주소(https://…)를 입력해 주세요.")
    values = [
        title,
        _text(p.get("description"), 2000),
        mode,
        url or None,
        _text(p.get("notionGuideUrl"), 1000) or None,
        _parse_due(p.get("dueAt")),
        bool(p.get("published", True)),
        json.dumps(questions, ensure_ascii=False),
    ]
    task = cmd.resolve_row(cur, "submission_tasks", p["id"]) if p.get("id") else None
    if task:
        _require_task_access(cur, user, task)
        cur.execute(
            """UPDATE submission_tasks
               SET title = %s, description = %s, submission_type = %s, external_url = %s, guide_url = %s,
                   due_at = %s, published = %s, questions = %s::jsonb, updated_at = now()
               WHERE id = %s""",
            [*values, task["id"]],
        )
        return {"id": _public_id(task)}
    cohort_id = cmd.resolve_cohort(cur, p.get("cohortId"), user)
    if cohort_id is None or not cmd.can_access_cohort(user, cohort_id):
        raise PermissionError("cohort")
    cur.execute(
        """INSERT INTO submission_tasks (title, description, submission_type, external_url, guide_url,
               due_at, published, questions, created_at, updated_at)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb, now(), now()) RETURNING id""",
        values,
    )
    pk = cur.fetchone()[0]
    cur.execute("INSERT INTO submission_task_cohorts (task_id, cohort_id) VALUES (%s,%s)", [pk, cohort_id])
    return {"id": str(pk)}


def op_delete_form_task(cur, user, p):
    cmd = _commands()
    cmd._require_staff(user)
    task = cmd.resolve_row(cur, "submission_tasks", p["id"])
    if not task:
        return {"ok": True}
    _require_task_access(cur, user, task)
    cur.execute("DELETE FROM submission_responses WHERE task_id = %s", [task["id"]])
    cur.execute("DELETE FROM submission_task_cohorts WHERE task_id = %s", [task["id"]])
    cur.execute("DELETE FROM submission_tasks WHERE id = %s", [task["id"]])
    return {"ok": True}


def op_submit_form_response(cur, user, p):
    """학생이 LMS 설문을 낸다. 마감 전이면 다시 내서 고칠 수 있다(마지막 것이 남는다)."""
    cmd = _commands()
    if user.get("role") != "student":
        raise PermissionError("student only")
    task = cmd.resolve_row(cur, "submission_tasks", p.get("taskId"))
    if not task:
        raise KeyError("form")
    _require_task_access(cur, user, task)
    if task.get("submission_type") != "builtin":
        raise ValueError("이 설문은 외부 폼에서 제출합니다.")
    if not task.get("published"):
        raise ValueError("아직 공개되지 않은 설문입니다.")
    now = datetime.now(timezone.utc)
    if task.get("due_at") and task["due_at"] < now:
        raise ValueError("마감이 지나 제출할 수 없습니다.")
    questions = _load(task.get("questions")) or []
    answers = validate_answers(questions, p.get("answers"))
    cur.execute(
        """INSERT INTO submission_responses (task_id, user_id, source, response, submitted_at)
           VALUES (%s,%s,'builtin',%s::jsonb, now())
           ON CONFLICT (task_id, user_id) DO UPDATE
           SET source = EXCLUDED.source, response = EXCLUDED.response, submitted_at = now()""",
        [task["id"], user["id"], json.dumps({"answers": answers}, ensure_ascii=False)],
    )
    return {"ok": True, "answers": answers, "submittedAt": now.isoformat()}


FORM_SURVEY_OPS = {
    "saveFormTask": op_save_form_task,
    "deleteFormTask": op_delete_form_task,
    "submitFormResponse": op_submit_form_response,
}
