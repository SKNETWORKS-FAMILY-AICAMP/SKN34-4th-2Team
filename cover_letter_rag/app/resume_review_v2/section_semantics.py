"""Runtime source separation and section meaning plans. No persistence or I/O."""
import re
from .models import (ApplicantIntentClaim, AssertionState, ClaimType, FactType,
    SectionContract, SectionSemanticProfile, SemanticUnit, SentencePlan,
    SentencePlanItem, SourceRef)

CONTRACTS = {
    'project': ('문제 해결과 기술적 실행', ['purpose', 'observation', 'role', 'action', 'technology', 'decision', 'validation', 'outcome']),
    'motivation': ('지원 이유·형성 배경·근거·직무 연결·향후 방향',
        ['motivation', 'motivation_origin', 'supporting_experience', 'job_connection', 'intended_contribution']),
    'future_plan': ('입사 초기 적응·업무 이해·단기 기여·개선·장기 성장',
        ['early_adaptation', 'work_understanding', 'short_term_contribution', 'improvement_plan', 'long_term_direction']),
    'strength_weakness': ('특성과 근거·영향·한계·보완 행동', ['trait', 'concrete_evidence', 'positive_impact', 'downside', 'mitigation']),
    'challenge': ('도전·원인·행동·검증·배움', ['challenge', 'cause', 'action', 'validation', 'lesson']),
    'growth': ('형성 경험·가치·행동 변화·현재 연결', ['formative_experience', 'value', 'behavior_change', 'job_relevance']),
    'self_intro': ('정체성·강점·근거·직무 관련성·방향', ['identity', 'strength', 'evidence', 'job_relevance', 'direction']),
    'career': ('역할·직접 기여·성과', ['role', 'action', 'outcome']),
    'education': ('학습·실습·확인된 변화', ['learning', 'action', 'outcome']),
    'activity': ('활동 역할·기여', ['role', 'action', 'outcome']),
    'other': ('해당 문서 목적과 확인된 의미', ['identity', 'evidence', 'direction']),
}
INTENT_ROLE = {
    'motivation': 'motivation', 'job_interest': 'job_connection', 'company_interest': 'job_connection',
    'short_term_plan': 'early_adaptation', 'learning_plan': 'work_understanding',
    'contribution_plan': 'short_term_contribution', 'improvement_goal': 'improvement_plan',
    'long_term_goal': 'long_term_direction', 'career_direction': 'direction', 'work_value': 'value',
}
FACT_ROLE = {
    FactType.CONTEXT: 'purpose', FactType.ROLE: 'role', FactType.ACTION: 'action',
    FactType.IMPLEMENTATION: 'action', FactType.TECHNOLOGY: 'technology',
    FactType.TECHNICAL_DECISION: 'decision', FactType.VERIFICATION: 'validation',
    FactType.RESULT: 'outcome', FactType.SCOPE: 'scale', FactType.DURATION: 'scale',
}
CLAIM_TYPES = {
    FactType.TECHNOLOGY: ClaimType.TECHNOLOGY, FactType.ACTION: ClaimType.ACTION,
    FactType.IMPLEMENTATION: ClaimType.ACTION, FactType.ROLE: ClaimType.OWNERSHIP,
    FactType.TECHNICAL_DECISION: ClaimType.DECISION, FactType.VERIFICATION: ClaimType.VALIDATION,
    FactType.RESULT: ClaimType.OUTCOME, FactType.CONTEXT: ClaimType.OBSERVATION,
    FactType.SCOPE: ClaimType.SCALE, FactType.DURATION: ClaimType.SCALE,
}
ACTIVE = {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}


def section_contract(section):
    objective, roles = CONTRACTS[section]
    return SectionContract(section_type=section, objective=objective, high_value_semantics=roles)


def validate_intents(request, extracted):
    from .validation import ContractError, _exact_source_quote
    sources = {s.source_id: s.text for s in request.resume_sources}
    sources[request.experience.experience_id] = request.experience.current_text
    claims = {}
    new_ids = {c.id for c in extracted}
    for original in [*request.existing_intents, *extracted]:
        c = original.model_copy(deep=True)
        # The exact owning field path is an unambiguous alias, never another
        # section's ID. Normalize only fresh model output; persisted identity is strict.
        if c.id in new_ids and c.source_section_id == request.experience.field_path:
            c.source_section_id = request.experience.experience_id
        if c.source_section_id != request.experience.experience_id or c.id in claims:
            raise ContractError('cross-section or duplicate intent')
        if c.id in new_ids:
            source = sources.get(c.source_id) if c.source_type == 'resume_text' else (
                request.answer if c.source_id == request.answer_source_id else None)
            if source is None or not _exact_source_quote(source, c.evidence_quote):
                raise ContractError('intent quote absent from source')
        claims[c.id] = c
    if len({c.id for c in extracted}) != len(extracted):
        raise ContractError('duplicate extracted intent')
    for c in claims.values():
        for old_id in c.supersedes_intent_ids:
            if (c.source_type != 'user_answer' or c.state != AssertionState.USER_ASSERTED
                    or old_id not in claims or old_id == c.id):
                raise ContractError('invalid intent correction')
            claims[old_id].state = AssertionState.SUPERSEDED
    return claims


def prepare_section(request, extraction, evidence, revision_plan):
    from .validation import ContractError
    from .project_planning import active_facts, merge_facets
    from .writing_policy import target_section
    section = target_section(request.experience)
    contract = section_contract(section)
    intents = validate_intents(request, extraction.intent_claims)
    active_intents = {cid: c for cid, c in intents.items() if c.state in ACTIVE}
    active = active_facts(evidence)
    if set(active) & set(intents):
        raise ContractError('Evidence and Intent IDs must be distinct')
    target = {r.requirement_id for r in request.job_requirements if r.posting_quote.strip()}
    units = {}
    for unit, is_new in [(u, False) for u in request.previous_semantic_units] + [(u, True) for u in extraction.semantic_units]:
        unit = unit.model_copy(deep=True)
        # Profile facets and rhetorical roles previously used conflicting names.
        # These are labels, not new claims: sources remain strictly validated below.
        unit.semantic_role = {
            'overview': 'purpose', 'purpose_or_problem': 'purpose',
            'problem_observation': 'observation', 'personal_role': 'role',
            'technologies': 'technology', 'actions': 'action',
            'technical_decisions': 'decision', 'validation_method': 'validation',
            'insight_or_learning': 'learning', 'scale_or_constraints': 'scale',
        }.get(unit.semantic_role, unit.semantic_role)
        if unit.id in units:
            if is_new:
                raise ContractError('duplicate semantic unit')
            continue
        valid = True
        for ref in unit.source_refs:
            pool = {'applicant_evidence': active, 'applicant_intent': active_intents, 'target_context': target}[ref.type]
            if ref.id not in pool:
                # A superseded prior unit loses protection, not its replacement.
                if not is_new:
                    valid = False
                    break
                raise ContractError('semantic unit has unapproved source')
        if valid:
            # An unfamiliar editorial label is optional metadata. It cannot
            # authorize a source, nor should it invalidate otherwise valid facts.
            if all(r.type == 'target_context' for r in unit.source_refs) and unit.semantic_role in {
                    'motivation', 'early_adaptation', 'short_term_contribution', 'long_term_direction', 'intended_contribution', 'direction'}:
                raise ContractError('target context cannot establish applicant intent')
            if unit.semantic_role in {'motivation', 'early_adaptation', 'work_understanding',
                    'short_term_contribution', 'improvement_plan', 'long_term_direction', 'intended_contribution', 'direction'}:
                if not any(r.type == 'applicant_intent' for r in unit.source_refs):
                    raise ContractError('intent semantic unit requires ApplicantIntent')
            units[unit.id] = unit
    # Migration-free compatibility for atomic facts. Protected section intents
    # always get their own unit; a missing extractor unit cannot silently erase it.
    for cid, claim in active_intents.items():
        if not any(any(r.type == 'applicant_intent' and r.id == cid for r in u.source_refs) for u in units.values()):
            role = INTENT_ROLE[claim.intent_type]
            if section == 'motivation' and role in {'short_term_contribution', 'long_term_direction', 'direction'}:
                role = 'intended_contribution'
            if role not in contract.high_value_semantics:
                role = 'direction' if section in {'self_intro', 'other'} else contract.high_value_semantics[0]
            units['intent:' + cid] = SemanticUnit(id='intent:' + cid, semantic_role=role,
                meaning=claim.text, source_refs=[SourceRef(type='applicant_intent', id=cid)])
    approved = set(revision_plan.core_evidence_ids + revision_plan.supporting_evidence_ids + revision_plan.preserved_evidence_ids)
    if section != 'project':
        # Meaning hierarchy is section-specific: no project slot selection leaks in.
        approved = set(active)
        revision_plan.core_evidence_ids = []
        revision_plan.supporting_evidence_ids = list(active)
        revision_plan.preserved_evidence_ids = []
        revision_plan.omitted_evidence = [o for o in revision_plan.omitted_evidence if o.evidence_id not in active]
        revision_plan.operation = 'replace_field' if active or active_intents else 'no_change'
    for eid, fact in active.items():
        if eid not in approved or any(any(r.type == 'applicant_evidence' and r.id == eid for r in u.source_refs) for u in units.values()):
            continue
        role = FACT_ROLE[fact.fact_type]
        if section == 'motivation' and fact.fact_type != FactType.TECHNOLOGY: role = 'supporting_experience'
        elif section != 'project' and fact.fact_type == FactType.TECHNOLOGY: role = 'technology'
        elif section not in {'project', 'career', 'education', 'activity', 'challenge'}: role = 'evidence' if section == 'self_intro' else 'concrete_evidence' if section == 'strength_weakness' else 'formative_experience' if section == 'growth' else 'identity'
        units['fact:' + eid] = SemanticUnit(id='fact:' + eid, semantic_role=role,
            meaning=fact.normalized_fact, source_refs=[SourceRef(type='applicant_evidence', id=eid)])
    selected = [u for u in units.values() if all(r.type != 'applicant_evidence' or r.id in approved for r in u.source_refs)]
    explicit_meanings = {u.id for u in extraction.semantic_units} | {u.id for u in request.previous_semantic_units}
    material_ids = {f.evidence_id for f in merge_facets(active, request.previous_facets, extraction.facets) if f.material}
    required = [u.id for u in selected if u.semantic_role in contract.high_value_semantics
                and not (section == 'motivation' and u.semantic_role == 'supporting_experience')
                and (section != 'project' or (
                    any(r.type == 'applicant_evidence' and r.id in revision_plan.core_evidence_ids + revision_plan.preserved_evidence_ids for r in u.source_refs)
                    or (u.id in explicit_meanings and u.semantic_role in {'purpose', 'observation', 'action', 'decision', 'validation', 'outcome'}
                        and any(r.type == 'applicant_evidence' and r.id in material_ids for r in u.source_refs))))]
    profile = SectionSemanticProfile(section_type=section, original_semantic_units=selected,
        evidence_claim_ids=list(approved), intent_claim_ids=list(active_intents), target_context_ids=sorted(target),
        required_semantics=required, protected_semantics=required,
        optional_semantics=[u.id for u in selected if u.id not in required])
    groups = {}
    for u in selected:
        groups.setdefault(u.semantic_role, []).append(u)
    items = [SentencePlanItem(plan_id=f'{request.experience.experience_id}:{role}', purpose=role,
        semantic_unit_ids=[u.id for u in group], source_refs=list({(r.type, r.id): r for u in group for r in u.source_refs}.values()))
        for role, group in groups.items()]
    order = {role: index for index, role in enumerate(contract.high_value_semantics)}
    items.sort(key=lambda i: order.get(i.purpose, len(order)))
    sentence_plan = SentencePlan(section_type=section, items=items)
    updated = request.model_copy(update={'section_profile': profile, 'sentence_plan': sentence_plan,
        'approved_intents': list(active_intents.values())})
    return updated, list(intents.values()), profile, sentence_plan


def editorial_brief(request):
    """One derived writing contract; legacy plans remain diagnostic-only.

    Protect the argument, not every example. A supporting group requires some
    relevant support, not every project name or every cited fact in that group.
    """
    from .writing_policy import target_section
    section = target_section(request.experience)
    profile = request.section_profile
    units = profile.original_semantic_units if profile else []
    required = set(profile.required_semantics) if profile else set()
    return {
        'section': section,
        'objective': section_contract(section).objective,
        'must_express': [u.model_dump(mode='json') for u in units if u.id in required],
        'optional_support': [u.model_dump(mode='json') for u in units if u.id not in required],
        'support_required': section == 'motivation' and any(u.semantic_role == 'supporting_experience' for u in units),
    }


def verification_sources(request, plan, permitted, used_ids):
    """Keep the brief's citation basis available even when a draft omits it."""
    profile = request.section_profile
    required_ids = {ref.id for unit in profile.original_semantic_units
                    if unit.id in profile.required_semantics for ref in unit.source_refs
                    if ref.type == 'applicant_evidence'} if profile else set()
    needed = set(used_ids) | required_ids | set(plan.core_evidence_ids) | set(plan.preserved_evidence_ids)
    return [e for e in permitted if e.evidence_id in needed]


# Verb detection is a conservative candidate gate; semantic scope is also checked
# against cited quote by the verifier. Merely citing technology is never ownership.
OWNED = r'맡(?:았|아|는|고|은)|담당|책임'
LED = r'주도|리드|총괄'
DESIGNED = r'설계'


def agency_issues(sentence, facts, intents=()):
    from .models import ValidationIssue
    cited = [facts[eid] for eid in sentence.evidence_ids if eid in facts]
    issues = []
    # Pure, cited future intentions are checked against intent quotes by the
    # semantic verifier. A future leadership goal is not past leadership.
    intent_ids = {c.id for c in intents}
    pure_intent = (not sentence.evidence_ids and bool(set(sentence.intent_ids) & intent_ids)
                   and set(sentence.claim_types) <= {ClaimType.PLAN, ClaimType.MOTIVATION})
    if pure_intent:
        return issues
    for pattern, kind in [(OWNED, ClaimType.OWNERSHIP), (LED, ClaimType.LEADERSHIP), (DESIGNED, ClaimType.DECISION)]:
        # Choosing an evaluation criterion is a decision, not necessarily a
        # design claim. Only actual design wording needs the design-word gate;
        # ordinary decision entailment remains the independent verifier's job.
        if pattern == DESIGNED and not re.search(pattern, sentence.text):
            continue
        asserted = bool(re.search(pattern, sentence.text)) or kind in sentence.claim_types
        if not asserted:
            continue
        if pattern == DESIGNED:
            supported = any(re.search(pattern, f.evidence_quote) for f in cited)
        else:
            supported = any(re.search(pattern, f.evidence_quote) for f in cited)
        if not supported:
            issues.append(ValidationIssue(code='unsupported_agency', detail=f'{kind.value}: {sentence.text}'))
    return issues
