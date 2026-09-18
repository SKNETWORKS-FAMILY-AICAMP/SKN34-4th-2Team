from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.json_schema import SkipJsonSchema


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequirementStatus(StrEnum):
    MET = "충족"
    PARTIAL = "부분 충족"
    NOT_MET = "미충족"
    NEEDS_CONFIRMATION = "확인 필요"


class ConfirmationAnswer(StrictModel):
    question_id: str | None = None
    field_path: str = Field(min_length=1, max_length=300)
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=3000)


class NewProjectOut(StrictModel):
    """후속 첨삭에서 답변이 이력서의 어느 항목에도 없는 별도 경험을 말할 때 모델이 내는 새 프로젝트 제안.

    서버가 이름·설명·기술을 답변과 대조한 뒤에만 수정안(SentenceReview.new_item)으로 싣는다.
    """

    answer_quote: str = Field(description="이 경험이 적힌 이번 답변의 연속 인용")
    name: str = Field(description="답변에 나온 말로 지은 짧은 프로젝트 이름")
    role: str = Field(default='', description="답변에 적힌 형태나 역할(예: 개인 과제). 없으면 빈 문자열")
    tech_stack: str = Field(default='', description="답변에 나온 기술 이름만 쉼표로 구분. 없으면 빈 문자열")
    description: str = Field(description="답변에 적힌 사실만으로 쓴 1~3문장 설명")


class NewResumeItem(StrictModel):
    """서버가 검증한 새 항목. 적용하면 해당 목록 끝에 항목 하나가 생긴다."""

    section: Literal['projects'] = 'projects'
    question_id: str | None = None
    name: str
    role: str = ''
    tech_stack: str = ''
    description: str


class SentenceReview(StrictModel):
    field_path: str
    original_quote: str
    reason: str
    suggested_revision: str | None = None
    evidence_quotes: list[str] = Field(default_factory=list)
    confirmation_question: str | None = None
    status: Literal['unchanged', 'formatting', 'improved', 'needs_confirmation'] = 'needs_confirmation'
    evidence_sources: list[str] = Field(default_factory=list)
    edit_type: Literal['none', 'spelling', 'tone', 'clarity', 'content'] = 'content'
    validation_issues: list[str] = Field(default_factory=list)
    # Server-derived evidence anchors. The model must not decide which facts are protected.
    fact_anchors: list[str] = Field(default_factory=list)
    change_rate: float | None = Field(default=None, ge=0, le=1)
    change_rate_notice: str | None = None
    # 서버가 채운다. 수정안 문장이 다른 칸 문장과 비슷할 때 사용자에게 보이는 안내. 막지 않고 알린다.
    overlap_notice: str | None = None
    # 서버가 채운다. 원문의 바람·목적 부정 표현("불편을 겪지 않는")이 수정안에서 빠졌을 때의 안내. 막지 않고 알린다.
    meaning_notice: SkipJsonSchema[str | None] = None
    # 서버가 채운다. 원문에 한 일·결과로 적힌 사실이 수정안에서 빠지거나 약해졌을 때의 안내(검사 모델 판단). 막지 않는다.
    fact_notice: SkipJsonSchema[str | None] = None
    # 서버가 채운다. 답을 원문 뒤에 "또한 …" 별도 문단으로만 덧붙인 수정안의 안내. 막지 않는다.
    flow_notice: SkipJsonSchema[str | None] = None
    # 서버가 채운다. 기존 칸을 고치는 대신 새 항목을 추가하는 수정안이면 그 항목. field_path는 추가될 자리다.
    # 모델 출력 스키마에서는 뺀다(모델이 채울 칸이 아니고, 첫 첨삭마다 스키마만 길어진다).
    new_item: SkipJsonSchema[NewResumeItem | None] = None
    # 서버가 채운다. requirement_id는 이 수정안이 보강하는 공고 요건, stage는 대화 단계
    # (1 문장 다듬기 · 2 공고 요건 확인 · 3 경험 보완 · 4 지원동기 · 5 자기소개서).
    requirement_id: str | None = None
    stage: int = Field(default=0, ge=0, le=5)


class FirestoreResumeReviewRequest(StrictModel):
    # 일반 첨삭은 공고와 분리해 이력서 원문 자체를 검토한다. 기존 공고 첨삭 호출은
    # 호환성을 위해 job 모드를 기본값으로 유지한다.
    review_mode: Literal['general', 'job'] = 'job'
    review_phase: Literal['standard', 'gap_audit'] = 'standard'
    selected_job_id: str | None = Field(default=None, min_length=1, max_length=200)
    expected_job_hash: str | None = None
    request_id: str = Field(default_factory=lambda: __import__('uuid').uuid4().hex, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    previous_review_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    expected_input_hash: str | None = None
    cohort_id: str = Field(min_length=1, max_length=200)
    resume_id: str = Field(min_length=1, max_length=200)
    # 공고 맞춤 첨삭은 기본 이력서가 아닌 공고별 사본을 대상으로 한다.
    tailored_resume_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,100}$')
    job_posting_text: str | None = Field(default=None, max_length=50_000)
    review_focus: str | None = Field(default=None, max_length=2_000)
    answers: list[ConfirmationAnswer] = Field(default_factory=list, max_length=10)

    @field_validator("cohort_id", "resume_id")
    @classmethod
    def reject_blank_id(cls, value: str) -> str:
        if not value.strip() or '/' in value or value.strip() in {'.', '..'}:
            raise ValueError("identifier must not be blank")
        return value.strip()

    @field_validator("tailored_resume_id")
    @classmethod
    def normalize_tailored_resume_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value or '/' in value or value in {'.', '..'}:
            raise ValueError("tailored resume identifier must not be blank")
        return value

    @field_validator("job_posting_text", "review_focus")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None


class TailoredResumeCreateRequest(StrictModel):
    cohort_id: str = Field(min_length=1, max_length=200)
    resume_id: str = Field(min_length=1, max_length=200)
    selected_job_id: str = Field(min_length=1, max_length=200)

    @field_validator("cohort_id", "resume_id", "selected_job_id")
    @classmethod
    def reject_unsafe_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or '/' in value or value in {'.', '..'}:
            raise ValueError("identifier must not be blank")
        return value


class TailoredResumeSummary(StrictModel):
    tailored_resume_id: str
    base_resume_id: str
    job_id: str
    company_name: str
    job_title: str
    title: str = ''
    source_resume_hash: str
    job_snapshot_hash: str
    status: Literal['draft', 'ready', 'archived']
    review_progress: Literal['not_started', 'in_progress', 'completed'] = 'not_started'
    workspace_resume_id: str = ''


class TailoredResumeResponse(TailoredResumeSummary):
    content: dict[str, Any]
    review_session: dict[str, Any] = Field(default_factory=dict)


class TailoredResumeSessionRequest(StrictModel):
    cohort_id: str = Field(min_length=1, max_length=200)
    state: dict[str, Any] = Field(default_factory=dict)

    @field_validator("cohort_id")
    @classmethod
    def reject_unsafe_cohort_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or '/' in value or value in {'.', '..'}:
            raise ValueError("identifier must not be blank")
        return value


class TailoredResumePromoteRequest(StrictModel):
    cohort_id: str = Field(min_length=1, max_length=200)

    @field_validator("cohort_id")
    @classmethod
    def reject_unsafe_cohort_identifier(cls, value: str) -> str:
        value = value.strip()
        if not value or '/' in value or value in {'.', '..'}:
            raise ValueError("identifier must not be blank")
        return value


class ResumeSectionReview(StrictModel):
    section_key: str
    strengths: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    resume_quotes: list[str] = Field(default_factory=list)
    suggested_revision: str | None = None
    confirmation_questions: list[str] = Field(default_factory=list)


class Diagnostic(StrictModel):
    criterion: Literal['aspiration', 'emotion', 'abstract_result', 'ordering', 'relevance', 'duplication', 'company_fit']
    status: Literal['issue', 'clear', 'not_evaluated']
    field_paths: list[str] = Field(default_factory=list)
    reason: str


StarElement = Literal['situation', 'task', 'action', 'result']
STAR_ELEMENTS: tuple[str, ...] = ('situation', 'task', 'action', 'result')


class StarCheck(StrictModel):
    """경험 항목 하나의 STAR 판정. 서버가 인용을 원문·확인 답변과 대조한 뒤 채운다.

    present는 원문이나 그 항목의 확인 답변에 연속 인용이 실제로 있는 요소만 담는다. 모델이 "있다"고
    해도 인용이 확인되지 않으면 missing으로 둔다(요건 판정의 met과 같은 규칙).
    """

    field_path: str
    missing: list[StarElement] = Field(default_factory=list)
    reason: str = ''
    present: list[StarElement] = Field(default_factory=list)
    quotes: dict[str, str] = Field(default_factory=dict)


class StarJudgementOut(StrictModel):
    """모델이 경험 항목마다 내는 STAR 판정. 요소마다 원문 인용을 적고, 없으면 null."""

    field_path: str
    situation_quote: str | None = Field(default=None, description="해결하려던 문제·배경이 적힌 원문 인용. 없으면 null")
    task_quote: str | None = Field(default=None, description="맡은 역할·목표가 적힌 원문 인용. 없으면 null")
    action_quote: str | None = Field(default=None, description="본인이 직접 한 구체적 방법이 적힌 원문 인용. 없으면 null")
    result_quote: str | None = Field(default=None, description="결과·변화·확인한 내용이 적힌 원문 인용. 없으면 null")
    result_kind: Literal['metric_change', 'state_change', 'verification', 'recognition', 'activity', 'learning', 'plan'] | None = Field(
        default=None,
        description="result_quote의 종류. metric_change 수치 변화, state_change 문제 해결·상태 변화, verification 검증·확인 결과, "
                    "recognition 수상·선정·합격·병합, activity 한 일만 적음, learning 배운 점·깨달음, plan 목표·계획. 인용이 없으면 null",
    )
    missing_reason: str = Field(default='', description="빠진 요소가 있으면 무엇이 왜 빠졌는지 한 문장. 사용자에게 보인다")


class ReviewQuestion(StrictModel):
    question_id: str = ''
    field_path: str
    topic: Literal['situation', 'task', 'action', 'result', 'scope', 'other']
    question: str
    reason: str
    priority: int = Field(default=2, ge=1, le=3)
    requirement_id: str | None = None
    stage: int = Field(default=0, ge=0, le=5)


class RequirementMatchOut(StrictModel):
    """첨삭 모델이 공고 요건마다 내는 판정. 코드가 인용을 원문과 대조한 뒤 요건 표에 싣는다."""

    requirement_id: str
    status: Literal['met', 'partial', 'unconfirmed']
    evidence_paths: list[str] = Field(default_factory=list)
    evidence_quotes: list[str] = Field(default_factory=list)


class ResumeReviewGeneration(StrictModel):
    summary: str
    section_reviews: list[ResumeSectionReview]
    confirmation_questions: list[str] = Field(default_factory=list)
    sentence_reviews: list[SentenceReview] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)
    star_checks: list[StarCheck] = Field(default_factory=list)
    questions: list[ReviewQuestion] = Field(default_factory=list)
    requirement_matches: list[RequirementMatchOut] = Field(default_factory=list)
    star_judgements: list[StarJudgementOut] = Field(default_factory=list)
    new_projects: list[NewProjectOut] = Field(default_factory=list)


class ResumeReviewModelOutput(StrictModel):
    """모델이 채우는 출력. 앱에 보이는 요약·문장 수정안·질문만 받는다.

    섹션 진단·7개 기준 진단·STAR 점검은 앱 어디에서도 쓰지 않는데 출력의 절반을 차지했다.
    2026-09-14 A/B(같은 이력서·공고 4쌍 × 3회)에서 빼니 첫 첨삭이 61.7초 → 26.3초, 출력 토큰이
    6,429 → 3,337로 줄었고 수정안(1.0 → 1.5개)과 질문은 나빠지지 않았다. 응답 모델
    (ResumeReviewGeneration)의 해당 칸은 이전 결과와 호환하려고 빈 값으로 남긴다.

    STAR만 다시 받는다(star_judgements). 이번에는 앱이 항목마다 네 칸으로 보여 주고, 서버가 이미
    행동·결과가 적힌 항목의 질문을 거르는 데 쓴다. 요소마다 인용 한 줄이라 예전 STAR 점검보다 짧다.
    """

    summary: str
    requirement_matches: list[RequirementMatchOut] = Field(default_factory=list)
    star_judgements: list[StarJudgementOut] = Field(default_factory=list)
    sentence_reviews: list[SentenceReview] = Field(default_factory=list)
    questions: list[ReviewQuestion] = Field(default_factory=list)


class ResumeReviewFollowupOutput(ResumeReviewModelOutput):
    """후속 첨삭 전용 출력. 새 프로젝트 제안(new_projects)은 답변을 받은 뒤에만 받는다.

    첫 첨삭 스키마에도 두었더니 비워 두라고 했는데도 fresh 4케이스 모두 출력이 늘어 첫 첨삭이 46.3초 → 53.6초가
    됐다(2026-09-15 v16k). 첫 첨삭·누락 점검은 이 칸이 없는 ResumeReviewModelOutput을 쓴다.
    """

    new_projects: list[NewProjectOut] = Field(default_factory=list)


class FirestoreResumeReviewResponse(ResumeReviewGeneration):
    job_source: dict = Field(default_factory=dict)
    review_id: str
    cohort_id: str
    resume_id: str
    tailored_resume_id: str | None = None
    grounding_warnings: list[str] = Field(default_factory=list)
    input_fields: dict[str, str] = Field(default_factory=dict)
    input_hash: str = ""
    excluded_fields: list[str] = Field(default_factory=list)
    confirmed_answers: list[ConfirmationAnswer] = Field(default_factory=list)
    item_refs: dict[str, str] = Field(default_factory=dict)
    changes: dict[str, list[str]] = Field(default_factory=dict)
    # 공고 맞춤 첨삭의 요건 표. app.job_requirements.RequirementStatusRow를 dict로 담는다.
    requirement_map: list[dict] = Field(default_factory=list)
    # 후속 첨삭에서 답에 이름이 나와 함께 고칠 수 있었던 다른 항목 칸. 앱은 답한 칸과 이 칸의 수정안을 보여 준다.
    answer_scope_paths: list[str] = Field(default_factory=list)
    telemetry: dict = Field(default_factory=dict)
    notice: str = (
        "원본 이력서는 변경하지 않았습니다. 확인된 이력서 근거만 사용한 첨삭이며 "
        "합격 가능성이나 지원자 점수가 아닙니다."
    )


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    model: str
    firebase_auth: Literal["configured", "not_configured"] = "not_configured"
