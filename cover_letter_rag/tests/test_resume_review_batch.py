"""Batch orchestration regression; no network/API calls."""
import time
import pytest
from app.resume_review_v2.batch import BatchReviewEngine
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, AnalystOutput,
    RevisionPlan, WriterOutput, WriterDraft, RevisionSentence, FactVerification, Usage, ExtractionOutput)
from app.resume_review_v2.validation import ContractError


def inputs():
    return [ReviewInput(experience=Experience(experience_id=str(i), kind='project',
        title='API', current_text='API 구현', field_path=f'projects[{i}].description',
        content_hash='h')) for i in range(4)]


class FakeBatch(BatchReviewEngine):
    def __init__(self, invalid=False, fail_verify=False):
        super().__init__('fake', 'medium')
        self.calls = []
        self.invalid, self.fail_verify = invalid, fail_verify

    def _batch(self, method, items):
        if not items:
            return {}
        self.calls.append((method, len(items)))
        self.usage.calls += 1
        result = {}
        for key, args in items.items():
            r = args[0]
            if method == 'analyze':
                ev = Evidence(evidence_id='ev-' + key, experience_id=key, fact_type='action',
                    normalized_fact='API 구현', evidence_quote=r.experience.current_text,
                    source_type='resume_text', source_id=key, assertion_state='resume_stated')
                result[key] = ExtractionOutput(experience_id=key, extracted_evidence=[ev])
            elif method == 'write':
                result[key] = WriterOutput(experience_id=key, operation='replace_field', original_quote=r.experience.current_text,
                    sentences=[RevisionSentence(text='API를 구현했습니다.',
                        evidence_ids=['unknown' if self.invalid else 'ev-' + key])])
            else:
                if self.fail_verify:
                    raise RuntimeError('verifier unavailable')
                result[key] = FactVerification()
        return result


def test_four_experiences_three_calls_and_independent_provenance():
    engine = FakeBatch()
    results = engine.run_many(inputs())
    assert engine.calls == [('analyze', 4), ('write', 4), ('verify', 4)]
    assert sum(r.usage.calls for r in results) == 3
    assert all(r.validation.status == 'READY' for r in results)
    for r in results:
        assert r.candidate.sentences[0].evidence_ids == ['ev-' + r.experience.experience_id]


def test_invalid_provenance_never_ready_and_rewrite_only_once():
    engine = FakeBatch(invalid=True)
    results = engine.run_many(inputs())
    assert all(r.validation.status != 'READY' for r in results)
    assert sum(method == 'write' for method, _ in engine.calls) <= 2
    assert not any(method == 'verify' for method, _ in engine.calls)


def test_semantic_failure_is_not_exposed_as_success():
    results = FakeBatch(fail_verify=True).run_many(inputs())
    assert all(r.validation.status == 'REJECTED' for r in results)
    assert all(r.validation.factual_issues[0].code == 'verification_unavailable' for r in results)


def test_duplicate_experience_rejected_before_calls():
    engine = FakeBatch()
    with pytest.raises(ContractError):
        engine.run_many([inputs()[0], inputs()[0]])
    assert engine.calls == []


def test_deadline_prevents_network_call():
    engine = BatchReviewEngine('fake', 'medium')
    engine.deadline = time.monotonic() - 1
    with pytest.raises(TimeoutError):
        engine.run_many(inputs())
    assert engine.attempted_calls == 0


def test_rewrite_verification_failure_keeps_other_ready_results(monkeypatch):
    from app.resume_review_v2 import batch
    from app.resume_review_v2.models import ValidationResult, ValidationIssue
    original = batch.validate_candidate
    def validation(r, w, p, e, verification=None):
        if r.experience.experience_id == '1':
            return ValidationResult(status='REWRITE', quality_issues=[ValidationIssue(code='verbosity', detail='long')])
        return original(r, w, p, e, verification)
    monkeypatch.setattr(batch, 'validate_candidate', validation)
    engine = FakeBatch()
    call = engine._batch
    def fail_last(method, items):
        if method == 'verify' and len(items) == 1:
            raise TimeoutError('deadline')
        return call(method, items)
    engine._batch = fail_last
    results = engine.run_many(inputs())
    assert [r.validation.status for r in results] == ['READY', 'REJECTED', 'READY', 'READY']


def test_batch_envelope_shares_requirements_without_loss(monkeypatch):
    import langchain_openai
    from app.resume_review_v2.llm import LangChainReviewLLM
    from app.resume_review_v2.models import JobRequirement
    received = {}
    monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kwargs: received.update(kwargs) or object())
    def invoke(self, prompt, payload, schema):
        received['payload'] = payload
        data = {}
        for key, item in payload.items():
            data[key] = ExtractionOutput(experience_id=item['experience']['experience_id'], extracted_evidence=[])
        return schema.model_validate(data), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    requests = inputs()
    for r in requests:
        r.job_requirements = [JobRequirement(requirement_id='req-1', text='Python', posting_quote='Python 우대')]
    engine = BatchReviewEngine('fake', 'medium')
    results = engine.run_many(requests)
    assert len(results) == 4
    assert received['max_retries'] == 0
    assert received['reasoning_effort'] == 'medium'
    assert 0 < received['timeout'] <= 165
    # Extraction deliberately never sees job context, so it cannot classify a
    # posting requirement as an applicant fact. Sharing remains on Writer only.
    assert all('job_requirements' not in item for item in received['payload'].values())


def test_one_bad_analysis_cannot_abort_other_experiences():
    engine = FakeBatch()
    original = engine._batch
    def invalid_one(method, items):
        rows = original(method, items)
        if method == 'analyze':
            rows['1'].extracted_evidence[0].evidence_quote = 'fabricated quote'
        return rows
    engine._batch = invalid_one
    results = engine.run_many(inputs())
    assert [r.validation.status for r in results] == ['READY', 'REJECTED', 'READY', 'READY']
    assert results[1].candidate is None
    assert results[1].validation.factual_issues[0].code == 'analysis_contract_invalid'
    assert engine.calls == [('analyze', 4), ('write', 3), ('verify', 3)]


def test_writer_batch_preserves_shared_requirement_provenance(monkeypatch):
    import langchain_openai
    from app.resume_review_v2.llm import LangChainReviewLLM
    from app.resume_review_v2.models import JobRequirement
    captured = {}
    monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kwargs: object())
    def invoke(self, prompt, payload, schema):
        captured.update(payload)
        return schema.model_validate({key: WriterDraft(
            experience_id=item['experience']['experience_id'],
            sentences=[RevisionSentence(text='API를 구현했습니다.', evidence_ids=['ev'])])
            for key, item in payload['items'].items()}), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    requests = inputs()
    requirement = JobRequirement(requirement_id='req-1', text='Python', posting_quote='Python 우대')
    rows = {}
    for request in requests:
        request.job_requirements = [requirement]
        rows[request.experience.experience_id] = (request,
            RevisionPlan(objective='근거 확인', operation='no_change'), [])
    result = BatchReviewEngine('fake', 'medium')._batch('write', rows)
    assert len(result) == 4
    assert captured['shared_job_requirements'] == [requirement.model_dump(mode='json')]
    assert all('job_requirements' not in item for item in captured['items'].values())
