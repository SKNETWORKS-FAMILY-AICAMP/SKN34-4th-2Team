from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

VERSION = 'application-plan-v4b'
ANALYSIS_VERSION = 'question-analysis-v2'
AskKey = Literal['company_motivation', 'role_motivation', 'preparation_effort', 'desired_work',
    'differentiating_strength', 'supporting_experience', 'challenge', 'problem', 'personal_action',
    'technical_contribution', 'collaboration', 'difficulty', 'solution', 'result', 'lesson', 'growth', 'future_plan']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Constraints(StrictModel):
    character_limit: int | None = Field(default=None, gt=0)
    count_unit: Literal['characters', 'bytes', 'unknown'] = 'characters'
    include_spaces: bool | None = None

class Question(StrictModel):
    question_id: str
    raw_text: str = Field(min_length=1)
    constraints: Constraints

class Ask(StrictModel):
    key: AskKey
    required: bool = True
    source_quote: str = Field(min_length=1)

class QuestionAnalysis(StrictModel):
    question_id: str
    asks_for: list[Ask] = Field(min_length=1)
    constraints: Constraints

class AnalysisBatch(StrictModel):
    questions: list[QuestionAnalysis]

class Fact(StrictModel):
    evidence_id: str
    experience_id: str
    fact_type: str
    normalized_fact: str
    assertion_state: Literal['resume_stated', 'user_asserted']

class PlanningExperience(StrictModel):
    experience_id: str
    title: str
    kind: str
    evidence: list[Fact]

class AnswerDocument(StrictModel):
    question_id: str
    content: str
    source_type: str
    target_experience_id: str | None = None
    confirmation_key: str = ''
    topic_resolved: bool = False

class PlanningInput(StrictModel):
    application_id: str
    questions: list[QuestionAnalysis]
    experiences: list[PlanningExperience]
    target_context: dict = Field(default_factory=dict)
    answers: list[AnswerDocument] = Field(default_factory=list)
    previous_question_keys: list[str] = Field(default_factory=list)

class Gap(StrictModel):
    key: AskKey
    category: Literal['experience_evidence', 'applicant_intent', 'target_context'] = Field(
        description='experience_evidence: applicant facts; applicant_intent: personal wishes/motivation; target_context: company/role source information')
    target_experience_id: str | None = Field(default=None,
        description='Required selected Experience ID for experience_evidence; must be null for intent/context')
    reason: str = Field(min_length=1)
    importance: Literal['high', 'medium', 'low']
    question_proposal: str = ''

    @field_validator('category', mode='before')
    @classmethod
    def legacy_category(cls, value):
        # Saved offline v2 plans remain inspectable. New model-facing schema
        # exposes ONLY experience_evidence; v3 cache never reuses old plans.
        return 'experience_evidence' if value == 'applicant_evidence' else value

class RequirementCoverage(StrictModel):
    requirement: AskKey
    status: Literal['satisfied', 'partial', 'missing']
    evidence_ids: list[str] = Field(default_factory=list,
        description='Selected approved applicant facts supporting this requirement; empty for intent/context')
    reason: str = Field(min_length=1, description='Why existing material can or cannot reliably cover the requirement')
    blocking_missing_information: str = Field(default='',
        description='Actual essential missing material, not optional extra detail; empty when satisfied or merely improvable')

class QuestionAssignment(StrictModel):
    question_id: str
    primary_experience_ids: list[str] = Field(description='Explicit scope of ALL selected evidence. Multiple experiences allowed only when substantively necessary.')
    story_focus: str
    core_evidence_ids: list[str] = Field(default_factory=list, max_length=2,
        description='At most TWO individual approved IDs. Each element is ONE ID, never a joined string. Choose highest-value facts, not all facts.')
    supporting_evidence_ids: list[str] = Field(default_factory=list,
        description='Optional individual approved IDs within declared Experience scope. Additional useful facts go here, not concatenated into core.')
    result_evidence_ids: list[str] = Field(default_factory=list,
        description='Only active fact_type=result within primary_experience_ids. Action/implementation/verification are NOT results. Empty is valid.')
    missing_information: list[Gap] = Field(default_factory=list)
    rationale: str
    requirement_coverage: list[RequirementCoverage] = Field(default_factory=list,
        description='Assess every asks_for before proposing gaps. Historical offline plans may omit this field.')

class ApplicationPlan(StrictModel):
    assignments: list[QuestionAssignment]

class PlanningResult(StrictModel):
    plan: ApplicationPlan
    duplicate_story_warnings: list[list[str]] = Field(default_factory=list)
    next_question: Gap | None = None
