"""Versioned contracts for the standalone v2 engine (not the v1 API schema)."""

from enum import StrEnum
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactType(StrEnum):
    CONTEXT = "context"
    ROLE = "role"
    SCOPE = "scope"
    ACTION = "action"
    TECHNOLOGY = "technology"
    IMPLEMENTATION = "implementation"
    TECHNICAL_DECISION = "technical_decision"
    RESULT = "result"
    VERIFICATION = "verification"
    DURATION = "duration"


class AssertionState(StrEnum):
    RESUME_STATED = "resume_stated"
    USER_ASSERTED = "user_asserted"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"
    RETRACTED = "retracted"
    SUPERSEDED = "superseded"


class Evidence(StrictModel):
    evidence_id: str = Field(min_length=1)
    experience_id: str = Field(min_length=1)
    fact_type: FactType
    normalized_fact: str = Field(min_length=1)
    evidence_quote: str = Field(min_length=1)
    source_type: Literal["resume_text", "user_answer", "uploaded_document"]
    source_id: str = Field(min_length=1)
    assertion_state: AssertionState
    supersedes_evidence_ids: list[str] = Field(default_factory=list)
    conflicts_with_evidence_ids: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class Experience(StrictModel):
    experience_id: str = Field(min_length=1)
    kind: Literal["project", "employment", "education", "activity", "other"]
    title: str
    current_text: str
    field_path: str = Field(min_length=1)  # Apply locator, never the editing identity.
    content_hash: str = Field(min_length=1)
    existing_evidence: list[Evidence] = Field(default_factory=list)
    # Evidence references, not duplicate copies of the asserted facts.
    context_problem: list[str] = Field(default_factory=list)
    role: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    implementations: list[str] = Field(default_factory=list)
    technical_decisions: list[str] = Field(default_factory=list)
    results: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)


class JobRequirement(StrictModel):
    requirement_id: str
    text: str
    posting_quote: str


class ReviewInput(StrictModel):
    experience: Experience
    question: str = ""
    answer: str = ""
    answer_source_id: str = ""
    job_requirements: list[JobRequirement] = Field(default_factory=list)
    previous_question_keys: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def answer_needs_source(self):
        if self.answer.strip() and not self.answer_source_id:
            raise ValueError("answer_source_id required when answer is present")
        return self


class OmittedEvidence(StrictModel):
    evidence_id: str
    reason: str


class AnalysisSignal(StrictModel):
    kind: Literal["direct_contribution", "technology", "implementation", "decision", "result", "duplication", "missing_information"]
    description: str
    evidence_ids: list[str] = Field(default_factory=list)


class QuestionProposal(StrictModel):
    question: str
    missing_fact_type: FactType
    improvement_hypothesis: str
    dedupe_key: str


class RevisionPlan(StrictModel):
    objective: str
    operation: Literal["replace_field", "no_change"]
    core_evidence_ids: list[str] = Field(default_factory=list, max_length=2)
    supporting_evidence_ids: list[str] = Field(default_factory=list, max_length=2)
    preserved_evidence_ids: list[str] = Field(default_factory=list)
    omitted_evidence: list[OmittedEvidence] = Field(default_factory=list)
    reason: str = ""


class AnalystOutput(StrictModel):
    experience_id: str
    extracted_evidence: list[Evidence]
    signals: list[AnalysisSignal] = Field(default_factory=list)
    plan: RevisionPlan
    question: QuestionProposal | None = None


class RevisionSentence(StrictModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class WriterOutput(StrictModel):
    experience_id: str
    operation: Literal["replace_field"]
    original_quote: str
    sentences: list[RevisionSentence] = Field(min_length=1)

    @property
    def suggested_text(self) -> str:
        return " ".join(sentence.text.strip() for sentence in self.sentences)


class FactVerification(StrictModel):
    """Independent semantic check; the server still runs deterministic checks."""

    unsupported_claims: list[str] = Field(default_factory=list)
    weakened_original_facts: list[str] = Field(default_factory=list)
    unclaimed_factual_content: list[str] = Field(default_factory=list)
    critical_technical_signal_loss: list[str] = Field(default_factory=list)


class ValidationIssue(StrictModel):
    code: str
    detail: str


class ValidationResult(StrictModel):
    status: Literal["READY", "REWRITE", "NEEDS_EVIDENCE", "REJECTED"]
    factual_issues: list[ValidationIssue] = Field(default_factory=list)
    quality_issues: list[ValidationIssue] = Field(default_factory=list)


class RevisionCandidate(StrictModel):
    experience_id: str
    field_path: str
    content_hash: str
    original_quote: str
    suggested_text: str
    sentences: list[RevisionSentence]
    validation: ValidationResult


class Usage(StrictModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class ReviewResult(StrictModel):
    engine_version: Literal["v2-offline-1"] = "v2-offline-1"
    experience: Experience
    question: str
    answer: str
    extracted_evidence: list[Evidence]
    selected_evidence: list[Evidence]
    omitted_evidence: list[OmittedEvidence]
    plan: RevisionPlan
    proposed_question: QuestionProposal | None
    candidate: RevisionCandidate | None
    validation: ValidationResult
    usage: Usage
