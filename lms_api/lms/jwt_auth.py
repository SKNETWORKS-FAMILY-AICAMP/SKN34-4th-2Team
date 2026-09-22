"""LMS users 테이블 기준 JWT. Django auth_user / dj-rest-auth 없음."""

from __future__ import annotations

from django.db import connection
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken


class AuthError(Exception):
    """토큰/사용자 인증 실패."""


def load_lms_user(firebase_uid: str | None) -> dict | None:
    if not firebase_uid:
        return None
    with connection.cursor() as cur:
        cur.execute(
            """SELECT u.id, u.firebase_uid, u.email, u.display_name, u.role, u.cohort_id,
                      u.is_active, u.must_change_password, c.code
               FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
               WHERE u.firebase_uid = %s""",
            [firebase_uid],
        )
        row = cur.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "firebase_uid": row[1],
        "email": row[2],
        "display_name": row[3],
        "role": row[4],
        "cohort_id": row[5],
        "is_active": row[6],
        "must_change_password": bool(row[7]),
        "cohort_code": row[8],
    }


def issue_tokens(user: dict) -> dict:
    refresh = RefreshToken()
    refresh["uid"] = user["firebase_uid"]
    refresh["role"] = user["role"]
    refresh["user_id"] = user["id"]
    access = refresh.access_token
    access["uid"] = user["firebase_uid"]
    access["role"] = user["role"]
    access["user_id"] = user["id"]
    return {"access": str(access), "refresh": str(refresh)}


def user_from_access(raw: str) -> dict:
    try:
        token = AccessToken(raw)
    except TokenError as exc:
        raise AuthError("invalid token") from exc
    user = load_lms_user(str(token.get("uid") or ""))
    if not user or not user.get("is_active"):
        raise AuthError("user not found")
    return user
