"""Firebase 학생 정보로 LMS 챗봇을 초기화하고 NDJSON으로 스트리밍한다."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from functools import lru_cache
from typing import Any, Iterator

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from firebase_admin import auth, credentials, firestore, storage
from pydantic import BaseModel, Field

from chatbot.firebase_student_context import (
    load_student_context,
    load_unit_period_context,
    parse_schedule_date,
)
from chatbot.ops_log import (
    build_done_event,
    build_generation_log_payload,
    write_generation_log,
)
from chatbot.student_chatbot import LmsStudentChatbot, create_student_chatbot

router = APIRouter(prefix="/api/v1/student-chatbot", tags=["student-chatbot"])
THREAD_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class InitRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=80, pattern=THREAD_RE.pattern)


class ChatRequest(InitRequest):
    question: str = Field(min_length=1, max_length=2000)


_parse_schedule_date = parse_schedule_date


@lru_cache
def _firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        options = None
        if project_id:
            options = {
                "projectId": project_id,
                "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
                or f"{project_id}.firebasestorage.app",
            }
        return firebase_admin.initialize_app(credentials.ApplicationDefault(), options)


def _student_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Firebase 로그인이 필요합니다")
    try:
        app = _firebase_app()
        uid = auth.verify_id_token(authorization[7:].strip(), app=app).get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("missing uid")
        db = firestore.client(app=app)
        profile = db.collection("users").document(uid).get().to_dict() or {}
        if profile.get("role") != "student" or profile.get("isActive") is not True:
            raise HTTPException(status_code=403, detail="학생 계정만 챗봇을 사용할 수 있습니다")
        cohort = str(profile.get("cohortId") or "").strip()
        if not cohort:
            raise HTTPException(status_code=422, detail="학생 기수 정보가 없습니다")
        return {"uid": uid, "cohort": cohort, "db": db}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase 로그인이 만료됐습니다") from exc


_load_unit_context = load_unit_period_context


@lru_cache
def get_student_chatbot() -> LmsStudentChatbot:
    app = _firebase_app()
    db = firestore.client(app=app)
    project_id = app.project_id
    bucket_name = os.getenv("FIREBASE_STORAGE_BUCKET") or (
        f"{project_id}.firebasestorage.app" if project_id else None
    )
    bucket = storage.bucket(bucket_name, app=app)

    def loader(uid: str, cohort: str, scopes: list[Any], query: str) -> dict[str, Any]:
        return load_student_context(
            db=db,
            bucket=bucket,
            uid=uid,
            cohort=cohort,
            scopes=scopes,
            query=query,
        )

    return create_student_chatbot(student_context_loader=loader)


def _ready_chatbot() -> LmsStudentChatbot:
    try:
        return get_student_chatbot()
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="챗봇 서버를 준비하지 못했습니다.") from exc


def _chat_inputs(request: InitRequest, session: dict[str, Any]) -> dict[str, Any]:
    uid_key = hashlib.sha256(session["uid"].encode()).hexdigest()[:24]
    return {
        "thread_id": f"{uid_key}.{request.thread_id}",
        "student_uid": session["uid"],
        "cohort": session["cohort"],
    }


@router.post("/init")
def initialize_chatbot(
    request: InitRequest,
    session: dict[str, Any] = Depends(_student_session),
) -> dict[str, Any]:
    _ready_chatbot()
    inputs = _chat_inputs(request, session)
    return {
        "thread_id": request.thread_id,
        "cohort": inputs["cohort"],
        "unit_period_context": _load_unit_context(session),
    }


def _ndjson_chat(
    bot: LmsStudentChatbot,
    inputs: dict[str, Any],
    session: dict[str, Any],
) -> Iterator[str]:
    started = time.perf_counter()
    status = "success"
    error_message: str | None = None
    try:
        for chunk in bot.stream(inputs):
            yield json.dumps({"type": "token", "content": chunk}, ensure_ascii=False) + "\n"
    except Exception:
        status = "error"
        error_message = "답변 생성 중 오류가 발생했습니다"
        yield json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n"
    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    snapshot: dict[str, Any] = {}
    try:
        snapshot = bot.ops_snapshot(inputs)
    except Exception:
        snapshot = {}
    payload = build_generation_log_payload(
        cohort_id=str(session.get("cohort") or ""),
        created_by=str(session.get("uid") or ""),
        latency_ms=latency_ms,
        status=status,
        snapshot=snapshot,
        error_message=error_message,
        thread_id=str(inputs.get("thread_id") or ""),
    )
    log_id = ""
    try:
        log_id = write_generation_log(session["db"], payload)
    except Exception:
        log_id = ""
    yield json.dumps(build_done_event(log_id, payload), ensure_ascii=False) + "\n"


@router.post("/stream")
def stream_chat(
    request: ChatRequest,
    session: dict[str, Any] = Depends(_student_session),
) -> StreamingResponse:
    inputs = _chat_inputs(request, session)
    inputs["question"] = request.question.strip()
    return StreamingResponse(
        _ndjson_chat(_ready_chatbot(), inputs, session),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
