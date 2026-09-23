"""Django Ninja API. URL·JSON 계약은 기존 DRF /api 와 동일."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.http import HttpRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from ninja import Body, NinjaAPI, Schema
from ninja.responses import Response
from ninja.security import HttpBearer
from pydantic import Field
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from lms.bootstrap_service import build_bootstrap
from lms.commands import dispatch, resolve_cohort
from lms.jwt_auth import AuthError, issue_tokens, load_lms_user, user_from_access
from lms.permissions import can_access_cohort
from lms.publish import publish_scheduled_notices
from lms.services import schedule_notice_vector


class LmsAuth(HttpBearer):
    def authenticate(self, request: HttpRequest, token: str):
        try:
            user = user_from_access(token)
        except AuthError:
            return None
        request.lms_user = user
        return user


api = NinjaAPI(
    title="LMS API",
    version="1.0.0",
    urls_namespace="lms_api",
    auth=LmsAuth(),
    docs_url="/docs" if os.environ.get("DJANGO_DEBUG", "1") == "1" else None,
)


class LoginIn(Schema):
    email: str = ""
    password: str = ""


class RefreshIn(Schema):
    refresh: str = ""


class CommandIn(Schema):
    op: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _data(body: dict[str, Any] | None) -> dict[str, Any]:
    return body or {}


def _require_user(request: HttpRequest) -> dict:
    user = getattr(request, "auth", None) or getattr(request, "lms_user", None)
    if not user:
        raise AuthError("unauthenticated")
    return user


def _run_op(op: str, user: dict, payload: dict):
    try:
        return 200, dispatch(user, op, payload)
    except PermissionError:
        return 403, {"detail": "forbidden"}
    except KeyError as exc:
        return 404, {"detail": f"not found: {exc}"}
    except ValueError as exc:
        return 400, {"detail": str(exc)}


def _dicts(cur):
    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _one(cur):
    rows = _dicts(cur)
    return rows[0] if rows else None


@api.exception_handler(AuthError)
def on_auth_error(request, exc: AuthError):
    return api.create_response(request, {"detail": str(exc) or "unauthenticated"}, status=401)


@api.get("/csrf", auth=None)
@ensure_csrf_cookie
def csrf(request):
    return Response({"ok": True})


@api.post("/login", auth=None)
def login(request, body: LoginIn):
    email = (body.email or "").strip().lower()
    password = body.password or ""
    with connection.cursor() as cur:
        cur.execute(
            """SELECT id, firebase_uid, email, password, role, is_active, must_change_password
               FROM users WHERE lower(email) = %s""",
            [email],
        )
        user = _one(cur)
    if not user or not user["is_active"]:
        return Response(
            {"ok": False, "message": "등록되지 않은 이메일이거나 비활성 계정입니다."},
            status=400,
        )
    stored = user.get("password") or ""
    if not stored or not check_password(password, stored):
        return Response({"ok": False, "message": "비밀번호가 올바르지 않습니다."}, status=400)
    with connection.cursor() as cur:
        cur.execute("UPDATE users SET last_login = now() WHERE id = %s", [user["id"]])
    lms_user = load_lms_user(user["firebase_uid"]) or {
        "id": user["id"],
        "firebase_uid": user["firebase_uid"],
        "email": user["email"],
        "role": user["role"],
        "must_change_password": bool(user.get("must_change_password")),
        "cohort_code": None,
        "display_name": "",
    }
    tokens = issue_tokens(lms_user)
    return {
        "ok": True,
        "access": tokens["access"],
        "refresh": tokens["refresh"],
        "uid": user["firebase_uid"],
        "role": user["role"],
        "mustChangePassword": bool(user.get("must_change_password")),
        "user": {
            "uid": user["firebase_uid"],
            "email": user["email"],
            "role": user["role"],
            "mustChangePassword": bool(user.get("must_change_password")),
            "cohortId": lms_user.get("cohort_code"),
            "displayName": lms_user.get("display_name"),
        },
    }


@api.post("/token/refresh", auth=None)
def token_refresh(request, body: RefreshIn):
    raw = body.refresh or ""
    try:
        incoming = RefreshToken(raw)
    except TokenError:
        return Response({"detail": "invalid refresh"}, status=401)
    uid = str(incoming.get("uid") or "")
    user = load_lms_user(uid)
    if not user or not user.get("is_active"):
        return Response({"detail": "unauthenticated"}, status=401)
    return issue_tokens(user)


@api.post("/password")
def password(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    data = _data(body)
    if data.get("skip"):
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE users SET must_change_password = false, updated_at = now() WHERE id = %s",
                [user["id"]],
            )
        return {"ok": True, "skipped": True}
    new_password = str(data.get("password") or data.get("newPassword") or "")
    current = str(data.get("currentPassword") or "")
    if len(new_password) < 8:
        return Response({"ok": False, "message": "비밀번호는 8자 이상이어야 합니다."}, status=400)
    with connection.cursor() as cur:
        cur.execute(
            "SELECT password, must_change_password FROM users WHERE id = %s",
            [user["id"]],
        )
        row = cur.fetchone()
        if not row:
            return Response({"ok": False, "message": "사용자를 찾을 수 없습니다."}, status=404)
        stored, must_change = row[0] or "", bool(row[1])
        if not must_change and (not stored or not check_password(current, stored)):
            return Response({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}, status=400)
        cur.execute(
            """UPDATE users
               SET password = %s, must_change_password = false, updated_at = now()
               WHERE id = %s""",
            [make_password(new_password), user["id"]],
        )
    return {"ok": True}


@api.post("/logout", auth=None)
def logout(request):
    return {"ok": True}


@api.get("/me")
def me(request):
    user = _require_user(request)
    return {
        **user,
        "uid": user["firebase_uid"],
        "cohortId": user.get("cohort_code"),
        "mustChangePassword": bool(user.get("must_change_password")),
    }


class ChatIn(Schema):
    message: str = ""
    question: str = ""


@api.post("/chat")
def chat(request, body: ChatIn):
    user = _require_user(request)
    message = (body.message or body.question or "").strip()
    if not message:
        return Response({"detail": "message required"}, status=400)
    if user.get("role") != "student":
        return Response({"detail": "학생 계정만 챗봇을 사용할 수 있습니다"}, status=403)
    base = (os.environ.get("CHATBOT_URL") or "").rstrip("/")
    if not base:
        return {
            "answer": "학습 도우미 서버가 연결되어 있지 않습니다. 관리자에게 문의하세요.",
        }
    internal_token = os.environ.get("LMS_AI_SHARED_TOKEN") or ""
    if not internal_token:
        return Response({"detail": "AI 서비스 내부 인증이 설정되지 않았습니다"}, status=503)
    payload = json.dumps(
        {"message": message, "uid": user["firebase_uid"], "thread_id": "web"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/v1/student-chatbot/chat",
        data=payload,
        headers={"Content-Type": "application/json", "X-LMS-AI-Token": internal_token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            body_json = json.loads(raw)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            msg = detail.get("detail") or detail.get("answer") or str(exc.reason)
        except Exception:
            msg = "학습 도우미에 잠시 연결하지 못했습니다. 잠시 후 다시 시도하세요."
        # React 는 2xx 만 성공으로 보므로 사용자 메시지는 200 으로 돌려준다.
        return {"answer": str(msg)}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return {
            "answer": "학습 도우미에 잠시 연결하지 못했습니다. 잠시 후 다시 시도하세요.",
        }
    answer = body_json.get("answer") or body_json.get("text") or body_json.get("message") or ""
    return {"answer": answer or "답변을 받지 못했습니다."}


def _study_note_proxy(request: HttpRequest, body: dict[str, Any], action: str):
    user = _require_user(request)
    if action not in {"tree", "generate", "get"}:
        return Response({"detail": "unsupported study note action"}, status=400)
    base = (os.environ.get("CHATBOT_URL") or "").rstrip("/")
    token = os.environ.get("LMS_AI_SHARED_TOKEN") or ""
    if not base or not token:
        return Response({"detail": "공부방 AI 서비스가 연결되지 않았습니다"}, status=503)
    cohort = body.get("cohortId")
    if not isinstance(cohort, str) or not cohort.strip():
        return Response({"detail": "cohortId required"}, status=400)
    payload = {**body, "userPk": user["id"]}
    req = urllib.request.Request(
        f"{base}/api/v1/study-notes/internal/{action}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-LMS-AI-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = {"detail": "공부방 요청을 처리하지 못했습니다"}
        return Response(detail, status=exc.code if exc.code < 500 else 502)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Response({"detail": "공부방 AI 서비스에 연결하지 못했습니다"}, status=502)


@api.post("/study-notes/tree")
def study_note_tree(request, body: dict[str, Any] = Body(...)):
    return _study_note_proxy(request, body, "tree")


@api.post("/study-notes/generate")
def study_note_generate(request, body: dict[str, Any] = Body(...)):
    return _study_note_proxy(request, body, "generate")


@api.post("/study-notes/get")
def study_note_get(request, body: dict[str, Any] = Body(...)):
    return _study_note_proxy(request, body, "get")


@api.get("/bootstrap")
def bootstrap(request):
    user = _require_user(request)
    return build_bootstrap(user)


@api.post("/notices")
def create_notice(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    data = _data(body)
    if user["role"] not in ("admin", "instructor"):
        return Response({"detail": "forbidden"}, status=403)
    title = data.get("title") or ""
    content = data.get("content") or ""
    with connection.cursor() as cur:
        cohort_id = resolve_cohort(cur, data.get("cohortId"), user)
    if not cohort_id:
        return Response({"detail": "cohort required"}, status=400)
    if not can_access_cohort(user, cohort_id) and user["role"] != "admin":
        return Response({"detail": "forbidden"}, status=403)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT code FROM cohorts WHERE id = %s", [cohort_id])
            code = (cur.fetchone() or [None])[0]
            cur.execute(
                """INSERT INTO notices (cohort_id, title, content, author_id, author_name, is_favorite, priority, vector_chunk_count, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,0, now(), now()) RETURNING id""",
                [
                    cohort_id,
                    title,
                    content,
                    user["id"],
                    user["display_name"],
                    bool(data.get("isFavorite")),
                    int(data.get("priority") or 0),
                ],
            )
            notice_id = cur.fetchone()[0]
        schedule_notice_vector(
            cohort_code=code,
            notice_id=notice_id,
            data={
                "title": title,
                "content": content,
                "author_id": user["id"],
                "author_name": user["display_name"],
                "is_favorite": bool(data.get("isFavorite")),
                "priority": int(data.get("priority") or 0),
            },
            previous_chunk_count=0,
        )
    return {"id": str(notice_id)}


@api.patch("/notices/{pk}")
def patch_notice(request, pk: int, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    data = _data(body)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                """SELECT n.id, n.cohort_id, n.vector_chunk_count, n.author_id, c.code, n.title, n.content
                   FROM notices n JOIN cohorts c ON c.id = n.cohort_id WHERE n.id = %s""",
                [pk],
            )
            row = cur.fetchone()
            if not row:
                return Response({"detail": "not found"}, status=404)
            _id, cohort_id, chunk_count, author_id, code, title, content = row
            if user["role"] != "admin" and not (
                user["role"] == "instructor" and user["id"] == author_id
            ):
                return Response({"detail": "forbidden"}, status=403)
            title = data.get("title", title)
            content = data.get("content", content)
            cur.execute(
                "UPDATE notices SET title=%s, content=%s, updated_at=now() WHERE id=%s",
                [title, content, pk],
            )
        schedule_notice_vector(
            cohort_code=code,
            notice_id=pk,
            data={"title": title, "content": content, "author_id": author_id},
            previous_chunk_count=chunk_count,
        )
    return {"ok": True}


@api.delete("/notices/{pk}")
def delete_notice(request, pk: int):
    user = _require_user(request)
    if user["role"] != "admin":
        return Response({"detail": "forbidden"}, status=403)
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                """SELECT n.vector_chunk_count, c.code FROM notices n JOIN cohorts c ON c.id = n.cohort_id WHERE n.id = %s""",
                [pk],
            )
            row = cur.fetchone()
            if not row:
                return Response({"detail": "not found"}, status=404)
            chunk_count, code = row
            cur.execute("DELETE FROM notices WHERE id = %s", [pk])
        schedule_notice_vector(
            cohort_code=code, notice_id=pk, data=None, previous_chunk_count=chunk_count
        )
    return {"ok": True}


@api.post("/mileage/adjust")
def mileage_adjust(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    data = _data(body)
    if user["role"] != "admin":
        return Response({"detail": "forbidden"}, status=403)
    target_uid = data.get("uid")
    amount = int(data.get("amount") or 0)
    reason = data.get("reason") or ""
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT id, cohort_id, mileage_balance FROM users WHERE firebase_uid = %s FOR UPDATE",
                [target_uid],
            )
            row = cur.fetchone()
            if not row:
                return Response({"detail": "user not found"}, status=404)
            uid, cohort_id, balance = row
            cur.execute(
                """INSERT INTO mileage_transactions (cohort_id, user_id, amount, type, reason, adjusted_by, created_at)
                   VALUES (%s,%s,%s,'adjust',%s,%s, now())""",
                [cohort_id, uid, amount, reason, user["id"]],
            )
            cur.execute(
                "UPDATE users SET mileage_balance = mileage_balance + %s WHERE id = %s",
                [amount, uid],
            )
    return {"ok": True}


@api.post("/command")
def command(request, body: CommandIn):
    user = _require_user(request)
    status, result = _run_op(body.op, user, body.payload or {})
    return Response(result, status=status)


@api.get("/qual-exams")
def qual_exams(request, year: str = ""):
    _require_user(request)
    with connection.cursor() as cur:
        if year:
            cur.execute(
                "SELECT key, data, synced_at FROM system_cache WHERE key = %s OR key = %s",
                [f"qualExamSchedules_{year}", f"qualExamSchedules{year}"],
            )
        else:
            cur.execute("SELECT key, data, synced_at FROM system_cache WHERE key LIKE 'qualExam%'")
        rows = _dicts(cur)
    return {"items": rows}


@api.post("/scheduled-notices")
def create_scheduled(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    status, result = _run_op(
        "upsertScheduledNotice", user, {**_data(body), "action": "insert"}
    )
    return Response(result, status=status)


@api.post("/scheduled-notices/publish")
def publish_scheduled(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    if user["role"] not in ("admin", "instructor"):
        return Response({"detail": "forbidden"}, status=403)
    data = _data(body)
    ids = data.get("ids") or data.get("scheduledIds")
    count = publish_scheduled_notices(
        ids=ids, cohort_id=None if user["role"] == "admin" else user.get("cohort_id") or -1,
    )
    return {"ok": True, "published": count}


@api.patch("/scheduled-notices/{pk}")
def patch_scheduled(request, pk: int, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    status, result = _run_op(
        "upsertScheduledNotice", user, {**_data(body), "id": pk, "action": "update"}
    )
    return Response(result, status=status)


@api.delete("/scheduled-notices/{pk}")
def delete_scheduled(request, pk: int):
    user = _require_user(request)
    status, result = _run_op(
        "upsert", user, {"table": "scheduled_notices", "id": pk, "action": "delete"}
    )
    return Response(result, status=status)


@api.post("/alert-popups")
def create_alert(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    status, result = _run_op("upsertAlertPopup", user, {**_data(body), "action": "insert"})
    return Response(result, status=status)


@api.patch("/alert-popups/{pk}")
def patch_alert(request, pk: int, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    status, result = _run_op(
        "upsertAlertPopup", user, {**_data(body), "id": pk, "action": "update"}
    )
    return Response(result, status=status)


@api.delete("/alert-popups/{pk}")
def delete_alert(request, pk: int):
    user = _require_user(request)
    status, result = _run_op(
        "upsert", user, {"table": "alert_popups", "id": pk, "action": "delete"}
    )
    return Response(result, status=status)


@api.post("/alert-popups/{pk}/dismiss")
def dismiss_alert(request, pk: int, body: dict[str, Any] | None = Body(None)):
    user = _require_user(request)
    status, result = _run_op(
        "dismissAlertPopup", user, {**_data(body), "popupId": pk}
    )
    return Response(result, status=status)
