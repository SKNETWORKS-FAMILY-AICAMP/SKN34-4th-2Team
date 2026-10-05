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


class ProjectSlot(StrEnum):
    OVERVIEW = 'overview'
    PURPOSE = 'purpose_or_problem'
    OBSERVATION = 'problem_observation'
    ROLE = 'personal_role'
    TECHNOLOGIES = 'technologies'
    ACTIONS = 'actions'
    DECISIONS = 'technical_decisions'
    VALIDATION = 'validation_method'
    OUTCOME = 'outcome'
    INSIGHT = 'insight_or_learning'
    SCALE = 'scale_or_constraints'


class EvidenceFacet(StrictModel):
    """Planning classification, never a new applicant assertion or DB field."""
    evidence_id: str
    slots: list[ProjectSlot]
    material: bool = True


class SourceDocument(StrictModel):
    source_id: str
    text: str


class ClaimType(StrEnum):
    TECHNOLOGY = 'technology_used'
    ACTION = 'action_performed'
    OWNERSHIP = 'role_owned'
    LEADERSHIP = 'role_led'
    OBSERVATION = 'problem_observed'
    DECISION = 'decision_made'
    METRIC = 'metric_used'
    VALIDATION = 'validation_performed'
    OUTCOME = 'outcome_observed'
    SCALE = 'scale'
    LEARNING = 'learning'
    MOTIVATION = 'motivation'
    PLAN = 'future_plan'


class ApplicantIntentClaim(StrictModel):
    id: str
    source_section_id: str
    intent_type: Literal['motivation', 'job_interest', 'company_interest',
        'short_term_plan', 'learning_plan', 'contribution_plan', 'improvement_goal',
        'long_term_goal', 'career_direction', 'work_value']
    text: str = Field(min_length=1)
    source_type: Literal['resume_text', 'user_answer']
    source_id: str
    evidence_quote: str = Field(min_length=1)
    state: AssertionState
    supersedes_intent_ids: list[str] = Field(default_factory=list)


class SourceRef(StrictModel):
    type: Literal['applicant_evidence', 'applicant_intent', 'target_context']
    id: str


class SemanticUnit(StrictModel):
    id: str
    semantic_role: str
    meaning: str
    source_refs: list[SourceRef] = Field(min_length=1)


class SectionContract(StrictModel):
    section_type: str
    objective: str
    high_value_semantics: list[str]


class SectionSemanticProfile(StrictModel):
    section_type: str
    original_semantic_units: list[SemanticUnit] = Field(default_factory=list)
    evidence_claim_ids: list[str] = Field(default_factory=list)
    intent_claim_ids: list[str] = Field(default_factory=list)
    target_context_ids: list[str] = Field(default_factory=list)
    required_semantics: list[str] = Field(default_factory=list)
    optional_semantics: list[str] = Field(default_factory=list)
    protected_semantics: list[str] = Field(default_factory=list)


class SentencePlanItem(StrictModel):
    plan_id: str
    purpose: str
    semantic_unit_ids: list[str]
    source_refs: list[SourceRef]


class SentencePlan(StrictModel):
    section_type: str
    items: list[SentencePlanItem] = Field(default_factory=list)


class ProfileSlot(StrictModel):
    evidence_ids: list[str] = Field(default_factory=list)


class ProjectEvidenceProfile(StrictModel):
    experience_id: str
    project_type: Literal['data_analysis', 'machine_learning', 'ai_service', 'backend',
        'frontend', 'fullstack', 'data_engineering', 'general_software', 'unknown'] = 'unknown'
    overview: ProfileSlot = Field(default_factory=ProfileSlot)
    purpose_or_problem: ProfileSlot = Field(default_factory=ProfileSlot)
    problem_observation: ProfileSlot = Field(default_factory=ProfileSlot)
    personal_role: ProfileSlot = Field(default_factory=ProfileSlot)
    technologies: ProfileSlot = Field(default_factory=ProfileSlot)
    actions: ProfileSlot = Field(default_factory=ProfileSlot)
    technical_decisions: ProfileSlot = Field(default_factory=ProfileSlot)
    validation_method: ProfileSlot = Field(default_factory=ProfileSlot)
    outcome: ProfileSlot = Field(default_factory=ProfileSlot)
    insight_or_learning: ProfileSlot = Field(default_factory=ProfileSlot)
    scale_or_constraints: ProfileSlot = Field(default_factory=ProfileSlot)


class EvidenceGap(StrictModel):
    gap_type: Literal['missing', 'clarification']
    target_slot: ProjectSlot
    priority: Literal['HIGH', 'MEDIUM']
    existing_evidence_ids: list[str] = Field(default_factory=list)
    why_needed: str
    focus: Literal['open', 'observation_basis', 'comparison_basis', 'model_evaluation', 'analysis_validation'] = 'open'


class QuestionPresupposition(StrictModel):
    fact: str
    evidence_ids: list[str]


class GapQuestion(StrictModel):
    experience_id: str = Field(min_length=1)
    experience_title: str = ''
    question: str
    gap_type: Literal['missing', 'clarification']
    target_slot: ProjectSlot
    evidence_basis: list[str] = Field(default_factory=list)
    priority: Literal['HIGH', 'MEDIUM']
    why_needed: str
    presuppositions: list[QuestionPresupposition] = Field(default_factory=list)
    dedupe_key: str
    focus: Literal['open', 'observation_basis', 'comparison_basis', 'model_evaluation', 'analysis_validation'] = 'open'


class ReviewInput(StrictModel):
    experience: Experience
    question: str = ""
    answer: str = ""
    answer_source_id: str = ""
    job_requirements: list[JobRequirement] = Field(default_factory=list)
    previous_question_keys: list[str] = Field(default_factory=list)
    question_history: list[str] = Field(default_factory=list)
    resume_sources: list[SourceDocument] = Field(default_factory=list)
    previous_facets: list[EvidenceFacet] = Field(default_factory=list)
    unavailable_slots: list[ProjectSlot] = Field(default_factory=list)
    existing_intents: list[ApplicantIntentClaim] = Field(default_factory=list)
    previous_semantic_units: list[SemanticUnit] = Field(default_factory=list)
    section_profile: SectionSemanticProfile | None = None
    sentence_plan: SentencePlan | None = None
    approved_intents: list[ApplicantIntentClaim] = Field(default_factory=list)

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
    core_evidence_ids: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    preserved_evidence_ids: list[str] = Field(default_factory=list)
    omitted_evidence: list[OmittedEvidence] = Field(default_factory=list)
    reason: str = ""


class AnalystOutput(StrictModel):
    experience_id: str
    extracted_evidence: list[Evidence]
    signals: list[AnalysisSignal] = Field(default_factory=list)
    plan: RevisionPlan
    question: QuestionProposal | None = None


class ExtractionOutput(StrictModel):
    """Source extraction and one optional editorial clarification; no revision plan."""
    experience_id: str
    extracted_evidence: list[Evidence]
    facets: list[EvidenceFacet] = Field(default_factory=list)
    intent_claims: list[ApplicantIntentClaim] = Field(default_factory=list)
    semantic_units: list[SemanticUnit] = Field(default_factory=list)
    question: GapQuestion | None = None


class RevisionSentence(StrictModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    intent_ids: list[str] = Field(default_factory=list)
    target_context_ids: list[str] = Field(default_factory=list)
    semantic_unit_ids: list[str] = Field(default_factory=list)
    claim_types: list[ClaimType] = Field(default_factory=list)


class WriterDraft(StrictModel):
    experience_id: str
    sentences: list[RevisionSentence] = Field(min_length=1)


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
    quality_issues: list['ValidationIssue'] = Field(default_factory=list)
    unsupported_intents: list[str] = Field(default_factory=list)
    section_meaning_loss: list[str] = Field(default_factory=list)
    revision_quality: Literal['improved', 'no_better', 'worse'] = 'improved'
    comparison_reason: str = ''


class ValidationIssue(StrictModel):
    code: str
    detail: str


class ValidationResult(StrictModel):
    status: Literal["READY", "REWRITE", "NEEDS_EVIDENCE", "REJECTED", "UNCHANGED"]
    factual_issues: list[ValidationIssue] = Field(default_factory=list)
    quality_issues: list[ValidationIssue] = Field(default_factory=list)
    intent_issues: list[ValidationIssue] = Field(default_factory=list)
    section_issues: list[ValidationIssue] = Field(default_factory=list)

    @property
    def all_issues(self):
        return self.factual_issues + self.intent_issues + self.section_issues + self.quality_issues


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
    project_profile: ProjectEvidenceProfile | None = None
    evidence_facets: list[EvidenceFacet] = Field(default_factory=list)
    evidence_gaps: list[EvidenceGap] = Field(default_factory=list)
    gap_questions: list[GapQuestion] = Field(default_factory=list)
    unavailable_slots: list[ProjectSlot] = Field(default_factory=list)
    intent_claims: list[ApplicantIntentClaim] = Field(default_factory=list)
    section_profile: SectionSemanticProfile | None = None
    sentence_plan: SentencePlan | None = None
    debug_trace: dict = Field(default_factory=dict)
