"""공부방 노트 API. 취업 코치 통합 서버(8000)에 include_router로 붙는다.

두 갈래다.
- /tree · /generate · /get — Flutter 앱. Firebase ID 토큰(Authorization: Bearer)으로 학생을 확인하고
  Firestore 에서 저장소를 읽고 노트를 저장한다. 학생·강사는 자기 기수만, 관리자는 모든 기수.
- /proxy/tree · /proxy/generate — LMS(Django). Django 가 JWT 로 학생을 확인하고 DB 에서 저장소 정보를
  읽어 넘긴다. 여기서는 저장소를 읽어 노트를 만들어 돌려주기만 하고, 잠금·저장은 Django 가 한다.
  이력서 첨삭의 /proxy 와 같이 바깥에 열지 않는다(Django 만 부른다).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from firebase_admin import auth, firestore
from pydantic import BaseModel, Field

from chatbot.api import _firebase_app
from study_notes import github, service
from study_notes.git_tools import GitToolError
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


class ProxySource(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=200)
    repoUrl: str = Field(min_length=1, max_length=500)
    branch: str = Field(default="main", max_length=200)
    allowedPrefixes: list[str] = Field(default_factory=list, max_length=100)


class ProxyTreeRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    source: ProxySource


class ProxyGenerateRequest(ProxyTreeRequest):
    scopeType: str = Field(min_length=1, max_length=10)
    scopeValue: Any


class ProxyReposRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=39)


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


@router.post("/proxy/tree")
def proxy_tree(request: ProxyTreeRequest) -> dict[str, Any]:
    source = service.source_from_payload(request.source.model_dump())
    return service.source_tree(request.cohortId, source)


@router.post("/proxy/generate")
def proxy_generate(request: ProxyGenerateRequest) -> dict[str, Any]:
    """몇 분 걸린다. Django 는 학생 요청을 먼저 돌려보내고 뒤에서 이걸 기다린다."""
    source = service.source_from_payload(request.source.model_dump())
    return service.build_note_for_lms(request.cohortId, source, request.scopeType, request.scopeValue)


@router.post("/proxy/repos")
def proxy_repos(request: ProxyReposRequest) -> dict[str, Any]:
    """GitHub 계정·조직의 수업 저장소 목록 — LMS 가 새 저장소를 공부방에 자동으로 올릴 때 쓴다."""
    try:
        return {"repos": github.list_owner_repos(request.owner)}
    except GitToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
