"""Batch orchestration regression; no network/API calls."""
import time
import pytest
from app.resume_review_v2.batch import BatchReviewEngine
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, AnalystOutput,
    RevisionPlan, WriterOutput, WriterDraft, RevisionSentence, FactVerification, Usage, ExtractionOutput)
from app.resume_review_v2.validation import ContractError


@pytest.mark.parametrize('case', ['directional_auc', 'threshold_f1'])
@pytest.mark.parametrize('kind', ['verification', 'result', 'context'])
def test_r4_measurements_without_actions_reach_writer_and_verifier(case, kind):
    from app.resume_review_v2.models import EvidenceFacet, SemanticUnit, SourceRef
    from app.resume_review_v2.engine import ReviewEngineV2
    if case == 'directional_auc':
        original = 'days_to_expire 변수가 이탈 예측에서 중요한 방향성을 가진 변수임을 분석했습니다.'
        quote = 'days_to_expire를 단일 변수로 확인했을 때 directional AUC가 약 0.905였고, 만료일까지 남은 일수가 짧을수록 이탈 가능성이 높아지는 방향으로 나타났습니다.'
        text = 'days_to_expire 단일 변수의 directional AUC는 약 0.905였으며, 만료일까지 남은 일수가 짧을수록 이탈 가능성이 높아졌습니다.'
    else:
        original = '이탈 예측 threshold를 비교했습니다.'
        quote = 'threshold 0.5 / 0.3 / 0.2 / 0.1의 F1은 0.2257 / 0.2538 / 0.2612 / 0.2592였고 테스트 값 중 0.2가 최고였습니다. 최종 모델은 미확정입니다.'
        text = 'threshold 0.5 / 0.3 / 0.2 / 0.1에서 F1 0.2257 / 0.2538 / 0.2612 / 0.2592를 확인했고 테스트 값 중 0.2가 최고였습니다. 최종 모델은 미확정입니다.'
    req = ReviewInput(experience=Experience(experience_id='r4', kind='project', title='분석',
        field_path='projects[0].description', current_text=original, content_hash='h'),
        answer=quote, answer_source_id='answer-r4')
    fact = Evidence(evidence_id='measurement', experience_id='r4', fact_type=kind,
        normalized_fact=quote, evidence_quote=quote, source_type='user_answer',
        source_id='answer-r4', assertion_state='user_asserted')
    extraction = ExtractionOutput(experience_id='r4', extracted_evidence=[fact],
        facets=[EvidenceFacet(evidence_id='measurement', slots=['validation_method', 'outcome'])],
        semantic_units=[SemanticUnit(id='measured-result', semantic_role='validation',
            meaning=quote, source_refs=[SourceRef(type='applicant_evidence', id='measurement')])])
    class ScriptedBatch(FakeBatch):
        def _batch(self, method, items):
            if not items: return {}
            self.calls.append((method, len(items)))
            if method == 'analyze': return {key: extraction for key in items}
            if method == 'write': return {key: WriterOutput(experience_id='r4', operation='replace_field',
                original_quote=original, sentences=[RevisionSentence(text=text, evidence_ids=['measurement'],
                    semantic_unit_ids=['measured-result'])]) for key in items}
            return {key: FactVerification() for key in items}
    batch = ScriptedBatch()
    result = batch.run_many([req])[0]
    assert result.project_profile.actions.evidence_ids == []
    assert batch.calls == [('analyze', 1), ('write', 1), ('verify', 1)]
    assert result.candidate and result.validation.status == 'READY', result.validation
    assert result.candidate.suggested_text == text
    # The single-experience engine uses the same gate, not a separate action rule.
    class Single:
        def analyze(self, r): return extraction, Usage(calls=1)
        def write(self, *args): return WriterOutput.model_validate(result.debug_trace['writer_output']), Usage(calls=1)
        def verify(self, *args): return FactVerification(), Usage(calls=1)
    single = Single()
    once = ReviewEngineV2(single).run(req)
    assert once.usage.calls == 3 and once.candidate is not None
    assert once.validation.status == 'READY'


@pytest.mark.parametrize('with_question', [False, True])
def test_unwritten_gate_is_needs_evidence_even_without_question(with_question):
    from app.resume_review_v2.models import QuestionNeed
    engine = FakeBatch()
    original = engine._batch
    def empty(method, items):
        if method != 'analyze': return original(method, items)
        engine.calls.append((method, len(items)))
        return {key: ExtractionOutput(experience_id=key, extracted_evidence=[],
            question=QuestionNeed(experience_id=key,
                target_slot='personal_role', gap_type='missing', priority='HIGH',
                why_needed='편집할 경험 근거가 없어 직접 수행 내용을 확인합니다.', dedupe_key='role')
            if with_question else None) for key in items}
    engine._batch = empty
    result = engine.run_many([inputs()[0]])[0]
    assert engine.calls == [('analyze', 1)]
    assert result.candidate is None and result.validation.status == 'NEEDS_EVIDENCE'
    assert result.validation.quality_issues[0].code == 'writing_not_attempted'
    assert bool(result.proposed_question) == with_question


def test_actual_compared_candidate_can_still_be_unchanged():
    engine = FakeBatch()
    call = engine._batch
    def no_better(method, items):
        result = call(method, items)
        return {key: FactVerification(revision_quality='no_better', comparison_reason='원문이 충분함')
            for key in result} if method == 'verify' else result
    engine._batch = no_better
    result = engine.run_many([inputs()[0]])[0]
    assert engine.calls == [('analyze', 1), ('write', 1), ('verify', 1)]
    assert result.candidate is not None and result.validation.status == 'UNCHANGED'


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
        for key, item in payload.get('items', payload).items():
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
    assert 'shared_target_context' in received['payload']
    assert all('target_context' not in item for item in received['payload']['items'].values())
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
