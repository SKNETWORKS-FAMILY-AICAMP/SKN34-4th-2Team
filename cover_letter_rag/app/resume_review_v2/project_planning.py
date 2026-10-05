"""Evidence-only projection, useful gaps, guarded questions and value selection.

No model/DB access. All inputs are validated applicant facts; job relevance can
rank an existing fact but cannot create a slot or a question presupposition.
"""
import hashlib
import re
from dataclasses import dataclass
from .models import (AnalystOutput, AssertionState, EvidenceFacet, EvidenceGap,
    ExtractionOutput, FactType, GapQuestion, OmittedEvidence, ProjectEvidenceProfile,
    ProjectSlot as S, QuestionPresupposition, QuestionProposal, RevisionPlan)
from .validation import ContractError, validate_analysis
from .policy import MAX_PROGRESSIVE_QUESTIONS, PROJECT_TYPE_PRIORITY
from .writing_policy import target_section


TYPE_SLOTS = {
    FactType.CONTEXT: [S.OVERVIEW], FactType.ROLE: [S.ROLE],
    FactType.SCOPE: [S.SCALE], FactType.DURATION: [S.SCALE],
    FactType.ACTION: [S.ACTIONS, S.ROLE], FactType.IMPLEMENTATION: [S.ACTIONS, S.ROLE],
    FactType.TECHNOLOGY: [S.TECHNOLOGIES], FactType.TECHNICAL_DECISION: [S.DECISIONS],
    FactType.VERIFICATION: [S.VALIDATION], FactType.RESULT: [S.OUTCOME],
}
SLOT_FACT_TYPE = {
    S.OVERVIEW: FactType.CONTEXT, S.PURPOSE: FactType.CONTEXT,
    S.OBSERVATION: FactType.CONTEXT, S.ROLE: FactType.ROLE,
    S.TECHNOLOGIES: FactType.TECHNOLOGY, S.ACTIONS: FactType.ACTION,
    S.DECISIONS: FactType.TECHNICAL_DECISION, S.VALIDATION: FactType.VERIFICATION,
    S.OUTCOME: FactType.RESULT, S.INSIGHT: FactType.RESULT, S.SCALE: FactType.SCOPE,
}


def active_facts(evidence):
    blocked = set()
    for fact in evidence.values():
        for other_id in fact.conflicts_with_evidence_ids:
            other = evidence.get(other_id)
            if other and other.assertion_state != AssertionState.SUPERSEDED:
                blocked.update([fact.evidence_id, other_id])
    return {eid: fact for eid, fact in evidence.items()
        if fact.assertion_state in {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}
        and eid not in blocked}


def merge_facets(active, previous, extracted):
    facets = {}
    for facet in [*previous, *extracted]:
        if facet.evidence_id not in active:
            continue
        if len(set(facet.slots)) != len(facet.slots):
            raise ContractError('duplicate profile slot')
        if active[facet.evidence_id].fact_type == FactType.TECHNOLOGY and set(facet.slots) - {S.TECHNOLOGIES}:
            raise ContractError('technology names cannot establish role/action/validation')
        facets[facet.evidence_id] = facet
    for eid, fact in active.items():
        if eid not in facets:
            facets[eid] = EvidenceFacet(evidence_id=eid, slots=TYPE_SLOTS[fact.fact_type])
    return list(facets.values())


def project_type(active):
    """Conservative planning label; no posting/title inference or persisted fact."""
    text = ' '.join(f.evidence_quote for f in active.values())
    if re.search(r'XGBoost|LightGBM|CatBoost|머신러닝|모델 학습|이탈 예측', text, re.I):
        return 'machine_learning'
    if re.search(r'RAG|LLM|챗봇|생성형|인공지능 서비스', text, re.I):
        return 'ai_service'
    front = bool(re.search(r'React|Vue|프론트엔드', text, re.I))
    back = bool(re.search(r'FastAPI|Django|백엔드|REST API', text, re.I))
    if front and back: return 'fullstack'
    if back: return 'backend'
    if front: return 'frontend'
    if re.search(r'ETL|파이프라인|데이터 엔지니어링', text, re.I): return 'data_engineering'
    if re.search(r'데이터 분석|통계 분석|탐색적 분석', text): return 'data_analysis'
    if any(f.fact_type in {FactType.ACTION, FactType.IMPLEMENTATION} for f in active.values()):
        return 'general_software'
    return 'unknown'


def build_profile(experience, evidence, facets=()):
    active = active_facts(evidence)
    resolved = merge_facets(active, [], facets)
    profile = ProjectEvidenceProfile(experience_id=experience.experience_id,
                                     project_type=project_type(active))
    for facet in resolved:
        for slot in facet.slots:
            getattr(profile, slot.value).evidence_ids.append(facet.evidence_id)
    return profile


def detect_gaps(profile, evidence, unavailable=()):
    active = active_facts(evidence)
    gaps = []
    blocked = set(unavailable)
    def ids(slot): return getattr(profile, slot.value).evidence_ids
    def add(slot, why, priority='HIGH', basis=(), focus='open'):
        if slot not in blocked:
            gaps.append(EvidenceGap(gap_type='clarification' if basis else 'missing',
                target_slot=slot, priority=priority, existing_evidence_ids=list(basis),
                why_needed=why, focus=focus))
    # Personal actions already answer "what did you do?". A missing role label
    # is not missing contribution, and this does not create an ownership claim.
    if ids(S.ACTIONS) and (ids(S.VALIDATION) or ids(S.OUTCOME)):
        return []
    if not ids(S.ROLE) and not ids(S.ACTIONS): add(S.ROLE, '팀 전체 작업과 구분되는 본인의 직접 기여를 확인합니다.')
    if ids(S.ROLE) and not ids(S.ACTIONS):
        add(S.ACTIONS, '확인된 역할에서 직접 구현·분석한 행동을 보여줍니다.')
    if not ids(S.PURPOSE) and not ids(S.OVERVIEW):
        add(S.PURPOSE, '프로젝트가 무엇을 해결하거나 분석했는지 확인합니다.')
    if not ids(S.VALIDATION) and not ids(S.OUTCOME):
        focus = {'machine_learning': 'model_evaluation', 'data_analysis': 'analysis_validation'}.get(profile.project_type, 'open')
        add(S.VALIDATION, '숫자를 강요하지 않고 구현·분석 결과를 확인한 방법을 찾습니다.', focus=focus)
    # A sufficient contribution need not complete every schema slot.
    sufficient = bool(ids(S.ROLE) and ids(S.ACTIONS) and (ids(S.PURPOSE) or ids(S.OVERVIEW))
                      and (ids(S.VALIDATION) or ids(S.OUTCOME)))
    if not sufficient:
        imbalance = [eid for eid, f in active.items() if re.search(r'불균형|imbalanc', f.normalized_fact, re.I)
                     and re.search(r'불균형|imbalanc', f.evidence_quote, re.I)]
        observed_basis = any(re.search(r'분포|비율|건수|집계|분석해서|비교해서', active[eid].normalized_fact)
                             for eid in ids(S.OBSERVATION))
        if imbalance and not observed_basis:
            add(S.OBSERVATION, '확인된 데이터 특성이 어떤 관찰에서 나왔는지 구체화합니다.',
                'MEDIUM', imbalance, 'observation_basis')
        compared = [eid for eid, f in active.items() if re.search(r'threshold|임계값', f.normalized_fact, re.I)
                    and f.fact_type in {FactType.ACTION, FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION, FactType.VERIFICATION}
                    and re.search(r'비교|조정|변경|바꿔|compare', f.normalized_fact, re.I)
                    and re.search(r'threshold|임계값', f.evidence_quote, re.I)
                    and re.search(r'비교|조정|변경|바꿔|compare', f.evidence_quote, re.I)]
        if compared and not ids(S.DECISIONS):
            add(S.DECISIONS, '이미 수행한 비교의 기준을 확인해 기술적 판단을 드러냅니다.',
                'MEDIUM', compared, 'comparison_basis')
        elif ids(S.ACTIONS) and not ids(S.DECISIONS):
            add(S.DECISIONS, '수행한 작업에서 의미 있는 방법 선택이 있었는지 확인합니다.', 'MEDIUM')
    # Clarifications use established facts and distinguish progressive stages.
    return sorted(gaps, key=lambda g: (0 if g.gap_type == 'clarification' else 1,
                                     0 if g.priority == 'HIGH' else 1))


OPEN_QUESTIONS = {
    S.ROLE: '프로젝트에서 본인이 직접 한 작업은 무엇인가요? 팀 작업이라면 다른 구성원의 작업과 구분해 알려주세요.',
    S.ACTIONS: '프로젝트에서 직접 구현하거나 분석한 핵심 작업은 무엇인가요?',
    S.PURPOSE: '이 프로젝트로 해결하거나 분석하려던 문제는 무엇인가요?',
    S.VALIDATION: '구현이나 분석 결과는 어떤 방법 또는 기준으로 확인했나요? 정량 수치가 없어도 괜찮습니다.',
    S.DECISIONS: '직접 수행한 작업 중 방법이나 구조를 선택할 때 고려한 점이 있다면 알려주세요.',
}
CLARIFICATION_QUESTIONS = {
    S.OBSERVATION: '클래스 불균형은 어떤 데이터나 분포를 보고 확인했나요?',
    S.DECISIONS: '이미 수행한 threshold 또는 임계값 비교는 어떤 기준으로 진행했고, 확인한 결과가 있다면 무엇인가요?',
}
TYPE_QUESTIONS = {
    'model_evaluation': '모델 성능을 평가한 적이 있나요? 있다면 어떤 기준이나 지표를 사용했나요? 정량 수치가 없어도 괜찮습니다.',
    'analysis_validation': '분석 결과나 발견한 패턴은 어떤 방법 또는 기준으로 확인했나요?',
}


def question_for_gap(experience_id, gap, evidence, experience_title=''):
    active = active_facts(evidence)
    basis = [eid for eid in gap.existing_evidence_ids if eid in active]
    if gap.gap_type == 'clarification' and not basis:
        raise ContractError('question premise has no active applicant evidence')
    premises = [QuestionPresupposition(fact=active[eid].normalized_fact, evidence_ids=[eid]) for eid in basis]
    if gap.focus == 'observation_basis':
        if not any(re.search(r'불균형|imbalanc', active[eid].normalized_fact, re.I) for eid in basis):
            raise ContractError('unbacked imbalance premise')
        text = CLARIFICATION_QUESTIONS[S.OBSERVATION]
    elif gap.focus == 'comparison_basis':
        if not any(re.search(r'threshold|임계값', active[eid].normalized_fact, re.I)
                   and re.search(r'비교|조정|변경|바꿔|compare', active[eid].normalized_fact, re.I) for eid in basis):
            raise ContractError('unbacked threshold comparison premise')
        text = CLARIFICATION_QUESTIONS[S.DECISIONS]
    else:
        text = TYPE_QUESTIONS.get(gap.focus) or OPEN_QUESTIONS[gap.target_slot]
    fingerprint = '\n'.join(sorted(p.fact for p in premises))
    suffix = hashlib.sha256(fingerprint.encode()).hexdigest()[:12] if premises else 'open'
    question = GapQuestion(experience_id=experience_id, experience_title=experience_title,
        question=text, gap_type=gap.gap_type, target_slot=gap.target_slot,
        evidence_basis=basis, priority=gap.priority, why_needed=gap.why_needed,
        presuppositions=premises, focus=gap.focus,
        dedupe_key=f'{experience_id}:{gap.target_slot.value}:{gap.focus}:{suffix}')
    validate_question(question, evidence)
    return question


def validate_question(question, evidence):
    """No freely generated text: both premises AND wording must match safe builder."""
    active = active_facts(evidence)
    if any(f.experience_id != question.experience_id for f in evidence.values()):
        raise ContractError('question experience does not match evidence')
    for premise in question.presuppositions:
        if not premise.evidence_ids or any(eid not in active for eid in premise.evidence_ids):
            raise ContractError('unsupported question presupposition')
        if not any(premise.fact == active[eid].normalized_fact for eid in premise.evidence_ids):
            raise ContractError('question presupposition does not match evidence')
    if any(eid not in active for eid in question.evidence_basis):
        raise ContractError('unapproved question evidence')
    if question.gap_type == 'missing':
        allowed = TYPE_QUESTIONS.get(question.focus) or OPEN_QUESTIONS.get(question.target_slot)
        if question.presuppositions or question.evidence_basis or question.question != allowed:
            raise ContractError('open gap question must not introduce premises')
        expected_type = {'model_evaluation': 'machine_learning', 'analysis_validation': 'data_analysis'}.get(question.focus)
        if expected_type and (question.target_slot != S.VALIDATION or project_type(active) != expected_type):
            raise ContractError('type-specific question has no applicant planning basis')
    elif not question.presuppositions:
        raise ContractError('clarification requires supported premises')
    else:
        if question.question != CLARIFICATION_QUESTIONS.get(question.target_slot):
            raise ContractError('question wording contains unvalidated premises')
        pattern = r'불균형|imbalanc' if question.target_slot == S.OBSERVATION else r'threshold|임계값'
        if not any(re.search(pattern, p.fact, re.I) for p in question.presuppositions):
            raise ContractError('unsupported clarification subject')
        for premise in question.presuppositions:
            if not any(re.search(pattern, active[eid].evidence_quote, re.I) for eid in premise.evidence_ids):
                raise ContractError('question subject absent from source quote')
        if question.target_slot == S.DECISIONS and not any(
                re.search(r'비교|조정|변경|바꿔|compare', active[eid].evidence_quote, re.I)
                and active[eid].fact_type in {FactType.ACTION, FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION, FactType.VERIFICATION}
                for eid in question.evidence_basis):
            raise ContractError('comparison absent from source quote')
    return question


def plan_questions(experience_id, gaps, evidence, previous_keys=(), experience_title=''):
    questions = []
    for gap in gaps:
        question = question_for_gap(experience_id, gap, evidence, experience_title)
        if question.dedupe_key not in previous_keys:
            questions.append(question)
        if len(questions) == MAX_PROGRESSIVE_QUESTIONS:
            break
    return questions


def select_evidence(request, profile, evidence, facets, semantic_units=()):
    active = active_facts(evidence)
    material = {f.evidence_id for f in facets if f.material}
    def score(eid):
        text = active[eid].normalized_fact.casefold()
        # Relevance ranks only existing facts; must/preferred aren't blanket scores.
        relevance = sum(bool(set(re.findall(r'[\w-]+', r.text.casefold())) & set(re.findall(r'[\w-]+', text)))
                        for r in request.job_requirements)
        # IDs are identity, not editorial ranking. Tie-break by source content.
        concrete = active[eid].fact_type in {FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION, FactType.VERIFICATION}
        return (-relevance, -int(concrete), active[eid].evidence_quote, active[eid].normalized_fact)
    core, support = [], []
    core_slots = [S(slot) for slot in PROJECT_TYPE_PRIORITY.get(profile.project_type, PROJECT_TYPE_PRIORITY['software'])]
    if not profile.outcome.evidence_ids:
        core_slots.append(S.INSIGHT)
    for slot in core_slots:
        candidates = sorted((eid for eid in getattr(profile, slot.value).evidence_ids if eid in material), key=score)
        if candidates and not any(eid in core for eid in candidates):
            core.append(candidates[0])
        support.extend(eid for eid in candidates if eid not in core)
    core = list(dict.fromkeys(core))
    # Overview, constraints and a secondary insight provide context, not a slot
    # quota. Even a populated profile does not make every slot mandatory prose.
    for slot in (S.OVERVIEW, S.SCALE, S.INSIGHT):
        contextual = sorted((eid for eid in getattr(profile, slot.value).evidence_ids if eid in material), key=score)
        support.extend(contextual[:1])
    support = [eid for eid in dict.fromkeys(support) if eid not in core]
    # Availability is not an inclusion quota. Keep material sources available to
    # the meaning plan without promoting every decision/check to mandatory prose.
    support.extend(eid for eid in active if eid in material and eid not in {*core, *support})
    # Semantic duplicates are not another mandatory meaning; lexical normalization
    # only deduplicates identical assertions, never substitutes one fact for another.
    seen, selected = set(), []
    for eid in core:
        key = re.sub(r'\W+', '', active[eid].normalized_fact).casefold()
        if key not in seen:
            selected.append(eid)
            seen.add(key)
    core = selected
    identity = set(profile.overview.evidence_ids) if not profile.purpose_or_problem.evidence_ids else set()
    preserved = [eid for eid in [*core, *support] if active[eid].source_type == 'resume_text'
                 and active[eid].source_id == request.experience.experience_id
                 and (eid in core or eid in identity)]
    # An explicitly extracted action meaning can describe performed work even
    # when its atomic source received a different taxonomy label. Source quote
    # validation and independent entailment review still decide its truth.
    action_meaning = any(u.semantic_role in {'action', 'actions'} and any(
        r.type == 'applicant_evidence' and r.id in active for r in u.source_refs)
        for u in semantic_units)
    can_write = bool(core and (profile.actions.evidence_ids or action_meaning or target_section(request.experience) != 'project'))
    return RevisionPlan(objective='근거 있는 핵심 기여·기술적 판단·검증을 보여주는 제출 문장',
        operation='replace_field' if can_write else 'no_change', core_evidence_ids=core if can_write else [],
        supporting_evidence_ids=support if can_write else [], preserved_evidence_ids=preserved if can_write else [],
        omitted_evidence=[OmittedEvidence(evidence_id=eid, reason='비활성·중복 또는 이번 섹션의 낮은 정보 가치')
                          for eid in evidence if not can_write or eid not in {*core, *support, *preserved}])


@dataclass
class PreparedReview:
    analysis: AnalystOutput
    evidence: dict
    profile: ProjectEvidenceProfile
    facets: list
    gaps: list
    questions: list
    request: object
    intents: list
    section_profile: object
    sentence_plan: object


def prepare_review(request, extraction):
    if not isinstance(extraction, ExtractionOutput):
        raise ContractError('live extraction must not contain a revision plan')
    from .planning_state import reconcile_extraction
    extraction = reconcile_extraction(request, extraction)
    # Reuse existing source/state/correction validation without selecting anything.
    neutral = AnalystOutput(experience_id=extraction.experience_id,
        extracted_evidence=extraction.extracted_evidence,
        plan=RevisionPlan(objective='출처와 상태 검증', operation='no_change'))
    evidence, _ = validate_analysis(request, neutral)
    if any(f.evidence_id not in evidence for f in extraction.facets):
        raise ContractError('unknown profile evidence')
    if len({f.evidence_id for f in extraction.facets}) != len(extraction.facets):
        raise ContractError('duplicate profile classification')
    active = active_facts(evidence)
    facets = merge_facets(active, request.previous_facets, extraction.facets)
    project = target_section(request.experience) == 'project'
    profile = build_profile(request.experience, evidence, facets) if project else None
    gaps = detect_gaps(profile, evidence, request.unavailable_slots) if project else []
    plan = select_evidence(request, profile, evidence, facets,
        [*request.previous_semantic_units, *extraction.semantic_units]) if project else RevisionPlan(objective='섹션 의미 보존', operation='no_change')
    from .section_semantics import prepare_section
    request, intents, section_profile, sentence_plan = prepare_section(request, extraction, evidence, plan)
    from .question_planning import select_question
    questions = select_question(request, extraction.question, evidence)
    first = questions[0] if questions else None
    analysis = AnalystOutput(experience_id=request.experience.experience_id,
        extracted_evidence=[evidence[f.evidence_id] for f in extraction.extracted_evidence], plan=plan,
        question=QuestionProposal(question=first.question, missing_fact_type=SLOT_FACT_TYPE[first.target_slot],
            improvement_hypothesis=first.why_needed, dedupe_key=first.dedupe_key) if first else None)
    validate_analysis(request, analysis)  # One common approval contract for live/offline.
    return PreparedReview(analysis, evidence, profile, facets, gaps, questions,
                          request, intents, section_profile, sentence_plan)
