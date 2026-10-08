"""Django Ninja API. URL·JSON 계약은 기존 DRF /api 와 동일."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from django.contrib.auth.hashers import check_password, make_password
from django.db import connection, transaction
from django.http import HttpRequest, StreamingHttpResponse
from django.views.decorators.csrf import ensure_csrf_cookie
from ninja import Body, File, Form, NinjaAPI, Schema, UploadedFile
from ninja.responses import Response
from ninja.security import HttpBearer
from pydantic import Field
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from lms.bootstrap_service import build_bootstrap
from lms.commands import dispatch, resolve_cohort
from lms.holidays import holidays_of
from lms.jwt_auth import AuthError, issue_tokens, load_lms_user, user_from_access
from lms.permissions import can_access_cohort
from lms.posting_link import job_id_from_link
from lms.publish import publish_scheduled_notices
from lms.resume_text import build_profile, build_resume_text
from lms.services import schedule_notice_vector
from lms import apply_link, featured_postings, folder_upload, practice_auto, practice_custom, practice_tutor, practice_web, study_note_service, study_source_service


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


@api.get("/holidays")
def holidays(request, year: int):
    """그 해 공휴일 {"YYYY-MM-DD": 이름} — 출석 달력이 일요일처럼 칠한다(lms/holidays.py)."""
    _require_user(request)
    if not 2000 <= year <= 2100:
        return Response({"detail": "year 는 2000~2100 사이여야 합니다."}, status=400)
    return {"year": year, "days": holidays_of(year)}


@api.get("/me")
def me(request):
    user = _require_user(request)
    return {
        **user,
        "uid": user["firebase_uid"],
        "cohortId": user.get("cohort_code"),
        "mustChangePassword": bool(user.get("must_change_password")),
    }


class PushTokenIn(Schema):
    token: str
    platform: str = ""


@api.post("/push-tokens")
def register_push_token(request, body: PushTokenIn):
    """앱이 로그인 뒤 기기 푸시 토큰을 올린다"""
    from lms.push import is_expo_token, register_token

    user = _require_user(request)
    token = body.token.strip()
    if not is_expo_token(token):
        return Response({"detail": "Expo 푸시 토큰이 아닙니다"}, status=400)
    with transaction.atomic(), connection.cursor() as cur:
        register_token(cur, user["id"], token, body.platform.strip())
    return {"ok": True}


@api.post("/push-tokens/remove")
def remove_push_token(request, body: PushTokenIn):
    """로그아웃할 때 — 이 기기로는 더 보내지 않는다"""
    from lms.push import remove_token

    user = _require_user(request)
    with transaction.atomic(), connection.cursor() as cur:
        remove_token(cur, user["id"], body.token.strip())
    return {"ok": True}


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
    upstream_started = time.perf_counter()
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
    upstream_ms = (time.perf_counter() - upstream_started) * 1000
    return Response(
        {"answer": answer or "답변을 받지 못했습니다."},
        headers={"Server-Timing": f"ai_upstream;dur={upstream_ms:.1f}"},
    )


@api.post("/chat/stream")
def chat_stream(request, body: ChatIn):
    user = _require_user(request)
    message = (body.message or body.question or "").strip()
    if not message:
        return Response({"detail": "message required"}, status=400)
    if user.get("role") != "student":
        return Response({"detail": "학생 계정만 챗봇을 사용할 수 있습니다"}, status=403)
    base = (os.environ.get("CHATBOT_URL") or "").rstrip("/")
    internal_token = os.environ.get("LMS_AI_SHARED_TOKEN") or ""
    if not base or not internal_token:
        return Response({"detail": "학습 도우미 서버가 설정되지 않았습니다"}, status=503)
    req = urllib.request.Request(
        f"{base}/api/v1/student-chatbot/chat/stream",
        data=json.dumps({
            "message": message, "uid": user["firebase_uid"], "thread_id": "web",
        }, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json", "Accept": "application/x-ndjson",
            "X-LMS-AI-Token": internal_token,
        },
        method="POST",
    )
    try:
        upstream = urllib.request.urlopen(req, timeout=120)
    except urllib.error.HTTPError as exc:
        return Response({"detail": "학습 도우미 요청을 처리하지 못했습니다"}, status=exc.code)
    except (urllib.error.URLError, TimeoutError):
        return Response({"detail": "학습 도우미에 연결하지 못했습니다"}, status=503)

    def relay():
        try:
            for line in upstream:
                yield line
        except (urllib.error.URLError, TimeoutError, OSError):
            yield (json.dumps({
                "type": "error", "message": "학습 도우미와 연결이 끊겼습니다",
            }, ensure_ascii=False) + "\n").encode("utf-8")
        finally:
            upstream.close()

    response = StreamingHttpResponse(relay(), content_type="application/x-ndjson; charset=utf-8")
    response["Cache-Control"] = "no-store"
    response["X-Accel-Buffering"] = "no"
    return response


class ResumeReviewIn(Schema):
    resumeId: str
    """공고 맞춤 첨삭이면 그 공고 id. 없으면 이력서 자체를 본다."""
    selectedJobId: str | None = None
    tailoredResumeId: str | None = None
    reviewMode: str = "general"
    # 아래는 첨삭 창이 대화를 이어 갈 때 보낸다(job_resume_review_dialog.dart 의 요청 그대로).
    requestId: str | None = None
    expectedInputHash: str | None = None
    expectedJobHash: str | None = None
    """standard · gap_audit(질문을 다 마친 뒤 한 번 하는 누락 점검)"""
    reviewPhase: str | None = None
    previousReviewId: str | None = None
    """[{question_id, field_path, question, answer}]"""
    answers: list[dict] | None = None
    answerChanges: list[dict] | None = None


def _owned_resume(request, resume_id: str):
    """이 학생이 볼 수 있는 이력서인지 보고 (행, 오류) 를 돌려준다."""
    user = _require_user(request)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT r.id, r.legacy_id, c.code, u.firebase_uid, r.cohort_id
               FROM resumes r JOIN users u ON u.id = r.user_id
               JOIN cohorts c ON c.id = r.cohort_id
               WHERE r.legacy_id = %s OR r.id::text = %s""",
            [resume_id, resume_id],
        )
        row = _one(cur)
    if not row:
        return None, Response({"detail": "이력서를 찾을 수 없습니다."}, status=404)
    if row["firebase_uid"] != user["firebase_uid"] and not (
        user["role"] in ("admin", "instructor") and can_access_cohort(user, row["cohort_id"])
    ):
        return None, Response({"detail": "본인 이력서만 첨삭받을 수 있습니다."}, status=403)
    return row, None


def _review_resume_id(row) -> str:
    """첨삭 서버로 넘길 이력서 id — 화면의 공개 id 와 같다(legacy_id, 없으면 resumes.id).

    화면에서 새로 만든 이력서는 legacy_id 가 없다. legacy_id 를 그대로 넘기면 None 이 가서 첨삭을 못 받았다.
    """
    return str(row["legacy_id"] or row["id"])


def _review_call(path: str, payload: dict, timeout: int = 180):
    """첨삭 서버로 넘긴다. 주소는 RESUME_REVIEW_URL(없으면 AI 서버와 같은 곳)."""
    base = (os.environ.get("RESUME_REVIEW_URL") or os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return Response({"detail": "첨삭 서버가 연결되어 있지 않습니다(RESUME_REVIEW_URL)."}, status=503)
    req = urllib.request.Request(
        f"{base}/resume-review{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        return Response({"detail": detail or "첨삭하지 못했습니다."}, status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Response({"detail": "첨삭 서버에 연결하지 못했습니다."}, status=503)


class StudyTreeIn(Schema):
    sourceId: str


class StudyFileIn(Schema):
    sourceId: str
    path: str
    commit: str = ""


class StudyNoteIn(Schema):
    sourceId: str
    scopeType: str
    scopeValue: Any = None


def _study(call):
    """공부방 노트 — 실패 이유를 화면이 그대로 보여 줄 수 있게 {"detail"} 로"""
    try:
        return call()
    except study_note_service.StudyNoteError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.post("/study-notes/tree")
def study_notes_tree(request, body: StudyTreeIn):
    """수업 저장소의 최근 수업 날짜와 파일 목록 — 노트 범위를 고르는 화면이 쓴다."""
    user = _require_user(request)
    return _study(lambda: study_note_service.source_tree(user, body.sourceId))


@api.post("/study-notes/file")
def study_notes_file(request, body: StudyFileIn):
    """수업 파일 하나의 원문 — 노트의 핵심 코드를 연습장 탭으로 연다."""
    user = _require_user(request)
    return _study(lambda: study_note_service.lesson_file(user, body.sourceId, body.path, body.commit))


@api.post("/study-notes")
def study_notes_create(request, body: StudyNoteIn):
    """노트 만들기. 몇 분 걸려서 「정리 중」 노트를 바로 돌려주고, 화면은 GET 으로 끝났는지 본다.
    같은 범위의 노트가 이미 있으면 새로 만들지 않고 그것을 돌려준다."""
    user = _require_user(request)
    return _study(lambda: study_note_service.start_note(user, body.sourceId, body.scopeType, body.scopeValue))


@api.get("/study-notes/{note_id}")
def study_notes_get(request, note_id: str):
    user = _require_user(request)
    return _study(lambda: study_note_service.get_note(user, note_id))


@api.delete("/study-notes/{note_id}")
def study_notes_delete(request, note_id: str):
    """내 노트 지우기 — 다른 학생 노트는 404"""
    user = _require_user(request)
    return _study(lambda: study_note_service.delete_note(user, note_id))


class StudyOwnerIn(Schema):
    cohortId: str = ""
    owner: str


class StudySyncIn(Schema):
    cohortId: str = ""
    force: bool = False


class StudySourcePatch(Schema):
    isActive: bool | None = None
    title: str | None = None


def _sources(call):
    try:
        return call()
    except study_source_service.StudySourceError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.get("/study-sources/github")
def study_sources_owners(request, cohortId: str = ""):
    """기수에 연결한 GitHub 조직·계정 — 강사는 자기 기수, 관리자는 모든 기수"""
    user = _require_user(request)
    return _sources(lambda: study_source_service.list_owners(user, cohortId))


@api.post("/study-sources/github")
def study_sources_add_owner(request, body: StudyOwnerIn):
    """조직·계정을 연결하고 바로 저장소를 찾아 올린다(바로 공개)"""
    user = _require_user(request)
    return _sources(lambda: study_source_service.add_owner(user, body.cohortId, body.owner))


@api.delete("/study-sources/github/{owner_id}")
def study_sources_remove_owner(request, owner_id: str):
    user = _require_user(request)
    return _sources(lambda: study_source_service.remove_owner(user, owner_id))


@api.post("/study-sources/sync")
def study_sources_sync(request, body: StudySyncIn):
    """새 저장소 찾기. force 가 아니면 10분 안에 찾은 조직·계정은 건너뛴다(화면을 열 때마다 부른다)."""
    user = _require_user(request)
    return _sources(lambda: study_source_service.sync_cohort(user, body.cohortId, force=body.force))


@api.get("/study-sources/schedule")
def study_sources_schedule(request, cohortId: str = ""):
    """커리큘럼 ↔ 실제 수업 날짜 어긋남 — 강사 · 관리자 수업 저장소 화면.
    아래 PATCH /study-sources/{source_id} 보다 먼저 둔다 — 뒤에 두면 그쪽이 이 주소를 가져가 405 가 난다."""
    user = _require_user(request)
    return _sources(lambda: folder_upload.schedule(user, cohortId))


@api.patch("/study-sources/{source_id}")
def study_sources_update(request, source_id: str, body: StudySourcePatch):
    """공개 · 숨김, 이름 바꾸기"""
    user = _require_user(request)
    return _sources(lambda: study_source_service.update_source(user, source_id, is_active=body.isActive, title=body.title))


# ── 폴더 올리기(GitHub 없이) — lms/folder_upload.py ──


@api.post("/study-sources/upload/plan")
def study_upload_plan(request, body: dict[str, Any] = Body(...)):
    """올리기 전 계획 — 파일 목록(경로 · 지문 · 앞부분 글, 내용 없음). mode: import(처음 가져오기) · daily(오늘 수업 올리기)"""
    user = _require_user(request)
    return _sources(lambda: folder_upload.plan(user, body))


@api.post("/study-sources/upload/commit")
def study_upload_commit(
    request,
    cohortId: str = Form(...),
    manifest: str = Form(...),
    sourceId: str = Form(""),
    name: str = Form(""),
    files: list[UploadedFile] = File(...),
):
    """확정한 파일 올리기(한 번에 100개까지 — 많으면 화면이 나눠 보낸다). sourceId 가 없으면 name 으로 과목을 만든다."""
    user = _require_user(request)
    return _sources(lambda: folder_upload.commit(
        user, cohort_code=cohortId, source_key=sourceId, name=name, manifest=manifest, files=files,
    ))


class PracticeAutoPatch(Schema):
    enabled: bool


@api.get("/practice-auto")
def practice_auto_status(request, cohortId: str = ""):
    """저장소마다 복습 문제 자동 출제(매일 18:30) 켜짐 여부와 마지막 출제"""
    user = _require_user(request)
    return _sources(lambda: practice_auto.status(user, cohortId))


@api.patch("/practice-auto/{source_id}")
def practice_auto_toggle(request, source_id: str, body: PracticeAutoPatch):
    user = _require_user(request)
    return _sources(lambda: practice_auto.set_enabled(user, source_id, body.enabled))


class PracticeRunIn(Schema):
    dates: list[str] = []


@api.post("/practice-auto/{source_id}/run")
def practice_auto_run(request, source_id: str, body: PracticeRunIn | None = None):
    """「지금 만들기」 — 고른 수업 날짜로(없으면 자동과 같은 규칙). 몇 분 걸려서 바로 돌려주고 뒤에서 출제한다"""
    user = _require_user(request)
    dates = body.dates if body else []
    return _sources(lambda: practice_auto.run_now(user, source_id, dates))


@api.get("/practice-sets")
def practice_sets(request, ids: str = ""):
    """세트 본문 전체(문제 · 코드 · 테스트) — bootstrap 은 목록만 보내므로 연습장을 열 때 받는다. ids 는 쉼표로"""
    from lms.practice_service import practice_sets_full

    user = _require_user(request)
    with connection.cursor() as cur:
        return {"practiceSets": practice_sets_full(cur, user, ids.split(","))}


class PracticeFileIn(Schema):
    name: str = ""
    content: str = ""


@api.get("/practice-custom")
def practice_custom_remaining(request):
    """학생이 만드는 복습 문제 — 오늘 남은 횟수"""
    user = _require_user(request)
    return _sources(lambda: practice_custom.remaining(user))


@api.post("/practice-custom/note/{note_id}")
def practice_custom_note(request, note_id: str):
    """내 노트로 복습 문제 만들기 — 몇 분 걸려서 일(job)을 먼저 돌려준다. 만든 세트는 나만 본다"""
    user = _require_user(request)
    return _sources(lambda: practice_custom.from_note(user, note_id))


@api.post("/practice-custom/file")
def practice_custom_file(request, body: PracticeFileIn):
    """연습장에서 연 .py · .ipynb 로 복습 문제 만들기"""
    user = _require_user(request)
    return _sources(lambda: practice_custom.from_file(user, body.name, body.content))


@api.get("/practice-custom/{job_id}")
def practice_custom_job(request, job_id: str):
    user = _require_user(request)
    return _sources(lambda: practice_custom.get_job(user, job_id))


class TutorIn(Schema):
    mode: str = "cell"  # problem · cell
    action: str = "ask"  # ask · more(힌트 더) · answer(정답 알려 줘)
    question: str = ""
    setId: str = ""
    index: int = 0
    code: str = ""
    run: str = ""
    grade: str = ""
    # 오답노트에서 연 문제 — 'retry:YYYY-MM-DD'. 복습 때 대화와 따로, 그날 새로 시작한다
    thread: str = ""


@api.post("/practice-tutor")
def practice_tutor_ask(request, body: TutorIn):
    """연습장 튜터 — 문제 셀엔 3단계 힌트(단계는 서버가 정한다), 일반 셀엔 코드 · 오류 설명"""
    user = _require_user(request)
    return _sources(lambda: practice_tutor.ask(user, body.model_dump()))


class WebGradeIn(Schema):
    setId: str
    index: int
    html: str = ""


@api.post("/practice-web-grade")
def practice_web_grade(request, body: WebGradeIn):
    """웹 실습 채점 — 학생 HTML 을 서버 jsdom 에서 그 문제의 검사문(DB)으로 본다. 검사문은 브라우저가 보내지 않는다"""
    user = _require_user(request)
    return _sources(lambda: practice_web.grade(user, body.setId, body.index, body.html))


@api.get("/practice-tutor")
def practice_tutor_thread(request, mode: str = "cell", setId: str = "", index: int = 0, thread: str = ""):
    """튜터 창을 다시 열 때 — 그 문제(또는 일반 셀)의 지난 대화와 힌트 단계"""
    user = _require_user(request)
    return _sources(lambda: practice_tutor.thread(user, mode, setId or None, index, thread))


@api.delete("/practice-tutor")
def practice_tutor_reset(request, mode: str = "cell", setId: str = "", index: int = 0, thread: str = ""):
    """튜터 「새 대화」 — 그 문제(또는 일반 셀)의 내 대화를 지운다"""
    user = _require_user(request)
    return _sources(lambda: practice_tutor.reset(user, mode, setId or None, index, thread))


class ResumeReviewApplyIn(Schema):
    resumeId: str
    reviewId: str
    requestId: str
    expectedInputHash: str
    """반영할 수정안 번호들(첨삭 결과의 차례). 되돌릴 때는 비운다."""
    selectedIndices: list[int] = []
    applicationId: str | None = None
    tailoredResumeId: str | None = None


@api.post("/resume-review/apply")
def resume_review_apply(request, body: ResumeReviewApplyIn):
    """수정안을 이력서에 반영한다 — 글자는 서버가 바꾸고 기록도 서버가 남긴다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "request_id": body.requestId,
        "review_id": body.reviewId,
        "expected_input_hash": body.expectedInputHash,
        "selected_indices": body.selectedIndices,
    }
    if body.tailoredResumeId:
        payload["tailored_resume_id"] = body.tailoredResumeId
    return _review_call("/api/v1/resumes/reviews/apply/proxy", payload, timeout=60)


@api.post("/resume-review/undo")
def resume_review_undo(request, body: ResumeReviewApplyIn):
    """반영을 되돌린다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "request_id": body.requestId,
        "application_id": body.applicationId or "",
        "expected_input_hash": body.expectedInputHash,
    }
    if body.tailoredResumeId:
        payload["tailored_resume_id"] = body.tailoredResumeId
    return _review_call("/api/v1/resumes/reviews/undo/proxy", payload, timeout=60)


@api.post("/resume-review")
def resume_review(request, body: ResumeReviewIn):
    """이력서 첨삭 — 학생을 확인하고 첨삭 서버(cover_letter_rag)로 넘긴다.

    첨삭 서버는 원래 Firebase 토큰을 받았는데 우리 앱은 자체 JWT 를 쓴다(학생에게 그 토큰이
    아예 없다). 그래서 uid 를 받는 창구(`/reviews/proxy`)로 넘긴다 — 챗봇과 같은 방식이다.
    이력서 · 첨삭 기록은 그쪽도 Postgres 를 보므로, 여기서 넘기는 것은 누구인지뿐이다.

    첨삭은 1분쯤 걸린다.
    """
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "review_mode": "job" if body.selectedJobId else body.reviewMode,
    }
    if body.selectedJobId:
        payload["selected_job_id"] = body.selectedJobId
    if body.tailoredResumeId:
        payload["tailored_resume_id"] = body.tailoredResumeId
    for key, value in (
        ("request_id", body.requestId),
        ("expected_input_hash", body.expectedInputHash),
        ("expected_job_hash", body.expectedJobHash),
        ("review_phase", body.reviewPhase),
        ("previous_review_id", body.previousReviewId),
        ("answers", body.answers),
        ("answer_changes", body.answerChanges),
    ):
        if value:
            payload[key] = value
    return _review_call("/api/v1/resumes/reviews/proxy", payload)


@api.post("/resume-review/answer-change")
def resume_review_answer_change(request, body: ResumeReviewIn):
    if not body.answerChanges:
        raise HttpError(422, 'answer_change_required')
    return resume_review(request, body)


class ReviewContextIn(Schema):
    resumeId: str
    selectedJobId: str | None = None
    tailoredResumeId: str | None = None


@api.post("/resume-review/context")
def resume_review_context(request, body: ReviewContextIn):
    """첨삭 창이 보는 이력서 · 공고 스냅샷. 저장된 판(input_hash)과 화면이 같은지 여기서 본다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {"uid": row["firebase_uid"], "cohort_id": row["code"], "resume_id": _review_resume_id(row)}
    if body.selectedJobId:
        payload["job_id"] = body.selectedJobId
    if body.tailoredResumeId:
        payload["tailored_resume_id"] = body.tailoredResumeId
    return _review_call("/api/v1/resumes/review-context/proxy", payload, timeout=60)


class TailoredRefIn(Schema):
    resumeId: str
    tailoredResumeId: str


@api.post("/resume-review/tailored/get")
def resume_review_tailored_get(request, body: TailoredRefIn):
    """공고 맞춤본과 저장된 첨삭 대화 — 재첨삭 창이 이어서 연다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "tailored_resume_id": body.tailoredResumeId,
    }
    return _review_call("/api/v1/resumes/tailored/get/proxy", payload, timeout=60)


class TailoredSessionIn(TailoredRefIn):
    state: dict


@api.post("/resume-review/session")
def resume_review_session(request, body: TailoredSessionIn):
    """첨삭 대화를 공고 맞춤본에 남긴다. 창을 닫았다 열면 이어 간다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "tailored_resume_id": body.tailoredResumeId,
        "state": body.state,
    }
    return _review_call("/api/v1/resumes/tailored/session/proxy", payload, timeout=60)


class TailoredResumeIn(Schema):
    resumeId: str
    selectedJobId: str
    # review=이력서 관리의 공고 맞춤 첨삭, apply=공고 맞춤 지원(문항 답변). 같은 공고라도 사본을 따로 뜬다
    purpose: Literal["review", "apply"] = "review"


@api.post("/resume-review/tailored")
def resume_review_tailored(request, body: TailoredResumeIn):
    """공고 맞춤 첨삭을 시작한다 — 원본을 그 공고용 사본으로 떠 둔다.

    첨삭 · 반영은 이 사본에 한다. 원본은 그대로 남는다. 돌려주는 `tailored_resume_id` 를
    첨삭 · 반영 · 옮기기에 같이 보낸다.
    """
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "selected_job_id": body.selectedJobId,
        "purpose": body.purpose,
    }
    return _review_call("/api/v1/resumes/tailored/proxy", payload, timeout=60)


QUESTION_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
QUESTION_IMAGE_MAX_BYTES = 8 * 1024 * 1024
QUESTION_PDF_MAX_BYTES = 10 * 1024 * 1024
# 지원서 양식 문서 — 확장자 → 첨삭 서버에 넘길 종류. 셋 다 ZIP 이라 속 구성까지 본다(_office_kind).
# 옛 한글(.hwp) · 옛 Word(.doc)는 ZIP 이 아니어서 받지 않는다
QUESTION_DOCUMENT_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".hwpx": "application/hwp+zip",
}
QUESTION_FILE_TYPES_TEXT = "PNG · JPG · WEBP 이미지나 PDF · Word(.docx) · PowerPoint(.pptx) · 한글(.hwpx) 파일만 올릴 수 있어요."


def _office_kind(data: bytes) -> str | None:
    """ZIP 속 구성으로 문서 형식(확장자)을 가린다. 확장자만 바꾼 파일은 None. 압축은 풀지 않고 목차만 본다."""
    import io
    import zipfile

    if not data.startswith(b"PK\x03\x04"):
        return None
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        names = set(archive.namelist())
        if "[Content_Types].xml" in names and "word/document.xml" in names:
            return ".docx"
        if "[Content_Types].xml" in names and "ppt/presentation.xml" in names:
            return ".pptx"
        if "mimetype" in names and archive.getinfo("mimetype").file_size <= 64 and archive.read("mimetype").strip() == b"application/hwp+zip":
            return ".hwpx"
    except (zipfile.BadZipFile, zipfile.LargeZipFile, KeyError, ValueError, OSError):
        return None
    return None


def _question_file_kind(name: str, content_type: str) -> str:
    """'image' · 'pdf' · 문서 확장자(.docx …) · 'hwp' · ''(못 받음). 문서는 브라우저가 종류를 비워 보내기도 해 확장자로 본다."""
    ext = os.path.splitext(name or "")[1].lower()
    if ext in QUESTION_DOCUMENT_TYPES or content_type in QUESTION_DOCUMENT_TYPES.values():
        return ext if ext in QUESTION_DOCUMENT_TYPES else next(e for e, t in QUESTION_DOCUMENT_TYPES.items() if t == content_type)
    if ext in (".hwp", ".doc", ".ppt"):
        return "hwp"
    if content_type == "application/pdf":
        return "pdf"
    return "image" if content_type in QUESTION_IMAGE_TYPES else ""


@api.post("/resume-review/question-extract")
def resume_review_question_extract(request, files: list[UploadedFile] = File(...)):
    """캡처한 자기소개서 문항 · 지원서 양식 파일 → 문항 목록. 파일은 저장하지 않고 첨삭 서버로만 넘긴다.

    회사 채용 사이트는 로그인해야 문항이 보이거나 복사가 막힌 경우가 많아 학생이 캡처해 올린다.
    이미지(png · jpeg · webp) 세 장까지 한 장 8MB, 또는 PDF · DOCX · PPTX · HWPX 한 개 10MB.
    문서는 확장자와 ZIP 속 구성이 맞아야 넘긴다. 뽑은 문항은 화면에서 학생이 확인하고 고친다.
    """
    import base64

    _require_user(request)
    if not 1 <= len(files) <= 3:
        return Response({"detail": "캡처는 한 번에 세 장까지 올릴 수 있어요."}, status=400)
    kinds = [_question_file_kind(file.name, (file.content_type or "").split(";")[0].strip().lower()) for file in files]
    if "hwp" in kinds:
        return Response({"detail": "옛 한글(.hwp) · Word(.doc) · PowerPoint(.ppt) 파일은 읽지 못해요. PDF 나 HWPX · DOCX · PPTX 로 저장해 올려 주세요."}, status=400)
    if "" in kinds:
        return Response({"detail": QUESTION_FILE_TYPES_TEXT}, status=400)
    if any(kind != "image" for kind in kinds) and len(files) > 1:
        return Response({"detail": "PDF · 문서 파일은 한 번에 한 개만, 캡처와 따로 올려 주세요."}, status=400)
    images = []
    for file, kind in zip(files, kinds):
        limit = QUESTION_IMAGE_MAX_BYTES if kind == "image" else QUESTION_PDF_MAX_BYTES
        data = file.read(limit + 1)
        if len(data) > limit:
            what = {"image": "이미지", "pdf": "PDF"}.get(kind, "문서 파일")
            return Response({"detail": f"{what}는 {limit // (1024 * 1024)}MB 이하만 올릴 수 있어요."}, status=400)
        if kind in QUESTION_DOCUMENT_TYPES:
            if _office_kind(data) != kind:
                return Response({"detail": f"파일 내용이 {kind} 형식이 아니에요. 열 수 있는 원본을 올리거나 PDF 로 저장해 올려 주세요."}, status=400)
            content_type = QUESTION_DOCUMENT_TYPES[kind]
        else:
            content_type = "application/pdf" if kind == "pdf" else (file.content_type or "").split(";")[0].strip().lower()
        images.append(f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}")
    return _review_call("/api/v1/resumes/question-extract/proxy", {"images": images}, timeout=120)


QUESTION_LINK_HOSTS = ("saramin.co.kr", "jobkorea.co.kr")


def _attachment_host_allowed(url: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host == h or host.endswith(f".{h}") for h in QUESTION_LINK_HOSTS)


class _AllowedRedirects(urllib.request.HTTPRedirectHandler):
    """사람인 · 잡코리아 안에서만 넘겨 간다. 다른 곳(내부망 주소 등)으로 넘기면 열지 않는다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _attachment_host_allowed(newurl):
            raise urllib.error.HTTPError(newurl, 403, "redirect to a host that is not allowed", headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_ATTACHMENT_OPENER = urllib.request.build_opener(_AllowedRedirects)


class QuestionLinkIn(Schema):
    url: str = Field(min_length=1, max_length=1000)


@api.post("/resume-review/question-extract-link")
def resume_review_question_extract_link(request, body: QuestionLinkIn):
    """공고에 첨부된 지원서 양식 링크 → 문항 목록. 내려받아 올리는 수고를 던다.

    서버가 대신 여는 주소라 사람인 · 잡코리아(https)만 연다. 아무 주소나 열면 내부망을 대신 두드리는 통로가 된다.
    넘겨 가는 주소도 같은 규칙으로 본다. PDF · 문서 10MB · 이미지 8MB 까지, 종류는 파일 첫 바이트(문서는 ZIP 속 구성)로 가린다.
    """
    import base64

    _require_user(request)
    url = body.url.strip()
    if not _attachment_host_allowed(url):
        return Response({"detail": "사람인 · 잡코리아에 올라온 첨부파일 링크만 읽을 수 있어요. 다른 곳의 파일은 내려받아 올려 주세요."}, status=400)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (LMS attachment reader)"})
    try:
        with _ATTACHMENT_OPENER.open(req, timeout=20) as resp:
            data = resp.read(QUESTION_PDF_MAX_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        return Response({"detail": "첨부파일을 열지 못했어요. 링크를 확인하거나 파일을 내려받아 올려 주세요."}, status=400)
    if len(data) > QUESTION_PDF_MAX_BYTES:
        return Response({"detail": "첨부파일이 10MB 보다 커요. 문항이 있는 쪽을 캡처해 올려 주세요."}, status=400)
    kinds = {b"%PDF-": "application/pdf", b"\x89PNG": "image/png", b"\xff\xd8\xff": "image/jpeg"}
    kind = next((k for magic, k in kinds.items() if data.startswith(magic)), None)
    office = _office_kind(data)
    if office is not None:
        kind = QUESTION_DOCUMENT_TYPES[office]
    if kind is None:
        return Response({"detail": "PDF · 이미지 · Word · PowerPoint · 한글(hwpx) 파일 링크가 아니에요. 옛 한글(.hwp) 양식은 내려받아 PDF 로 저장해 올려 주세요."}, status=400)
    if kind != "application/pdf" and len(data) > QUESTION_IMAGE_MAX_BYTES:
        return Response({"detail": "이미지는 8MB 이하만 읽을 수 있어요."}, status=400)
    image = f"data:{kind};base64,{base64.b64encode(data).decode('ascii')}"
    return _review_call("/api/v1/resumes/question-extract/proxy", {"images": [image]}, timeout=120)


class QuestionAnswerItemIn(Schema):
    question: str = Field(max_length=500)
    answer: str = Field(max_length=3000)


class QuestionAnswerIn(Schema):
    resumeId: str
    tailoredResumeId: str
    questionId: str
    answers: list[QuestionAnswerItemIn] = []


@api.post("/resume-review/question-answer")
def resume_review_question_answer(request, body: QuestionAnswerIn):
    """공고 맞춤 이력서의 회사 자기소개서 문항 하나에 답을 쓴다 — 공고 요건 · 이력서 근거로.

    기존 첨삭과 따로 돈다. 답만 돌려주고 저장은 하지 않는다(화면이 사용자가 고친 답을 저장한다).
    """
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "tailored_resume_id": body.tailoredResumeId,
        "question_id": body.questionId,
        "answers": [item.dict() for item in body.answers[:12]],
    }
    return _review_call("/api/v1/resumes/question-answer/proxy", payload, timeout=120)


class TailoredPromoteIn(Schema):
    resumeId: str
    tailoredResumeId: str


@api.post("/resume-review/promote")
def resume_review_promote(request, body: TailoredPromoteIn):
    """첨삭을 마친 공고 사본을 편집할 수 있는 이력서로 옮긴다. 새 이력서 id 를 돌려준다."""
    row, error = _owned_resume(request, body.resumeId)
    if error is not None:
        return error
    payload = {
        "uid": row["firebase_uid"],
        "cohort_id": row["code"],
        "resume_id": _review_resume_id(row),
        "tailored_resume_id": body.tailoredResumeId,
    }
    return _review_call("/api/v1/resumes/tailored/promote/proxy", payload, timeout=60)


class JobRecommendIn(Schema):
    resumeId: str
    topK: int = 10
    # 코치 대화에서 "프로젝트만 보고 추천해줘"처럼 좁혀 부를 때. 서버 챗봇이 정해 준 값이다.
    scope: str = "전체"


# 좁혀 읽을 때 지우는 칸 — ai_job_coach_panel.dart 의 _scopedResume 그대로.
# 학력 · 자격증 · 기본정보는 남긴다. 조건 판정(build_profile)은 어차피 이력서 전체에서 뽑는다.
# 자기소개서에는 핵심역량을 남긴다. 자기소개서만으로는 글이 너무 짧아 검색이 흐려진다.
_SCOPE_DROP = {
    "프로젝트": ("experience", "techStack", "awards", "trainingExperience", "otherActivities", "coreCompetencies", "selfIntroduction"),
    "기술스택": ("experience", "projects", "awards", "trainingExperience", "otherActivities", "coreCompetencies", "selfIntroduction"),
    "자기소개서": ("experience", "projects", "techStack", "awards", "trainingExperience", "otherActivities"),
    "경력": ("projects", "techStack", "awards", "trainingExperience", "otherActivities", "coreCompetencies", "selfIntroduction"),
}


def _scoped_content(content: dict, scope: str) -> dict:
    """추천 서버가 **읽을 글**만 남긴 이력서. 모르는 범위면 전체를 쓴다."""
    drop = _SCOPE_DROP.get(scope)
    if drop is None:
        return content
    return {key: value for key, value in content.items() if key not in drop}


def _jobs_resume(request, resume_id: str):
    """공고 추천 · 코치 대화에 쓸 이력서 → (행, 내용, 오류 응답).

    이력서 평문을 화면에서 받지 않는다. 남의 이력서로 추천을 받거나, 화면이 보낸 글이
    DB 와 달라지는 것을 막는다. 본인 이력서이거나 그 기수를 맡은 강사 · 관리자만 읽는다.
    """
    user = _require_user(request)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT r.content, r.user_id, r.cohort_id, u.firebase_uid, p.preferences AS job_preferences
               FROM resumes r JOIN users u ON u.id = r.user_id
               LEFT JOIN user_job_preferences p ON p.user_id = u.id
               WHERE r.legacy_id = %s OR r.id::text = %s""",
            [resume_id, resume_id],
        )
        row = _one(cur)
    if not row:
        return None, None, Response({"detail": "이력서를 찾을 수 없습니다."}, status=404)
    if row["firebase_uid"] != user["firebase_uid"] and not (
        user["role"] in ("admin", "instructor") and can_access_cohort(user, row["cohort_id"])
    ):
        return None, None, Response({"detail": "본인 이력서만 추천받을 수 있습니다."}, status=403)
    content = row["content"] or {}
    if isinstance(content, str):
        content = json.loads(content or "{}")
    return row, content, None


@api.post("/jobs/recommend")
def jobs_recommend(request, body: JobRecommendIn):
    """공고 추천 — 이력서를 DB 에서 읽어 추천 서버(job_matching_bot)로 넘긴다.

    희망 조건은 마이페이지(`user_job_preferences`)에서 읽는다.
    추천은 15초쯤 걸린다. 서버가 없으면(`JOBS_URL` 없음) 무엇이 빠졌는지 알려 준다.
    """
    row, content, error = _jobs_resume(request, body.resumeId)
    if error is not None:
        return error
    resume_text = build_resume_text(_scoped_content(content, body.scope))
    if len(resume_text) < 20:
        return Response({"detail": "이력서 내용이 너무 적습니다. 먼저 이력서를 채워 주세요."}, status=400)

    prefs = row["job_preferences"] or {}
    if isinstance(prefs, str):
        prefs = json.loads(prefs or "{}")
    profile = build_profile(content)
    payload = json.dumps(
        {
            "resume_text": resume_text,
            "preferred_regions": prefs.get("regions") or [],
            "preferred_employment_types": prefs.get("employmentTypes") or [],
            "top_k": max(1, min(body.topK, 12)),
            **profile,
        },
        ensure_ascii=False,
    ).encode("utf-8")

    base = (os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return Response({"detail": "공고 추천 서버가 연결되어 있지 않습니다(JOBS_URL)."}, status=503)
    req = urllib.request.Request(
        f"{base}/api/v1/jobs/recommend",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        return Response({"detail": detail or "공고를 추천하지 못했습니다."}, status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Response({"detail": "공고 추천 서버에 연결하지 못했습니다."}, status=503)


class JobChatIn(Schema):
    message: str = Field(min_length=1, max_length=500)
    # 직전 답의 filters 를 그대로 되돌려 보낸다. 서버가 대화를 저장하지 않아서다.
    filters: dict[str, Any] | None = None
    # 공고 하나를 놓고 묻는 중이면 그 공고
    jobId: str | None = None
    # 있으면 이 이력서의 평문을 서버가 만들어 붙인다. "나한테 맞아?"는 이력서를 봐야 답한다
    resumeId: str | None = None
    lastJobIds: list[str] = []
    lastAnswerJobIds: list[str] = []
    seenJobIds: list[str] = []
    # 직전 검색 답이 준 이어 볼 거리. "더 보여줘"에 그대로 되돌려 보낸다
    requirementQuery: str = Field(default="", max_length=1000)
    preferRoles: list[str] = []


def _jobs_chat_payload(request, body: JobChatIn) -> tuple[dict[str, Any] | None, Response | None]:
    """공고 서버에 넘길 대화 한 턴. 이력서 평문은 화면이 보낸 글이 아니라 DB 에서 만든다."""
    payload: dict[str, Any] = {
        "message": body.message,
        "filters": body.filters,
        "job_id": body.jobId,
        "last_job_ids": body.lastJobIds[:20],
        "last_answer_job_ids": body.lastAnswerJobIds[:20],
        "seen_job_ids": body.seenJobIds[:3000],
        "requirement_query": body.requirementQuery,
        "prefer_roles": body.preferRoles[:20],
    }
    if body.resumeId:
        _row, content, error = _jobs_resume(request, body.resumeId)
        if error is not None:
            return None, error
        payload["resume_text"] = build_resume_text(content)[:50_000] or None
    return payload, None


@api.post("/jobs/chat")
def jobs_chat(request, body: JobChatIn):
    """코치에게 묻기 — 말로 공고를 찾고 채용을 묻는다(job_matching_bot `/api/v1/jobs/chat`).

    조건 해석 · 검색 · 집계는 공고 서버가 한다. 여기서는 로그인을 확인하고 이력서 평문을
    DB 에서 만들어 붙인다. 화면이 보낸 이력서 글은 받지 않는다(추천과 같은 이유).
    """
    _require_user(request)
    payload, error = _jobs_chat_payload(request, body)
    if error is not None:
        return error

    base = (os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return Response({"detail": "공고 서버가 연결되어 있지 않습니다(JOBS_URL)."}, status=503)
    req = urllib.request.Request(
        f"{base}/api/v1/jobs/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail")
        except Exception:
            detail = None
        if not isinstance(detail, str):
            detail = None
        return Response({"detail": detail or "답을 찾지 못했습니다. 잠시 후 다시 물어봐 주세요."}, status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Response({"detail": "공고 서버에 연결하지 못했습니다."}, status=503)


class JobChatMoreIn(Schema):
    # 직전 검색 답이 준 그대로. 서버가 대화를 저장하지 않아서다
    filters: dict[str, Any]
    requirementQuery: str = Field(default="", max_length=1000)
    preferRoles: list[str] = []
    seenJobIds: list[str] = []


@api.post("/jobs/chat/more")
def jobs_chat_more(request, body: JobChatMoreIn):
    """코치 답 아래 「더 보기」 — 같은 조건으로 다음 공고(job_matching_bot `/api/v1/jobs/chat/more`).

    말을 해석하지 않으므로 LLM 호출이 없고 이력서도 필요 없다. 앞에 세울 직무는 직전 답이 준 것을 쓴다.
    """
    _require_user(request)
    base = (os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return Response({"detail": "공고 서버가 연결되어 있지 않습니다(JOBS_URL)."}, status=503)
    payload = {
        "filters": body.filters,
        "requirement_query": body.requirementQuery,
        "prefer_roles": body.preferRoles[:20],
        "seen_job_ids": body.seenJobIds[:3000],
    }
    req = urllib.request.Request(
        f"{base}/api/v1/jobs/chat/more",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return Response({"detail": "공고를 더 불러오지 못했습니다."}, status=exc.code)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return Response({"detail": "공고 서버에 연결하지 못했습니다."}, status=503)


@api.post("/jobs/chat/stream")
def jobs_chat_stream(request, body: JobChatIn):
    """`/jobs/chat`과 같은 대화를, 공고 서버가 만드는 동안 흘려받아 그대로 넘긴다.

    공고 서버의 `/api/v1/jobs/chat/stream`(Server-Sent Events)을 줄 단위로 중계한다.
    열기 전에 막히면(로그인 · 이력서 · 연결) 평소처럼 JSON 오류를 준다. 화면은 그때
    `/jobs/chat`으로 물러난다.
    """
    _require_user(request)
    payload, error = _jobs_chat_payload(request, body)
    if error is not None:
        return error

    base = (os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return Response({"detail": "공고 서버가 연결되어 있지 않습니다(JOBS_URL)."}, status=503)
    req = urllib.request.Request(
        f"{base}/api/v1/jobs/chat/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    try:
        upstream = urllib.request.urlopen(req, timeout=90)
    except urllib.error.HTTPError as exc:
        return Response({"detail": "답을 찾지 못했습니다. 잠시 후 다시 물어봐 주세요."}, status=exc.code)
    except (urllib.error.URLError, TimeoutError):
        return Response({"detail": "공고 서버에 연결하지 못했습니다."}, status=503)

    def relay():
        # 한 줄씩 넘긴다. 모아 두었다 보내면 단계 표시와 글 조각이 한꺼번에 온다.
        try:
            for line in upstream:
                yield line
        except (urllib.error.URLError, TimeoutError, OSError):
            failed = {"event": "error", "status": 503, "detail": "공고 서버와 연결이 끊겼습니다."}
            yield f"data: {json.dumps(failed, ensure_ascii=False)}\n\n".encode("utf-8")
        finally:
            upstream.close()

    response = StreamingHttpResponse(relay(), content_type="text/event-stream; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# 주요 기업 카드는 모든 수강생에게 같다. 후보를 고르는 정규식이 인덱스 없이 공고 전체를 훑어(7~9초) 10분 둔다.
# 수업 시작에 여럿이 한꺼번에 열면 캐시가 빈 동안 같은 조회가 사람 수만큼 RDS 로 간다 — 한 번에 하나만 계산한다
_FEATURED_TTL = 600
_featured_cache: dict[tuple[str, Any], tuple[float, list[dict]]] = {}
_featured_lock = threading.Lock()


def _featured_cards(view: Literal["live", "past"]) -> list[dict]:
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    hit = _featured_cache.get((view, today))
    if hit is not None and time.monotonic() - hit[0] < _FEATURED_TTL:
        return hit[1]
    with _featured_lock:
        # 기다리는 동안 앞 요청이 채웠으면 그것을 쓴다
        hit = _featured_cache.get((view, today))
        if hit is not None and time.monotonic() - hit[0] < _FEATURED_TTL:
            return hit[1]
        cards = _load_featured_cards(view, today)
        # 날짜가 바뀌면 어제 것은 버린다
        for key in [k for k in _featured_cache if k[1] != today]:
            del _featured_cache[key]
        _featured_cache[(view, today)] = (time.monotonic(), cards)
        return cards


def _load_featured_cards(view: Literal["live", "past"], today) -> list[dict]:
    norm = featured_postings.NORM_SQL
    with connection.cursor() as cur:
        # 지원 방법 칸 · 회사 정보 표는 migration 0014 가 만든다(회사 표는 public 스키마). 없으면 빈 값으로 읽는다
        cur.execute(
            """SELECT EXISTS (SELECT 1 FROM information_schema.columns
                              WHERE table_schema = 'jobs' AND table_name = 'jobs' AND column_name = 'apply_method'),
                      to_regclass('public.company_profiles') IS NOT NULL"""
        )
        has_apply, has_profiles = cur.fetchone()
        cur.execute(f"SELECT DISTINCT {norm} FROM jobs.jobs WHERE company_type ~* %s", [featured_postings.BIG_TYPE])
        big_names = frozenset(row[0] for row in cur.fetchall() if row[0])
        # 사람인이 중견 · 중소로만 적은 회사 — 잡코리아가 대기업으로 달아도 대기업으로 치지 않는다
        cur.execute(
            f"""SELECT {norm} FROM jobs.jobs WHERE source = 'SARAMIN_POC' GROUP BY 1
                HAVING bool_or(COALESCE(company_type, '') ~* %s) AND NOT bool_or(COALESCE(company_type, '') ~* %s)""",
            [featured_postings.SMALLER_TYPE, featured_postings.BIG_TYPE],
        )
        small_names = frozenset(row[0] for row in cur.fetchall() if row[0])
        if view == "live":
            when = "j.status = 'OPEN' AND (j.deadline IS NULL OR j.deadline = '' OR j.deadline >= %s)"
            params: list[Any] = [today.isoformat()]
        else:
            # 상태는 보지 않는다 — 마감일이 지났는데 OPEN 으로 남은 공고도 지난 공채다
            when = "j.deadline >= %s AND j.deadline < %s"
            params = [(today - timedelta(days=featured_postings.PAST_DAYS)).isoformat(), today.isoformat()]
        cur.execute(
            f"""SELECT j.job_id, j.source, j.group_key, j.company, j.company_type, j.title, j.deadline, j.posted_at,
                       j.career_type, j.employment_type, j.tech_stack, j.status,
                       {"j.apply_method" if has_apply else "NULL::varchar AS apply_method"},
                       {"p.logo_url" if has_profiles else "NULL::varchar AS logo_url"}
                FROM jobs.jobs j
                {f"LEFT JOIN public.company_profiles p ON p.company_key = {featured_postings.PROFILE_KEY_SQL}" if has_profiles else ""}
                WHERE {when} AND j.career_type IN ('ENTRY', 'ANY')
                  AND (j.company_type ~* %s OR j.company ~* %s OR {norm} = ANY(%s))""",
            [*params, featured_postings.COARSE_TYPE, featured_postings.COARSE_NAME, list(big_names)],
        )
        rows = _dicts(cur)
    pick = featured_postings.pick_live if view == "live" else featured_postings.pick_past
    return pick(rows, today, big_names, small_names)


@api.get("/featured-postings")
def featured_posting_list(request, view: str = "live", tier: str = "", offset: int = 0, limit: int = 12):
    """공고 맞춤 지원 첫 화면의 주요 기업 카드(featured_postings.py).

    `view` 는 live(진행 중) · past(지난 공채). `tier` 로 기업 구분 하나만 거른다. `counts` 는 거르기 단추에 붙일 수다.
    """
    _require_user(request)
    if view not in ("live", "past"):
        return Response({"detail": "view 는 live 나 past 여야 합니다."}, status=400)
    cards = _featured_cards(view)
    shown = [c for c in cards if c["tier"] == tier] if tier else cards
    offset = max(offset, 0)
    return {
        "items": shown[offset : offset + max(1, min(limit, 48))],
        "total": len(shown),
        "counts": {t: sum(1 for c in cards if c["tier"] == t) for t in featured_postings.TIERS},
    }


class SharedQuestionItemIn(Schema):
    question: str = Field(max_length=500)
    limit: int | None = None


class SharedQuestionsIn(Schema):
    jobId: str = Field(min_length=1, max_length=255)
    roleName: str = Field(min_length=1, max_length=255)
    questions: list[SharedQuestionItemIn] = Field(max_length=20)
    share: bool = True


class SharedQuestionReportIn(Schema):
    reason: str = Field(max_length=40)


def _shared_call(fn, *args, **kwargs):
    from lms import shared_questions

    try:
        return fn(*args, **kwargs)
    except shared_questions.SharedQuestionError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


def _role_id(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


@api.get("/apply/shared-questions")
def shared_question_list(request, jobId: str):
    """공고 맞춤 지원 3단계 — 고른 공고의 회사 · 시즌에 다른 수강생이 정리한 문항(직무별 · 공통). shared_questions.py"""
    from lms import shared_questions

    user = _require_user(request)
    return _shared_call(shared_questions.list_shared, user["id"], jobId)


@api.post("/apply/shared-questions/check")
def shared_question_check(request, body: SharedQuestionsIn):
    """확정 전 — 이름은 다른데 문항이 같은 직무가 있으면 알려 준다(합칠지 묻는다)."""
    from lms import shared_questions

    user = _require_user(request)
    questions = [q.dict() for q in body.questions]
    return _shared_call(shared_questions.check, user["id"], body.jobId, body.roleName, questions)


@api.post("/apply/shared-questions")
def shared_question_save(request, body: SharedQuestionsIn):
    """학생이 문항을 확정했을 때 남긴다. share=False 면 올린 학생만 본다. 답 · 메모는 받지 않는다."""
    from lms import shared_questions

    user = _require_user(request)
    questions = [q.dict() for q in body.questions]
    return _shared_call(shared_questions.save, user["id"], body.jobId, body.roleName, questions, share=body.share)


@api.post("/apply/shared-questions/{role_id}/use")
def shared_question_use(request, role_id: str):
    """「이 문항으로 쓰기」 — 사용 수를 올린다(올린 학생 자신은 세지 않는다)."""
    from lms import shared_questions

    user = _require_user(request)
    if not _role_id(role_id):
        return Response({"detail": "정리를 찾을 수 없어요."}, status=404)
    result = _shared_call(shared_questions.use, user["id"], role_id)
    return result if isinstance(result, Response) else {"ok": True}


@api.post("/apply/shared-questions/{role_id}/report")
def shared_question_report(request, role_id: str, body: SharedQuestionReportIn):
    """이상해요 — 2명이 누르면 숨긴다. recruit_role_reports 표가 생기기 전에는 503."""
    from lms import shared_questions

    user = _require_user(request)
    if not _role_id(role_id):
        return Response({"detail": "정리를 찾을 수 없어요."}, status=404)
    return _shared_call(shared_questions.report, user["id"], role_id, body.reason)


@api.get("/postings/{job_id}", auth=None)
def job_posting(request, job_id: str):
    """공고 원문 한 건 — 추천 카드에서 새 탭으로 여는 화면이 읽는다.

    채용 사이트에 공개된 공고를 수집해 둔 것이라 로그인 없이 준다. 새 탭은 로그인 정보
    (sessionStorage)를 넘겨받지 못한다. 마감돼 사이트에서 내려간 공고도 수집본으로 읽힌다.
    """
    with connection.cursor() as cur:
        cur.execute(
            """SELECT job_id, source, source_url, company, title, description, region,
                      career_type, min_career_years, employment_type, education, deadline, status,
                      required_skills, preferred_skills, body_is_image, group_key
               FROM jobs.jobs WHERE job_id = %s""",
            [job_id],
        )
        row = _one(cur)
        if row and row["group_key"]:
            # 같은 공고가 사람인 · 잡코리아에 함께 올라오면 수집기가 group_key 로 묶어 둔다.
            # 사이트마다 원문 링크를 준다. 사이트에서 내려간(REMOVED) 쪽은 링크가 죽어 뺀다
            cur.execute(
                """SELECT job_id, source, source_url, status FROM jobs.jobs
                   WHERE group_key = %s AND status <> 'REMOVED'
                   ORDER BY (job_id = %s) DESC, (status = 'OPEN') DESC, source""",
                [row["group_key"], job_id],
            )
            row["links"] = _dicts(cur)
    if not row:
        return Response({"detail": "공고를 찾을 수 없습니다."}, status=404)
    row.setdefault("links", [{k: row[k] for k in ("job_id", "source", "source_url", "status")}])
    del row["group_key"]
    for key in ("required_skills", "preferred_skills"):
        if isinstance(row[key], str):
            row[key] = json.loads(row[key] or "[]")
    return row


# 회사 채용 사이트 주소는 공고가 바뀌지 않는 한 그대로다. 찾으면 6시간, 못 찾았으면 10분 둔다
# (사이트가 잠깐 안 열렸던 것일 수 있다)
_APPLY_LINK_TTL = 6 * 3600
_APPLY_LINK_MISS_TTL = 600
_APPLY_LINK_CACHE_SIZE = 2000
_apply_link_cache: dict[str, tuple[float, dict]] = {}


def _read_listing_page(url: str) -> str | None:
    """사람인 · 잡코리아 페이지 한 장. 허용 목록 밖으로 넘겨 가면 열지 않는다(_ATTACHMENT_OPENER)."""
    if not _attachment_host_allowed(url):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (LMS apply link reader)"})
    try:
        with _ATTACHMENT_OPENER.open(req, timeout=10) as resp:
            return resp.read(2_000_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


@api.get("/postings/{job_id}/apply-link")
def posting_apply_link(request, job_id: str):
    """홈페이지 지원 공고의 회사 채용 사이트 주소(apply_link.py). 못 찾으면 url 이 null — 화면이 공고 원문을 연다.

    같은 공고가 사람인 · 잡코리아에 함께 있으면(group_key) 잡코리아 쪽을 먼저 본다. 공고 페이지로 바로 가서다.
    `precise` 는 공고 페이지로 바로 가는 주소인가(잡코리아)다. 사람인 주소는 채용 사이트 첫 화면일 때가 많다.
    """
    _require_user(request)
    hit = _apply_link_cache.get(job_id)
    if hit is not None:
        ttl = _APPLY_LINK_TTL if hit[1]["url"] else _APPLY_LINK_MISS_TTL
        if time.monotonic() - hit[0] < ttl:
            return hit[1]
    with connection.cursor() as cur:
        cur.execute("SELECT job_id, group_key FROM jobs.jobs WHERE job_id = %s", [job_id])
        row = _one(cur)
        if row is None:
            return Response({"detail": "공고를 찾을 수 없습니다."}, status=404)
        ids = [job_id]
        if row["group_key"]:
            cur.execute(
                "SELECT job_id FROM jobs.jobs WHERE group_key = %s AND job_id <> %s AND status <> 'REMOVED'",
                [row["group_key"], job_id],
            )
            ids += [r["job_id"] for r in _dicts(cur)]
    found = apply_link.find_homepage(ids, _read_listing_page)
    result = (
        {"url": found[0], "precise": found[1].startswith("JOBKOREA-")}
        if found is not None
        else {"url": None, "precise": False}
    )
    _apply_link_cache[job_id] = (time.monotonic(), result)
    # 눌린 공고마다 쌓인다. 넘치면 오래된 것부터 버린다(dict 는 넣은 순서를 지킨다)
    while len(_apply_link_cache) > _APPLY_LINK_CACHE_SIZE:
        del _apply_link_cache[next(iter(_apply_link_cache))]
    return result


@api.get("/posting-link")
def posting_by_link(request, url: str = ""):
    """붙여 넣은 공고 링크로 수집해 둔 공고를 찾는다 — 공고 맞춤 지원 화면이 쓴다.

    `/postings/{job_id}` 와 같은 모양으로 돌려준다. 링크의 공고 번호로 job_id 를 만들어
    기본 키로 찾으므로(posting_link.py) 수집 안 된 공고는 404 다.
    """
    _require_user(request)
    job_id = job_id_from_link(url)
    if job_id is None:
        return Response({"detail": "사람인 · 잡코리아 공고 상세 페이지 주소를 붙여 넣어 주세요."}, status=400)
    found = job_posting(request, job_id)
    if isinstance(found, Response):
        return Response({"detail": "아직 수집되지 않은 공고예요. 수집된 공고만 불러올 수 있어요."}, status=404)
    if found["status"] in ("REMOVED", "EXPIRED"):
        # 둘 다 틀릴 수 있다. REMOVED 는 목록에서 몇 번 안 보였다는 뜻일 뿐이고, EXPIRED 는 목록 문구의
        # 옛 마감일 기준이라 회사가 마감일을 늘리면 열린 공고가 걸린다(9/20 → 9/30 연장). 페이지를 열어 확인한다
        alive = _verify_posting(job_id)
        if alive is True:
            # 공고 서버가 OPEN 으로 되돌렸다(EXPIRED 는 페이지 마감일이 안 지났을 때만). 다시 읽는다
            found = job_posting(request, job_id)
        elif alive is False:
            # 페이지에 「마감되었습니다」가 떠 있다(조기 마감). 화면이 까닭을 바로 말하게 CLOSED 로 준다
            found["status"] = "CLOSED"
    return found


def _verify_posting(job_id: str) -> bool | None:
    """공고 서버가 페이지를 열어 보고 살아 있으면 OPEN 으로 되돌린다. True=열림 · False=마감 · None=모름.

    확인이 안 되면(서버 없음 · 다른 사이트 · 일시 오류) None — 저장소 상태를 그대로 보여 준다.
    """
    base = (os.environ.get("JOBS_URL") or "").rstrip("/")
    if not base:
        return None
    req = urllib.request.Request(
        f"{base}/api/v1/jobs/verify",
        data=json.dumps({"job_id": job_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            alive = json.loads(resp.read().decode("utf-8")).get("alive")
            return alive if isinstance(alive, bool) else None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


class JobRequirementsIn(Schema):
    jobId: str = Field(min_length=1, max_length=200)


@api.post("/resume-review/requirements")
def resume_review_requirements(request, body: JobRequirementsIn):
    """공고 하나의 요건(필수 · 우대 · 주요 업무)과 원문 인용 — 이력서를 만들기 전에 보여 준다.

    이력서를 읽지 않으므로 로그인만 확인한다. 요건은 첨삭 서버가 공고 스냅샷마다 한 번 만들어
    저장한 것을 첫 첨삭과 같이 쓴다. 마감 · 이미지 공고면 첨삭과 같은 까닭(409 · 422)으로 막힌다.
    """
    _require_user(request)
    return _review_call("/api/v1/resumes/job-requirements/proxy", {"job_id": body.jobId}, timeout=60)


@api.get("/bootstrap")
def bootstrap(request):
    user = _require_user(request)
    return build_bootstrap(user)


def _notice_image_key(data: dict, user: dict, current: str | None = None) -> str | None | bool:
    if "imageStorageKey" not in data and "imageUrl" not in data:
        return current
    key = data.get("imageStorageKey", data.get("imageUrl"))
    if key in (None, "") or key == current:
        return key or None
    if not isinstance(key, str):
        return False
    import re

    own_file = re.fullmatch(
        rf"notices/{re.escape(user['firebase_uid'])}/[0-9a-f]{{32}}\.(?:png|jpg|gif|webp)", key
    )
    return key if own_file or key.startswith("https://") else False


@api.post("/notices")
def create_notice(request, body: dict[str, Any] = Body(...)):
    user = _require_user(request)
    data = _data(body)
    if user["role"] not in ("admin", "instructor"):
        return Response({"detail": "forbidden"}, status=403)
    title = data.get("title") or ""
    content = data.get("content") or ""
    image_key = _notice_image_key(data, user)
    if image_key is False:
        return Response({"detail": "본인이 올린 공지 이미지만 사용할 수 있습니다."}, status=400)
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
                """INSERT INTO notices (cohort_id, title, content, author_id, author_name, is_favorite, priority, image_storage_key, vector_chunk_count, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0, now(), now()) RETURNING id""",
                [
                    cohort_id,
                    title,
                    content,
                    user["id"],
                    user["display_name"],
                    bool(data.get("isFavorite")),
                    int(data.get("priority") or 0),
                    image_key,
                ],
            )
            notice_id = cur.fetchone()[0]
        schedule_notice_vector(
            cohort_code=code,
            notice_id=notice_id,
            data={
                "title": title,
                "content": content,
                "image_storage_key": image_key,
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
                """SELECT n.id, n.cohort_id, n.vector_chunk_count, n.author_id, c.code, n.title, n.content,
                          n.image_storage_key, n.is_favorite, n.priority
                   FROM notices n JOIN cohorts c ON c.id = n.cohort_id WHERE n.id = %s""",
                [pk],
            )
            row = cur.fetchone()
            if not row:
                return Response({"detail": "not found"}, status=404)
            _id, cohort_id, chunk_count, author_id, code, title, content, old_image_key, favorite, priority = row
            if user["role"] != "admin" and not (
                user["role"] == "instructor" and user["id"] == author_id
            ):
                return Response({"detail": "forbidden"}, status=403)
            title = data.get("title", title)
            content = data.get("content", content)
            image_key = _notice_image_key(data, user, old_image_key)
            if image_key is False:
                return Response({"detail": "본인이 올린 공지 이미지만 사용할 수 있습니다."}, status=400)
            cur.execute(
                "UPDATE notices SET title=%s, content=%s, is_favorite=%s, priority=%s, image_storage_key=%s, updated_at=now() WHERE id=%s",
                [title, content, bool(data.get("isFavorite", favorite)), int(data.get("priority", priority) or 0), image_key, pk],
            )
        schedule_notice_vector(
            cohort_code=code,
            notice_id=pk,
            data={"title": title, "content": content, "image_storage_key": image_key, "author_id": author_id},
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


def _counsel(request, call):
    from lms.counsel_service import CounselError

    user = _require_user(request)
    try:
        with transaction.atomic(), connection.cursor() as cur:
            return call(cur, user)
    except PermissionError:
        return Response({"detail": "forbidden"}, status=403)
    except CounselError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.get("/counsel-notes")
def counsel_notes(request, student: str = "", cohort: str = ""):
    from lms.counsel_service import list_notes

    return _counsel(request, lambda cur, user: {"notes": list_notes(cur, user, student, cohort)})


@api.post("/counsel-notes")
def counsel_note_create(request, body: dict[str, Any] = Body(...)):
    from lms.counsel_service import create_note

    return _counsel(request, lambda cur, user: {"note": create_note(cur, user, _data(body))})


@api.patch("/counsel-notes/{pk}")
def counsel_note_update(request, pk: int, body: dict[str, Any] = Body(...)):
    from lms.counsel_service import update_note

    return _counsel(request, lambda cur, user: {"note": update_note(cur, user, pk, _data(body))})


@api.delete("/counsel-notes/{pk}")
def counsel_note_delete(request, pk: int):
    from lms.counsel_service import delete_note

    def run(cur, user):
        delete_note(cur, user, pk)
        return {"ok": True}

    return _counsel(request, run)


def _quest(request, call):
    from lms.quest_service import QuestError

    user = _require_user(request)
    try:
        with transaction.atomic(), connection.cursor() as cur:
            return call(cur, user)
    except PermissionError:
        return Response({"detail": "forbidden"}, status=403)
    except QuestError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.get("/quests")
def quests(request, cohort: str = ""):
    from lms.quest_service import list_quests

    return _quest(request, lambda cur, user: list_quests(cur, user, cohort))


@api.post("/quests")
def quest_create(request, body: dict[str, Any] = Body(...)):
    from lms.quest_service import create_quest

    return _quest(request, lambda cur, user: {"quest": create_quest(cur, user, _data(body))})


@api.patch("/quests/{pk}")
def quest_update(request, pk: int, body: dict[str, Any] = Body(...)):
    from lms.quest_service import update_quest

    return _quest(request, lambda cur, user: {"quest": update_quest(cur, user, pk, _data(body))})


@api.post("/quests/{pk}/submit")
def quest_submit(request, pk: int, body: dict[str, Any] = Body(...)):
    from lms.quest_service import submit_quest

    return _quest(request, lambda cur, user: {"submission": submit_quest(cur, user, pk, _data(body))})


@api.get("/quest-submissions")
def quest_submissions(request, cohort: str = "", status: str = "", quest: str = ""):
    from lms.quest_service import list_submissions

    return _quest(request, lambda cur, user: {"submissions": list_submissions(cur, user, cohort, status, quest)})


@api.post("/quest-submissions/{pk}/review")
def quest_review(request, pk: int, body: dict[str, Any] = Body(...)):
    from lms.quest_service import review_submission

    return _quest(request, lambda cur, user: {"submission": review_submission(cur, user, pk, _data(body))})


@api.post("/command")
def command(request, body: CommandIn):
    user = _require_user(request)
    status, result = _run_op(body.op, user, body.payload or {})
    return Response(result, status=status)


def _assessment(call):
    from lms.assessment_service import AssessmentError

    try:
        with connection.cursor() as cur:
            return call(cur)
    except AssessmentError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.get("/assessments/{assessment_id}/take")
def assessment_take(request, assessment_id: str):
    """응시할 문항 — 정답 · 해설 없이(getAssessmentForTake). bootstrap 은 학생에게 문항을 보내지 않는다."""
    from lms.assessment_service import take

    user = _require_user(request)
    return _assessment(lambda cur: take(cur, user, assessment_id))


RECORD_FILE_MAX_BYTES = 10 * 1024 * 1024
RECORD_FILE_TYPES = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp",
    "image/heic": ".heic", "application/pdf": ".pdf",
}


NOTICE_IMAGE_TYPES = {key: ext for key, ext in RECORD_FILE_TYPES.items() if key.startswith("image/") and key != "image/heic"}


@api.post("/uploads/notice-image")
def upload_notice_image(request, file: UploadedFile = File(...)):
    import uuid

    from lms import notice_vectors
    from lms.storage import put_object, read_url

    user = _require_user(request)
    if user["role"] not in ("admin", "instructor"):
        return Response({"detail": "forbidden"}, status=403)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in NOTICE_IMAGE_TYPES:
        return Response({"detail": "JPG, PNG, GIF, WEBP 이미지만 올릴 수 있습니다."}, status=400)
    if file.size is not None and file.size > RECORD_FILE_MAX_BYTES:
        return Response({"detail": "파일은 10MB 이하만 올릴 수 있습니다."}, status=400)
    data = file.read(RECORD_FILE_MAX_BYTES + 1)
    if len(data) > RECORD_FILE_MAX_BYTES:
        return Response({"detail": "파일은 10MB 이하만 올릴 수 있습니다."}, status=400)
    signatures = {
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/gif": data.startswith((b"GIF87a", b"GIF89a")),
        "image/webp": data.startswith(b"RIFF") and data[8:12] == b"WEBP",
    }
    if not signatures[content_type]:
        return Response({"detail": "올바른 이미지 파일이 아닙니다."}, status=400)
    key = f"notices/{user['firebase_uid']}/{uuid.uuid4().hex}{NOTICE_IMAGE_TYPES[content_type]}"
    try:
        extracted_text = notice_vectors.extract_image_text(data, content_type)
    except Exception:  # noqa: BLE001 — OpenAI 권한 · 네트워크 · 미지원 이미지
        return Response({"detail": "이미지의 글자를 읽지 못했습니다. 이미지를 확인하고 다시 시도해 주세요."}, status=502)
    try:
        put_object(key, data, content_type)
        put_object(key + ".txt", extracted_text.encode("utf-8"), "text/plain; charset=utf-8")
    except Exception:  # noqa: BLE001 — S3 권한 · 네트워크
        return Response({"detail": "이미지를 저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요."}, status=502)
    return {"key": key, "url": read_url(key)}


@api.post("/uploads/record-evidence")
def upload_record_evidence(request, file: UploadedFile = File(...)):
    """기록 증빙 한 장 — 이미지 · PDF, 10MB 까지. 키를 돌려주고, 제출할 때 그 키를 files 로 붙인다.

    키에 올린 학생 uid 가 들어간다(records/기수/uid/무작위). 제출 때 본인 키인지 이것으로 본다.
    """
    import uuid

    from lms.storage import put_object, read_url

    user = _require_user(request)
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type not in RECORD_FILE_TYPES:
        return Response({"detail": "이미지나 PDF 만 올릴 수 있습니다."}, status=400)
    if file.size is not None and file.size > RECORD_FILE_MAX_BYTES:
        return Response({"detail": "파일은 10MB 이하만 올릴 수 있습니다."}, status=400)
    data = file.read(RECORD_FILE_MAX_BYTES + 1)
    if len(data) > RECORD_FILE_MAX_BYTES:
        return Response({"detail": "파일은 10MB 이하만 올릴 수 있습니다."}, status=400)
    key = f"records/{user.get('cohort_code') or 'none'}/{user['firebase_uid']}/{uuid.uuid4().hex}{RECORD_FILE_TYPES[content_type]}"
    try:
        put_object(key, data, content_type)
    except Exception:  # noqa: BLE001 — S3 권한 · 네트워크
        return Response({"detail": "파일을 저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요."}, status=502)
    return {"key": key, "name": file.name, "contentType": content_type, "size": len(data), "url": read_url(key)}


@api.get("/files", auth=None)
def stored_file(request, t: str = ""):
    """로컬 저장 파일 읽기 — bootstrap 이 준 서명 주소(1시간). S3 를 쓰면 S3 서명 주소로 가서 여기에 오지 않는다."""
    import mimetypes

    from django.http import FileResponse, Http404

    from lms.storage import key_from_read_token, local_path

    key = key_from_read_token(t)
    path = local_path(key) if key else None
    if path is None or not path.is_file():
        raise Http404("file")
    return FileResponse(open(path, "rb"), content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")


@api.get("/assessments/{assessment_id}/review")
def assessment_review(request, assessment_id: str, submissionId: str = ""):
    """제출 뒤 결과 — 정답 · 해설 + 답안(getAssessmentReview). 학생은 자기 것만."""
    from lms.assessment_service import review

    user = _require_user(request)
    return _assessment(lambda cur: review(cur, user, assessment_id, submissionId or None))


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


@api.post("/qual-exams/sync")
def qual_exams_sync(request):
    """관리자 — 공공데이터포털에서 시험 일정을 지금 다시 받는다"""
    from lms.external_feeds import FeedError, sync_qual_exams

    user = _require_user(request)
    if user["role"] != "admin":
        return Response({"detail": "forbidden"}, status=403)
    try:
        counts = sync_qual_exams()
    except FeedError as exc:
        return Response({"detail": exc.detail}, status=exc.status)
    return {"ok": True, "counts": {str(year): n for year, n in counts.items()}}


@api.get("/study/youtube-weekly")
def study_youtube_weekly(request, cohortId: str = "", force: bool = False):
    """이번 주 커리큘럼 주제로 찾은 YouTube 영상(12시간 캐시). force 는 강사·관리자만."""
    from lms.external_feeds import FeedError, weekly_youtube

    user = _require_user(request)
    try:
        return weekly_youtube(user, cohortId, force=force)
    except FeedError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


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


@api.get("/alert-popups/mine")
def my_alert_popups(request):
    """학생 화면이 새 알림 · 출결 신청 처리 결과를 확인하는 가벼운 조회 — 1분마다 bootstrap 전체를 다시 받지 않게 한다."""
    from lms.attendance_requests import public_request
    from lms.jsonutil import public_row
    from lms.storage import read_url

    user = _require_user(request)
    if user["role"] != "student" or not user.get("cohort_id"):
        return {"alertPopups": [], "dismissals": [], "readPopupIds": [], "attendanceIssues": []}
    with connection.cursor() as cur:
        cur.execute(
            """SELECT p.*, u.display_name AS author_name FROM alert_popups p
               LEFT JOIN users u ON u.id = p.author_id
               WHERE p.cohort_id = %s AND p.is_active = true
                 AND (p.end_date IS NULL OR p.end_date >= (now() AT TIME ZONE 'Asia/Seoul')::date)
                 AND (NOT EXISTS (SELECT 1 FROM alert_popup_targets t WHERE t.popup_id = p.id)
                      OR EXISTS (SELECT 1 FROM alert_popup_targets t WHERE t.popup_id = p.id AND t.user_id = %s))
               ORDER BY p.sort_order NULLS LAST, p.created_at DESC NULLS LAST""",
            [user["cohort_id"], user["id"]],
        )
        popups = _dicts(cur)
        cur.execute("SELECT * FROM alert_popup_dismissals WHERE user_id = %s", [user["id"]])
        dismissals = _dicts(cur)
        cur.execute("SELECT popup_id FROM alert_popup_reads WHERE user_id = %s", [user["id"]])
        read_ids = [str(row[0]) for row in cur.fetchall()]
        cur.execute(
            """SELECT id, user_id, cohort_id, attendance_date, issue_type, status, details,
                      evidence_storage_key, reviewed_by_id, reviewed_at, created_at
               FROM attendance_issue_reports WHERE user_id = %s
               ORDER BY attendance_date DESC, created_at DESC""",
            [user["id"]],
        )
        issues = _dicts(cur)
    uid_by_pk = {user["id"]: user["firebase_uid"]}
    code_by_pk = {user["cohort_id"]: user.get("cohort_code")}
    return {
        "alertPopups": [public_row(p, uid_by_pk, code_by_pk) for p in popups],
        "dismissals": [public_row(d, uid_by_pk, code_by_pk) for d in dismissals],
        "readPopupIds": read_ids,
        "attendanceIssues": [public_request(row, uid_by_pk, read_url) for row in issues],
    }


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


@api.post("/alert-popups/{pk}/read")
def read_alert(request, pk: int):
    user = _require_user(request)
    status, result = _run_op("markAlertRead", user, {"popupId": pk})
    return Response(result, status=status)


class AssistantIn(Schema):
    messages: list[dict[str, Any]] = Field(default_factory=list)
    context: str = ""
    cohortId: str = ""


class AssistantActionIn(Schema):
    action: dict[str, Any] = Field(default_factory=dict)
    cohortId: str = ""


def _assistant_cohort(user: dict, cohort_key: str) -> int | None:
    with connection.cursor() as cur:
        cohort_id = resolve_cohort(cur, cohort_key or None, user)
    return cohort_id if cohort_id is not None and can_access_cohort(user, cohort_id) else None


@api.post("/admin/assistant")
def admin_assistant(request, body: AssistantIn):
    from lms.admin_assistant import AssistantError, run_assistant

    user = _require_user(request)
    cohort_id = _assistant_cohort(user, body.cohortId)
    if cohort_id is None:
        return Response({"detail": "forbidden"}, status=403)
    try:
        return run_assistant(user, cohort_id, body.messages, context_token=body.context)
    except AssistantError as exc:
        return Response({"detail": exc.detail}, status=exc.status)


@api.post("/admin/assistant/execute")
def admin_assistant_execute(request, body: AssistantActionIn):
    from lms.admin_assistant import AssistantError, execute_action

    user = _require_user(request)
    cohort_id = _assistant_cohort(user, body.cohortId)
    if cohort_id is None:
        return Response({"detail": "forbidden"}, status=403)
    try:
        return execute_action(user, cohort_id, body.action)
    except AssistantError as exc:
        return Response({"detail": exc.detail}, status=exc.status)
    except PermissionError:
        return Response({"detail": "forbidden"}, status=403)
    except (KeyError, ValueError) as exc:
        return Response({"detail": str(exc)}, status=400)
