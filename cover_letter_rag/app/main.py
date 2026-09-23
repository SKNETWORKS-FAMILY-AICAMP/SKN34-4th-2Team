from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from langchain_core.exceptions import LangChainException
from openai import OpenAIError
from pydantic import Field

from app.config import Settings, get_settings
from app.models import (
    FirestoreResumeReviewRequest,
    FirestoreResumeReviewResponse,
    HealthResponse,
    TailoredResumeCreateRequest,
    TailoredResumePromoteRequest,
    TailoredResumeResponse,
    TailoredResumeSessionRequest,
    TailoredResumeSummary,
)
from app.firebase_gateway import (
    FirebaseAuthenticationError,
    FirebaseGateway,
    ResumeNotFoundError,
    extract_bearer_token,
)
from app.resume_review import ResumeReviewService
from app.review_workflow import ReviewConflict, ReviewInputError
from app.firebase_gateway import ResumeAccessError
from google.api_core.exceptions import GoogleAPIError
from google.auth.exceptions import GoogleAuthError
from app.tailored_resumes import TailoredResumeService


app = FastAPI(
    title="Resume Review API",
    version="0.2.0",
    description="선택 공고와 이력서를 대조하는 대화형 이력서 첨삭·맞춤 이력서 API",
)
from app.resume_apply import router as resume_apply_router
app.include_router(resume_apply_router)


def get_context_gateway() -> FirebaseGateway:
    settings = get_settings()
    if not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail='Firebase configuration unavailable')
    try:
        return FirebaseGateway(settings)
    except (GoogleAuthError, GoogleAPIError, ValueError) as exc:
        raise HTTPException(status_code=503, detail='Firebase configuration unavailable') from exc


@app.get('/api/v1/resumes/review-context')
def review_context(
    cohort_id: str = Query(min_length=1, max_length=200, pattern=r'^[^/]+$'),
    resume_id: str = Query(min_length=1, max_length=200, pattern=r'^[^/]+$'),
    job_id: str | None = Query(default=None, min_length=1, max_length=200),
    tailored_resume_id: str | None = Query(default=None, min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$'),
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    from app.matching_handoff import load_selected_job
    from app.review_workflow import digest
    from fastapi.responses import JSONResponse
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        job = load_selected_job(settings.matching_job_store_path, job_id) if job_id else None
        if tailored_resume_id:
            resume = gateway.get_owned_tailored_resume(cohort_id, resume_id, tailored_resume_id, uid)
            if job and resume.get('jobId') != job_id:
                raise ReviewConflict('tailored_resume_job_mismatch')
            if job and resume.get('jobSnapshotHash') != job['source']['snapshot_hash']:
                raise ReviewConflict('tailored_resume_job_changed')
        else:
            resume = gateway.get_owned_resume(cohort_id, resume_id, uid)
        content = resume.get('content') or {}
        return JSONResponse({'content': content, 'input_hash': digest(content), 'job_source': job['source'] if job else {},
                             'tailored_resume_id': tailored_resume_id},
                            headers={'Cache-Control': 'no-store'})
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Resume was not found') from exc
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


def _warm_job_requirements(gateway, settings, job):
    from app.job_requirements import build_requirement_extractor, load_or_extract_requirements
    try:
        load_or_extract_requirements(gateway, build_requirement_extractor(settings), job['text'], job['source'])
    except Exception:  # noqa: BLE001 — 미리 만들어 두는 일일 뿐이다
        pass


@app.post('/api/v1/resumes/tailored', response_model=TailoredResumeResponse)
def create_tailored_resume(
    request: TailoredResumeCreateRequest,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    from app.matching_handoff import load_selected_job
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        jobs = {}

        def load_job(job_id):
            jobs[job_id] = load_selected_job(settings.matching_job_store_path, job_id)
            return jobs[job_id]

        service = TailoredResumeService(gateway, load_job)
        created = service.create(uid, request)
        job = jobs.get(request.selected_job_id)
        if job and settings.openai_api_key:
            # 맞춤본을 만들고 첨삭 시작을 누르기까지 몇 초가 걸린다. 그 사이 공고 요건을 정리해 두면 첫
            # 첨삭이 요건 정리(약 4초)를 기다리지 않는다. 실패해도 첫 첨삭이 다시 만든다.
            background.add_task(_warm_job_requirements, gateway, settings, job)
        return created
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Resume or job was not found') from exc
    except (ReviewConflict, ReviewInputError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


@app.get('/api/v1/resumes/{resume_id}/tailored', response_model=list[TailoredResumeSummary])
def list_tailored_resumes(
    resume_id: str,
    cohort_id: str = Query(min_length=1, max_length=200, pattern=r'^[^/]+$'),
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        return TailoredResumeService(gateway, lambda _: {}).list(uid, cohort_id, resume_id)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Resume was not found') from exc


@app.get(
    '/api/v1/resumes/{resume_id}/tailored/{tailored_resume_id}',
    response_model=TailoredResumeResponse,
)
def get_tailored_resume(
    resume_id: str,
    tailored_resume_id: str,
    cohort_id: str = Query(min_length=1, max_length=200, pattern=r'^[^/]+$'),
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        return TailoredResumeService(gateway, lambda _: {}).get(
            uid, cohort_id, resume_id, tailored_resume_id,
        )
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


@app.put('/api/v1/resumes/{resume_id}/tailored/{tailored_resume_id}/session')
def save_tailored_resume_session(
    resume_id: str,
    tailored_resume_id: str,
    request: TailoredResumeSessionRequest,
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        gateway.save_tailored_resume_session(
            request.cohort_id, resume_id, tailored_resume_id, uid, request.state,
        )
        return {'saved': True}
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc


@app.delete('/api/v1/resumes/{resume_id}/tailored/{tailored_resume_id}')
def delete_tailored_resume(
    resume_id: str,
    tailored_resume_id: str,
    cohort_id: str = Query(min_length=1, max_length=200, pattern=r'^[^/]+$'),
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        gateway.delete_tailored_resume(
            cohort_id, resume_id, tailored_resume_id, uid,
        )
        return {'deleted': True}
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


@app.post('/api/v1/resumes/{resume_id}/tailored/{tailored_resume_id}/promote')
def promote_tailored_resume(
    resume_id: str,
    tailored_resume_id: str,
    request: TailoredResumePromoteRequest,
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    try:
        uid = gateway.verify_id_token(extract_bearer_token(authorization))
        workspace_resume_id = gateway.promote_tailored_resume(
            request.cohort_id,
            resume_id,
            tailored_resume_id,
            uid,
        )
        return {'workspace_resume_id': workspace_resume_id}
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


def get_resume_review_service(authorization: str | None = Header(default=None)) -> ResumeReviewService:
    try:
        extract_bearer_token(authorization)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail='Firebase authentication failed') from exc
    return build_resume_review_service()


def build_resume_review_service() -> ResumeReviewService:
    """토큰 검사 없이 서비스만 만든다. LMS 프록시 창구가 쓴다 — 학생 확인은 Django 가 한다."""
    settings = get_settings()
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY is not configured on the server")
    if not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail="FIREBASE_PROJECT_ID is not configured on the server")
    try:
        return ResumeReviewService(settings, FirebaseGateway(settings))
    except (GoogleAuthError, GoogleAPIError, ValueError) as exc:
        raise HTTPException(status_code=503, detail='Firebase configuration unavailable') from exc


@app.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        model=settings.openai_model,
        firebase_auth="configured" if settings.firebase_project_id else "not_configured",
    )


class ProxyResumeReviewRequest(FirestoreResumeReviewRequest):
    """LMS(Django) 프록시용. Firebase 토큰 대신 uid 로 학생을 확인한다."""

    uid: str = Field(min_length=1, max_length=128)


@app.post("/api/v1/resumes/reviews/proxy", response_model=FirestoreResumeReviewResponse)
def review_stored_resume_as_user(request: ProxyResumeReviewRequest) -> FirestoreResumeReviewResponse:
    """LMS 가 학생을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다)."""
    service = build_resume_review_service()
    inner = FirestoreResumeReviewRequest(**request.model_dump(exclude={"uid"}))
    try:
        return service.review_as(request.uid, inner)
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail="Resume access denied") from exc
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resume was not found") from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc
    except (OpenAIError, LangChainException, ValueError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


@app.post("/api/v1/resumes/reviews", response_model=FirestoreResumeReviewResponse)
def review_stored_resume(
    request: FirestoreResumeReviewRequest,
    authorization: str | None = Header(default=None),
    service: ResumeReviewService = Depends(get_resume_review_service),
) -> FirestoreResumeReviewResponse:
    try:
        id_token = extract_bearer_token(authorization)
        return service.review(id_token, request)
    except FirebaseAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Firebase authentication failed") from exc
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Resume was not found") from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc
    except (OpenAIError, LangChainException, ValueError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


def _safe_error(exc: Exception) -> str:
    return f"RAG service is unavailable: {type(exc).__name__}"
