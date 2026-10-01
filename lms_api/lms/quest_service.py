"""마일리지 퀘스트 — 관리자가 만들고, 학생이 인증을 내고, 완료되면 마일리지가 자동으로 들어간다.

- approval=auto: 제출하는 순간 지급. 남용을 막으려고 마감일(end_on)이 꼭 있어야 한다.
- approval=manual: 관리자가 승인하는 순간 지급. 반려하면 학생이 다시 낼 수 있다.
- 승인 취소(revoke)는 지급한 만큼 마이너스 내역을 남기고 잔액에서 뺀다.

지급 · 회수는 제출 줄을 FOR UPDATE 로 잠근 한 트랜잭션 안에서 내역 INSERT 와 잔액 UPDATE 를 같이 한다.
그래서 두 번 누르거나 동시에 눌러도 한 번만 들어간다. 호출하는 쪽이 transaction.atomic 으로 감싼다.
"""

from __future__ import annotations

from datetime import date, datetime

from lms.permissions import can_access_cohort

EVIDENCE_TYPES = ("none", "text", "link", "file")
APPROVALS = ("manual", "auto")
MAX_REWARD = 1_000_000
MAX_COMPLETIONS = 100
MAX_TITLE_CHARS = 100
MAX_DESCRIPTION_CHARS = 3000
MAX_TEXT_CHARS = 3000
MAX_LINK_CHARS = 500
MAX_FILES = 5
TX_GRANT = "quest"
TX_REVOKE = "quest_revoke"


class QuestError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _rows(cur, sql: str, args: list) -> list[dict]:
    cur.execute(sql, args)
    names = [column[0] for column in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def _iso(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionError("admin only")


def _cohort_id(cur, user: dict, cohort_code: str) -> int:
    if user.get("role") == "student":
        return user["cohort_id"]
    cur.execute("SELECT id FROM cohorts WHERE code = %s", [cohort_code or user.get("cohort_code") or ""])
    row = cur.fetchone()
    if not row or not can_access_cohort(user, row[0]):
        raise PermissionError("cohort")
    return row[0]


def _today() -> date:
    from django.utils import timezone

    return timezone.localdate()


def _open_now(quest: dict) -> bool:
    today = _today()
    return (
        quest["published"] and not quest["closed"]
        and (quest["start_on"] is None or quest["start_on"] <= today)
        and (quest["end_on"] is None or today <= quest["end_on"])
    )


def _quest_json(q: dict) -> dict:
    return {
        "id": str(q["id"]), "title": q["title"], "description": q["description"],
        "reward": q["reward"], "evidenceType": q["evidence_type"], "approval": q["approval"],
        "maxCompletions": q["max_completions"], "startOn": _iso(q["start_on"]), "endOn": _iso(q["end_on"]),
        "published": q["published"], "closed": q["closed"], "open": _open_now(q),
        "createdAt": _iso(q["created_at"]),
    }


def _submission_json(s: dict) -> dict:
    from lms.storage import read_url

    return {
        "id": str(s["id"]), "questId": str(s["quest_id"]), "questTitle": s.get("quest_title") or "",
        "uid": s.get("student_uid") or "", "studentName": s.get("student_name") or "",
        "status": s["status"], "text": s["text"], "link": s["link"],
        "files": [{"key": k, "url": read_url(k)} for k in (s["file_keys"] or [])],
        "reviewComment": s["review_comment"], "grantedAmount": s["granted_amount"],
        "submittedAt": _iso(s["submitted_at"]), "reviewedAt": _iso(s["reviewed_at"]),
    }


_SUBMISSIONS = """SELECT s.*, q.title AS quest_title, u.firebase_uid AS student_uid, u.display_name AS student_name
                  FROM quest_submissions s JOIN quests q ON q.id = s.quest_id JOIN users u ON u.id = s.user_id"""


# ── 조회 ─────────────────────────────────────────────


def list_quests(cur, user: dict, cohort_code: str = "") -> dict:
    """관리자: 기수 퀘스트 전체 + 상태별 제출 수. 학생: 공개된 퀘스트 + 내 제출."""
    cohort_id = _cohort_id(cur, user, cohort_code)
    staff = user.get("role") == "admin"
    if user.get("role") not in ("admin", "student"):
        raise PermissionError("role")
    quests = _rows(
        cur,
        f"""SELECT * FROM quests WHERE cohort_id = %s {'' if staff else 'AND published = true'}
            ORDER BY closed, COALESCE(end_on, '9999-12-31'::date), id DESC""",
        [cohort_id],
    )
    if staff:
        counts = _rows(
            cur,
            """SELECT quest_id, status, COUNT(*) AS n FROM quest_submissions WHERE cohort_id = %s
               GROUP BY quest_id, status""",
            [cohort_id],
        )
        stats: dict[int, dict] = {}
        for c in counts:
            stats.setdefault(c["quest_id"], {})[c["status"]] = c["n"]
        return {"quests": [{**_quest_json(q), "counts": stats.get(q["id"], {})} for q in quests]}
    mine = _rows(cur, f"{_SUBMISSIONS} WHERE s.user_id = %s ORDER BY s.submitted_at DESC", [user["id"]])
    return {"quests": [_quest_json(q) for q in quests], "submissions": [_submission_json(s) for s in mine]}


def list_submissions(cur, user: dict, cohort_code: str = "", status: str = "", quest_id: str = "") -> list[dict]:
    _require_admin(user)
    cohort_id = _cohort_id(cur, user, cohort_code)
    where, args = ["s.cohort_id = %s"], [cohort_id]
    if status:
        where.append("s.status = %s")
        args.append(status)
    if quest_id:
        where.append("s.quest_id = %s")
        args.append(int(quest_id))
    rows = _rows(cur, f"{_SUBMISSIONS} WHERE {' AND '.join(where)} ORDER BY s.submitted_at DESC LIMIT 500", args)
    return [_submission_json(s) for s in rows]


# ── 관리자: 등록 · 수정 ───────────────────────────────


def _date(value, field: str) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise QuestError(f"{field} 날짜 형식이 올바르지 않습니다.") from exc


def _clean_quest(data: dict, current: dict | None) -> dict:
    """화면 값 → 컬럼 값. 수정이면 들어온 칸만 바꾸고 나머지는 지금 값으로 검사한다."""
    merged = dict(current or {})

    def take(key: str, column: str, convert):
        if current is None or key in data:
            merged[column] = convert(data.get(key))

    take("title", "title", lambda v: str(v or "").strip())
    take("description", "description", lambda v: str(v or "").strip())
    take("reward", "reward", lambda v: int(v) if str(v or "").lstrip("-").isdigit() else 0)
    take("evidenceType", "evidence_type", lambda v: v or "none")
    take("approval", "approval", lambda v: v or "manual")
    take("maxCompletions", "max_completions", lambda v: int(v) if str(v or "").isdigit() else 1)
    take("startOn", "start_on", lambda v: _date(v, "시작일"))
    take("endOn", "end_on", lambda v: _date(v, "마감일"))
    take("published", "published", bool)
    take("closed", "closed", bool)

    if not merged["title"] or len(merged["title"]) > MAX_TITLE_CHARS:
        raise QuestError(f"제목은 1~{MAX_TITLE_CHARS}자로 적어 주세요.")
    if len(merged["description"]) > MAX_DESCRIPTION_CHARS:
        raise QuestError(f"설명은 {MAX_DESCRIPTION_CHARS}자까지 적을 수 있습니다.")
    if not 1 <= merged["reward"] <= MAX_REWARD:
        raise QuestError(f"보상은 1~{MAX_REWARD:,}M 사이로 정해 주세요.")
    if merged["evidence_type"] not in EVIDENCE_TYPES:
        raise QuestError("인증 방식이 올바르지 않습니다.")
    if merged["approval"] not in APPROVALS:
        raise QuestError("완료 방식이 올바르지 않습니다.")
    if not 1 <= merged["max_completions"] <= MAX_COMPLETIONS:
        raise QuestError(f"받을 수 있는 횟수는 1~{MAX_COMPLETIONS}회로 정해 주세요.")
    if merged["start_on"] and merged["end_on"] and merged["start_on"] > merged["end_on"]:
        raise QuestError("시작일이 마감일보다 늦습니다.")
    if merged["approval"] == "auto" and not merged["end_on"]:
        raise QuestError("제출 즉시 지급 미션은 마감일을 꼭 정해 주세요.")
    return {k: merged[k] for k in (
        "title", "description", "reward", "evidence_type", "approval", "max_completions",
        "start_on", "end_on", "published", "closed",
    )}


def create_quest(cur, user: dict, data: dict) -> dict:
    _require_admin(user)
    cohort_id = _cohort_id(cur, user, data.get("cohortId") or "")
    values = _clean_quest(data, None)
    columns = ", ".join(values)
    marks = ", ".join(["%s"] * len(values))
    cur.execute(
        f"""INSERT INTO quests (cohort_id, {columns}, created_by_id, created_at, updated_at)
            VALUES (%s, {marks}, %s, now(), now()) RETURNING *""",
        [cohort_id, *values.values(), user["id"]],
    )
    names = [column[0] for column in cur.description]
    return _quest_json(dict(zip(names, cur.fetchone())))


def update_quest(cur, user: dict, pk: int, data: dict) -> dict:
    _require_admin(user)
    rows = _rows(cur, "SELECT * FROM quests WHERE id = %s FOR UPDATE", [pk])
    if not rows or not can_access_cohort(user, rows[0]["cohort_id"]):
        raise QuestError("마일리지 미션을 찾지 못했습니다.", 404)
    current = rows[0]
    values = _clean_quest(data, current)
    # 이미 지급된 퀘스트의 보상을 바꾸면 학생마다 받은 금액이 달라진다 — 회수 · 지급은 제출에 남은 금액으로 한다
    sets = ", ".join(f"{column} = %s" for column in values)
    cur.execute(f"UPDATE quests SET {sets}, updated_at = now() WHERE id = %s RETURNING *", [*values.values(), pk])
    names = [column[0] for column in cur.description]
    return _quest_json(dict(zip(names, cur.fetchone())))


# ── 지급 · 회수 ───────────────────────────────────────


def _grant(cur, submission: dict, quest: dict, actor_id: int | None) -> int:
    amount = quest["reward"]
    cur.execute(
        """INSERT INTO mileage_transactions (cohort_id, user_id, amount, type, reason, related_id, adjusted_by, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
        [submission["cohort_id"], submission["user_id"], amount, TX_GRANT,
         f"마일리지 미션 완료: {quest['title']}", f"quest_submission:{submission['id']}", actor_id],
    )
    cur.execute("UPDATE users SET mileage_balance = mileage_balance + %s WHERE id = %s", [amount, submission["user_id"]])
    return amount


def _revoke(cur, submission: dict, quest_title: str, actor_id: int) -> None:
    amount = submission["granted_amount"]
    if amount <= 0:
        return
    cur.execute(
        """INSERT INTO mileage_transactions (cohort_id, user_id, amount, type, reason, related_id, adjusted_by, created_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, now())""",
        [submission["cohort_id"], submission["user_id"], -amount, TX_REVOKE,
         f"마일리지 미션 승인 취소: {quest_title}", f"quest_submission:{submission['id']}", actor_id],
    )
    cur.execute("UPDATE users SET mileage_balance = mileage_balance - %s WHERE id = %s", [amount, submission["user_id"]])


# ── 학생: 제출 ────────────────────────────────────────


def _clean_evidence(user: dict, quest: dict, data: dict) -> dict:
    kind = quest["evidence_type"]
    text = str(data.get("text") or "").strip()
    link = str(data.get("link") or "").strip()
    keys = [str(k) for k in (data.get("fileKeys") or []) if k]
    if len(text) > MAX_TEXT_CHARS:
        raise QuestError(f"글은 {MAX_TEXT_CHARS}자까지 적을 수 있습니다.")
    if len(link) > MAX_LINK_CHARS:
        raise QuestError("링크가 너무 깁니다.")
    if link and not link.startswith(("https://", "http://")):
        raise QuestError("링크는 http:// 나 https:// 로 시작해야 합니다.")
    if len(keys) > MAX_FILES:
        raise QuestError(f"파일은 {MAX_FILES}개까지 올릴 수 있습니다.")
    owner = f"/{user['firebase_uid']}/"
    if any(not k.startswith("records/") or owner not in k for k in keys):
        raise PermissionError("본인이 올린 파일만 붙일 수 있습니다.")
    if kind == "text" and not text:
        raise QuestError("인증 내용을 적어 주세요.")
    if kind == "link" and not link:
        raise QuestError("인증 링크를 붙여 주세요.")
    if kind == "file" and not keys:
        raise QuestError("인증 사진이나 파일을 올려 주세요.")
    return {"text": text, "link": link, "file_keys": keys}


def submit_quest(cur, user: dict, pk: int, data: dict) -> dict:
    import json

    if user.get("role") != "student":
        raise PermissionError("student only")
    rows = _rows(cur, "SELECT * FROM quests WHERE id = %s", [pk])
    quest = rows[0] if rows else None
    if not quest or quest["cohort_id"] != user["cohort_id"] or not quest["published"]:
        raise QuestError("마일리지 미션을 찾지 못했습니다.", 404)
    if not _open_now(quest):
        raise QuestError("지금은 참여할 수 있는 기간이 아닙니다.")
    evidence = _clean_evidence(user, quest, data)
    # 같은 학생이 같은 퀘스트를 동시에 두 번 내도 횟수 검사가 어긋나지 않게 잠근다
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"quest:{pk}:user:{user['id']}"])
    cur.execute(
        "SELECT status, COUNT(*) FROM quest_submissions WHERE quest_id = %s AND user_id = %s GROUP BY status",
        [pk, user["id"]],
    )
    counts = dict(cur.fetchall())
    if counts.get("pending"):
        raise QuestError("검토 중인 제출이 있습니다. 결과가 나온 뒤 다시 낼 수 있어요.", 409)
    if counts.get("approved", 0) >= quest["max_completions"]:
        raise QuestError("이 미션은 받을 수 있는 횟수를 모두 채웠습니다.", 409)
    auto = quest["approval"] == "auto"
    cur.execute(
        """INSERT INTO quest_submissions (quest_id, user_id, cohort_id, status, text, link, file_keys,
               review_comment, granted_amount, reviewed_at, submitted_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, '', 0, CASE WHEN %s THEN now() END, now(), now()) RETURNING *""",
        [pk, user["id"], user["cohort_id"], "approved" if auto else "pending",
         evidence["text"], evidence["link"], json.dumps(evidence["file_keys"]), auto],
    )
    names = [column[0] for column in cur.description]
    submission = dict(zip(names, cur.fetchone()))
    if auto:
        amount = _grant(cur, submission, quest, None)
        cur.execute("UPDATE quest_submissions SET granted_amount = %s WHERE id = %s", [amount, submission["id"]])
        submission["granted_amount"] = amount
    submission["quest_title"] = quest["title"]
    return _submission_json(submission)


# ── 관리자: 심사 ──────────────────────────────────────


def review_submission(cur, user: dict, pk: int, data: dict) -> dict:
    """approve: 대기 → 승인 + 지급 / reject: 대기 → 반려 / revoke: 승인 → 취소 + 회수"""
    _require_admin(user)
    decision = data.get("decision")
    comment = str(data.get("comment") or "").strip()[:1000]
    rows = _rows(cur, "SELECT * FROM quest_submissions WHERE id = %s FOR UPDATE", [pk])
    submission = rows[0] if rows else None
    if not submission or not can_access_cohort(user, submission["cohort_id"]):
        raise QuestError("제출을 찾지 못했습니다.", 404)
    quest = _rows(cur, "SELECT * FROM quests WHERE id = %s", [submission["quest_id"]])[0]
    status = submission["status"]

    if decision == "approve":
        if status != "pending":
            raise QuestError("검토 대기 중인 제출만 승인할 수 있습니다.", 409)
        cur.execute(
            "SELECT COUNT(*) FROM quest_submissions WHERE quest_id = %s AND user_id = %s AND status = 'approved'",
            [quest["id"], submission["user_id"]],
        )
        if cur.fetchone()[0] >= quest["max_completions"]:
            raise QuestError("이 학생은 받을 수 있는 횟수를 이미 채웠습니다.", 409)
        amount = _grant(cur, submission, quest, user["id"])
        new_status, granted = "approved", amount
    elif decision == "reject":
        if status != "pending":
            raise QuestError("검토 대기 중인 제출만 반려할 수 있습니다.", 409)
        if not comment:
            raise QuestError("반려 사유를 적어 주세요.")
        new_status, granted = "rejected", 0
    elif decision == "revoke":
        if status != "approved":
            raise QuestError("승인된 제출만 취소할 수 있습니다.", 409)
        _revoke(cur, submission, quest["title"], user["id"])
        new_status, granted = "revoked", 0
    else:
        raise QuestError("decision 은 approve · reject · revoke 중 하나입니다.")

    cur.execute(
        """UPDATE quest_submissions SET status = %s, granted_amount = %s, review_comment = %s,
               reviewed_by_id = %s, reviewed_at = now(), updated_at = now()
           WHERE id = %s""",
        [new_status, granted, comment, user["id"], pk],
    )
    return _submission_json(_rows(cur, f"{_SUBMISSIONS} WHERE s.id = %s", [pk])[0])
