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

# Rhetorical labels are an index, never evidence. Unknown/compound labels are
# resolved from approved source claims rather than a growing string alias list.
def canonical_role(role, refs, active, intents, contract, facets):
    if role in contract.high_value_semantics or (contract.section_type != 'project' and role in {'technology', 'evidence', 'identity', 'scale', 'learning', 'concrete_evidence'}):
        return role
    candidates = set()
    slot_roles = {'overview':'purpose', 'purpose_or_problem':'purpose', 'problem_observation':'observation',
        'personal_role':'role', 'actions':'action', 'technologies':'technology',
        'technical_decisions':'decision', 'validation_method':'validation', 'outcome':'outcome',
        'insight_or_learning':'learning', 'scale_or_constraints':'scale'}
    for ref in refs:
        if ref.type == 'applicant_evidence' and ref.id in active:
            fact = active[ref.id]
            candidates.add(FACT_ROLE[fact.fact_type])
            for facet in facets:
                if facet.evidence_id == ref.id:
                    candidates.update(slot_roles[str(slot)] for slot in facet.slots)
        elif ref.type == 'applicant_intent' and ref.id in intents:
            candidates.add(INTENT_ROLE[intents[ref.id].intent_type])
    # Do not coerce unknown source-less/Job meanings into applicant action.
    return next((r for r in contract.high_value_semantics if r in candidates), 'evidence')
CLAIM_TYPES = {
    FactType.TECHNOLOGY: ClaimType.TECHNOLOGY, FactType.ACTION: ClaimType.ACTION,
    FactType.IMPLEMENTATION: ClaimType.ACTION, FactType.ROLE: ClaimType.OWNERSHIP,
    FactType.TECHNICAL_DECISION: ClaimType.DECISION, FactType.VERIFICATION: ClaimType.VALIDATION,
    FactType.RESULT: ClaimType.OUTCOME, FactType.CONTEXT: ClaimType.OBSERVATION,
    FactType.SCOPE: ClaimType.SCALE, FactType.DURATION: ClaimType.SCALE,
}
ACTIVE = {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}


def _supported_optional_detail(detail, quotes):
    """Accept exact excerpts or an inventory of exact source terms only."""
    if not detail.strip():
        return False
    if any(detail in quote for quote in quotes):
        return True
    parts = [part.strip() for part in detail.split(',')]
    if len(parts) < 2 or any(not part for part in parts):
        return False
    return all(any(re.search(r'(?<![A-Za-z0-9_])' + re.escape(part) +
                             r'(?![A-Za-z0-9_])', quote) for quote in quotes)
               for part in parts)

# Explicit source-language relations, not tool names or chronology alone.
GROWTH_TRANSITION = re.compile(r'시작(?:해|하여|해서).*?까지.*?(?:경험|확장|넓)|(?:범위|영역|관점).*?(?:넓|확장|전환)')
FORMATION = re.compile(r'(?:하면서|하며|통해|바탕으로|계기로).*?(?:배웠|깨달|알게|관점.{0,20}형성(?:했|하였))', re.S)


def section_contract(section):
    objective, roles = CONTRACTS[section]
    return SectionContract(section_type=section, objective=objective, high_value_semantics=roles)


def validate_intents(request, extracted):
    from .validation import ContractError, _exact_source_quote
    sources = request.factual_resume_sources()
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


def coverage_context_refs(request, unit, evidence):
    """Structural/source permission only, never a semantic redundancy verdict."""
    from .project_planning import active_facts
    from .validation import ContractError
    active = active_facts(evidence)
    refs = {(r.type,r.id) for r in unit.source_refs}
    context = {(r.type,r.id) for r in unit.context_source_refs}
    essential = refs - context
    if context and (len(context) != len(unit.context_source_refs) or not context < refs
            or any(typ != 'applicant_evidence' or eid not in active
                   or active[eid].experience_id != request.experience.experience_id
                   or active[eid].source_type != 'resume_text'
                   or active[eid].source_id != request.experience.experience_id
                   or active[eid].evidence_quote not in request.factual_resume_sources()[request.experience.experience_id] for typ,eid in context)
            or not any(typ == 'applicant_evidence' and eid in active
                       and active[eid].experience_id == request.experience.experience_id
                       and active[eid].source_type == 'user_answer' for typ,eid in essential)):
        raise ContractError('invalid contextual semantic reference',
            {'phase':'semantic_sources','semantic_unit_id':unit.id,'reference_category':'invalid_context_reference'})
    return context


def prepare_section(request, extraction, evidence, revision_plan, replaced_semantic_ids=(), diagnostics=None):
    from .validation import ContractError
    from .project_planning import _PERFORMED_ACTION, active_facts, merge_facets
    from .writing_policy import target_section
    section = target_section(request.experience)
    contract = section_contract(section)
    intents = validate_intents(request, extraction.intent_claims)
    active_intents = {cid: c for cid, c in intents.items() if c.state in ACTIVE}
    active = active_facts(evidence)
    facets = merge_facets(active, request.previous_facets, extraction.facets)
    if set(active) & set(intents):
        raise ContractError('Evidence and Intent IDs must be distinct')
    target = {r.requirement_id for r in request.job_requirements if r.posting_quote.strip()}
    known = {'applicant_evidence': evidence, 'applicant_intent': intents,
             'target_context': {r.requirement_id:r for r in request.job_requirements}}
    excluded, restored = [], []
    if diagnostics is not None:
        diagnostics.update(excluded_units=excluded, restored_atomic_units=restored)
    units = {}
    seen_unit_ids = set()
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
        if unit.id in seen_unit_ids:
            if is_new:
                raise ContractError('duplicate semantic unit')
            continue
        seen_unit_ids.add(unit.id)
        valid = True
        rejected_refs = []
        for ref in unit.source_refs:
            pool = {'applicant_evidence': active, 'applicant_intent': active_intents, 'target_context': target}[ref.type]
            if ref.id not in pool:
                source = known[ref.type].get(ref.id)
                if source is not None and ref.type != 'target_context':
                    # validate_analysis/validate_intents already checked owning
                    # scope and exact quotes. Inactive is not missing or usable.
                    rejected_refs.append(dict(type=ref.type, id=ref.id,
                        category='inactive_evidence' if ref.type == 'applicant_evidence' else 'inactive_intent',
                        **({'assertion_state':source.assertion_state.value,
                            'inactive_reason':'unresolved_conflict' if source.assertion_state in ACTIVE else 'assertion_state',
                            'conflict_ids':source.conflicts_with_evidence_ids} if ref.type == 'applicant_evidence' else {})))
                    valid = False
                    continue  # Check ALL refs: inactivity must not hide a missing ID.
                # A superseded prior unit loses protection, not its replacement.
                if not is_new:
                    rejected_refs.append(dict(type=ref.type, id=ref.id, category='missing_prior_reference'))
                    valid = False
                    continue
                raise ContractError('semantic unit has unapproved source', {'phase':'semantic_sources',
                    'semantic_unit_id':unit.id, 'source_type':ref.type, 'unknown_reference_ids':[ref.id],
                    'available_reference_ids':sorted(pool),
                    'reference_category':'target_quote_unavailable' if source is not None else 'missing_reference'})
        if not valid:
            excluded.append(dict(semantic_unit_id=unit.id, origin='new' if is_new else 'previous',
                reason='unapproved_reference', references=rejected_refs))
        if valid:
            context_refs = coverage_context_refs(request, unit, evidence)
            if context_refs:
                # A model cannot erase complementary/intent citations with a
                # generic "one of these sources" contract. Only an identified
                # prior resume reference can be contextual; all other refs stay
                # conjunctive, approved and owning. Semantic entailment remains
                # independently checked against quotes and the original.
                if diagnostics is not None:
                    diagnostics.setdefault('contextual_references', []).append(dict(semantic_unit_id=unit.id,
                        context_refs=[r.model_dump(mode='json') for r in unit.context_source_refs],
                        required_refs=[r.model_dump(mode='json') for r in unit.source_refs if (r.type,r.id) not in context_refs]))
            if is_new:
                sources = [known[ref.type][ref.id].evidence_quote if ref.type != 'target_context'
                    else known[ref.type][ref.id].posting_quote for ref in unit.source_refs]
                unsupported = [detail for detail in unit.optional_details
                    if not _supported_optional_detail(detail, sources)]
                if unsupported:
                    # Optional decoration is not a source or a protected claim.
                    # Drop only that decoration; the semantic unit and every
                    # applicant assertion still undergo normal source checks.
                    unit.optional_details = [detail for detail in unit.optional_details if detail not in unsupported]
                    if diagnostics is not None:
                        diagnostics.setdefault('excluded_optional_details', []).append(dict(
                            semantic_unit_id=unit.id, reason='quote_absent', details=unsupported))
            unit.semantic_role = canonical_role(unit.semantic_role, unit.source_refs, active, active_intents, contract, facets)
            if section == 'project' and unit.semantic_role != 'technology' and unit.source_refs and all(
                    ref.type == 'applicant_evidence' and ref.id in active
                    and active[ref.id].fact_type == FactType.TECHNOLOGY for ref in unit.source_refs):
                sourced_action = any(not active[ref.id].source_id.endswith(':techStack')
                    and _PERFORMED_ACTION.search(active[ref.id].evidence_quote) for ref in unit.source_refs)
                if unit.semantic_role != 'action' or not sourced_action:
                    original_role=unit.semantic_role
                    unit.semantic_role='technology'
                    if diagnostics is not None:
                        diagnostics.setdefault('source_meaning_repairs',[]).append(dict(
                            semantic_unit_id=unit.id,reason='technology_source_does_not_establish_role',
                            previous_role=original_role,role='technology'))
            if section == 'growth' and unit.semantic_role not in contract.high_value_semantics:
                quoted = [active[r.id].evidence_quote for r in unit.source_refs
                    if r.type == 'applicant_evidence']
                if any(GROWTH_TRANSITION.search(quote) for quote in quoted):
                    unit.semantic_role = 'behavior_change'
                    if diagnostics is not None:
                        diagnostics.setdefault('source_meaning_repairs', []).append(dict(
                            semantic_unit_id=unit.id, reason='explicit_growth_transition', role='behavior_change'))
            # An unfamiliar editorial label is optional metadata. It cannot
            # authorize a source, nor should it invalidate otherwise valid facts.
            if all(r.type == 'target_context' for r in unit.source_refs) and unit.semantic_role in {
                    'motivation', 'early_adaptation', 'short_term_contribution', 'long_term_direction', 'intended_contribution', 'direction'}:
                raise ContractError('target context cannot establish applicant intent')
            if unit.semantic_role in {'motivation', 'early_adaptation', 'work_understanding',
                    'short_term_contribution', 'improvement_plan', 'long_term_direction', 'intended_contribution', 'direction'}:
                if not any(r.type == 'applicant_intent' for r in unit.source_refs):
                    from .validation import is_explicit_intention
                    quotes=[active[r.id].evidence_quote for r in unit.source_refs if r.type=='applicant_evidence']
                    if not quotes or any(is_explicit_intention(q) for q in quotes):
                        raise ContractError('intent semantic unit requires ApplicantIntent')
                    # A rhetorical direction label cannot turn sourced performed
                    # work/current identity into an intention or block its use.
                    original_role=unit.semantic_role
                    unit.semantic_role=canonical_role('source_evidence',unit.source_refs,active,active_intents,contract,facets)
                    if diagnostics is not None:
                        diagnostics.setdefault('source_meaning_repairs',[]).append(dict(semantic_unit_id=unit.id,
                            reason='factual_source_not_intent',previous_role=original_role,role=unit.semantic_role))
            units[unit.id] = unit
    approved = set(revision_plan.core_evidence_ids + revision_plan.supporting_evidence_ids + revision_plan.preserved_evidence_ids)
    if section != 'project':
        # Meaning hierarchy is section-specific: no project slot selection leaks in.
        approved = set(active)
        revision_plan.core_evidence_ids = []
        revision_plan.supporting_evidence_ids = list(active)
        revision_plan.preserved_evidence_ids = []
        revision_plan.omitted_evidence = [o for o in revision_plan.omitted_evidence if o.evidence_id not in active]
        revision_plan.operation = 'replace_field' if active or active_intents else 'no_change'
    # A mixed unit is not safely editable by deleting some of its references:
    # that could invent a relationship. Filter the whole unit first, then test
    # which approved atomic facts/intentions still need a representation.
    retained = {}
    for uid, unit in units.items():
        unselected = [dict(type=r.type, id=r.id, category='active_not_selected')
            for r in unit.source_refs if r.type == 'applicant_evidence' and r.id not in approved]
        if unselected:
            excluded.append(dict(semantic_unit_id=uid, reason='unselected_evidence', references=unselected))
        else:
            retained[uid] = unit
    units = retained
    if section == 'motivation':
        # Recover a formation relation lost in a value paraphrase from its exact
        # owning quote, not from a new inferred intention or applicant fact.
        for cid, claim in active_intents.items():
            if claim.intent_type not in {'work_value','motivation'} or not FORMATION.search(claim.evidence_quote):
                continue
            if any(u.semantic_role == 'motivation_origin' and any(
                    r.type == 'applicant_intent' and r.id == cid for r in u.source_refs) for u in units.values()):
                continue
            uid = 'origin:' + cid
            units[uid] = SemanticUnit(id=uid, semantic_role='motivation_origin', meaning=claim.evidence_quote,
                source_refs=[SourceRef(type='applicant_intent', id=cid)])
            if diagnostics is not None:
                diagnostics.setdefault('source_meaning_repairs', []).append(dict(
                    semantic_unit_id=uid, reason='explicit_value_formation', source_ref=dict(type='applicant_intent',id=cid)))
    # Protected intentions and approved atomic facts cannot disappear merely
    # because a mixed extractor unit was removed above.
    for cid, claim in active_intents.items():
        if not any(any(r.type == 'applicant_intent' and r.id == cid for r in u.source_refs) for u in units.values()):
            role = INTENT_ROLE[claim.intent_type]
            if section == 'motivation' and role in {'short_term_contribution', 'long_term_direction', 'direction'}:
                role = 'intended_contribution'
            if role not in contract.high_value_semantics:
                role = 'direction' if section in {'self_intro', 'other'} else contract.high_value_semantics[0]
            units['intent:' + cid] = SemanticUnit(id='intent:' + cid, semantic_role=role,
                meaning=claim.text, source_refs=[SourceRef(type='applicant_intent', id=cid)])
            restored.append(dict(semantic_unit_id='intent:' + cid, type='applicant_intent', id=cid))
    for eid, fact in active.items():
        if eid not in approved or any(any(r.type == 'applicant_evidence' and r.id == eid for r in u.source_refs) for u in units.values()):
            continue
        role = FACT_ROLE[fact.fact_type]
        if section == 'motivation' and fact.fact_type != FactType.TECHNOLOGY: role = 'supporting_experience'
        elif section != 'project' and fact.fact_type == FactType.TECHNOLOGY: role = 'technology'
        elif section not in {'project', 'career', 'education', 'activity', 'challenge'}: role = 'evidence' if section == 'self_intro' else 'concrete_evidence' if section == 'strength_weakness' else 'formative_experience' if section == 'growth' else 'identity'
        units['fact:' + eid] = SemanticUnit(id='fact:' + eid, semantic_role=role,
            meaning=fact.normalized_fact, source_refs=[SourceRef(type='applicant_evidence', id=eid)])
        restored.append(dict(semantic_unit_id='fact:' + eid, type='applicant_evidence', id=eid))
    if diagnostics is not None:
        diagnostics['state'] = 'atomic_fallback' if excluded and restored else 'excluded_only' if excluded else 'complete'
    selected = [u for u in units.values() if all(r.type != 'applicant_evidence' or r.id in approved for r in u.source_refs)]
    explicit_meanings = {u.id for u in extraction.semantic_units} | {u.id for u in request.previous_semantic_units}
    material_ids = {f.evidence_id for f in merge_facets(active, request.previous_facets, extraction.facets) if f.material}
    inventory_ids = {eid for eid,fact in active.items() if fact.source_id.endswith(':techStack')}
    # Mixed role/inventory units are optional as a whole; protect the sourced
    # role separately without making its attached technology list mandatory.
    for unit in list(selected):
        applicant_refs = [ref for ref in unit.source_refs if ref.type == 'applicant_evidence']
        if section == 'project' and any(ref.id in inventory_ids for ref in applicant_refs):
            for ref in applicant_refs:
                if ref.id not in inventory_ids and active[ref.id].fact_type == FactType.ROLE:
                    if not any(u.semantic_role == 'role' and u.source_refs == [ref] for u in selected):
                        uid = 'role:' + ref.id
                        selected.append(SemanticUnit(id=uid, semantic_role='role',
                            meaning=active[ref.id].normalized_fact, source_refs=[ref]))
    required = [u.id for u in selected if u.id not in replaced_semantic_ids and u.semantic_role in contract.high_value_semantics
                and (section != 'project' or (u.semantic_role != 'technology'
                    and not any(r.type == 'applicant_evidence' and r.id in inventory_ids for r in u.source_refs)))
                and not (section == 'motivation' and u.semantic_role == 'supporting_experience')
                and (section != 'project' or (
                    any(r.type == 'applicant_evidence' and r.id in revision_plan.core_evidence_ids + revision_plan.preserved_evidence_ids for r in u.source_refs)
                    or (u.id in explicit_meanings and u.semantic_role in {'purpose', 'observation', 'action', 'decision', 'validation', 'outcome'}
                        and any(r.type == 'applicant_evidence' and r.id in material_ids for r in u.source_refs))))]
    profile = SectionSemanticProfile(section_type=section, original_semantic_units=selected,
        evidence_claim_ids=list(approved), intent_claim_ids=list(active_intents), target_context_ids=sorted(target),
        required_semantics=required, protected_semantics=required,
        optional_semantics=[u.id for u in selected if u.id not in required])
    if section == 'project':
        # An editing opportunity is a sourced high-value meaning, not completion
        # of an action slot. A bare tool inventory is context, not a contribution.
        # Explicit meaning units can express the same work under different fact
        # taxonomies; all references have already passed source/state validation.
        writable = any(u.semantic_role in contract.high_value_semantics and u.semantic_role != 'technology' and
            (u.id in explicit_meanings or any(r.type == 'applicant_evidence' and
                r.id in revision_plan.core_evidence_ids for r in u.source_refs)) and
            any(r.type == 'applicant_evidence' and r.id in material_ids for r in u.source_refs)
            for u in selected)
        revision_plan.operation = 'replace_field' if writable else 'no_change'
        revision_plan.reason = '' if writable else '작성에 사용할 고가치 경험 근거가 부족해 후보를 생성하지 않았습니다.'
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
        # Extractor paraphrases are not new applicant propositions. The shared
        # Writer/Verifier contract names protected source refs, not generated
        # verbs/relations that may already have strengthened or lost a claim.
        'must_express': [u.model_dump(mode='json', exclude={'meaning','optional_details'}) for u in units if u.id in required],
        'optional_support': [u.model_dump(mode='json', exclude={'meaning','optional_details'}) for u in units if u.id not in required],
        'compressible_details': [dict(semantic_unit_id=u.id, details=u.optional_details,
            source_refs=[r.model_dump(mode='json') for r in u.source_refs]) for u in units if u.optional_details],
        'support_required': section == 'motivation' and any(u.semantic_role == 'supporting_experience' for u in units),
        # Reuse the existing plan as grouping hints, not a second meaning gate
        # or one sentence per unit/group. IDs retain the shared coverage contract.
        'meaning_groups': [dict(purpose=item.purpose, semantic_unit_ids=item.semantic_unit_ids)
            for item in request.sentence_plan.items] if request.sentence_plan else [],
    }


def rewrite_source_review(request, previous_text, previous_candidate=None):
    """Repair focus references, not a second inclusion policy or a safe-sentence list.

    The Writer already receives these quotes once in approved_evidence/intents.
    Point back to the originals when compressed labels lose actions/conditions.
    """
    if not previous_text:
        return None
    required = editorial_brief(request)['must_express']
    refs = {(ref['type'],ref['id']) for unit in required for ref in unit['source_refs']}
    protected={u['id'] for u in required}
    prior_coverage=[]
    if previous_candidate is not None:
        for index,sentence in enumerate(previous_candidate.sentences):
            expressed=sorted(protected.intersection(sentence.semantic_unit_ids))
            if expressed:
                prior_coverage.append(dict(sentence_index=index,semantic_unit_ids=expressed,
                    evidence_ids=sentence.evidence_ids,intent_ids=sentence.intent_ids))
    return dict(protected_meaning_ids=[u['id'] for u in required],
        source_refs_to_recheck=[dict(type=typ,id=eid) for typ,eid in sorted(refs)],
        prior_draft_coverage=prior_coverage,prior_draft_is_not_approved=True)


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
ROLE_DECLARATION = re.compile(r'(?:역할|업무)\s*(?:은|는|:)\s*(.+?)(?:이었습니다|였습니다|입니다|이었다|였다)(?=[\s.,;!?]|$)')
ROLE_OBJECT = re.compile(r'([^.,;!?]+?)(?:을|를)\s*(?:맡(?:았|아|고|는|은)|담당|책임)')
ROLE_NOUN = re.compile(r'([^.,;!?]+?)\s*(?:역할|업무)(?:을|를|로)(?=\s|$)')


def _role_scope_equal(left, right, experience=None):
    # Only presentation normalization, not synonym inference or broader duties.
    def clean(text):
        text = re.sub(r'^(?:저는|제가|본인은|본인이)\s*', '', text.strip())
        # Remove only an owning-context frame, not arbitrary preceding clauses
        # or qualifiers (e.g. 전체, 주도, 다른 프로젝트). No substring matching.
        if experience is not None:
            label = {'project':'프로젝트','employment':'업무','activity':'활동'}.get(experience.kind)
            frames = [re.escape(experience.title)]
            if label:
                frames.append(r'(?:이\s*|해당\s*)?' + label)
            text = re.sub(r'^(?:' + '|'.join(frames) + r')에서(?:는)?\s+', '', text)
            if experience.kind == 'project':
                frame = re.match(r'^(?P<context>.+(?:는|한|던))\s+프로젝트에서(?:는)?\s+(?P<scope>.+)$',text)
                if frame:
                    context = frame.group('context')
                    # Separate a syntactic project-description frame, not a
                    # matching role substring. Never discard another role or
                    # responsibility claim embedded in that frame; ambiguous
                    # nested project scopes also remain unnormalized.
                    if (not re.search(OWNED + '|' + LED + '|' + DESIGNED,context)
                            and not ROLE_NOUN.search(context) and '프로젝트' not in context):
                        text = frame.group('scope')
        text = re.sub(r'\s+(?:역할|업무)$', '', text)
        return re.sub(r'[\s.,;!?]+', '', text)
    if clean(left) == clean(right):
        return True
    # Split only an explicit list in the SOURCE, not arbitrary Korean noun
    # suffixes (e.g. the 과 in 성과). Restatement must retain every same member.
    members = [clean(part) for part in re.split(r'\s+(?:및|그리고)\s+|[,·/]', right) if clean(part)]
    return len(members) > 1 and any(clean(left) == connector.join(members)
        for connector in ('', '및', '그리고', '와', '과'))


def _explicit_role_support(sentence, role_facts, experience=None):
    """A nominal role field establishes that role, never arbitrary responsibility.

    Every declared/owned scope in the sentence must have its own cited role basis.
    Other actor/action/result assertions still require independent verification.
    """
    declarations = list(ROLE_DECLARATION.finditer(sentence.text))
    scopes = [m.group(1) for m in declarations]
    nominal = list(ROLE_NOUN.finditer(sentence.text))
    scopes.extend(m.group(1) for m in nominal)
    owned = list(ROLE_OBJECT.finditer(sentence.text))
    # A responsibility verb outside a recognized object is not a nominal role.
    spans = [m.span() for m in [*owned,*declarations,*nominal]]
    if any(not any(left <= m.start() < right for left,right in spans) for m in re.finditer(OWNED, sentence.text)):
        return False
    scopes.extend(m.group(1) for m in owned)
    source_scopes = [scope for f in role_facts for scope in
        [f.evidence_quote, *(m.group(1) for pattern in (ROLE_DECLARATION, ROLE_NOUN)
            for m in pattern.finditer(f.evidence_quote))]]
    return bool(scopes) and all(any(_role_scope_equal(scope, source, experience) for source in source_scopes) for scope in scopes)


def agency_issues(sentence, facts, intents=(), experience=None, resume_sources=()):
    from .models import ValidationIssue
    from .project_planning import active_facts
    active = active_facts(facts)
    cited = [active[eid] for eid in sentence.evidence_ids if eid in active
             and (experience is None or active[eid].experience_id == experience.experience_id)]
    sources = {s.source_id:s.text for s in resume_sources}
    role_facts = [f for f in cited if experience is not None and f.source_type == 'resume_text' and (
        f.source_id == experience.experience_id + ':role'
        and f.source_id in sources and f.evidence_quote in sources[f.source_id]
        or f.source_id == experience.experience_id and f.evidence_quote in experience.current_text
        and (ROLE_DECLARATION.search(f.evidence_quote) or ROLE_NOUN.search(f.evidence_quote)))]
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
        if kind == ClaimType.OWNERSHIP:
            # A tag is an annotation, not evidence of an assertion. Nominal role
            # wording invokes the scope gate regardless of the Writer's tag;
            # plain actions with a mistaken role tag still get semantic review.
            asserted = bool(re.search(OWNED, sentence.text) or ROLE_DECLARATION.search(sentence.text)
                            or ROLE_NOUN.search(sentence.text))
        if not asserted:
            continue
        supported = any(re.search(pattern, f.evidence_quote) for f in cited
            if f not in role_facts and not f.source_id.endswith(':techStack'))
        if kind == ClaimType.OWNERSHIP:
            supported = supported or _explicit_role_support(sentence, role_facts, experience)
        else:
            # Role fields can explicitly state leadership/design, but the mere
            # existence of a nominal role never establishes either assertion.
            supported = supported or any(re.search(pattern, f.evidence_quote) for f in role_facts)
        if not supported:
            issues.append(ValidationIssue(code='unsupported_agency', detail=f'{kind.value}: {sentence.text}'))
    return issues
