"""Real B HTTP orchestration with memory-only storage and scripted LLMs."""
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import Mock
import json
import pytest
from test_project_live_pipeline import pipeline, post
from app.resume_review_v2.batch import shared_context_payload
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import FactVerification, ValidationIssue
from app.review_workflow import ReviewConflict


def staged(db, reviews):
    saved = {}
    db.supports_stage_checkpoints = True
    @contextmanager
    def execution(*args):
        yield
    db.review_execution.side_effect = execution
    def claim(cohort, resume, uid, rid, fingerprint, tail=None):
        row = saved.setdefault(rid, {'fingerprint': fingerprint})
        assert row['fingerprint'] == fingerprint
        if rid in reviews:
            return {'response': reviews[rid]}
        return {'checkpoint': deepcopy(row.get('checkpoint', {}))}
    db.claim_review.side_effect = claim
    def progress(cohort, resume, uid, rid, telemetry, tail=None):
        # JSON round trip simulates a new process, never retained object identity.
        saved[rid]['checkpoint'] = json.loads(json.dumps(telemetry['stage_checkpoint']))
    db.review_progress.side_effect = progress
    return saved


def test_initial_stages_persist_and_resume_without_repeating_calls(pipeline):
    client, reviews, calls, db = pipeline
    saved = staged(db, reviews)
    first = post(client, 'initial')
    assert first['telemetry']['execution']['state'] == 'processing'
    assert first['questions'] == first['sentence_reviews'] == []
    assert saved['initial']['checkpoint']['states']
    second = post(client, 'initial')
    assert second['telemetry']['execution']['state'] == 'verification_pending'
    assert second['questions'] == second['sentence_reviews'] == []
    final = post(client, 'initial')
    assert final['telemetry']['execution']['state'] == 'verified'
    assert final['telemetry']['calls'] == 3
    selection = final['telemetry']['v2_results'][0]['debug_trace']['question_selection']
    assert selection['state'] == 'selected' and selection['candidate']['why_needed']
    assert final['telemetry']['question_delivery'][0]['state'] == 'displayed'
    assert [stage for stage, _, _ in calls] == ['BatchExtractionOutput', 'BatchWriterDraft', 'BatchFactVerification']
    assert all(s['budget_at_start_ms'] > 160000 for s in final['telemetry']['stages'])
    db.complete_review.assert_called_once()
    post(client, 'initial')
    assert len(calls) == 3  # completed request replay costs zero


def test_verify_timeout_resumes_draft_not_analysis_or_writer(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    staged(db, reviews)
    original = LangChainReviewLLM._call
    failures = []
    def invoke(self, prompt, payload, schema):
        if schema.__name__ == 'BatchFactVerification' and not failures:
            failures.append(True)
            raise TimeoutError('mock timeout')
        return original(self, prompt, payload, schema)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    post(client, 'r'); post(client, 'r')
    pending = post(client, 'r')
    assert pending['telemetry']['execution']['retryable_error']
    assert pending['sentence_reviews'] == [] and 'r' not in reviews
    final = post(client, 'r')
    assert final['telemetry']['execution']['state'] == 'verified'
    assert len(calls) == 3 and len(failures) == 1
    assert final['telemetry']['attempted_calls'] == 4


def test_semantic_exclusion_diagnostic_survives_all_stage_resumes(pipeline, monkeypatch):
    from app.resume_review_v2.models import Evidence, SemanticUnit, SourceRef
    client, reviews, calls, db = pipeline
    db.get_owned_resume.return_value['content']['projects'][0]['description'] += ' 성능 수치는 확인하지 못했습니다.'
    saved = staged(db, reviews)
    original = LangChainReviewLLM._call
    def invoke(self, prompt, payload, schema):
        result, usage = original(self, prompt, payload, schema)
        if schema.__name__ == 'BatchExtractionOutput':
            extraction = result.item_0
            extraction.extracted_evidence.append(Evidence(evidence_id='unconfirmed',
                experience_id=extraction.experience_id, fact_type='context',
                normalized_fact='성능 수치는 확인하지 못했습니다.', evidence_quote='성능 수치는 확인하지 못했습니다.',
                source_type='resume_text', source_id=extraction.experience_id, assertion_state='uncertain'))
            extraction.semantic_units = [SemanticUnit(id='mixed', semantic_role='outcome',
                meaning='API 구현으로 성능을 개선했습니다.', source_refs=[
                    SourceRef(type='applicant_evidence', id=eid) for eid in ['action','unconfirmed']])]
        return result, usage
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    post(client, 'semantic')
    first = saved['semantic']['checkpoint']['states']['projects:p1']['result']['debug_trace']['semantic_preparation']
    assert first['state'] == 'atomic_fallback'
    assert first['excluded_units'][0]['references'][0]['category'] == 'inactive_evidence'
    second = post(client, 'semantic')
    assert second['telemetry']['execution']['state'] == 'verification_pending'
    final = post(client, 'semantic')
    record = final['telemetry']['v2_results'][0]
    assert record['debug_trace']['semantic_preparation'] == first
    assert all(unit['id'] != 'mixed' for unit in record['section_profile']['original_semantic_units'])
    assert len(calls) == 3  # No recovery LLM stage.


@pytest.mark.parametrize('after_stage', ['BatchExtractionOutput', 'BatchWriterDraft'])
def test_crash_after_durable_raw_output_does_not_repeat_stage(pipeline, after_stage):
    client, reviews, calls, db = pipeline
    staged(db, reviews)
    original = db.review_progress.side_effect
    crashed = []
    def progress(*args):
        original(*args)
        outputs = args[4]['stage_checkpoint'].get('stage_outputs', {})
        if calls and calls[-1][0] == after_stage and outputs and not crashed:
            crashed.append(True)
            raise RuntimeError('simulated process boundary after durable output')
    db.review_progress.side_effect = progress
    for _ in range(6):
        try:
            result = post(client, 'r')
        except AssertionError as exc:
            assert '503' in str(exc)
            continue
        if result.get('telemetry', {}).get('execution', {}).get('state') == 'verified':
            break
    assert 'r' in reviews and crashed
    assert [stage for stage, _, _ in calls].count(after_stage) == 1
    assert len(calls) == 3


def test_rewrite_limit_survives_each_stage_resume(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    staged(db, reviews)
    original = LangChainReviewLLM._call
    def invoke(self, prompt, payload, schema):
        if schema.__name__ == 'BatchFactVerification':
            result, usage = original(self, prompt, payload, schema)
            for name in type(result).model_fields:
                setattr(result, name, FactVerification(quality_issues=[ValidationIssue(code='semantic_redundancy', detail='mock')]))
            return result, usage
        return original(self, prompt, payload, schema)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    for _ in range(6):
        result = post(client, 'r')
        if result['telemetry']['execution']['state'] == 'verified': break
    assert len([s for s, _, _ in calls if s == 'BatchWriterDraft']) == 2
    assert result['telemetry']['v2_results'][0]['debug_trace']['writer_attempts'] == 2
    assert result['sentence_reviews'][0]['suggested_revision'] is None


@pytest.mark.parametrize('repair_fails', [False, True])
def test_mixed_deterministic_repair_survives_stage_boundary(pipeline, monkeypatch, repair_fails):
    client, reviews, calls, db = pipeline
    db.get_owned_resume.return_value['content']['projects'].append({
        'id': 'p2', 'name': '별도 경험', 'description': 'API를 구현했습니다.'})
    saved = staged(db, reviews)
    original = LangChainReviewLLM._call
    write_sizes = []
    def invoke(self, prompt, payload, schema):
        result, usage = original(self, prompt, payload, schema)
        if schema.__name__ == 'BatchWriterDraft':
            write_sizes.append(len(type(result).model_fields))
            for name in type(result).model_fields:
                draft = getattr(result, name)
                if draft.experience_id == 'projects:p1' and (len(write_sizes) == 1 or repair_fails):
                    draft.sentences[0].evidence_ids = ['unapproved']
        return result, usage
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    post(client, 'mixed'); post(client, 'mixed')
    states = saved['mixed']['checkpoint']['states']
    repair = states['projects:p1']
    assert repair['result']['validation']['status'] == 'REWRITE'
    assert repair['needs_write'] and not repair['needs_verify']
    assert repair['write_count'] == 1
    assert len(repair['result']['debug_trace']['attempts']) == 1
    assert states['projects:p2']['needs_verify']
    # Also recover the pre-fix checkpoint, not just newly consistent flags.
    repair['needs_write'] = repair['needs_verify'] = False
    for _ in range(5):
        result = post(client, 'mixed')
        if result['telemetry']['execution']['state'] == 'verified':
            break
    assert 'mixed' in reviews
    rows = {r['experience']['experience_id']: r for r in result['telemetry']['v2_results']}
    assert rows['projects:p1']['debug_trace']['writer_attempts'] == 2
    assert len(rows['projects:p1']['debug_trace']['attempts']) == 2
    assert rows['projects:p1']['validation']['status'] == ('REJECTED' if repair_fails else 'UNCHANGED')
    assert rows['projects:p2']['debug_trace']['writer_attempts'] == 1
    assert rows['projects:p2']['validation']['status'] == 'UNCHANGED'
    assert write_sizes == [2, 1]
    assert [s for s, _, _ in calls].count('BatchExtractionOutput') == 1
    call_count = len(calls)
    post(client, 'mixed')
    assert len(calls) == call_count


def test_quality_rewrite_waits_for_verifier_before_repair():
    from app.resume_review_v2.batch import BatchReviewEngine
    from app.resume_review_v2.models import ValidationResult
    state = dict(writer=object(), write_count=1, needs_write=False, needs_verify=True,
        validation=ValidationResult(status='REWRITE', quality_issues=[ValidationIssue(code='verbosity', detail='long')]))
    BatchReviewEngine._sync_work(state)
    assert not state['needs_write'] and state['needs_verify']
    state['needs_verify'] = False  # The same verdict after independent verification.
    BatchReviewEngine._sync_work(state)
    assert state['needs_write'] and not state['needs_verify']


@pytest.mark.parametrize('change', ['text', 'answer', 'correction', 'job', 'model', 'policy'])
def test_exact_checkpoint_identity_invalidates_changed_inputs(change, monkeypatch):
    from test_resume_review_batch import inputs
    from app.resume_review_v2 import audit_resume
    from app.resume_review_v2.models import JobRequirement, Evidence
    requests = inputs()
    signature = audit_resume.stage_signature(requests, 'fake', 'medium')
    model = 'fake'
    if change == 'text': requests[0].experience.current_text += ' 변경'
    elif change == 'answer': requests[0].answer = '새로운 답변'
    elif change == 'correction':
        requests[0].experience.existing_evidence = [Evidence(evidence_id='old', experience_id='0',
            fact_type='action', normalized_fact='API 구현', evidence_quote='API 구현', source_type='resume_text',
            source_id='0', assertion_state='retracted')]
    elif change == 'job': requests[0].job_requirements = [JobRequirement(requirement_id='req', text='Python', posting_quote='Python 우대')]
    elif change == 'model': model = 'changed'
    else: monkeypatch.setattr(audit_resume, 'PIPELINE_VERSION', 'changed')
    assert audit_resume.stage_signature(requests, model, 'medium') != signature


def test_shared_context_preserves_quotes_scope_and_distinct_contexts():
    context = [{'requirement_id': 'req-1', 'posting_quote': 'Python 경험 우대', 'text': 'Python'}] * 14
    rows = [('policy', {'experience': {'experience_id': str(i)}, 'approved_evidence': [{'id': str(i)}],
        'allowed_target_context': context}, object) for i in range(11)]
    payload = shared_context_payload(rows)
    before = len(json.dumps({f'item_{i}': r[1] for i,r in enumerate(rows)}, ensure_ascii=False).encode())
    after = len(json.dumps(payload, ensure_ascii=False).encode())
    assert after < before
    assert payload['shared_allowed_target_context'] == context
    assert [item['approved_evidence'] for item in payload['items'].values()] == [[{'id':str(i)}] for i in range(11)]
    rows[-1][1]['allowed_target_context'] = []
    distinct = shared_context_payload(rows)
    assert 'shared_allowed_target_context' not in distinct
    assert distinct['item_10']['allowed_target_context'] == []


def test_local_execution_lock_rejects_concurrent_owner_and_releases():
    from app.local_resume_site_adapter import LocalGateway
    gateway = LocalGateway.__new__(LocalGateway)
    conn = Mock()
    held = []
    def execute(sql, args):
        if 'pg_try_advisory_lock' in sql:
            acquired = not held
            if acquired: held.append(args[0])
            return Mock(fetchone=lambda: (acquired,))
        if 'pg_advisory_unlock' in sql: held.clear()
        return Mock()
    conn.execute.side_effect = execute
    gateway._pg = Mock(return_value=conn)
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    gateway._cohort_user = Mock()
    with gateway.review_execution('c', 'r', 'u'):
        with pytest.raises(ReviewConflict, match='review_stage_busy'):
            with gateway.review_execution('c', 'r', 'u'): pass
    assert not held
    with gateway.review_execution('c', 'r', 'u'): pass


@pytest.mark.parametrize('role', ['validation', 'arbitrary_compound_label', 'evidence'])
@pytest.mark.parametrize('kind', ['verification', 'result', 'context'])
def test_sourced_meaning_not_taxonomy_controls_writing(role, kind):
    from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, EvidenceFacet,
        ExtractionOutput, SemanticUnit, SourceRef)
    from app.resume_review_v2.project_planning import prepare_review
    req = ReviewInput(experience=Experience(experience_id='exp', kind='project', title='분석',
        current_text='단일 변수의 방향성을 확인했습니다.', field_path='projects[0].description', content_hash='h'))
    ev = Evidence(evidence_id='measurement', experience_id='exp', fact_type=kind,
        normalized_fact=req.experience.current_text, evidence_quote=req.experience.current_text,
        source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[ev],
        facets=[EvidenceFacet(evidence_id='measurement', slots=['validation_method', 'outcome'])],
        semantic_units=[SemanticUnit(id='meaning', semantic_role=role, meaning=ev.normalized_fact,
            source_refs=[SourceRef(type='applicant_evidence', id='measurement')])])
    prepared = prepare_review(req, extraction)
    assert prepared.analysis.plan.operation == 'replace_field'
    assert prepared.section_profile.original_semantic_units[0].semantic_role in {'validation', 'outcome', 'purpose'}


def test_optional_sourced_role_can_write_with_no_required_semantics():
    from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, EvidenceFacet,
        ExtractionOutput, SemanticUnit, SourceRef, RevisionPlan)
    from app.resume_review_v2.section_semantics import prepare_section
    req = ReviewInput(experience=Experience(experience_id='exp', kind='project', title='서비스',
        current_text='API 연동을 담당했습니다.', content_hash='h', field_path='projects[0].description'))
    ev = Evidence(evidence_id='role', experience_id='exp', fact_type='role', normalized_fact=req.experience.current_text,
        evidence_quote=req.experience.current_text, source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[ev],
        facets=[EvidenceFacet(evidence_id='role', slots=['personal_role'])],
        semantic_units=[SemanticUnit(id='role-meaning', semantic_role='role', meaning=ev.normalized_fact,
            source_refs=[SourceRef(type='applicant_evidence', id='role')])])
    plan = RevisionPlan(objective='기여 명확화', operation='no_change', supporting_evidence_ids=['role'])
    _, _, profile, _ = prepare_section(req, extraction, {'role':ev}, plan)
    assert profile.required_semantics == []
    assert plan.operation == 'replace_field'


def test_unknown_label_cannot_turn_tool_inventory_into_contribution():
    from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, ExtractionOutput, SemanticUnit, SourceRef)
    from app.resume_review_v2.project_planning import prepare_review
    req = ReviewInput(experience=Experience(experience_id='exp', kind='project', title='도구', current_text='Python', content_hash='h', field_path='projects[0].description'))
    ev = Evidence(evidence_id='tool', experience_id='exp', fact_type='technology', normalized_fact='Python',
        evidence_quote='Python', source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[ev], semantic_units=[
        SemanticUnit(id='tool-only', semantic_role='unfamiliar_label', meaning='Python',
            source_refs=[SourceRef(type='applicant_evidence', id='tool')])])
    assert prepare_review(req, extraction).analysis.plan.operation == 'no_change'


@pytest.mark.parametrize('complete', [False, True])
def test_claim_reuses_canonical_request_and_durable_checkpoint(complete):
    from app.local_resume_site_adapter import LocalGateway
    gateway = LocalGateway.__new__(LocalGateway)
    conn = Mock()
    conn.__enter__ = Mock(return_value=conn)
    conn.__exit__ = Mock(return_value=False)
    prefix = gateway._resume_legacy('r', None) + '/'
    response = {'review_id':'old'} if complete else None
    conn.execute.return_value.fetchall.return_value = [(prefix+'old', 'same', response,
        {'stage_checkpoint': {'states': {'exp': 'saved'}}})]
    gateway._pg = Mock(return_value=conn)
    gateway._cohort_user = Mock(return_value={'user_pk':1})
    claimed = gateway.claim_review('c', 'r', 'u', 'new', 'same')
    assert claimed['request_id'] == 'old'
    if complete: assert claimed['response'] == response
    else: assert claimed['checkpoint']['states'] == {'exp':'saved'}
    with pytest.raises(ReviewConflict, match='different_input'):
        gateway.claim_review('c', 'r', 'u', 'old', 'changed')
