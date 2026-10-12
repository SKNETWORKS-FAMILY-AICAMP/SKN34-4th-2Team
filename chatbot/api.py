"""LMS student chatbot endpoints and the authenticated Django proxy."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import logging
import traceback
from functools import lru_cache
from typing import Any, Iterator

import firebase_admin
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from firebase_admin import auth, credentials
from pydantic import BaseModel, Field

from chatbot.database import connect
from chatbot.proxy_auth import valid_proxy_token
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
logger = logging.getLogger(__name__)


def _log_generation_failure(exc: Exception) -> None:
    # Keep request text, student records, credentials and exception payloads out
    # of logs; record exception type and code locations for diagnosis instead.
    frames = traceback.extract_tb(exc.__traceback__)
    logger.error('Chat generation failed: %s; frames=%s', type(exc).__name__,
                 ' > '.join(f'{os.path.basename(f.filename)}:{f.lineno}:{f.name}' for f in frames))
THREAD_RE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class InitRequest(BaseModel):
    thread_id: str = Field(min_length=1, max_length=80, pattern=THREAD_RE.pattern)


class ChatRequest(InitRequest):
    question: str = Field(min_length=1, max_length=2000)


class ProxyChatRequest(BaseModel):
    """Django가 인증한 학생 UID를 내부 공유 토큰과 함께 전달한다."""

    message: str = Field(default="", max_length=2000)
    question: str = Field(default="", max_length=2000)
    uid: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(default="web", min_length=1, max_length=80, pattern=THREAD_RE.pattern)


class WarmupRequest(BaseModel):
    uid: str = Field(min_length=1, max_length=128)


@router.post('/warmup', status_code=202)
def warmup_chatbot(request: WarmupRequest,
                   internal_token: str | None = Header(default=None, alias='X-LMS-AI-Token')) -> dict:
    from chatbot.context_cache import enabled
    from chatbot.warmup import schedule_warmup
    if not valid_proxy_token(internal_token):
        raise HTTPException(status_code=401, detail='Django proxy authentication required')
    if not enabled():
        return {'status': 'disabled'}
    uid = request.uid.strip()
    if not uid:
        raise HTTPException(status_code=400, detail='uid required')
    # Acceptance only, not permission confirmation. Worker resolves current
    # membership before accessing any context; endpoint does no DB/LLM work.
    return {'status': schedule_warmup({'uid': uid})}


def _session_from_uid(uid: str) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute(
            """SELECT u.role, u.is_active, c.code
               FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
               WHERE u.firebase_uid = %s""",
            (uid,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="학생 계정만 챗봇을 사용할 수 있습니다")
    role, is_active, cohort = row[0], row[1], row[2]
    if role != "student" or is_active is not True:
        raise HTTPException(status_code=403, detail="학생 계정만 챗봇을 사용할 수 있습니다")
    if not cohort:
        raise HTTPException(status_code=422, detail="학생 기수 정보가 없습니다")
    return {"uid": uid, "cohort": str(cohort)}


_parse_schedule_date = parse_schedule_date


@lru_cache
def _firebase_app():
    try:
        return firebase_admin.get_app()
    except ValueError:
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        options = {"projectId": project_id} if project_id else None
        return firebase_admin.initialize_app(credentials.ApplicationDefault(), options)


def _student_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Firebase 로그인이 필요합니다")
    try:
        app = _firebase_app()
        uid = auth.verify_id_token(authorization[7:].strip(), app=app).get("uid")
        if not isinstance(uid, str) or not uid:
            raise ValueError("missing uid")
        with connect() as conn:
            row = conn.execute(
                """SELECT u.role, u.is_active, c.code
                   FROM users u LEFT JOIN cohorts c ON c.id = u.cohort_id
                   WHERE u.firebase_uid = %s""",
                (uid,),
            ).fetchone()
        if not row:
            raise HTTPException(status_code=403, detail="학생 계정만 챗봇을 사용할 수 있습니다")
        role, is_active, cohort = row[0], row[1], row[2]
        if role != "student" or is_active is not True:
            raise HTTPException(status_code=403, detail="학생 계정만 챗봇을 사용할 수 있습니다")
        if not cohort:
            raise HTTPException(status_code=422, detail="학생 기수 정보가 없습니다")
        return {"uid": uid, "cohort": str(cohort)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase 로그인이 만료됐습니다") from exc


_load_unit_context = load_unit_period_context


def _shared_context(session: dict[str, Any]) -> dict[str, Any]:
    try:
        return _load_unit_context(session, include_attendance=False)
    except Exception:
        return {"unavailable_reason": "기수 날짜 조회에 실패했습니다. 날짜를 추측하지 마세요."}


@lru_cache
def get_student_chatbot() -> LmsStudentChatbot:
    def loader(uid: str, cohort: str, scopes: list[Any], query: str) -> dict[str, Any]:
        return load_student_context(uid=uid, cohort=cohort, scopes=scopes, query=query)

    return create_student_chatbot(student_context_loader=loader, shared_context_loader=_shared_context)


def _ready_chatbot() -> LmsStudentChatbot:
    try:
        return get_student_chatbot()
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="챗봇 서버를 준비하지 못했습니다.") from exc


def _chat_inputs(request: InitRequest, session: dict[str, Any], *,
                 defer_shared_context: bool = False) -> dict[str, Any]:
    uid_key = hashlib.sha256(session["uid"].encode()).hexdigest()[:24]
    shared_started = time.perf_counter()
    unit_context = {} if defer_shared_context else _shared_context(session)
    shared_context_ms = 0 if defer_shared_context else max(0, round((time.perf_counter() - shared_started) * 1000))
    return {
        "thread_id": f"{uid_key}.{request.thread_id}",
        "student_uid": session["uid"],
        "cohort": session["cohort"],
        "unit_period_context": unit_context,
        "defer_shared_context": defer_shared_context,
        "shared_context_ms": shared_context_ms,
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
    *,
    handler_started: float | None = None,
    preparation_timings: dict[str, int] | None = None,
) -> Iterator[str]:
    started = time.perf_counter()
    first_token_ms: int | None = None
    handler_first_token_ms: int | None = None
    status = "success"
    error_message: str | None = None
    try:
        for chunk in bot.stream(inputs):
            if chunk and first_token_ms is None:
                token_at = time.perf_counter()
                first_token_ms = max(0, round((token_at - started) * 1000))
                if handler_started is not None:
                    handler_first_token_ms = max(0, round((token_at - handler_started) * 1000))
            yield json.dumps({"type": "token", "content": chunk}, ensure_ascii=False) + "\n"
        generation_end = time.perf_counter()
    except Exception as exc:
        generation_end = time.perf_counter()
        _log_generation_failure(exc)
        status = "error"
        error_message = "답변 생성 중 오류가 발생했습니다"
        yield json.dumps({"type": "error", "message": error_message}, ensure_ascii=False) + "\n"
    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    snapshot: dict[str, Any] = {}
    try:
        snapshot = bot.ops_snapshot(inputs)
        if first_token_ms is not None:
            snapshot["first_token_ms"] = first_token_ms
            snapshot["generation_tail_ms"] = max(0, latency_ms - first_token_ms)
    except Exception:
        snapshot = {}
    snapshot.update(preparation_timings or {})
    if handler_started is not None:
        snapshot["handler_generation_end_ms"] = max(0, round((generation_end - handler_started) * 1000))
    if handler_first_token_ms is not None:
        snapshot["handler_first_token_ms"] = handler_first_token_ms
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
        log_id = write_generation_log(None, payload)
    except Exception:
        log_id = ""
    yield json.dumps(build_done_event(log_id, payload), ensure_ascii=False) + "\n"


@router.post("/stream")
def stream_chat(
    request: ChatRequest,
    session: dict[str, Any] = Depends(_student_session),
) -> StreamingResponse:
    # Depends authentication/session lookup finishes before handler entry and
    # is therefore excluded from these handler timings.
    handler_started = time.perf_counter()
    inputs_started = time.perf_counter()
    inputs = _chat_inputs(request, session, defer_shared_context=os.getenv('LMS_CHATBOT_PARALLEL_PREP', '').strip() == '1')
    preparation_timings = {"handler_chat_inputs_ms": max(0, round((time.perf_counter() - inputs_started) * 1000))}
    inputs["question"] = request.question.strip()
    bot_started = time.perf_counter()
    bot = _ready_chatbot()
    prepared_at = time.perf_counter()
    preparation_timings["handler_bot_prepare_ms"] = max(0, round((prepared_at - bot_started) * 1000))
    preparation_timings["handler_prepare_ms"] = max(0, round((prepared_at - handler_started) * 1000))
    return StreamingResponse(
        _ndjson_chat(bot, inputs, session, handler_started=handler_started, preparation_timings=preparation_timings),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@router.post("/chat")
def proxy_chat(
    request: ProxyChatRequest,
    internal_token: str | None = Header(default=None, alias="X-LMS-AI-Token"),
) -> dict[str, Any]:
    """React → Django → 여기. 스트리밍을 모아 { answer } JSON 으로 돌려준다."""
    handler_started = time.perf_counter()
    if not valid_proxy_token(internal_token):
        raise HTTPException(status_code=401, detail="Django proxy authentication required")
    question = (request.question or request.message or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="message required")
    session_started = time.perf_counter()
    session = _session_from_uid(request.uid.strip())
    preparation_timings = {"handler_session_ms": max(0, round((time.perf_counter() - session_started) * 1000))}
    init = InitRequest(thread_id=request.thread_id)
    inputs_started = time.perf_counter()
    inputs = _chat_inputs(init, session, defer_shared_context=os.getenv('LMS_CHATBOT_PARALLEL_PREP', '').strip() == '1')
    preparation_timings["handler_chat_inputs_ms"] = max(0, round((time.perf_counter() - inputs_started) * 1000))
    inputs["question"] = question
    bot_started = time.perf_counter()
    bot = _ready_chatbot()
    prepared_at = time.perf_counter()
    preparation_timings["handler_bot_prepare_ms"] = max(0, round((prepared_at - bot_started) * 1000))
    preparation_timings["handler_prepare_ms"] = max(0, round((prepared_at - handler_started) * 1000))
    parts: list[str] = []
    err: str | None = None
    started = time.perf_counter()
    first_token_ms: int | None = None
    handler_first_token_ms: int | None = None
    try:
        for chunk in bot.stream(inputs):
            if chunk:
                if first_token_ms is None:
                    token_at = time.perf_counter()
                    first_token_ms = max(0, round((token_at - started) * 1000))
                    handler_first_token_ms = max(0, round((token_at - handler_started) * 1000))
                parts.append(str(chunk))
        generation_end = time.perf_counter()
    except Exception as exc:
        generation_end = time.perf_counter()
        _log_generation_failure(exc)
        err = "답변 생성 중 오류가 발생했습니다"
    answer = "".join(parts).strip()
    if not answer:
        answer = err or "답변을 받지 못했습니다."
    latency_ms = max(0, round((time.perf_counter() - started) * 1000))
    snapshot: dict[str, Any] = {}
    try:
        snapshot = bot.ops_snapshot(inputs)
        if first_token_ms is not None:
            snapshot["first_token_ms"] = first_token_ms
            snapshot["generation_tail_ms"] = max(0, latency_ms - first_token_ms)
    except Exception:
        snapshot = {}
    snapshot.update(preparation_timings)
    snapshot["handler_generation_end_ms"] = max(0, round((generation_end - handler_started) * 1000))
    if handler_first_token_ms is not None:
        snapshot["handler_first_token_ms"] = handler_first_token_ms
    payload = build_generation_log_payload(
        cohort_id=str(session.get("cohort") or ""),
        created_by=str(session.get("uid") or ""),
        latency_ms=latency_ms,
        status="error" if err else "success",
        snapshot=snapshot,
        error_message=err,
        thread_id=str(inputs.get("thread_id") or ""),
    )
    try:
        write_generation_log(None, payload)
    except Exception:
        pass
    return {"answer": answer}


@router.post("/chat/stream")
def proxy_chat_stream(
    request: ProxyChatRequest,
    internal_token: str | None = Header(default=None, alias="X-LMS-AI-Token"),
) -> StreamingResponse:
    handler_started = time.perf_counter()
    if not valid_proxy_token(internal_token):
        raise HTTPException(status_code=401, detail="Django proxy authentication required")
    question = (request.question or request.message or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="message required")
    session_started = time.perf_counter()
    session = _session_from_uid(request.uid.strip())
    preparation_timings = {"handler_session_ms": max(0, round((time.perf_counter() - session_started) * 1000))}
    inputs_started = time.perf_counter()
    inputs = _chat_inputs(InitRequest(thread_id=request.thread_id), session,
                          defer_shared_context=os.getenv('LMS_CHATBOT_PARALLEL_PREP', '').strip() == '1')
    preparation_timings["handler_chat_inputs_ms"] = max(0, round((time.perf_counter() - inputs_started) * 1000))
    inputs["question"] = question
    bot_started = time.perf_counter()
    bot = _ready_chatbot()
    prepared_at = time.perf_counter()
    preparation_timings["handler_bot_prepare_ms"] = max(0, round((prepared_at - bot_started) * 1000))
    preparation_timings["handler_prepare_ms"] = max(0, round((prepared_at - handler_started) * 1000))
    return StreamingResponse(
        _ndjson_chat(bot, inputs, session, handler_started=handler_started, preparation_timings=preparation_timings),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
