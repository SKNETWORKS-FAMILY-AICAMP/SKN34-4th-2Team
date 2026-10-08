"""One per-experience audit checkpoint in existing review JSON, not a cache store."""
from app.review_workflow import digest
from .models import ReviewResult
from .policy import POLICY_VERSION

PIPELINE_VERSION = 'stage-checkpoint-6-apply-evidence-continuity'
PROVENANCE_PIPELINES = {'stage-checkpoint-5-source-target-question', PIPELINE_VERSION}
PROVENANCE_POLICIES = {'resume-policy-17-source-target-question',
    'resume-policy-18-source-proposition-editing',
    'resume-policy-19-source-repair-continuity',
    'resume-policy-20-source-meaning-advice',
    'resume-policy-21-material-meaning-intent-recovery', POLICY_VERSION}


def stage_signature(requests, model, reasoning):
    # Exact owning input includes corrections, source scope, Job and hash. It is
    # intentionally stricter than completed per-experience audit reuse.
    return digest([PIPELINE_VERSION, POLICY_VERSION, model, reasoning,
        [r.model_dump(mode='json',exclude={'requirement_review_context','prior_information_needs'}) for r in requests]])


def source_signature(request):
    e = request.experience
    return digest([e.experience_id, e.field_path, e.kind, e.title, e.current_text,
                   [s.model_dump(mode='json') for s in request.resume_sources]])


def input_signature(request, job_source, model, reasoning, record=None):
    # Global resume hash and transient request/answer-source IDs are deliberately
    # excluded: editing another experience does not change this input.
    state = record or {}
    evidence = state.get('evidence_state', [e.model_dump(mode='json') for e in request.experience.existing_evidence])
    intents = state.get('intent_claims', [c.model_dump(mode='json') for c in request.existing_intents])
    units = ((state.get('section_profile') or {}).get('original_semantic_units', []) if record is not None
             else [u.model_dump(mode='json') for u in request.previous_semantic_units])
    facets = state.get('evidence_facets', [f.model_dump(mode='json') for f in request.previous_facets])
    return digest([source_signature(request), request.question, request.answer, request.question_history,
        request.previous_question_keys, sorted(str(s) for s in request.unavailable_slots), evidence, intents, units, facets,
        [s.model_dump(mode='json') for s in request.historical_resume_sources],
        [r.model_dump(mode='json') for r in request.job_requirements], job_source, model, reasoning, POLICY_VERSION, PIPELINE_VERSION])


def reusable_record(request, record, previous, job_source, model, reasoning):
    if (record or {}).get('answer_state_invalidated'):
        return False
    if not record:
        return False
    if record.get('verified_apply'):
        return False  # Historical sources require the explicit apply proof below.
    try:
        saved = ReviewResult.model_validate({k: record[k] for k in ReviewResult.model_fields if k in record})
        e = request.experience
        if (saved.experience.experience_id != e.experience_id or saved.experience.field_path != e.field_path
                or saved.experience.current_text != e.current_text):
            return False
        if saved.candidate and (saved.candidate.original_quote != e.current_text
                or saved.candidate.experience_id != e.experience_id
                or saved.candidate.field_path != e.field_path
                or saved.candidate.validation != saved.validation):
            return False
        codes = {i.code for i in saved.validation.all_issues}
        if 'analysis_contract_invalid' in codes:
            # Reuse the explicit failure, never a successful candidate. Changed
            # answers/facts/policy naturally produce a different input signature.
            return (saved.candidate is None and record.get('audit_input_hash') ==
                input_signature(request,job_source,model,reasoning))
        if saved.validation.status == 'REWRITE':
            return False
        if 'verification_unavailable' in codes and not saved.candidate:
            return False
        available = {e.evidence_id for e in request.experience.existing_evidence}
        if not set(saved.plan.core_evidence_ids + saved.plan.supporting_evidence_ids
                   + saved.plan.preserved_evidence_ids) <= available:
            return False
        if record.get('audit_input_hash'):
            return record['audit_input_hash'] == input_signature(request, job_source, model, reasoning)
        # Old B records lack auxiliary-source snapshots. Reuse them only when
        # the ENTIRE original resume hash still matches, not just visible prose.
        # Once admitted, the adapter saves the narrower checkpoint for next time.
        telemetry = previous.get('telemetry') or {}
        return (saved.experience.content_hash == e.content_hash
            and saved.experience.title == e.title and saved.experience.kind == e.kind
            and saved.answer == request.answer and saved.question == request.question
            and telemetry.get('policy_version') == POLICY_VERSION and telemetry.get('model') == model
            and telemetry.get('pipeline_version') == PIPELINE_VERSION
            and telemetry.get('reasoning_effort', reasoning) == reasoning
            and previous.get('job_source', {}) == job_source
            and [dict(requirement_id=r['id'], text=r['label'], posting_quote=r['posting_quote'])
                 for r in previous.get('requirement_map', [])]
                == [r.model_dump(mode='json') for r in request.job_requirements])
    except (ValueError, KeyError, TypeError):
        return False  # Incomplete/corrupt historical state is never promoted.


def sources_changed(request, record):
    if not record:
        return False
    if record.get('audit_source_hash'):
        return record['audit_source_hash'] != source_signature(request)
    return record.get('experience', {}).get('content_hash') != request.experience.content_hash


_STATE_KEYS = ('plan','evidence_state','intent_claims','section_profile','sentence_plan',
    'evidence_facets','project_profile','gap_questions','answered_question_keys',
    'unavailable_slots','question','answer','requirement_matches','requirement_warnings','requirement_context_hash')


def _state_hash(record):
    state={key:record.get(key) for key in _STATE_KEYS}
    state['gap_questions']=[{k:v for k,v in q.items() if not (k=='requirement_anchor' and v is None)}
        for q in state.get('gap_questions') or []]
    return digest(state)


def _receipt_hash(receipt):
    return digest({k:v for k,v in receipt.items() if k != 'integrity'})


def bind_verified_apply(response, before, after, application):
    """Called only inside the existing successful apply transaction. No I/O.

    Keep original source documents, not fabricated quotes in the new document.
    Existing per-experience state stays intact; only a bounded proof is attached.
    """
    telemetry = response.get('telemetry', {})
    if (telemetry.get('engine') != 'v2-local-ui-2' or telemetry.get('policy_version') != POLICY_VERSION
            or telemetry.get('pipeline_version') != PIPELINE_VERSION
            or response.get('review_id') != application.review_id
            or response.get('cohort_id') != application.cohort_id
            or response.get('resume_id') != application.resume_id
            or response.get('tailored_resume_id') != application.tailored_resume_id
            or digest(before) != application.expected_input_hash):
        return
    from app.resume_review import extract_review_fields
    from app.resume_review_runtime import experience_sources
    from .models import Experience, ReviewInput
    old_fields,_ = extract_review_fields(before)
    new_fields,_ = extract_review_fields(after)
    for index in application.selected_indices:
        edit = response.get('sentence_reviews', [])[index]
        path = edit.get('field_path')
        for record in telemetry.get('v2_results', []):
            candidate = record.get('candidate') or {}
            if (record['experience']['field_path'] != path or edit.get('validation_status') != 'READY'
                    or record.get('validation', {}).get('status') != 'READY'
                    or candidate.get('validation') != record['validation']
                    or candidate.get('field_path') != path
                    or candidate.get('experience_id') != record['experience']['experience_id']
                    or candidate.get('original_quote') != old_fields.get(path)
                    or record['experience']['current_text'] != old_fields.get(path)
                    or candidate.get('suggested_text') != new_fields.get(path)
                    or edit.get('suggested_revision') != candidate.get('suggested_text')
                    or not record.get('audit_input_hash') or not record.get('audit_source_hash')):
                continue
            exp = Experience.model_validate(record['experience'])
            title,sources = experience_sources(before,path,exp.experience_id)
            old = ReviewInput(experience=exp.model_copy(update={'title':title}),resume_sources=sources)
            if source_signature(old) != record['audit_source_hash']:
                continue
            title,new_sources = experience_sources(after,path,exp.experience_id)
            current = ReviewInput(experience=exp.model_copy(update={'current_text':new_fields[path],'title':title}),resume_sources=new_sources)
            origin = exp.model_dump(mode='json');origin['existing_evidence'] = []
            receipt = dict(operation_id=application.request_id,review_id=application.review_id,index=index,
                operation_before_hash=digest(before),operation_after_hash=digest(after),
                origin_experience=origin,origin_sources=[s.model_dump(mode='json') for s in sources],
                completed_candidate=candidate,origin_input_hash=record['audit_input_hash'],origin_source_hash=record['audit_source_hash'],
                after_source_hash=source_signature(current),state_hash=_state_hash(record),
                policy_version=POLICY_VERSION,pipeline_version=PIPELINE_VERSION,
                model=telemetry.get('model'),reasoning=telemetry.get('reasoning_effort'),
                job_source=response.get('job_source',{}),requirement_context_hash=record.get('requirement_context_hash'))
            prior = record.get('source_provenance') or record.get('verified_apply')
            if prior and (prior.get('integrity')!=_receipt_hash(prior)
                    or prior.get('completed_candidate',{}).get('suggested_text')!=exp.current_text
                    or prior.get('after_source_hash')!=source_signature(old)):
                continue
            roots = (prior or {}).get('fact_sources') or ([dict(source_id=exp.experience_id,text=exp.current_text)] + receipt['origin_sources'])
            receipt['fact_sources'] = roots
            receipt['origin_historical_sources'] = roots if prior else []
            if prior:receipt['parent_provenance']=prior
            receipt['integrity'] = _receipt_hash(receipt)
            record['verified_apply'] = receipt
            record.pop('source_provenance',None)


def applied_provenance(request, record, previous, job_source, requirement_context, model, reasoning, operation=None, completed=False):
    """Source validity is independent of completion/input equality. No reactivation.

    The existing transaction receipt proves how generated editing text relates to
    applicant sources. New answers invalidate plans, not these source documents.
    """
    from copy import deepcopy
    from .models import Experience, SourceDocument, Evidence
    from .validation import _exact_source_quote
    receipt = (record or {}).get('verified_apply') if completed else (
        (record or {}).get('source_provenance') or (record or {}).get('verified_apply'))
    if not receipt or completed and record.get('answer_state_invalidated'):
        return None
    try:
        from app.resume_review import extract_review_fields
        if (not isinstance(operation,dict) or operation.get('kind') != 'apply' or operation.get('undone_by')
                or operation.get('source_id') != receipt['review_id']
                or operation.get('after_hash') != receipt['operation_after_hash']
                or digest(operation.get('before')) != receipt['operation_before_hash']
                or (operation.get('payload') or {}).get('expected_input_hash') != receipt['operation_before_hash']
                or (operation.get('payload') or {}).get('review_id') != receipt['review_id']
                or receipt['index'] not in (operation.get('payload') or {}).get('selected_indices',[])):
            return None
        applied_fields,_ = extract_review_fields(operation['before'])
        if applied_fields.get(request.experience.field_path) != receipt['origin_experience']['current_text']:
            return None
        candidate = receipt['completed_candidate']
        exp = request.experience
        if (receipt.get('integrity') != _receipt_hash(receipt) or completed and receipt['state_hash'] != _state_hash(record)
                or receipt['policy_version'] not in PROVENANCE_POLICIES or receipt['pipeline_version'] not in PROVENANCE_PIPELINES
                or completed and receipt['policy_version'] != POLICY_VERSION
                or completed and receipt['pipeline_version'] != PIPELINE_VERSION
                or receipt['model'] != model or receipt['reasoning'] != reasoning or receipt['job_source'] != job_source
                or receipt['requirement_context_hash'] != requirement_context
                or candidate['validation']['status'] != 'READY'
                or candidate['validation'].get('factual_issues') or candidate['validation'].get('intent_issues')
                or candidate['validation'].get('section_issues') or candidate['validation'].get('quality_issues')
                or candidate['suggested_text'] != exp.current_text or candidate['experience_id'] != exp.experience_id
                or candidate['field_path'] != exp.field_path or receipt['after_source_hash'] != source_signature(request)):
            return None
        historical = request.model_copy(deep=True)
        historical.experience.current_text = receipt['origin_experience']['current_text']
        historical.resume_sources = [SourceDocument.model_validate(s) for s in receipt['origin_sources']]
        historical.historical_resume_sources = [SourceDocument.model_validate(s) for s in receipt.get('origin_historical_sources',[])]
        original = deepcopy(record);original.pop('verified_apply',None)
        original.update(experience=receipt['origin_experience'],candidate=candidate,validation=candidate['validation'],
            audit_input_hash=receipt['origin_input_hash'],audit_source_hash=receipt['origin_source_hash'])
        if completed and not reusable_record(historical,original,previous,job_source,model,reasoning):
            return None
        sources = {s.source_id:s.text for s in map(SourceDocument.model_validate,receipt.get('fact_sources',[]))}
        if not sources:sources = historical.factual_resume_sources()
        allowed={exp.experience_id,*[s.source_id for s in historical.resume_sources]}
        if not set(sources)<=allowed:return None
        for fact in map(Evidence.model_validate,record.get('evidence_state',[])):
            if fact.assertion_state.value not in {'resume_stated','user_asserted'}:
                continue
            text = sources.get(fact.source_id) if fact.source_type == 'resume_text' else request.answer if fact.source_type == 'user_answer' else None
            if fact.experience_id != exp.experience_id or text is None or _exact_source_quote(text,fact.evidence_quote) is None:
                return None
        if not completed:
            return [SourceDocument(source_id=k,text=v) for k,v in sources.items()]
        restored = deepcopy(record)
        restored.update(experience=exp.model_dump(mode='json'),candidate=None,
            validation=dict(status='UNCHANGED',factual_issues=[],quality_issues=[],intent_issues=[],section_issues=[]))
        return restored
    except (KeyError,ValueError,TypeError):
        return None


def applied_record(request, record, previous, job_source, requirement_context, model, reasoning, operation=None):
    return applied_provenance(request,record,previous,job_source,requirement_context,model,reasoning,operation,completed=True)
