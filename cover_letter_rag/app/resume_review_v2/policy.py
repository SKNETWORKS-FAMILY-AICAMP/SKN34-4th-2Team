"""Authoritative v2 policy. Role prompts reference these definitions, not overrides."""

POLICY_VERSION = 'resume-policy-22-requirement-scope-review-state'
PRECEDENCE = (
    'Factual safety', 'Applicant provenance', 'Target-section fitness',
    'Evidence value', 'Writing quality', 'Length',
)
PRECEDENCE_POLICY = 'Decision priority (highest first):\n' + '\n'.join(
    f'{i}. {value}' for i, value in enumerate(PRECEDENCE, 1))

FACTUAL_POLICY = '''ApplicantEvidence != ApplicantIntent != TargetContext.
Use active approved ApplicantEvidence for past factual claims; use source-quoted
ApplicantIntent for user-stated motivation, values, goals and plans. Intent is not
past experience and must neither be discarded for lacking past evidence nor
converted into performed work. TargetContext supports only job/company statements,
never applicant facts or intentions. Do not invent applicant intent.
Never invent or distort experience, role, scope, technology, implementation,
decision rationale, outcome, number, duration, uncertainty or negation.
Resume text is editing context, not authority for uncited claims. A user assertion
is self-reported, not independently verified. Job/company requirements are target
context, never applicant evidence; relevance never establishes applicant experience.
A result/outcome may be a supported working feature, completed flow, resolved
error, comparison finding, insight or passed validation; a numerical KPI is not
required. Merely performing a check is not proof that it passed or improved.
Technology use, action performed, role owned and role led are distinct claims.
Use ownership/leadership/design wording only with explicit quote support for that
agency and scope; doing work or using a tool alone never establishes ownership.'''

EVIDENCE_POLICY = '''ApplicantEvidence selection roles (not an intent-selection algorithm):
core: selected high-value meaning that must remain visible, not separate mandatory
sentences. It may include the problem, contribution, technical decision or result.
supporting: optional clarification or implementation detail; unused support is not
a factual failure, including support extracted from the original resume.
preserved: narrowly selected active original meaning essential to identity, role,
central technical contribution or major result. Protect that meaning when editing;
it is not an include-all list, a literal quote obligation or a separate clause quota.
omitted: known but not approved for this revision; never use it to support claims.
The brief protects propositions established by its source_refs, not generated
semantic paraphrases or fact/intent labels. Read the approved quotes for actor,
performed stages, certainty, conditions, relations and results. Rhetorical roles
and grouping hints are not additional facts or one-sentence-per-meaning quotas.
Preserve factual truth and high-value evidence. Select, merge, compress or omit
other supported details according to the target section. Original sentence
structure and all original details are not preservation targets.'''

QUALITY_POLICY = '''Preserve semantic value, not wording. Follow the supplied
editorial brief, not a universal project outline.
Preserve the section's protected original meanings, allowing merging and compression.
In motivation retain stated reason, origin, supporting experience, job connection
and intended direction when present; experience summary is not a substitute.
In future plans retain stated adaptation/work understanding, contribution,
improvement and growth when present; technical keywords are not a substitute.
In projects keep meaningful implementation, decision and verification signal.
Avoid redundant ideas, filler, flat enumeration, report-like narration and routine
chronology. Compression must not erase a supported diagnosis, decision rationale,
verification or key result. Related evidence may share one dense sentence.
Representative technology collections may be compressed while retaining concrete
signal and relevant supported job-critical keywords; never replace them with a
content-free summary. Length alone, optional omission and restructured prose are
not quality failures. Retain useful reasoning detail even when it needs more space.'''

QUESTION_POLICY = '''The analysis call compares the original, answer history and
target context to discover useful information needs separately from the next
question. Retain worthwhile deferred needs and explicit review decisions; absent
review data means unreviewed, not sufficient. Ask at most one active clarification
per experience at a time whose editing benefit justifies effort. Empty slots are not questions.
The server checks ownership, source references and exact-repeat identity, and
exposes at most three questions across the resume. Semantic repetition and marginal
value are judged from meaning, not lexical similarity or a mandatory checklist.'''

PROJECT_POLICY = '''A project description is not merely a summary. Show the supported
problem and how it was recognized, the applicant's own work, technology/method,
technical judgment, verification and result or insight that best explain the
contribution. These are opportunities, not slots that must all be filled.
Edit the complete paragraph when evidence changes, rather than retaining its
sentence sequence and appending new facts. Organize related evidence together.
Give functionality and its directly supported verification one coherent passage:
when functionality is already explained, refer back to it for the check instead
of enumerating the same features a second time. Integrate a new verification into
the related implementation passage, not a closing recap of those same features.
Connect a judgment, comparison and finding when the sources establish that
relationship. Independent findings may stay independent.
Neither evidence order nor semantic-role order prescribes prose order. Do not
invent causality, chronology or a universal outline to make the paragraph flow.
Merge repetition without compressing away meaningful reasoning or design decisions.
Use enough sentences for that evidence; no fixed sentence count. Prefer performed
work and implementation-focused Korean resume prose over plans, tool inventories
or report filler. Omit low-value steps; do not omit valuable technical detail just
because it is implementation detail.'''

SECTION_RULES = {
    'project': PROJECT_POLICY,
    'career': 'Show supported role/scope, direct contribution and results. Do not impose project structure.',
    'self_intro': 'Answer the target self-introduction topic in its appropriate voice; no project sentence quota.',
    'motivation': 'Preserve supported why/origin/experience/job connection/direction; do not replace motivation with project summaries.',
    'future_plan': 'Preserve stated early adaptation/work understanding, contribution, improvement and long-term direction; keep future tense.',
    'strength_weakness': 'Preserve trait, evidence, impact, downside and mitigation when stated.',
    'challenge': 'Preserve supported challenge/cause/action/verification/lesson, not merely a tool list.',
    'growth': 'Preserve formative experience, value, behavioral change and supported relevance.',
    'education': 'Show supported learning and hands-on work, not invented employment or outcomes.',
    'activity': 'Show the supported activity role and contribution; do not force a result.',
    'other': 'Match the existing section purpose and express supported contribution without repetition.',
}

MAX_PROGRESSIVE_QUESTIONS = 3

# Planning priority only; no missing-slot obligations or inferred applicant facts.
PROJECT_TYPE_PRIORITY = {
    'machine_learning': ['purpose_or_problem', 'problem_observation', 'personal_role',
        'actions', 'validation_method', 'technical_decisions', 'outcome', 'technologies'],
    'data_analysis': ['purpose_or_problem', 'problem_observation', 'personal_role',
        'actions', 'validation_method', 'outcome', 'technical_decisions', 'technologies'],
    'software': ['purpose_or_problem', 'personal_role', 'actions', 'technical_decisions',
        'validation_method', 'outcome', 'technologies', 'problem_observation'],
}

REWRITE_POLICY = '''When a prior draft and validation issues are supplied, repair
those blockers using the same evidence roles, section policy and precedence as the
initial draft. Do not restore omitted or unused optional details to satisfy a
preservation quota. A prior draft is not evidence or approval of its unflagged parts.
Use rewrite_source_review to revisit the approved sources behind the brief's
protected meanings. Its prior_draft_coverage identifies meanings expressed in the
previous candidate; while repairing the reported defect, retain their supported
propositions or revise them only when the source or reported issue requires it.
Coverage metadata is not proof of correctness, a sentence template or a quota.
Repair the paragraph while keeping important action stages, decisions, conditions,
measurement subjects and results. A compressed label cannot replace a precise
source relation.
Re-ground any changed agency, outcome or causal connection against the same approved
quotes; keep claim tags consistent with the actual wording. Recheck the complete
draft, including possible omissions the first pass did not find. Never fix a prose
defect by inventing scope, promoting a test into success, or weakening core meaning.'''

SOURCE_POLICY = ('resume_text source_id is experience_id for current_text or a declared '
                 'resume_sources source_id; user_answer source_id is answer_source_id')
TARGET_POLICY = 'original_quote must equal current_text as an apply locator, not a prose-preservation instruction'
BATCH_POLICY = '''Process keyed items independently and return the same item keys.
Never transfer applicant evidence between experiences. shared_job_requirements,
shared_target_context and shared_allowed_target_context (when present) replace
only the corresponding target-context field for each item. Their requirement IDs
and quotes are unchanged; never treat shared context as applicant evidence.
When a field remains inside an item it belongs only to that item.'''

# Shared quality thresholds; none is a sentence-count or length rejection limit.
ENUMERATION_LIMIT = 5
REDUNDANCY_THRESHOLD = 0.84
REPORT_VERB_LIMIT = 3
CHRONOLOGY_LIMIT = 3
COPY_THRESHOLD = 0.83
DUPLICATION_THRESHOLD = 0.91
VERBOSITY_RATIO = 1.8
MIN_VERBOSITY_LENGTH = 180
REPRESENTATIVE_COLLECTION_MIN = 4
REPRESENTATIVE_SIGNAL_MIN = 2
