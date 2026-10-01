"""정기 상담 기록 — 관리자만 보고 쓴다.

상담 내용은 민감하고 계속 쌓이므로 bootstrap 에 넣지 않는다. 학생 상세 · 상담 현황 화면이 열 때 받는다.
기수 단위 조회(현황)는 내용을 빼고 차수 · 날짜 · 후속 조치 여부만 보낸다.
"""

from __future__ import annotations

from datetime import date

CATEGORIES = ("regular", "adhoc", "career", "other")
MAX_ROUND = 99
MAX_CONTENT_CHARS = 5000
MAX_FOLLOW_UP_CHARS = 1000


class CounselError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionError("admin only")


def _iso(value):
    return value.isoformat() if value else None


def _note_json(row: dict, full: bool) -> dict:
    out = {
        "id": str(row["id"]),
        "uid": row["student_uid"],
        "cohortId": row["cohort_code"],
        "round": row["round"],
        "counseledOn": _iso(row["counseled_on"]),
        "category": row["category"],
        "followUp": row["follow_up"] or "",
        "followUpDone": row["follow_up_done"],
        "nextOn": _iso(row["next_on"]),
        "counselorName": row["counselor_name"] or "",
        "createdAt": _iso(row["created_at"]),
        "updatedAt": _iso(row["updated_at"]),
    }
    if full:
        out["content"] = row["content"]
    return out


_SELECT = """SELECT n.*, s.firebase_uid AS student_uid, co.code AS cohort_code, c.display_name AS counselor_name
             FROM student_counsel_notes n
             JOIN users s ON s.id = n.user_id
             JOIN cohorts co ON co.id = n.cohort_id
             LEFT JOIN users c ON c.id = n.counselor_id"""


def _rows(cur, sql: str, args: list) -> list[dict]:
    cur.execute(sql, args)
    names = [column[0] for column in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def list_notes(cur, user: dict, student_uid: str = "", cohort_code: str = "") -> list[dict]:
    """student 를 주면 그 학생의 전체 기록, cohort 를 주면 기수 전체의 요약(내용 제외)."""
    _require_admin(user)
    if student_uid:
        rows = _rows(cur, f"{_SELECT} WHERE s.firebase_uid = %s ORDER BY n.round DESC, n.counseled_on DESC, n.id DESC",
                     [student_uid])
        return [_note_json(r, full=True) for r in rows]
    if cohort_code:
        rows = _rows(cur, f"{_SELECT} WHERE co.code = %s ORDER BY n.counseled_on DESC, n.id DESC", [cohort_code])
        return [_note_json(r, full=False) for r in rows]
    raise CounselError("student or cohort required")


def _date(value, field: str, required: bool) -> date | None:
    if value in (None, ""):
        if required:
            raise CounselError(f"{field} required")
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise CounselError(f"{field} invalid") from exc


def _text(value, field: str, limit: int, required: bool) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise CounselError(f"{field} required")
    if len(text) > limit:
        raise CounselError(f"{field} too long")
    return text


def _clean(data: dict, partial: bool) -> dict:
    """화면 값 → 컬럼 값. partial 이면 들어온 칸만 검사해 돌려준다(후속 조치 체크 등)."""
    out: dict = {}

    def given(key: str) -> bool:
        return not partial or key in data

    if given("round"):
        try:
            round_no = int(data.get("round"))
        except (TypeError, ValueError) as exc:
            raise CounselError("round invalid") from exc
        if not 1 <= round_no <= MAX_ROUND:
            raise CounselError("round invalid")
        out["round"] = round_no
    if given("counseledOn"):
        out["counseled_on"] = _date(data.get("counseledOn"), "counseledOn", required=True)
    if given("category"):
        category = data.get("category") or "regular"
        if category not in CATEGORIES:
            raise CounselError("category invalid")
        out["category"] = category
    if given("content"):
        out["content"] = _text(data.get("content"), "content", MAX_CONTENT_CHARS, required=True)
    if given("followUp"):
        out["follow_up"] = _text(data.get("followUp"), "followUp", MAX_FOLLOW_UP_CHARS, required=False)
    if given("followUpDone"):
        out["follow_up_done"] = bool(data.get("followUpDone"))
    if given("nextOn"):
        out["next_on"] = _date(data.get("nextOn"), "nextOn", required=False)
    return out


def _one(cur, pk: int) -> dict:
    rows = _rows(cur, f"{_SELECT} WHERE n.id = %s", [pk])
    if not rows:
        raise CounselError("not found", 404)
    return _note_json(rows[0], full=True)


def create_note(cur, user: dict, data: dict) -> dict:
    _require_admin(user)
    cur.execute("SELECT id, cohort_id FROM users WHERE firebase_uid = %s AND role = 'student'", [data.get("uid") or ""])
    student = cur.fetchone()
    if not student or student[1] is None:
        raise CounselError("student not found", 404)
    values = _clean(data, partial=False)
    cur.execute(
        """INSERT INTO student_counsel_notes
             (user_id, cohort_id, round, counseled_on, category, content, follow_up, follow_up_done, next_on,
              counselor_id, created_at, updated_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now()) RETURNING id""",
        [student[0], student[1], values["round"], values["counseled_on"], values["category"], values["content"],
         values["follow_up"], values["follow_up_done"], values["next_on"], user["id"]],
    )
    return _one(cur, cur.fetchone()[0])


def update_note(cur, user: dict, pk: int, data: dict) -> dict:
    _require_admin(user)
    values = _clean(data, partial=True)
    if values:
        sets = ", ".join(f"{column} = %s" for column in values)
        cur.execute(
            f"UPDATE student_counsel_notes SET {sets}, updated_at = now() WHERE id = %s",
            [*values.values(), pk],
        )
        if cur.rowcount == 0:
            raise CounselError("not found", 404)
    return _one(cur, pk)


def delete_note(cur, user: dict, pk: int) -> None:
    _require_admin(user)
    cur.execute("DELETE FROM student_counsel_notes WHERE id = %s", [pk])
    if cur.rowcount == 0:
        raise CounselError("not found", 404)
