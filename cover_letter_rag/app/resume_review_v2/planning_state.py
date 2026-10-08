"""Reconcile turn-local extraction IDs before the unchanged source validators."""
import hashlib
from .validation import ContractError


def extraction_diagnostics(request, extraction, error):
    """Private review JSON diagnostics: references/hashes, never source prose."""
    from app.review_workflow import digest
    return {'error':str(error), **getattr(error, 'diagnostics', {}),
        'experience_id':request.experience.experience_id,
        'source_hash':digest(request.experience.current_text), 'answer_hash':digest(request.answer),
        'extracted_ids':[e.evidence_id for e in extraction.extracted_evidence],
        'existing_ids':[e.evidence_id for e in request.experience.existing_evidence],
        'facet_ids':[f.evidence_id for f in extraction.facets],
        'semantic_sources':{u.id:[r.model_dump(mode='json') for r in u.source_refs] for u in extraction.semantic_units},
        'semantic_source_rows':[dict(position=i,id=u.id,source_refs=[r.model_dump(mode='json') for r in u.source_refs])
            for i,u in enumerate(extraction.semantic_units)]}


def _question_references(request, question, original_facts, turn_mapping, diagnostics):
    """Resolve exact canonical IDs or one explicit evidence: wrapper, not approval.

    Literal IDs win even when they contain the wrapper. Resolve in the original
    turn's namespace first, then compose the existing collision mapping.
    """
    entries = []
    if question is None:
        if diagnostics is not None:diagnostics['question_references'] = entries
        return
    known = {f.evidence_id:f for f in [*request.experience.existing_evidence,*original_facts]}
    known.update({turn_mapping[f.evidence_id]:f for f in original_facts if f.evidence_id in turn_mapping})
    def resolve(reference, location):
        canonical, reason = reference, 'canonical'
        if question.experience_id != request.experience.experience_id:
            reason = 'question_owner_mismatch'
        elif reference in known:
            if known[reference].experience_id != request.experience.experience_id:
                reason = 'evidence_owner_mismatch'
            else:
                canonical = turn_mapping.get(reference,reference)
                reason = 'turn_remap' if canonical != reference else 'canonical'
        elif reference.startswith('evidence:') and reference[len('evidence:'):] in known:
            local = reference[len('evidence:'):]
            if known[local].experience_id != request.experience.experience_id:
                reason = 'evidence_owner_mismatch'
            else:
                canonical = turn_mapping.get(local,local)
                reason = 'typed_reference_and_turn_remap' if canonical != local else 'typed_reference'
        else:
            reason = 'unknown_reference'
        entries.append(dict(location=location,original_id=reference,canonical_id=canonical,reason=reason,
            outcome='unresolved' if reason.endswith('mismatch') or reason=='unknown_reference' else
                'normalized' if canonical!=reference else 'unchanged'))
        return canonical
    question.evidence_basis = list(dict.fromkeys(resolve(eid,f'evidence_basis[{i}]')
        for i,eid in enumerate(question.evidence_basis)))
    for index,target in enumerate(question.targets):
        target.evidence_id = resolve(target.evidence_id,f'targets[{index}].evidence_id')
    if diagnostics is not None:diagnostics['question_references'] = entries


def reconcile_extraction(request, extraction, with_replacements=False, diagnostics=None):
    result = extraction.model_copy(deep=True)
    original_facts = [f.model_copy(deep=True) for f in result.extracted_evidence]
    scope = hashlib.sha256((request.experience.experience_id + '\n' +
        request.answer_source_id + '\n' + request.answer).encode()).hexdigest()[:16]

    def reconcile(rows, previous, id_field, namespace, applicant=False):
        old = {getattr(r, id_field): r for r in previous}
        from app.review_workflow import digest
        distinct={};unique=[]
        for position,row in enumerate(rows):
            key=getattr(row,id_field);value=row.model_dump(mode='json',exclude={'created_at','updated_at'})
            if key in distinct:
                first,prior_value=distinct[key]
                entry=dict(namespace=namespace,id=key,positions=[first,position],
                    relation='identical' if prior_value==value else 'conflicting',
                    row_hashes=[digest(prior_value),digest(value)])
                if diagnostics is not None:diagnostics.setdefault('duplicate_rows',[]).append(entry)
                if prior_value!=value:
                    error=ContractError('duplicate extraction ID within one turn',dict(phase='extraction_ids',
                        namespace=namespace,duplicate_ids=[key],duplicate_rows=[entry],
                        differing_fields=sorted(k for k in set(prior_value)|set(value) if prior_value.get(k)!=value.get(k))))
                    if namespace!='evidence':error.reconciled_extraction=result
                    raise error
                continue  # exact duplicate assertion/representation only
            distinct[key]=(position,value);unique.append(row)
        rows=unique
        ids = [getattr(r, id_field) for r in rows]
        kept, mapping = [], {}
        occupied = set(old) | set(ids)
        for row in rows:
            key = getattr(row, id_field)
            prior = old.get(key)
            if prior is not None:
                if row.model_dump(exclude={'created_at', 'updated_at'}) == prior.model_dump(exclude={'created_at', 'updated_at'}):
                    continue  # A verbatim echo adds no claim; preserve the canonical object.
                if applicant and not (row.source_type == 'user_answer'
                        and row.source_id == request.answer_source_id):
                    # Never overwrite/revive a prior source claim using a changed paraphrase.
                    raise ContractError('conflicting reuse of persisted claim ID')
                replacement = f'turn:{scope}:{key}'
                while replacement in occupied:
                    replacement += ':new'
                occupied.add(replacement)
                mapping[key] = replacement
                setattr(row, id_field, replacement)
            kept.append(row)
        return kept, mapping

    result.extracted_evidence, facts = reconcile(result.extracted_evidence,
        request.experience.existing_evidence, 'evidence_id', 'evidence', True)
    result.intent_claims, intents = reconcile(result.intent_claims, request.existing_intents, 'id', 'intent', True)
    for facet in result.facets:
        facet.evidence_id = facts.get(facet.evidence_id, facet.evidence_id)
    for match in result.requirement_matches or []:
        match.evidence_ids = [facts.get(eid, eid) for eid in match.evidence_ids]
    for unit in result.semantic_units:
        for ref in [*unit.source_refs, *unit.context_source_refs]:
            mapping = facts if ref.type == 'applicant_evidence' else intents if ref.type == 'applicant_intent' else {}
            ref.id = mapping.get(ref.id, ref.id)
    replacements = set()
    prior_units = {u.id:u for u in request.previous_semantic_units}
    for unit in result.semantic_units:
        prior = prior_units.get(unit.id)
        if prior and unit.meaning != prior.meaning and prior.semantic_role == unit.semantic_role:
            old_refs = {(r.type,r.id) for r in prior.source_refs}
            new_refs = {(r.type,r.id) for r in unit.source_refs}
            if old_refs <= new_refs:
                replacements.add(prior.id)
    result.semantic_units, _ = reconcile(result.semantic_units, request.previous_semantic_units, 'id', 'semantic')
    _question_references(request,result.question,original_facts,facts,diagnostics)
    if result.question_review is not None:
        entries=[]
        for index,row in enumerate(result.question_review.items):
            if row.need is not None:
                local={};_question_references(request,row.need,original_facts,facts,local)
                entries.extend(dict(review_index=index,**entry) for entry in local['question_references'])
            row.evidence_ids=[facts.get(eid,eid) for eid in row.evidence_ids]
        if diagnostics is not None:diagnostics['review_references']=entries
    # supersedes/conflicts point to persisted claims, not this turn's local IDs.
    return (result, replacements) if with_replacements else result
