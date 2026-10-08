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


_PERFORMED_ACTION = re.compile(
    r'(?:직접\s*)?(?:구현|개발|작성|분석|처리|연동|구축|적용|호출|수행|제작)'
    r'(?:했|하였|한|하여|해서|했습니다|하였습니다|했다|한\s*경험)', re.I)


def merge_facets(active, previous, extracted, diagnostics=None):
    facets = {}
    for facet in [*previous, *extracted]:
        if facet.evidence_id not in active:
            continue
        if len(set(facet.slots)) != len(facet.slots):
            raise ContractError('duplicate profile slot')
        fact = active[facet.evidence_id]
        if fact.fact_type == FactType.TECHNOLOGY:
            extra = set(facet.slots) - {S.TECHNOLOGIES}
            # Facets are derived labels. Keep a sourced performed action, but
            # never promote a technology inventory into work or ownership.
            allowed={S.TECHNOLOGIES}
            if not fact.source_id.endswith(':techStack') and _PERFORMED_ACTION.search(fact.evidence_quote):
                allowed.add(S.ACTIONS)
            if extra - allowed and diagnostics is not None:
                diagnostics.append(dict(evidence_id=facet.evidence_id,
                    removed_slots=sorted(slot.value for slot in extra-allowed),
                    reason='technology_facet_without_performed_source'))
            facet=facet.model_copy(update={'slots':[slot for slot in facet.slots if slot in allowed] or [S.TECHNOLOGIES]})
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


def question_for_gap(experience_id, gap, evidence, experience_title=''):
    """Offline diagnostic suggestions only; live candidate=null never calls this."""
    from .models import QuestionNeed
    from .question_planning import render_question
    active = active_facts(evidence)
    basis = [eid for eid in gap.existing_evidence_ids if eid in active]
    suffix = hashlib.sha256('\n'.join(sorted(basis)).encode()).hexdigest()[:12] if basis else 'open'
    need = QuestionNeed(experience_id=experience_id, gap_type=gap.gap_type,
        target_slot=gap.target_slot, evidence_basis=basis, priority=gap.priority,
        why_needed=gap.why_needed, focus=gap.focus,
        dedupe_key=f'{experience_id}:{gap.target_slot.value}:{gap.focus}:{suffix}')
    presentation,issue=render_question(need,evidence)
    if issue:raise ContractError(issue)
    question = GapQuestion(**need.model_dump(),experience_title=experience_title,**presentation)
    validate_question(question,evidence)
    return question


def validate_question(question,evidence):
    """Same ID/neutral-body contract as live selection; no copied premise gate."""
    from .question_planning import question_approval_issue
    issue = question_approval_issue(question,evidence)
    if issue:
        raise ContractError(issue)


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
        candidates = sorted((eid for eid in getattr(profile, slot.value).evidence_ids if eid in material
            and not active[eid].source_id.endswith(':techStack')), key=score)
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
    # Selection makes sources available, not a writing decision. The validated
    # section meaning plan below decides whether there is an editing opportunity.
    can_write = bool(core or support)
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
    requirement_matches: object = None
    requirement_warnings: object = None
    question_selection: object = None
    semantic_preparation: object = None


def _discard_duplicate_future_facts(request, extraction, diagnostics):
    """Do not approve a future plan twice as a performed applicant fact.

    Recovery is limited to a source-validated active Intent with the same
    owning quote. Any downstream reference to the would-be fact remains a
    contract failure rather than silently changing the model's meaning graph.
    """
    from .section_semantics import validate_intents
    from .validation import is_explicit_intention
    if target_section(request.experience) != 'future_plan':
        return extraction
    candidates=[fact for fact in extraction.extracted_evidence
        if is_explicit_intention(fact.evidence_quote)
        or re.search(r'하겠습니다|되겠습니다|싶습니다|계획입니다|예정입니다', fact.evidence_quote)]
    if not candidates:
        return extraction
    try:
        intents=validate_intents(request,extraction.intent_claims)
    except ContractError:
        return extraction
    referenced={facet.evidence_id for facet in extraction.facets}
    referenced.update(ref.id for unit in extraction.semantic_units for ref in unit.source_refs
        if ref.type=='applicant_evidence')
    referenced.update(eid for match in extraction.requirement_matches or [] for eid in match.evidence_ids)
    if extraction.question is not None:
        referenced.update(extraction.question.evidence_basis)
    if extraction.question_review is not None:
        referenced.update(eid for row in extraction.question_review.items for eid in row.evidence_ids)
        referenced.update(eid for row in extraction.question_review.items if row.need
            for eid in row.need.evidence_basis)
    dropped=[]
    for fact in candidates:
        if fact.evidence_id in referenced:
            continue
        if any(claim.state in {AssertionState.RESUME_STATED,AssertionState.USER_ASSERTED}
                and claim.source_section_id==request.experience.experience_id
                and claim.source_type==fact.source_type and claim.source_id==fact.source_id
                and fact.evidence_quote==claim.evidence_quote for claim in intents.values()):
            dropped.append(fact.evidence_id)
    if not dropped:
        return extraction
    diagnostics['future_fact_recovery']=dict(dropped_fact_ids=dropped,
        reason='same_source_validated_applicant_intent')
    return extraction.model_copy(update={'extracted_evidence':[
        fact for fact in extraction.extracted_evidence if fact.evidence_id not in dropped]})


def prepare_review(request, extraction):
    if not isinstance(extraction, ExtractionOutput):
        raise ContractError('live extraction must not contain a revision plan')
    from .planning_state import reconcile_extraction
    reconciliation = {}
    try:
        extraction, replaced_semantics = reconcile_extraction(request, extraction, with_replacements=True, diagnostics=reconciliation)
    except ContractError as exc:
        normalized=getattr(exc,'reconciled_extraction',None)
        if normalized is not None:
            # Evidence IDs were already reconciled. An Intent/semantic duplicate
            # is a separate boundary; approve facts only through the real source
            # and correction validator, never through raw reconciliation.
            neutral=AnalystOutput(experience_id=normalized.experience_id,extracted_evidence=normalized.extracted_evidence,
                plan=RevisionPlan(objective='출처 검증',operation='no_change'))
            try:
                evidence,_=validate_analysis(request,neutral)
            except ContractError as source_error:
                source_error.diagnostics['derived_failure']=exc.diagnostics
                raise source_error
            exc.approved_evidence=evidence
            exc.approved_extracted=[evidence[f.evidence_id] for f in normalized.extracted_evidence]
        raise
    extraction = _discard_duplicate_future_facts(request, extraction, reconciliation)
    # Reuse existing source/state/correction validation without selecting anything.
    neutral = AnalystOutput(experience_id=extraction.experience_id,
        extracted_evidence=extraction.extracted_evidence,
        plan=RevisionPlan(objective='출처와 상태 검증', operation='no_change'))
    try:
        evidence, _ = validate_analysis(request, neutral)
    except ContractError as exc:
        if extraction.question is not None:
            exc.diagnostics['question_reference_normalization'] = reconciliation['question_references']
        raise
    try:
        return _prepare_validated(request,extraction,evidence,replaced_semantics,reconciliation)
    except ContractError as exc:
        # Facts have passed the common source/correction validation. A derived
        # facet/semantic failure must not erase them or authorize partial writing.
        exc.approved_evidence = {k:v.model_copy(deep=True) for k,v in evidence.items()}
        exc.approved_extracted = [evidence[f.evidence_id].model_copy(deep=True) for f in extraction.extracted_evidence]
        raise


def _prepare_validated(request,extraction,evidence,replaced_semantics,reconciliation):
    unknown = sorted({f.evidence_id for f in extraction.facets if f.evidence_id not in evidence})
    if unknown:
        raise ContractError('unknown profile evidence', {'phase':'facet_sources',
            'unknown_reference_ids':unknown, 'available_evidence_ids':sorted(evidence)})
    if len({f.evidence_id for f in extraction.facets}) != len(extraction.facets):
        raise ContractError('duplicate profile classification')
    active = active_facts(evidence)
    facet_repairs=[]
    facets = merge_facets(active, request.previous_facets, extraction.facets, facet_repairs)
    project = target_section(request.experience) == 'project'
    profile = build_profile(request.experience, evidence, facets) if project else None
    gaps = detect_gaps(profile, evidence, request.unavailable_slots) if project else []
    plan = select_evidence(request, profile, evidence, facets,
        [*request.previous_semantic_units, *extraction.semantic_units]) if project else RevisionPlan(objective='섹션 의미 보존', operation='no_change')
    from .section_semantics import prepare_section
    semantic_preparation = {'facet_repairs':facet_repairs} if facet_repairs else {}
    if reconciliation.get('future_fact_recovery'):
        semantic_preparation['future_fact_recovery']=reconciliation['future_fact_recovery']
    request, intents, section_profile, sentence_plan = prepare_section(request, extraction, evidence, plan,
        replaced_semantic_ids=replaced_semantics, diagnostics=semantic_preparation)
    from .question_planning import review_information
    questions,question_selection = review_information(request,extraction,evidence,gaps)
    if reconciliation.get('duplicate_rows'):
        semantic_preparation['duplicate_rows']=reconciliation['duplicate_rows']
    if extraction.question is not None:
        question_selection['reference_normalization'] = reconciliation['question_references']
    first = questions[0] if questions else None
    analysis = AnalystOutput(experience_id=request.experience.experience_id,
        extracted_evidence=[evidence[f.evidence_id] for f in extraction.extracted_evidence], plan=plan,
        question=QuestionProposal(question=first.question, missing_fact_type=SLOT_FACT_TYPE[first.target_slot],
            improvement_hypothesis=first.why_needed, dedupe_key=first.dedupe_key) if first else None)
    validate_analysis(request, analysis)  # One common approval contract for live/offline.
    from .requirement_matching import ground_matches
    matches, warnings = ground_matches(request, extraction.requirement_matches, evidence)
    return PreparedReview(analysis, evidence, profile, facets, gaps, questions,
                          request, intents, section_profile, sentence_plan, matches, warnings, question_selection, semantic_preparation)
