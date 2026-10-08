"""B-route audit scheduling and fail-closed verification; no real LLM or DB."""
import pytest
from test_project_live_pipeline import pipeline, post
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import FactVerification


def projects(db, count=11):
    db.get_owned_resume.return_value['content']['projects'] = [
        {'id': f'p{i}', 'name': f'서비스 {i}', 'description': 'API를 구현했습니다.'} for i in range(count)]


def stage_counts(result):
    stages = result['telemetry']['stages']
    return {stage: [(s['items'], s['status']) for s in stages if s['stage'] == stage]
            for stage in ('analyze', 'write', 'verify')}


def first_timeout(monkeypatch):
    original = LangChainReviewLLM._call
    fired = False
    def invoke(self, system, payload, schema):
        nonlocal fired
        if schema.__name__ == 'BatchFactVerification' and not fired:
            fired = True
            raise TimeoutError('recorded verifier budget exhaustion')
        return original(self, system, payload, schema)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)


def test_eleven_timeout_drafts_resume_with_one_verify_only(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    projects(db)
    first_timeout(monkeypatch)
    first = post(client, 'initial')
    assert all(r['validation']['status'] == 'REJECTED' for r in first['telemetry']['v2_results'])
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [], 'write': [], 'verify': [(11, 'complete')]}
    assert audit['telemetry']['audit_resume'] == dict(reused_experiences=11,
        completed_reused=0, verification_resumed=11, reprocessed_experiences=0)
    assert all(r['candidate']['suggested_text'] == old['candidate']['suggested_text']
        for r, old in zip(audit['telemetry']['v2_results'], first['telemetry']['v2_results']))
    assert audit['telemetry']['calls'] == 1
    again = post(client, 'audit-again', previous_review_id='audit', review_phase='gap_audit')
    assert stage_counts(again) == {'analyze': [], 'write': [], 'verify': []}
    assert again['telemetry']['calls'] == 0


@pytest.mark.parametrize('change', ['description', 'name', 'techStack', 'role'])
def test_one_changed_source_reprocesses_only_that_experience(pipeline, monkeypatch, change):
    client, reviews, calls, db = pipeline
    projects(db)
    first_timeout(monkeypatch)
    post(client, 'initial')
    db.get_owned_resume.return_value['content']['projects'][0][change] = (
        ['Python'] if change == 'techStack' else 'API를 구현하고 동작을 확인했습니다.')
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [(1, 'complete')], 'write': [(1, 'complete')], 'verify': [(11, 'complete')]}
    assert audit['telemetry']['audit_resume']['reused_experiences'] == 10
    assert audit['telemetry']['audit_resume']['reprocessed_experiences'] == 1
    # Global apply hash is rebound even on the ten unchanged candidates.
    assert all(r['candidate']['content_hash'] == audit['input_hash'] for r in audit['telemetry']['v2_results'])


def test_followup_then_audit_keeps_other_experiences_and_new_evidence(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    projects(db)
    first_timeout(monkeypatch)
    first = post(client, 'initial')
    q = first['questions'][0]
    answer = post(client, 'answer', previous_review_id='initial', answers=[{
        'question_id': q['question_id'], 'field_path': q['field_path'], 'question': q['question'],
        'answer': '정상 조회 결과를 대조했습니다.'}])
    assert stage_counts(answer)['analyze'] == [(1, 'complete')]
    audit = post(client, 'audit', previous_review_id='answer', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [], 'write': [], 'verify': [(10, 'complete')]}
    stats = audit['telemetry']['audit_resume']
    assert stats['completed_reused'] == 1 and stats['verification_resumed'] == 10
    owner = next(r for r in audit['telemetry']['v2_results'] if r['experience']['experience_id'] == q['experience_id'])
    assert 'check' in {e['evidence_id'] for e in owner['evidence_state']}
    assert len(owner['evidence_state']) == 2


def test_repeated_timeout_never_promotes_candidate(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    original = LangChainReviewLLM._call
    def invoke(self, system, payload, schema):
        if schema.__name__ == 'BatchFactVerification': raise TimeoutError('still unavailable')
        return original(self, system, payload, schema)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    post(client, 'initial')
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [], 'write': [], 'verify': [(1, 'failed')]}
    assert audit['telemetry']['v2_results'][0]['validation']['status'] == 'REJECTED'
    assert audit['sentence_reviews'][0]['suggested_revision'] is None
    assert audit['sentence_reviews'][0]['validation_status'] == 'REJECTED'


def test_audit_cannot_reset_the_one_rewrite_budget(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    original = LangChainReviewLLM._call
    checks = 0
    def invoke(self, system, payload, schema):
        nonlocal checks
        if schema.__name__ == 'BatchFactVerification':
            checks += 1
            if checks == 2: raise TimeoutError('rewritten draft not verified')
            result, usage = original(self, system, payload, schema)
            for key in type(result).model_fields:
                setattr(result, key, FactVerification(unsupported_claims=['unverified claim']))
            return result, usage
        return original(self, system, payload, schema)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    first = post(client, 'initial')
    assert len(stage_counts(first)['write']) == 2
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [], 'write': [], 'verify': [(1, 'complete')]}
    assert audit['telemetry']['v2_results'][0]['validation']['status'] == 'REJECTED'


def test_legacy_record_requires_identical_whole_resume(pipeline):
    client, reviews, calls, db = pipeline
    projects(db, 2)
    post(client, 'initial')
    for r in reviews['initial']['telemetry']['v2_results']:
        r.pop('audit_input_hash'); r.pop('audit_source_hash')
    same = post(client, 'same', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(same)['analyze'] == []
    db.get_owned_resume.return_value['content']['projects'][0]['role'] = 'API 구현'
    changed = post(client, 'changed', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(changed)['analyze'] == [(2, 'complete')]  # Cannot certify old auxiliary fields.


def test_state_correction_invalidates_completed_analysis(pipeline):
    client, reviews, calls, db = pipeline
    post(client, 'initial')
    record = reviews['initial']['telemetry']['v2_results'][0]
    record['evidence_state'][0]['assertion_state'] = 'retracted'
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit)['analyze'] == [(1, 'complete')]
    assert audit['telemetry']['audit_resume']['reused_experiences'] == 0


@pytest.mark.parametrize('setting', ['openai_model', 'openai_reasoning_effort'])
def test_changed_model_configuration_cannot_skip_processing(pipeline, setting):
    client, reviews, calls, db = pipeline
    post(client, 'initial')
    from app import main
    setattr(main.build_resume_review_service().settings, setting, 'changed')
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit)['analyze'] == [(1, 'complete')]


def test_changed_job_context_invalidates_the_audit_checkpoint(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    from app import main, matching_handoff, job_requirements
    main.build_resume_review_service().settings.matching_job_store_path = 'unused'
    monkeypatch.setattr(matching_handoff, 'load_selected_job', lambda *_: {
        'text': '데이터 품질 관리', 'source': {'job_id': 'job', 'snapshot_hash': 'new'}})
    monkeypatch.setattr(job_requirements, 'load_or_extract_requirements', lambda *_: [])
    post(client, 'initial')
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit', selected_job_id='job')
    assert stage_counts(audit)['analyze'] == [(1, 'complete')]


def test_golden_timeout_resume_preserves_verifier_quality_context(pipeline, monkeypatch):
    from copy import deepcopy
    from test_section_golden import golden_case
    from app.resume_review_v2.models import WriterDraft, Usage
    client, reviews, calls, db = pipeline
    cases = {golden_case(name)[0].experience.experience_id: golden_case(name)
             for name in ['B-1', 'B-2', 'B-3']}
    db.get_owned_resume.return_value['content'] = {
        'projects': [{'id': 'garage', 'name': '자동차 정비소',
                      'description': cases['projects:garage'][0].experience.current_text}],
        'selfIntroduction': {key: {'body': cases[f'selfIntroduction.{key}'][0].experience.current_text}
                             for key in ('motivation', 'aspiration')},
    }
    verification_inputs = []
    def invoke(self, system, payload, schema):
        rows = {}
        if schema.__name__ == 'BatchFactVerification':
            verification_inputs.append(deepcopy(payload))
            if len(verification_inputs) == 1:
                raise TimeoutError('golden verification interrupted')
        for key, item in payload.get('items', payload).items():
            if schema.__name__ == 'BatchExtractionOutput':
                rows[key] = cases[item['experience']['experience_id']][1]
            elif schema.__name__ == 'BatchWriterDraft':
                identity = item['experience']['experience_id']
                rows[key] = WriterDraft(experience_id=identity, sentences=cases[identity][2])
            else:
                rows[key] = FactVerification()
        return schema.model_validate(rows), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    post(client, 'initial')
    audit = post(client, 'audit', previous_review_id='initial', review_phase='gap_audit')
    assert stage_counts(audit) == {'analyze': [], 'write': [], 'verify': [(3, 'complete')]}
    assert verification_inputs[0] == verification_inputs[1]
