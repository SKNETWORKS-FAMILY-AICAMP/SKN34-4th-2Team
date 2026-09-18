"""운영 UI가 참조하지 않는 Luna 실험 전용 API."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any, Iterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from firebase_admin import firestore, storage

from chatbot.api import (
    ChatRequest,
    InitRequest,
    _chat_inputs,
    _firebase_app,
    _load_unit_context,
    _student_session,
)
from chatbot.firebase_student_context import load_student_context
from chatbot_lab.bot import LAB_MODEL, LunaLabStudentChatbot, create_lab_chatbot

router = APIRouter(
    prefix="/api/v1/student-chatbot-lab",
    tags=["student-chatbot-lab"],
)
# Flutter 클라이언트는 경로가 고정되어 있고 base URL만 dart-define으로 바꾼다.
# 8002 실험 서버 안에서만 운영 경로와 같은 별칭을 제공해 앱 코드를 수정하지 않는다.
flutter_router = APIRouter(
    prefix="/api/v1/student-chatbot",
    tags=["student-chatbot-lab-flutter"],
)


@lru_cache
def get_lab_chatbot() -> LunaLabStudentChatbot:
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

    return create_lab_chatbot(student_context_loader=loader)


def _ready() -> LunaLabStudentChatbot:
    try:
        return get_lab_chatbot()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="실험 챗봇을 준비하지 못했습니다") from exc


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "isolated", "model": LAB_MODEL, "pinecone_key": "PINECONE_API_KEY2"}


@router.post("/init")
def initialize(
    request: InitRequest,
    session: dict[str, Any] = Depends(_student_session),
) -> dict[str, Any]:
    _ready()
    inputs = _chat_inputs(request, session)
    return {
        "thread_id": request.thread_id,
        "cohort": inputs["cohort"],
        "unit_period_context": _load_unit_context(session),
        "experiment": "luna-lab",
    }


def _ndjson(chunks: Iterator[str]) -> Iterator[str]:
    try:
        for chunk in chunks:
            yield json.dumps({"type": "token", "content": chunk}, ensure_ascii=False) + "\n"
        yield '{"type":"done"}\n'
    except Exception:
        yield json.dumps(
            {"type": "error", "message": "실험 답변 생성 중 오류가 발생했습니다"},
            ensure_ascii=False,
        ) + "\n"


@router.post("/stream")
def stream_chat(
    request: ChatRequest,
    session: dict[str, Any] = Depends(_student_session),
) -> StreamingResponse:
    inputs = _chat_inputs(request, session)
    inputs["question"] = request.question.strip()
    return StreamingResponse(
        _ndjson(_ready().stream(inputs)),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


flutter_router.add_api_route("/health", health, methods=["GET"])
flutter_router.add_api_route("/init", initialize, methods=["POST"])
flutter_router.add_api_route("/stream", stream_chat, methods=["POST"])
