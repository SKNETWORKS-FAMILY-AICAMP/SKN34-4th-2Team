"""공부방 노트 API. 취업 코치 통합 서버(8000)에 include_router로 붙는다.

인증은 학생 챗봇과 같은 Firebase ID 토큰(Authorization: Bearer)이다.
학생·강사는 자기 기수만, 관리자는 모든 기수에 접근할 수 있다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from firebase_admin import auth, firestore
from pydantic import BaseModel, Field

from chatbot.api import _firebase_app
from chatbot.proxy_auth import valid_proxy_token
from study_notes import service
from study_notes import postgres_service
from study_notes.service import Caller

router = APIRouter(prefix="/api/v1/study-notes", tags=["study-notes"])


class TreeRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    sourceId: str = Field(min_length=1, max_length=120)


class GenerateRequest(TreeRequest):
    scopeType: str = Field(min_length=1, max_length=10)
    scopeValue: Any


class GetNoteRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    noteId: str | None = Field(default=None, max_length=200)
    sourceId: str | None = Field(default=None, max_length=120)
    scopeType: str | None = Field(default=None, max_length=10)
    scopeValue: Any = None


class InternalTreeRequest(TreeRequest):
    userPk: int = Field(gt=0)


class InternalGenerateRequest(GenerateRequest):
    userPk: int = Field(gt=0)


class InternalGetNoteRequest(GetNoteRequest):
    userPk: int = Field(gt=0)


def _internal_auth(token: str | None = Header(default=None, alias="X-LMS-AI-Token")) -> None:
    if not valid_proxy_token(token):
        raise HTTPException(status_code=401, detail="Django proxy authentication required")


def _postgres_result(call):
    try:
        return call()
    except postgres_service.StudyNotesError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


class Session:
    def __init__(self, caller: Caller, db: Any) -> None:
        self.caller = caller
        self.db = db


def _session(authorization: str | None = Header(default=None)) -> Session:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Firebase 로그인이 필요합니다")
    app = _firebase_app()
    try:
        uid = auth.verify_id_token(authorization[7:].strip(), app=app).get("uid")
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Firebase 로그인이 만료됐습니다") from exc
    if not isinstance(uid, str) or not uid:
        raise HTTPException(status_code=401, detail="Firebase 로그인이 만료됐습니다")
    db = firestore.client(app=app)
    return Session(service.load_caller(db, uid), db)


@router.post("/tree")
def list_tree(request: TreeRequest, session: Session = Depends(_session)) -> dict[str, Any]:
    return service.list_source_tree(session.db, session.caller, request.cohortId, request.sourceId)


@router.post("/generate")
def generate(request: GenerateRequest, session: Session = Depends(_session)) -> dict[str, Any]:
    return service.generate_note(
        session.db,
        session.caller,
        request.cohortId,
        request.sourceId,
        request.scopeType,
        request.scopeValue,
    )


@router.post("/get")
def get_note(request: GetNoteRequest, session: Session = Depends(_session)) -> dict[str, Any]:
    return service.get_note(
        session.db,
        session.caller,
        request.cohortId,
        note_id=request.noteId,
        source_id=request.sourceId,
        scope_type=request.scopeType,
        scope_value=request.scopeValue,
    )


@router.post("/internal/tree", dependencies=[Depends(_internal_auth)])
def internal_tree(request: InternalTreeRequest) -> dict[str, Any]:
    return _postgres_result(lambda: postgres_service.list_tree(request.userPk, request.cohortId, request.sourceId))


@router.post("/internal/generate", dependencies=[Depends(_internal_auth)])
def internal_generate(request: InternalGenerateRequest) -> dict[str, Any]:
    return _postgres_result(lambda: postgres_service.generate_note(
        request.userPk, request.cohortId, request.sourceId, request.scopeType, request.scopeValue,
    ))


@router.post("/internal/get", dependencies=[Depends(_internal_auth)])
def internal_get(request: InternalGetNoteRequest) -> dict[str, Any]:
    return _postgres_result(lambda: postgres_service.get_note(
        request.userPk, request.cohortId, note_id=request.noteId, source_id=request.sourceId,
        scope_type=request.scopeType, scope_value=request.scopeValue,
    ))
