"""공부방 노트 API. 취업 코치 통합 서버(8000)에 include_router로 붙는다.

두 갈래다.
- /tree · /generate · /get — Flutter 앱. Firebase ID 토큰(Authorization: Bearer)으로 학생을 확인하고
  Firestore 에서 저장소를 읽고 노트를 저장한다. 학생·강사는 자기 기수만, 관리자는 모든 기수.
- /proxy/tree · /proxy/generate · /proxy/repos · /proxy/practice — LMS(Django). Django 가 JWT 로 학생을 확인하고 DB 에서 저장소 정보를
  읽어 넘긴다. 여기서는 저장소를 읽어 노트를 만들어 돌려주기만 하고, 잠금·저장은 Django 가 한다.
  이력서 첨삭의 /proxy 와 같이 바깥에 열지 않는다(Django 만 부른다).
"""

from __future__ import annotations

import os
import threading
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from firebase_admin import auth, firestore
from pydantic import BaseModel, Field

from chatbot.api import _firebase_app
from chatbot.proxy_auth import valid_proxy_token
from study_notes import github, postgres_service, service
from study_notes.git_tools import GitToolError, is_empty_repo
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


class PreviousNote(BaseModel):
    date: str = Field(min_length=1, max_length=10)
    report: str = Field(default="", max_length=60_000)


class ProxyGenerateRequest(ProxyTreeRequest):
    scopeType: str = Field(min_length=1, max_length=10)
    scopeValue: Any
    # 같은 과목의 이전 날짜 노트 — 「이전 학습과의 연결」을 이것과만 잇는다(pipeline.pack_previous)
    previous: list[PreviousNote] = Field(default_factory=list, max_length=10)


class ProxyReposRequest(BaseModel):
    owner: str = Field(min_length=1, max_length=39)


class ProxyPracticeRequest(ProxyTreeRequest):
    coverage: dict[str, Any] | None = None  # practice.coverage.data — 처음이면 없음
    today: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    # 강사가 고른 수업 날짜 — 없으면 자동(최근 14일 안에서 마지막으로 출제한 날부터)
    dates: list[str] | None = Field(default=None, max_length=10)


class ProxyNoteFile(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    commit: str = Field(min_length=1, max_length=64)


class ProxyUpload(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    content: str = Field(max_length=200_000)


class ProxyCustomPracticeRequest(BaseModel):
    """학생 자료로 문제 — 노트면 저장소 · 파일(커밋까지), 연습장이면 올린 글"""
    scopeLabel: str = Field(min_length=1, max_length=200)
    count: int = Field(default=6, ge=1, le=12)
    cohortId: str | None = Field(default=None, max_length=80)
    source: ProxySource | None = None
    files: list[ProxyNoteFile] = Field(default_factory=list, max_length=8)
    uploads: list[ProxyUpload] = Field(default_factory=list, max_length=3)


class ProxyTutorRequest(BaseModel):
    """튜터 한 번 — Django 가 문제(모범답안 · 숨긴 테스트 포함) · 힌트 단계 · 지난 대화를 붙여 보낸다"""
    mode: str = Field(pattern="^(problem|cell)$")
    # more = 「다음 힌트」 단추로 단계를 새로 열었다(튜터가 앞 대화보다 한 걸음 더 나간다), ask = 그 단계 안에서 대화
    action: str = Field(default="ask", pattern="^(ask|more|answer)$")
    question: str = Field(max_length=2000)
    code: str = Field(default="", max_length=20000)
    run: str = Field(default="", max_length=4000)
    grade: str = Field(default="", max_length=4000)
    hintLevel: int = Field(default=1, ge=1, le=3)
    problem: dict[str, Any] | None = None
    history: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
class InternalTreeRequest(TreeRequest):
    userPk: int = Field(gt=0)


class InternalGenerateRequest(GenerateRequest):
    userPk: int = Field(gt=0)


class InternalGetNoteRequest(GetNoteRequest):
    userPk: int = Field(gt=0)


def _internal_auth(token: str | None = Header(default=None, alias="X-LMS-AI-Token")) -> None:
    if not valid_proxy_token(token):
        raise HTTPException(status_code=401, detail="Django proxy authentication required")


def _proxy_auth_if_configured(token: str | None = Header(default=None, alias="X-LMS-AI-Token")) -> None:
    """LMS_AI_SHARED_TOKEN 이 있는 곳(운영 · 두 EC2)에서만 Django 의 토큰을 본다. 로컬처럼 비어 있으면 그냥 받는다.
    웹 채점처럼 받은 글(검사문)을 실행하는 창구에 건다 — 보안 그룹이 한 번 잘못 열려도 밖에서 JS 를 돌리지 못하게."""
    if os.environ.get("LMS_AI_SHARED_TOKEN") and not valid_proxy_token(token):
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


@router.post("/proxy/tree")
def proxy_tree(request: ProxyTreeRequest) -> dict[str, Any]:
    source = service.source_from_payload(request.source.model_dump())
    return service.source_tree(request.cohortId, source)


@router.post("/proxy/generate")
def proxy_generate(request: ProxyGenerateRequest) -> dict[str, Any]:
    """몇 분 걸린다. Django 는 학생 요청을 먼저 돌려보내고 뒤에서 이걸 기다린다."""
    source = service.source_from_payload(request.source.model_dump())
    previous = [p.model_dump() for p in request.previous]
    return service.build_note_for_lms(request.cohortId, source, request.scopeType, request.scopeValue, previous)


@router.post("/proxy/resolve")
def proxy_resolve(request: ProxyGenerateRequest) -> dict[str, Any]:
    """노트를 만들지 않고 범위의 파일 · 내용 해시만 — LLM 없음, 1~2초. Django 가 같은 자료로 만든 노트를 찾는 데 쓴다."""
    source = service.source_from_payload(request.source.model_dump())
    return service.resolve_note_for_lms(request.cohortId, source, request.scopeType, request.scopeValue)


class ProxyFileRequest(ProxyTreeRequest):
    path: str = Field(min_length=1, max_length=500)
    commit: str = Field(default="", max_length=64)


@router.post("/proxy/file")
def proxy_file(request: ProxyFileRequest) -> dict[str, Any]:
    """수업 파일 하나의 원문 — 노트의 「연습장에서 열기」. LLM 없음."""
    source = service.source_from_payload(request.source.model_dump())
    return service.lesson_file_for_lms(request.cohortId, source, request.path, request.commit)


class ProxySubjectDay(BaseModel):
    date: str = Field(min_length=10, max_length=10)
    report: str = Field(max_length=60_000)


class ProxySubjectRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=200)
    days: list[ProxySubjectDay] = Field(min_length=1, max_length=120)


@router.post("/proxy/subject")
def proxy_subject(request: ProxySubjectRequest) -> dict[str, Any]:
    """과목 전체 요약 — Django 가 모은 날짜별 노트를 한 장으로. 저장소는 읽지 않는다. LLM 1회."""
    from study_notes.pipeline import generate_subject_summary

    try:
        report = generate_subject_summary(
            subject=request.subject, days=[{"date": d.date, "report": d.report} for d in request.days],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=service.failure_message(exc)) from exc
    return {"status": "ready", "reportMarkdown": report}


@router.post("/proxy/repos")
def proxy_repos(request: ProxyReposRequest) -> dict[str, Any]:
    """GitHub 계정·조직의 수업 저장소 목록 — LMS 가 새 저장소를 공부방에 자동으로 올릴 때 쓴다."""
    try:
        return {"repos": github.list_owner_repos(request.owner)}
    except GitToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/proxy/practice")
def proxy_practice(request: ProxyPracticeRequest) -> dict[str, Any]:
    """복습 문제 자동 출제 — 저장소 하나. 수 분 걸린다(LLM + 검증). Django 가 매일 18:30 에 부른다."""
    from study_notes.practice.auto import run_source
    from study_notes.practice.runner import VERIFIER_DIR, PyodideRunner

    # LLM 을 부르기 전에 — 검증기가 없으면 만든 문제를 다 버리게 된다
    if not (VERIFIER_DIR / "node_modules" / "pyodide").exists():
        raise HTTPException(status_code=503, detail="문제 검증기(practice_verifier)가 설치되어 있지 않습니다. npm install 이 필요합니다.")
    source = service.source_from_payload(request.source.model_dump())
    try:
        return run_source(
            service.repo_cache(request.cohortId, source),
            source_title=source.title or source.id,
            prefixes=source.allowed_prefixes,
            coverage=request.coverage,
            today=request.today,
            runner=PyodideRunner(),
            dates=request.dates,
        )
    except GitToolError as exc:
        if is_empty_repo(exc):
            # 수업 전 과목 — 매일 18:30 마다 「실패」로 쌓이지 않게
            return {"sets": [], "coverage": request.coverage, "error": "", "note": "아직 수업 파일이 올라오지 않은 저장소예요."}
        raise HTTPException(status_code=502, detail=str(exc)) from exc


class ProxyWebGradeRequest(BaseModel):
    html: str = Field(default="", max_length=60_000)
    # Django 가 DB 에서 꺼낸 그 문제의 검사문 — 브라우저가 보낸 것이 아니다(lms/practice_web.py)
    checks: str = Field(min_length=1, max_length=4_000)


# 채점 한 번에 node 하나(jsdom, 수십 MB)를 띄운다. 한 반이 한꺼번에 누르면 AI 서버 메모리가 튄다 —
# 일꾼(프로세스)마다 이만큼만 동시에, 나머지는 잠깐 기다린다(한 번에 0.1~0.3초라 금방 빠진다)
WEB_GRADE_SLOTS = threading.BoundedSemaphore(4)
WEB_GRADE_WAIT = 20


@router.post("/proxy/practice/web-grade", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_practice_web_grade(request: ProxyWebGradeRequest) -> dict[str, Any]:
    """웹 실습 채점 — 학생 HTML 을 jsdom 으로 읽고 검사문을 돌린다(출제 검증과 같은 곳). Pyodide 는 띄우지 않는다. 1초 안팎"""
    from study_notes.practice.runner import VERIFIER_DIR, Job, PyodideRunner, VerifierError
    from study_notes.practice.web_problem import grade_result

    if not (VERIFIER_DIR / "node_modules" / "jsdom").exists():
        raise HTTPException(status_code=503, detail="채점기(practice_verifier)에 jsdom 이 없습니다. npm install 이 필요합니다.")
    if not WEB_GRADE_SLOTS.acquire(timeout=WEB_GRADE_WAIT):
        raise HTTPException(status_code=503, detail="채점하는 사람이 많아요. 잠시 후 다시 해 보세요.")
    try:
        results = PyodideRunner().run([Job("grade", [request.html, request.checks], 3000, kind="web")])
    except VerifierError as exc:
        raise HTTPException(status_code=503, detail="채점하지 못했어요. 잠시 후 다시 해 보세요.") from exc
    finally:
        WEB_GRADE_SLOTS.release()
    return grade_result(results["grade"])


@router.post("/proxy/practice/custom")
def proxy_practice_custom(request: ProxyCustomPracticeRequest) -> dict[str, Any]:
    """학생이 고른 자료(자기 노트 · 연습장 파일)로 복습 문제. 수 분 걸린다 — Django 가 뒤에서 기다린다."""
    from study_notes.practice.custom import make_problems, upload_materials
    from study_notes.practice.runner import VERIFIER_DIR, PyodideRunner

    if not (VERIFIER_DIR / "node_modules" / "pyodide").exists():
        raise HTTPException(status_code=503, detail="문제 검증기(practice_verifier)가 설치되어 있지 않습니다. npm install 이 필요합니다.")
    try:
        materials = upload_materials([u.model_dump() for u in request.uploads])
        if request.files:
            if not request.source or not request.cohortId:
                raise HTTPException(status_code=422, detail="노트의 저장소 정보가 없습니다.")
            source = service.source_from_payload(request.source.model_dump())
            cache = service.repo_cache(request.cohortId, source)
            cache.sync()
            materials += service._load_materials(cache, [f.model_dump() for f in request.files])
        return make_problems(materials, scope_label=request.scopeLabel, count=request.count, runner=PyodideRunner())
    except GitToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/proxy/tutor")
def proxy_tutor(request: ProxyTutorRequest) -> dict[str, Any]:
    """연습장 튜터 — 문제 셀엔 3단계 힌트, 일반 셀엔 코드 · 오류 설명. 잡담은 LLM 없이 돌려보낸다."""
    from study_notes.practice.tutor import ask

    return ask(request.model_dump())


# ── 폴더 올리기(GitHub 없이) ────────────────────────────────────────
_DAY = r"^\d{4}-\d{2}-\d{2}$"


class ProxyUploadFile(BaseModel):
    """올리기 전 목록의 한 줄 — 내용 없이 지문 · 앞부분 글만(upload_plan.UpFile)"""
    path: str = Field(min_length=1, max_length=500)
    blob: str = Field(pattern=r"^[0-9a-f]{40}$")
    size: int = Field(default=0, ge=0)
    mtime: int = Field(default=0, ge=0)
    head: str = Field(default="", max_length=8_000)
    cells: list[dict[str, str]] = Field(default_factory=list, max_length=400)


class ProxyCalendar(BaseModel):
    """Django 가 붙이는 기수 달력 — 기간 · 공휴일(lms/holidays.py) · 커리큘럼(날짜를 읽은 줄만) · 강사가 「수업 있었음」 한 날"""
    today: str = Field(pattern=_DAY)
    start: str = Field(default="", max_length=10)
    end: str = Field(default="", max_length=10)
    holidays: dict[str, str] = Field(default_factory=dict)
    curriculum: list[dict[str, str]] = Field(default_factory=list, max_length=400)
    unreadable: int = Field(default=0, ge=0)
    extraDays: list[str] = Field(default_factory=list, max_length=100)


class ProxyUploadSource(ProxySource):
    kind: str = Field(pattern="^(upload|github)$")


class ProxyUploadPlanRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    mode: str = Field(pattern="^(import|daily)$")
    what: str | None = Field(default=None, pattern="^(subject|cohort)$")  # 비우면 폴더 모양으로 정한다
    date: str | None = Field(default=None, pattern=_DAY)  # 오늘 수업 올리기의 수업 날짜(기본 오늘)
    target: str | None = Field(default=None, max_length=120)  # 오늘 수업 올리기 — 올릴 과목(소스 id)
    files: list[ProxyUploadFile] = Field(min_length=1, max_length=3000)
    sources: list[ProxyUploadSource] = Field(default_factory=list, max_length=200)  # 이 기수에 이미 있는 과목
    topics: dict[str, str] = Field(default_factory=dict)  # 강사가 고른 커리큘럼 과목 {과목 이름: 커리큘럼 과목 id}
    starts: dict[str, str] = Field(default_factory=dict)  # 강사가 고친 과목 시작일
    calendar: ProxyCalendar


class ProxyUploadContent(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    content: str = Field(max_length=8_000_000)  # base64


class ProxyUploadDay(BaseModel):
    date: str = Field(pattern=_DAY)
    files: list[ProxyUploadContent] = Field(min_length=1, max_length=300)


class ProxyUploadCommitRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    source: ProxySource
    days: list[ProxyUploadDay] = Field(default_factory=list, max_length=130)
    past: list[ProxyUploadContent] = Field(default_factory=list, max_length=300)  # 날짜 없는 지난 자료
    # 새 과목(저장소가 없어도 된다). 아니면 저장소가 없을 때 거절한다 — 빈 저장소에 커밋하면 그 보관본이
    # S3 의 전체 기록을 덮어쓴다(서버를 새로 띄워 캐시가 사라졌는데 되살리지 못한 경우)
    create: bool = False


@router.post("/proxy/upload/plan", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_upload_plan(request: ProxyUploadPlanRequest) -> dict[str, Any]:
    """올리기 전 계획 — 과목 나누기 · 날짜 근거 · 지난번과 같은 파일 · 넣을 폴더 · 확인할 날. LLM 없음, 파일 내용 없음."""
    from study_notes import upload_plan, upload_repo

    cal = upload_plan.calendar_from(request.calendar.model_dump())
    files = [f.model_dump() for f in request.files]
    try:
        if request.mode == "daily":
            target = next((s for s in request.sources if s.id == request.target and s.kind == "upload"), None)
            if target is None:
                raise HTTPException(status_code=400, detail="폴더로 올린 과목을 골라 주세요.")
            snap = upload_repo.snapshot(service.repo_cache(request.cohortId, service.source_from_payload(target.model_dump())))
            topic = request.topics.get(target.title) or upload_plan.match_topic(target.title, snap["dates"], cal)["id"]
            plan = upload_plan.plan_daily(
                files, cal, day=request.date or cal.today, tree=snap["tree"], texts=snap["texts"], topic=topic,
            )
            return {**plan, "topic": topic, "topics": cal.topics()}
        existing: dict[str, dict[str, Any]] = {}
        for s in request.sources:
            info: dict[str, Any] = {"kind": s.kind, "id": s.id}
            if s.kind == "upload":
                snap = upload_repo.snapshot(
                    service.repo_cache(request.cohortId, service.source_from_payload(s.model_dump())), texts=False,
                )
                info.update(tree=snap["tree"], dates=snap["dates"])
            existing[(s.title or s.id).lower()] = info
        return upload_plan.plan_import(
            files, cal, what=request.what, existing=existing, topics=request.topics, starts=request.starts,
        )
    except GitToolError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/proxy/upload/commit", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_upload_commit(request: ProxyUploadCommitRequest) -> dict[str, Any]:
    """확정한 파일을 서버 안 저장소에 — 지난 자료 커밋 하나 + 날짜별 커밋. 같은 내용은 건너뛴다. LLM 없음."""
    import base64
    import binascii
    from datetime import datetime

    from study_notes import upload_repo
    from study_notes.git_tools import SEOUL, parse_repo_url

    source = service.source_from_payload(request.source.model_dump())
    if not parse_repo_url(source.repo_url).upload:
        raise HTTPException(status_code=400, detail="폴더 올리기 과목이 아니에요.")
    today = datetime.now(SEOUL).strftime("%Y-%m-%d")
    if any(d.date > today for d in request.days):
        raise HTTPException(status_code=400, detail="앞으로 올 날짜로는 올릴 수 없어요.")

    def decode(items: list[ProxyUploadContent]) -> dict[str, bytes]:
        try:
            return {f.path: base64.b64decode(f.content, validate=True) for f in items}
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(status_code=422, detail="파일 내용을 읽지 못했어요.") from exc

    days: dict[str, dict[str, bytes]] = {}
    for d in request.days:
        days.setdefault(d.date, {}).update(decode(d.files))
    if not request.create and upload_repo.head(service.repo_cache(request.cohortId, source)) is None:
        raise HTTPException(status_code=409, detail="서버 안 저장소가 없어요. 보관본으로 되살린 뒤 다시 올려 주세요.")
    try:
        commits = upload_repo.import_all(
            service.repo_cache(request.cohortId, source), days, decode(request.past) if request.past else None,
        )
    except GitToolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    cache = service.repo_cache(request.cohortId, source)
    changed = any(c.sha for c in commits)
    return {
        "commits": [
            {"date": c.date or None, "sha": c.sha, "changed": c.changed, "skipped": c.skipped} for c in commits
        ],
        "head": upload_repo.head(cache),
        # 바뀐 게 있으면 저장소 전체 보관본 — Django 가 S3 에 둔다(서버를 새로 띄워도 되살리게)
        "bundle": base64.b64encode(upload_repo.bundle(cache)).decode() if changed else None,
    }


class ProxyUploadSourceRequest(BaseModel):
    cohortId: str = Field(min_length=1, max_length=80)
    source: ProxySource


class ProxyUploadRestoreRequest(ProxyUploadSourceRequest):
    bundle: str = Field(min_length=1, max_length=200_000_000)  # base64


def _upload_cache(request: ProxyUploadSourceRequest):
    from study_notes.git_tools import parse_repo_url

    source = service.source_from_payload(request.source.model_dump())
    if not parse_repo_url(source.repo_url).upload:
        raise HTTPException(status_code=400, detail="폴더 올리기 과목이 아니에요.")
    return service.repo_cache(request.cohortId, source)


@router.post("/proxy/upload/head", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_upload_head(request: ProxyUploadSourceRequest) -> dict[str, Any]:
    """서버 안 저장소의 마지막 커밋 — 없으면 null(Django 가 보관본으로 되살린다)"""
    from study_notes import upload_repo

    return {"head": upload_repo.head(_upload_cache(request))}


@router.post("/proxy/upload/restore", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_upload_restore(request: ProxyUploadRestoreRequest) -> dict[str, Any]:
    """보관본(git bundle)으로 서버 안 저장소를 되살린다. 이미 있으면 그대로."""
    import base64
    import binascii

    from study_notes import upload_repo

    try:
        data = base64.b64decode(request.bundle, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="보관본을 읽지 못했어요.") from exc
    try:
        return {"head": upload_repo.restore(_upload_cache(request), data)}
    except GitToolError as exc:
        raise HTTPException(status_code=422, detail=f"보관본으로 되살리지 못했어요: {exc}") from exc


class ProxyScheduleRequest(BaseModel):
    calendar: ProxyCalendar
    subjects: dict[str, dict[str, Any]] = Field(default_factory=dict)  # {과목 이름: {topic?, dates: [실제 수업 날짜]}}


@router.post("/proxy/upload/schedule", dependencies=[Depends(_proxy_auth_if_configured)])
def proxy_upload_schedule(request: ProxyScheduleRequest) -> dict[str, Any]:
    """커리큘럼 ↔ 실제 수업 날짜 어긋남(강사 · 관리자 수업 저장소 화면). 저장소는 읽지 않는다 — 날짜는 Django 가 준다."""
    from study_notes import upload_plan

    cal = upload_plan.calendar_from(request.calendar.model_dump())
    return {"issues": upload_plan.schedule_check(cal, request.subjects), "topics": cal.topics()}


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
