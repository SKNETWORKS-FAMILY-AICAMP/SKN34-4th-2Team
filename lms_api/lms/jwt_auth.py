"""LMS users 테이블 기준 JWT. Django auth_user / dj-rest-auth 없음."""

from __future__ import annotations

import hashlib
import hmac
from uuid import uuid4

from django.conf import settings
from django.db import connection
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from lms.auth_sessions import create_session, revoke_session, rotate_session, session_active


class AuthError(Exception):
    """토큰/사용자 인증 실패."""


def load_lms_user(firebase_uid: str | None) -> dict | None:
    if not firebase_uid:
        return None
    with connection.cursor() as cur:
        cur.execute(
            """SELECT u.id, u.firebase_uid, u.email, u.display_name, u.role, u.cohort_id,
                      u.is_active, u.must_change_password, c.code, u.password
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
        "_credential_fingerprint": credential_fingerprint(row[9] or ""),
    }


def credential_fingerprint(password_hash: str) -> str:
    """Password changes invalidate every old access/refresh token without a DB migration."""
    return hmac.new(settings.SECRET_KEY.encode(), password_hash.encode(), hashlib.sha256).hexdigest()


def _token_pair(user: dict, sid: str) -> tuple[RefreshToken, dict]:
    refresh = RefreshToken()
    refresh["uid"] = user["firebase_uid"]
    refresh["role"] = user["role"]
    refresh["user_id"] = user["id"]
    refresh["sid"] = sid
    refresh["cred"] = user["_credential_fingerprint"]
    return refresh, {"access": str(refresh.access_token), "refresh": str(refresh)}


def issue_tokens(user: dict) -> dict:
    if "_credential_fingerprint" not in user:
        user = load_lms_user(user["firebase_uid"]) or user
    if "_credential_fingerprint" not in user:
        raise AuthError("user not found")
    sid = uuid4().hex
    refresh, tokens = _token_pair(user, sid)
    create_session(user["firebase_uid"], str(refresh["jti"]), sid)
    return tokens


def _matching_user(token) -> dict:
    uid = str(token.get("uid") or "")
    user = load_lms_user(uid)
    if not user or not user.get("is_active"):
        raise AuthError("user not found")
    if not hmac.compare_digest(str(token.get("cred") or ""), user["_credential_fingerprint"]):
        raise AuthError("credentials changed")
    return user


def rotate_refresh(raw: str) -> dict:
    try:
        incoming = RefreshToken(raw)
    except TokenError as exc:
        raise AuthError("invalid refresh") from exc
    user = _matching_user(incoming)
    sid = str(incoming.get("sid") or "")
    if not sid:
        raise AuthError("invalid session")
    outgoing, tokens = _token_pair(user, sid)
    if not rotate_session(sid, user["firebase_uid"], str(incoming.get("jti") or ""), str(outgoing["jti"])):
        raise AuthError("refresh already used or revoked")
    return tokens


def logout_refresh(raw: str) -> None:
    try:
        token = RefreshToken(raw)
    except TokenError as exc:
        raise AuthError("invalid refresh") from exc
    user = _matching_user(token)
    sid = str(token.get("sid") or "")
    if not sid or not revoke_session(sid, user["firebase_uid"]):
        raise AuthError("session already revoked")


def user_from_access(raw: str) -> dict:
    try:
        token = AccessToken(raw)
    except TokenError as exc:
        raise AuthError("invalid token") from exc
    user = _matching_user(token)
    if not session_active(str(token.get("sid") or ""), user["firebase_uid"]):
        raise AuthError("session revoked")
    user.pop("_credential_fingerprint", None)
    return user
