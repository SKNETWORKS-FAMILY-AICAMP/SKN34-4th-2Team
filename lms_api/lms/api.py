"""Django Ninja API. URL·JSON 계약은 기존 DRF /api 와 동일."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from django.db import connection, transaction
from django.http import HttpRequest
from django.views.decorators.csrf import ensure_csrf_cookie
from ninja import NinjaAPI, Schema
from ninja.responses import Response
from ninja.security import HttpBearer
from pydantic import ConfigDict, Field
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from lms.bootstrap_service import build_bootstrap
from lms.commands import dispatch, resolve_cohort
from lms.jwt_auth import AuthError, issue_tokens, load_lms_user, user_from_access
from lms.permissions import can_access_cohort
from lms.publish import publish_scheduled_notices
from lms.resume_text import build_profile, build_resume_text
from lms.services import schedule_notice_vector
from lms import practice_auto, practice_custom, study_note_service, study_source_service


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


class LooseBody(Schema):
    """DRF request.data 처럼 임의 JSON을 받는다."""

    model_config = ConfigDict(extra="allow")


class LoginIn(Schema):
    email: str = ""
    password: str = ""


class RefreshIn(Schema):
    refresh: str = ""


class CommandIn(Schema):
    op: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _data(body: LooseBody | None) -> dict[str, Any]:
    if body is None:
        return {}
    return body.model_dump(exclude_none=False)


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
    if stored and stored != password:
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
def password(request, body: LooseBody):
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
        if not must_change and stored and stored != current:
            return Response({"ok": False, "message": "현재 비밀번호가 올바르지 않습니다."}, status=400)
        cur.execute(
            """UPDATE users
               SET password = %s, must_change_password = false, updated_at = now()
               WHERE id = %s""",
            [new_password, user["id"]],
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
    payload = json.dumps(
        {"message": message, "uid": user["firebase_uid"], "thread_id": "web"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/api/v1/student-chatbot/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
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


def _owned_resume(request, resume_id: str):
    """이 학생이 볼 수 있는 이력서인지 보고 (행, 오류) 를 돌려준다."""
    user = _require_user(request)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT r.legacy_id, c.code, u.firebase_uid, r.cohort_id
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


@api.patch("/study-sources/{source_id}")
def study_sources_update(request, source_id: str, body: StudySourcePatch):
    """공개 · 숨김, 이름 바꾸기"""
    user = _require_user(request)
    return _sources(lambda: study_source_service.update_source(user, source_id, is_active=body.isActive, title=body.title))


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
        "resume_id": row["legacy_id"],
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
        "resume_id": row["legacy_id"],
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
        "resume_id": row["legacy_id"],
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
    ):
        if value:
            payload[key] = value
    return _review_call("/api/v1/resumes/reviews/proxy", payload)


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
    payload = {"uid": row["firebase_uid"], "cohort_id": row["code"], "resume_id": row["legacy_id"]}
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
        "resume_id": row["legacy_id"],
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
        "resume_id": row["legacy_id"],
        "tailored_resume_id": body.tailoredResumeId,
        "state": body.state,
    }
    return _review_call("/api/v1/resumes/tailored/session/proxy", payload, timeout=60)


class TailoredResumeIn(Schema):
    resumeId: str
    selectedJobId: str


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
        "resume_id": row["legacy_id"],
        "selected_job_id": body.selectedJobId,
    }
    return _review_call("/api/v1/resumes/tailored/proxy", payload, timeout=60)


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
        "resume_id": row["legacy_id"],
        "tailored_resume_id": body.tailoredResumeId,
    }
    return _review_call("/api/v1/resumes/tailored/promote/proxy", payload, timeout=60)


class JobRecommendIn(Schema):
    resumeId: str
    topK: int = 10


@api.post("/jobs/recommend")
def jobs_recommend(request, body: JobRecommendIn):
    """공고 추천 — 이력서를 DB 에서 읽어 추천 서버(job_matching_bot)로 넘긴다.

    이력서 평문을 화면에서 받지 않는다. 남의 이력서로 추천을 받거나, 화면이 보낸 글이
    DB 와 달라지는 것을 막는다. 희망 조건은 마이페이지(`users.job_preferences`)에서 읽는다.

    추천은 15초쯤 걸린다. 서버가 없으면(`JOBS_URL` 없음) 무엇이 빠졌는지 알려 준다.
    """
    user = _require_user(request)
    with connection.cursor() as cur:
        cur.execute(
            """SELECT r.content, r.user_id, r.cohort_id, u.firebase_uid, u.job_preferences
               FROM resumes r JOIN users u ON u.id = r.user_id
               WHERE r.legacy_id = %s OR r.id::text = %s""",
            [body.resumeId, body.resumeId],
        )
        row = _one(cur)
    if not row:
        return Response({"detail": "이력서를 찾을 수 없습니다."}, status=404)
    # 본인 이력서이거나, 그 기수를 맡은 강사 · 관리자여야 한다
    if row["firebase_uid"] != user["firebase_uid"] and not (
        user["role"] in ("admin", "instructor") and can_access_cohort(user, row["cohort_id"])
    ):
        return Response({"detail": "본인 이력서만 추천받을 수 있습니다."}, status=403)

    content = row["content"] or {}
    if isinstance(content, str):
        content = json.loads(content or "{}")
    resume_text = build_resume_text(content)
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
                      required_skills, preferred_skills, body_is_image
               FROM jobs.jobs WHERE job_id = %s""",
            [job_id],
        )
        row = _one(cur)
    if not row:
        return Response({"detail": "공고를 찾을 수 없습니다."}, status=404)
    for key in ("required_skills", "preferred_skills"):
        if isinstance(row[key], str):
            row[key] = json.loads(row[key] or "[]")
    return row


@api.get("/bootstrap")
def bootstrap(request):
    user = _require_user(request)
    return build_bootstrap(user)


@api.post("/notices")
def create_notice(request, body: LooseBody):
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
                """INSERT INTO notices (cohort_id, title, content, author_id, author_name, is_favorite, priority, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s, now(), now()) RETURNING id""",
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
def patch_notice(request, pk: int, body: LooseBody):
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
def mileage_adjust(request, body: LooseBody):
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
def create_scheduled(request, body: LooseBody):
    user = _require_user(request)
    status, result = _run_op(
        "upsertScheduledNotice", user, {**_data(body), "action": "insert"}
    )
    return Response(result, status=status)


@api.patch("/scheduled-notices/{pk}")
def patch_scheduled(request, pk: int, body: LooseBody):
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


@api.post("/scheduled-notices/publish")
def publish_scheduled(request, body: LooseBody):
    user = _require_user(request)
    if user["role"] not in ("admin", "instructor"):
        return Response({"detail": "forbidden"}, status=403)
    data = _data(body)
    ids = data.get("ids") or data.get("scheduledIds")
    count = publish_scheduled_notices(ids=ids)
    return {"ok": True, "published": count}


@api.post("/alert-popups")
def create_alert(request, body: LooseBody):
    user = _require_user(request)
    status, result = _run_op("upsertAlertPopup", user, {**_data(body), "action": "insert"})
    return Response(result, status=status)


@api.patch("/alert-popups/{pk}")
def patch_alert(request, pk: int, body: LooseBody):
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
def dismiss_alert(request, pk: int, body: LooseBody = None):
    user = _require_user(request)
    status, result = _run_op(
        "dismissAlertPopup", user, {**_data(body), "popupId": pk}
    )
    return Response(result, status=status)
