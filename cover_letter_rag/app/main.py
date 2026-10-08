import re
from typing import Literal

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from langchain_core.exceptions import LangChainException
from openai import OpenAIError
from pydantic import Field

from app.config import Settings, get_settings
from app.models import (
    FirestoreResumeReviewRequest,
    FirestoreResumeReviewResponse,
    HealthResponse,
    StrictModel,
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
from app.review_runtime_factory import build_review_gateway, build_review_service


app = FastAPI(
    title="Resume Review API",
    version="0.2.0",
    description="선택 공고와 이력서를 대조하는 대화형 이력서 첨삭·맞춤 이력서 API",
)
from app.resume_apply import router as resume_apply_router
app.include_router(resume_apply_router)


def get_context_gateway() -> FirebaseGateway:
    settings = get_settings()
    if settings.resume_review_engine == 'v1' and not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail='Firebase configuration unavailable')
    try:
        return build_review_gateway(settings)
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
    return _review_context(
        lambda: gateway.verify_id_token(extract_bearer_token(authorization)),
        cohort_id, resume_id, job_id, tailored_resume_id, gateway, settings,
    )


class ProxyReviewContextRequest(StrictModel):
    """LMS(Django) 프록시용 review-context. uid 로 학생을 확인한다."""

    uid: str = Field(min_length=1, max_length=128)
    cohort_id: str = Field(min_length=1, max_length=200, pattern=r'^[^/]+$')
    resume_id: str = Field(min_length=1, max_length=200, pattern=r'^[^/]+$')
    job_id: str | None = Field(default=None, min_length=1, max_length=200)
    tailored_resume_id: str | None = Field(default=None, min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


@app.post('/api/v1/resumes/review-context/proxy')
def review_context_as_user(
    request: ProxyReviewContextRequest,
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    """LMS 가 학생을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다)."""
    return _review_context(
        lambda: request.uid, request.cohort_id, request.resume_id,
        request.job_id, request.tailored_resume_id, gateway, settings,
    )


def _review_context(resolve_uid, cohort_id, resume_id, job_id, tailored_resume_id, gateway, settings):
    from app.matching_handoff import load_selected_job
    from app.review_workflow import digest
    from fastapi.responses import JSONResponse
    try:
        uid = resolve_uid()
        job = load_selected_job(settings.matching_job_store_path, job_id) if job_id else None
        if tailored_resume_id:
            if job:
                # 옛 맞춤본은 공고 스냅샷 정보가 비어 있다. 이어 열 때 채워 둔다(있으면 그대로)
                gateway.adopt_legacy_tailored(cohort_id, resume_id, tailored_resume_id, uid, job['source'])
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


class ProxyJobRequirementsRequest(StrictModel):
    job_id: str = Field(min_length=1, max_length=200)


@app.post('/api/v1/resumes/job-requirements/proxy')
def job_requirements_as_user(
    request: ProxyJobRequirementsRequest,
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    """공고 하나의 요건 목록 — 공고를 먼저 고르고 이력서를 만드는 화면이 미리 보여 준다.

    이력서를 보지 않는다. 첫 첨삭이 쓰는 것과 같은 저장본(공고 스냅샷마다 한 번)을 읽고, 없으면
    만들어 저장한다. 그래서 여기서 먼저 보면 첫 첨삭이 요건 정리를 기다리지 않는다.
    LMS 가 로그인을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다).
    """
    from app.job_requirements import build_requirement_extractor, load_or_extract_requirements
    from app.matching_handoff import load_selected_job
    try:
        job = load_selected_job(settings.matching_job_store_path, request.job_id)
        extractor = build_requirement_extractor(settings) if settings.openai_api_key else None
        requirements = load_or_extract_requirements(gateway, extractor, job['text'], job['source'])
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError, OpenAIError, LangChainException) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc
    return {
        'job_id': request.job_id,
        'requirements': [
            {'id': item.id, 'group': item.group, 'label': item.label, 'posting_quote': item.posting_quote}
            for item in requirements
        ],
    }


class ProxyQuestionExtractRequest(StrictModel):
    """LMS(Django) 프록시용. 캡처 이미지 세 장까지, 또는 지원서 양식 파일(PDF · DOCX · PPTX · HWPX) 한 개(data URL)에서
    문항을 뽑는다. 저장하지 않는다."""

    images: list[str] = Field(min_length=1, max_length=3)


def get_question_extractor(settings: Settings = Depends(get_settings)):
    from app.question_extract import build_question_extractor
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail='문항을 읽을 모델이 설정되어 있지 않습니다(OPENAI_API_KEY).')
    return build_question_extractor(settings)


@app.post('/api/v1/resumes/question-extract/proxy')
def question_extract_as_user(request: ProxyQuestionExtractRequest, extractor=Depends(get_question_extractor)):
    """캡처 → 문항 목록(question_extract.py). 이미지는 저장하지 않고, 뽑은 문항은 화면에서 학생이 확인한다.

    LMS 가 로그인 · 파일 종류 · 크기를 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다).
    """
    from app.question_extract import DOCUMENT_TYPES, extract_questions
    kinds = '|'.join(['image/(png|jpeg|webp)', 'application/pdf', *map(re.escape, DOCUMENT_TYPES)])
    if any(not re.match(rf'^data:({kinds});base64,', url) for url in request.images):
        raise HTTPException(status_code=422, detail='unsupported_image')
    try:
        return extract_questions(extractor, request.images)
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, OpenAIError, LangChainException) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


class QuestionAnswerItem(StrictModel):
    question: str = Field(max_length=500)
    answer: str = Field(max_length=3000)
    source_type: Literal['memo', 'answer', 'selection'] = 'answer'
    selected_experience_id: str | None = Field(default=None, max_length=200)


class ProxyQuestionAnswerRequest(StrictModel):
    """LMS(Django) 프록시용. 공고 맞춤 이력서의 회사 문항 하나에 답을 쓴다."""

    uid: str = Field(min_length=1, max_length=128)
    cohort_id: str = Field(min_length=1, max_length=200, pattern=r'^[^/]+$')
    resume_id: str = Field(min_length=1, max_length=200, pattern=r'^[^/]+$')
    tailored_resume_id: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')
    question_id: str = Field(min_length=1, max_length=100)
    answers: list[QuestionAnswerItem] = Field(default_factory=list, max_length=12)


def get_question_answer_generator(settings: Settings = Depends(get_settings)):
    from app.question_answers import build_question_answer_generator
    if not settings.openai_api_key:
        raise HTTPException(status_code=503, detail='답변을 쓸 모델이 설정되어 있지 않습니다(OPENAI_API_KEY).')
    return build_question_answer_generator(settings)


@app.post('/api/v1/resumes/question-answer/proxy')
def question_answer_as_user(
    request: ProxyQuestionAnswerRequest,
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
    generator=Depends(get_question_answer_generator),
):
    """회사 자기소개서 문항 하나의 답 — 공고 요건과 이력서 근거로 쓴다(question_answers.py).

    기존 첨삭과 따로 돈다. 사본을 고치지 않고 답만 돌려준다. 저장은 화면이 사용자가 고른 답으로 한다.
    LMS 가 학생을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다).
    """
    from app.job_requirements import build_requirement_extractor, load_or_extract_requirements
    from app.matching_handoff import load_selected_job
    from app.question_answers import write_question_answer
    try:
        tailored = gateway.get_owned_tailored_resume(
            request.cohort_id, request.resume_id, request.tailored_resume_id, request.uid,
        )
        job = load_selected_job(settings.matching_job_store_path, tailored.get('jobId') or '')
        requirements = load_or_extract_requirements(
            gateway, build_requirement_extractor(settings), job['text'], job['source'],
        )
        return write_question_answer(
            tailored=tailored, question_id=request.question_id,
            answers=[item.model_dump() for item in request.answers],
            job=job, requirements=requirements, generator=generator,
        )
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Resume was not found') from exc
    except ReviewConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ReviewInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, GoogleAPIError, GoogleAuthError, OpenAIError, LangChainException) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


@app.post('/api/v1/resumes/tailored', response_model=TailoredResumeResponse)
def create_tailored_resume(
    request: TailoredResumeCreateRequest,
    background: BackgroundTasks,
    authorization: str | None = Header(default=None),
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    return _create_tailored(
        lambda: gateway.verify_id_token(extract_bearer_token(authorization)),
        request, background, gateway, settings,
    )


class ProxyTailoredResumeCreateRequest(TailoredResumeCreateRequest):
    """LMS(Django) 프록시용. Firebase 토큰 대신 uid 로 학생을 확인한다."""

    uid: str = Field(min_length=1, max_length=128)


@app.post('/api/v1/resumes/tailored/proxy', response_model=TailoredResumeResponse)
def create_tailored_resume_as_user(
    request: ProxyTailoredResumeCreateRequest,
    background: BackgroundTasks,
    gateway: FirebaseGateway = Depends(get_context_gateway),
    settings: Settings = Depends(get_settings),
):
    """LMS 가 학생을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다)."""
    return _create_tailored(lambda: request.uid, request, background, gateway, settings)


def _create_tailored(resolve_uid, request, background, gateway, settings):
    from app.matching_handoff import load_selected_job
    try:
        uid = resolve_uid()
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
    return _promote_tailored(
        lambda: gateway.verify_id_token(extract_bearer_token(authorization)),
        request.cohort_id, resume_id, tailored_resume_id, gateway,
    )


class ProxyTailoredResumePromoteRequest(TailoredResumePromoteRequest):
    """LMS(Django) 프록시용. 이력서 id 둘은 주소 대신 본문으로 받는다."""

    uid: str = Field(min_length=1, max_length=128)
    resume_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,200}$')
    tailored_resume_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')


@app.post('/api/v1/resumes/tailored/promote/proxy')
def promote_tailored_resume_as_user(
    request: ProxyTailoredResumePromoteRequest,
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    """LMS 가 학생을 확인한 뒤 부른다. 이 창구는 바깥에 열지 않는다(Django 만 부른다)."""
    return _promote_tailored(
        lambda: request.uid, request.cohort_id, request.resume_id, request.tailored_resume_id, gateway,
    )


class ProxyTailoredResumeRef(StrictModel):
    """LMS(Django) 프록시용. 맞춤본 하나를 가리킨다."""

    uid: str = Field(min_length=1, max_length=128)
    cohort_id: str = Field(min_length=1, max_length=200, pattern=r'^[^/]+$')
    resume_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,200}$')
    tailored_resume_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')


@app.post('/api/v1/resumes/tailored/get/proxy', response_model=TailoredResumeResponse)
def get_tailored_resume_as_user(
    request: ProxyTailoredResumeRef,
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    """맞춤본과 저장된 첨삭 대화. 재첨삭 창이 이어서 연다. Django 만 부른다."""
    try:
        return TailoredResumeService(gateway, lambda _: {}).get(
            request.uid, request.cohort_id, request.resume_id, request.tailored_resume_id,
        )
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc
    except (GoogleAPIError, GoogleAuthError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail=_safe_error(exc)) from exc


class ProxyTailoredSessionRequest(ProxyTailoredResumeRef):
    state: dict = Field(default_factory=dict)


@app.post('/api/v1/resumes/tailored/session/proxy')
def save_tailored_resume_session_as_user(
    request: ProxyTailoredSessionRequest,
    gateway: FirebaseGateway = Depends(get_context_gateway),
):
    """첨삭 대화를 맞춤본에 남긴다. 창을 닫았다 다시 열면 이어 간다. Django 만 부른다."""
    try:
        gateway.save_tailored_resume_session(
            request.cohort_id, request.resume_id, request.tailored_resume_id, request.uid, request.state,
        )
        return {'saved': True}
    except ResumeAccessError as exc:
        raise HTTPException(status_code=403, detail='Resume access denied') from exc
    except ResumeNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Tailored resume was not found') from exc


def _promote_tailored(resolve_uid, cohort_id, resume_id, tailored_resume_id, gateway):
    try:
        uid = resolve_uid()
        workspace_resume_id = gateway.promote_tailored_resume(
            cohort_id,
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
    if settings.resume_review_engine == 'v1' and not settings.firebase_project_id:
        raise HTTPException(status_code=503, detail="FIREBASE_PROJECT_ID is not configured on the server")
    try:
        return build_review_service(settings)
    except (GoogleAuthError, GoogleAPIError, ValueError) as exc:
        raise HTTPException(status_code=503, detail='Firebase configuration unavailable') from exc


@app.get("/health", response_model=HealthResponse)
def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        model=settings.openai_model,
        review_engine=settings.resume_review_engine,
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
        if inner.answer_changes and getattr(service, 'supports_answer_changes', False) is not True:
            raise ReviewInputError('answer_edit_not_supported')
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
