"""One per-experience audit checkpoint in existing review JSON, not a cache store."""
from app.review_workflow import digest
from .models import ReviewResult
from .policy import POLICY_VERSION


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
        [r.model_dump(mode='json') for r in request.job_requirements], job_source, model, reasoning, POLICY_VERSION])


def reusable_record(request, record, previous, job_source, model, reasoning):
    if not record:
        return False
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
        if 'analysis_contract_invalid' in codes or saved.validation.status == 'REWRITE':
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
