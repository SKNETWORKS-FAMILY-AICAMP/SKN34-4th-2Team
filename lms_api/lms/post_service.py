"""소통 피드 — 같은 기수 사람끼리 글 · 댓글 · 좋아요.

- 학생 · 강사는 자기 기수, 관리자는 고른 기수의 피드를 본다(can_access_cohort).
- 글 · 댓글은 쓴 사람이 지운다. 관리자 · 강사는 운영을 위해 남의 것도 지운다.
- 좋아요는 한 사람이 한 글에 한 번(uq_post_like_user). 다시 누르면 취소한다.
- 좋아요 · 댓글 수는 표에서 센다 — 따로 셈 칸을 두지 않아 어긋날 일이 없다.
DB 의 FK 는 ON DELETE 를 걸지 않으므로 글을 지울 때 좋아요 · 댓글을 먼저 지운다.
호출하는 쪽이 transaction.atomic 으로 감싼다.
"""

from __future__ import annotations

from datetime import date, datetime

from lms.permissions import can_access_cohort

MAX_POST_CHARS = 2000
MAX_COMMENT_CHARS = 500
PAGE_SIZE = 50
MODERATORS = ("admin", "instructor")


class PostError(Exception):
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


def _cohort_id(cur, user: dict, cohort_code: str) -> int:
    if user.get("role") == "student":
        return user["cohort_id"]
    cur.execute("SELECT id FROM cohorts WHERE code = %s", [cohort_code or user.get("cohort_code") or ""])
    row = cur.fetchone()
    if not row or not can_access_cohort(user, row[0]):
        raise PermissionError("cohort")
    return row[0]


def _text(value, limit: int, what: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise PostError(f"{what}을 적어 주세요.")
    if len(text) > limit:
        raise PostError(f"{what}은 {limit}자까지 쓸 수 있어요.")
    return text


def _public_post(row: dict, user: dict) -> dict:
    return {
        "id": str(row["id"]),
        "authorId": row["author_uid"] or str(row["author_id"]),
        "authorName": row["author_name"] or "",
        "content": row["content"],
        "likeCount": row["like_count"],
        "likedByMe": bool(row["liked_by_me"]),
        "commentCount": row["comment_count"],
        "createdAt": _iso(row["created_at"]),
        "canDelete": row["author_id"] == user["id"] or user.get("role") in MODERATORS,
    }


def _public_comment(row: dict, user: dict) -> dict:
    return {
        "id": str(row["id"]),
        "postId": str(row["post_id"]),
        "authorId": row["author_uid"] or str(row["author_id"]),
        "authorName": row["author_name"] or "",
        "content": row["content"],
        "createdAt": _iso(row["created_at"]),
        "canDelete": row["author_id"] == user["id"] or user.get("role") in MODERATORS,
    }


_POST_SELECT = """
    SELECT p.id, p.author_id, p.content, p.created_at, u.firebase_uid AS author_uid, u.display_name AS author_name,
           (SELECT count(*) FROM post_likes l WHERE l.post_id = p.id) AS like_count,
           EXISTS (SELECT 1 FROM post_likes l WHERE l.post_id = p.id AND l.user_id = %s) AS liked_by_me,
           (SELECT count(*) FROM post_comments c WHERE c.post_id = p.id) AS comment_count
      FROM posts p JOIN users u ON u.id = p.author_id
"""


def _post_row(cur, user: dict, post_id: int) -> dict:
    rows = _rows(cur, _POST_SELECT + " WHERE p.id = %s", [user["id"], post_id])
    return rows[0]


def _owned_post(cur, user: dict, post_id: int, lock: bool = False) -> dict:
    """The post if this user can see its cohort; 404 otherwise (another cohort's post stays invisible)."""
    rows = _rows(cur, "SELECT id, cohort_id, author_id FROM posts WHERE id = %s" + (" FOR UPDATE" if lock else ""),
                 [post_id])
    if not rows or not can_access_cohort(user, rows[0]["cohort_id"]):
        raise PostError("not_found", 404)
    return rows[0]


def list_posts(cur, user: dict, cohort_code: str = "", before: int | None = None) -> dict:
    cohort_id = _cohort_id(cur, user, cohort_code)
    where, args = " WHERE p.cohort_id = %s", [user["id"], cohort_id]
    if before:
        where += " AND p.id < %s"
        args.append(before)
    rows = _rows(cur, _POST_SELECT + where + " ORDER BY p.id DESC LIMIT %s", [*args, PAGE_SIZE])
    return {"posts": [_public_post(row, user) for row in rows]}


def create_post(cur, user: dict, data: dict) -> dict:
    cohort_id = _cohort_id(cur, user, str(data.get("cohort") or ""))
    content = _text(data.get("content"), MAX_POST_CHARS, "내용")
    cur.execute(
        "INSERT INTO posts (cohort_id, author_id, content, created_at, updated_at) VALUES (%s, %s, %s, now(), now()) RETURNING id",
        [cohort_id, user["id"], content],
    )
    return _public_post(_post_row(cur, user, cur.fetchone()[0]), user)


def delete_post(cur, user: dict, post_id: int) -> None:
    post = _owned_post(cur, user, post_id, lock=True)
    if post["author_id"] != user["id"] and user.get("role") not in MODERATORS:
        raise PermissionError("post author only")
    cur.execute("DELETE FROM post_likes WHERE post_id = %s", [post_id])
    cur.execute("DELETE FROM post_comments WHERE post_id = %s", [post_id])
    cur.execute("DELETE FROM posts WHERE id = %s", [post_id])


def toggle_like(cur, user: dict, post_id: int) -> dict:
    _owned_post(cur, user, post_id, lock=True)  # Serializes double clicks on the same post.
    cur.execute("DELETE FROM post_likes WHERE post_id = %s AND user_id = %s", [post_id, user["id"]])
    if cur.rowcount == 0:
        cur.execute("INSERT INTO post_likes (post_id, user_id, created_at) VALUES (%s, %s, now())", [post_id, user["id"]])
    return _public_post(_post_row(cur, user, post_id), user)


def list_comments(cur, user: dict, post_id: int) -> dict:
    _owned_post(cur, user, post_id)
    rows = _rows(cur, """
        SELECT c.id, c.post_id, c.author_id, c.content, c.created_at, u.firebase_uid AS author_uid,
               u.display_name AS author_name
          FROM post_comments c JOIN users u ON u.id = c.author_id
         WHERE c.post_id = %s ORDER BY c.id""", [post_id])
    return {"comments": [_public_comment(row, user) for row in rows]}


def create_comment(cur, user: dict, post_id: int, data: dict) -> dict:
    _owned_post(cur, user, post_id)
    content = _text(data.get("content"), MAX_COMMENT_CHARS, "댓글")
    cur.execute(
        "INSERT INTO post_comments (post_id, author_id, content, created_at) VALUES (%s, %s, %s, now()) RETURNING id",
        [post_id, user["id"], content],
    )
    comment_id = cur.fetchone()[0]
    rows = _rows(cur, """
        SELECT c.id, c.post_id, c.author_id, c.content, c.created_at, u.firebase_uid AS author_uid,
               u.display_name AS author_name
          FROM post_comments c JOIN users u ON u.id = c.author_id WHERE c.id = %s""", [comment_id])
    return _public_comment(rows[0], user)


def delete_comment(cur, user: dict, post_id: int, comment_id: int) -> None:
    _owned_post(cur, user, post_id)
    rows = _rows(cur, "SELECT author_id FROM post_comments WHERE id = %s AND post_id = %s FOR UPDATE",
                 [comment_id, post_id])
    if not rows:
        raise PostError("not_found", 404)
    if rows[0]["author_id"] != user["id"] and user.get("role") not in MODERATORS:
        raise PermissionError("comment author only")
    cur.execute("DELETE FROM post_comments WHERE id = %s", [comment_id])
