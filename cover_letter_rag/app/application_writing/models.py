from typing import Literal
from pydantic import Field
from app.application_planning.models import StrictModel, PlanningInput, ApplicationPlan, Question, AskKey
from app.job_requirements import JobRequirement

SourceType = Literal['evidence', 'applicant_intent', 'target_context']
Status = Literal['READY', 'NEEDS_INPUT', 'BLOCKED']


class RequirementSource(StrictModel):
    application_id: str
    profile_key: str
    snapshot_hash: str
    prompt_version: str
    requirement: JobRequirement
    requirement_hash: str


class ContextMaterial(StrictModel):
    """Caller-normalized, source-bound material, not a raw conversation."""
    material_id: str = Field(min_length=1)
    source_type: Literal['applicant_intent', 'target_context']
    question_id: str
    key: AskKey
    normalized_text: str = Field(min_length=1)
    source_quote: str = Field(min_length=1)
    source_path: list[str] = Field(default_factory=list)
    answer_index: int | None = None
    requirement_source: RequirementSource | None = None


class WriteRequest(StrictModel):
    planning_input: PlanningInput
    plan: ApplicationPlan
    questions: list[Question]
    materials: list[ContextMaterial] = Field(default_factory=list)
    plan_input_hash: str = Field(min_length=1)
    current_input_hash: str = Field(min_length=1)


class ReadinessResult(StrictModel):
    question_id: str
    status: Status
    issues: list[str] = Field(default_factory=list)
    missing_information: list[dict] = Field(default_factory=list)


class SupportRef(StrictModel):
    source_type: SourceType
    source_id: str


class AnswerSentence(StrictModel):
    text: str = Field(min_length=1)
    support_refs: list[SupportRef]
    claim_types: list[SourceType]


class WriterOutput(StrictModel):
    question_id: str
    sentences: list[AnswerSentence] = Field(min_length=1)

    @property
    def final_text(self):
        return ' '.join(s.text.strip() for s in self.sentences)


class SemanticResult(StrictModel):
    question_id: str
    factual_issues: list[str]
    quality_issues: list[str]
    expressed_core_evidence_ids: list[str]
    covered_requirements: list[AskKey]
    story_focus_preserved: bool


class ValidationResult(StrictModel):
    factual_issues: list[str] = Field(default_factory=list)
    quality_issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def passed(self):
        return not self.factual_issues and not self.quality_issues


class AnswerResult(StrictModel):
    question_id: str
    status: Status
    readiness: ReadinessResult
    candidate: WriterOutput | None = None
    validation: ValidationResult | None = None
    rewrite_count: int = Field(default=0, ge=0, le=1)
    attempts: list[dict] = Field(default_factory=list)
    error: str = ''

    @property
    def final_text(self):
        return self.candidate.final_text if self.status == 'READY' and self.candidate else ''
