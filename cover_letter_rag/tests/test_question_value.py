"""Question value/state regressions. Scripted transport is not a prose-quality eval."""
import pytest
from test_project_live_pipeline import pipeline, post
from test_section_golden import golden_case
from app.resume_review_v2.models import (Evidence, ExtractionOutput, GapQuestion,
    SemanticUnit, SourceRef, JobRequirement, WriterDraft, FactVerification, Usage, AssertionState)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.validation import ContractError


def candidate(req, **changes):
    return GapQuestion(**dict(dict(experience_id=req.experience.experience_id,
        question='관심 있는 업무에서 먼저 해결해 보고 싶은 구체적인 문제는 무엇인가요?',
        gap_type='missing', target_slot='purpose_or_problem', priority='HIGH',
        why_needed='분석을 업무에 연결하려는 이유는 이미 있습니다. 실제 해결할 문제를 알면 기여 방향을 구체화할 수 있습니다.',
        dedupe_key='specific-contribution'), **changes))


@pytest.mark.parametrize('role', ['motivation', 'motivation_and_origin', 'job_connection_and_contribution'])
def test_role_spelling_is_not_evidence_of_a_missing_reason(role):
    req, extraction, _, _ = golden_case('B-2')
    extraction.semantic_units[0].semantic_role = role
    prepared = prepare_review(req, extraction)
    assert prepared.questions == []
    assert prepared.analysis.plan.operation == 'replace_field'


def test_specific_value_candidate_can_follow_an_already_stated_motivation():
    req, extraction, _, _ = golden_case('B-2')
    extraction.question = candidate(req)
    prepared = prepare_review(req, extraction)
    assert len(prepared.questions) == 1
    assert prepared.questions[0].dedupe_key.startswith(req.experience.experience_id + ':value:')


@pytest.mark.parametrize('mode', ['owner', 'source', 'repeat', 'unavailable'])
def test_invalid_question_does_not_abort_valid_editing(mode):
    req, extraction, _, _ = golden_case('B-2')
    extraction.question = candidate(req)
    if mode == 'owner': extraction.question.experience_id = 'another-section'
    if mode == 'source': extraction.question.evidence_basis = ['job-requirement']
    if mode == 'repeat': req.question_history = [extraction.question.question]
    if mode == 'unavailable': req.unavailable_slots = [extraction.question.target_slot]
    prepared = prepare_review(req, extraction)
    assert prepared.questions == []
    assert prepared.analysis.plan.operation == 'replace_field'


def continued():
    req, extraction, _, _ = golden_case('B-2')
    first = prepare_review(req, extraction)
    req.experience.existing_evidence = list(first.evidence.values())
    req.existing_intents = first.intents
    req.previous_semantic_units = first.section_profile.original_semantic_units
    req.answer = '사용자가 결과를 이해하도록 비교 화면을 구현했습니다.'
    req.answer_source_id = 'turn-two:answer'
    return req, extraction


def test_verbatim_snapshot_echo_does_not_duplicate_or_drop_prior_intents():
    req, extraction = continued()
    prepared = prepare_review(req, extraction)
    assert len(prepared.evidence) == 2
    assert len(prepared.intents) == 2
    assert prepared.analysis.extracted_evidence == []
    assert prepared.analysis.plan.operation == 'replace_field'


def test_new_answer_may_reuse_local_fact_and_semantic_ids_without_overwriting():
    req, _ = continued()
    fact = Evidence(evidence_id='origin', experience_id=req.experience.experience_id,
        fact_type='implementation', normalized_fact=req.answer, evidence_quote=req.answer,
        source_type='user_answer', source_id=req.answer_source_id, assertion_state='user_asserted')
    extraction = ExtractionOutput(experience_id=req.experience.experience_id, extracted_evidence=[fact],
        semantic_units=[SemanticUnit(id='origin', semantic_role='supporting_experience', meaning=req.answer,
            source_refs=[SourceRef(type='applicant_evidence', id='origin')])])
    prepared = prepare_review(req, extraction)
    new = prepared.analysis.extracted_evidence[0]
    assert new.evidence_id != 'origin'
    assert prepared.evidence['origin'].source_type == 'resume_text'
    assert new.source_id == req.answer_source_id
    units = prepared.section_profile.original_semantic_units
    assert len({u.id for u in units}) == len(units)
    assert any(u.source_refs[0].id == new.evidence_id for u in units)
    assert prepared.analysis.plan.operation == 'replace_field'


def test_collision_reconciliation_still_checks_quote_and_experience():
    req, _ = continued()
    for quote, owner in [('없는 인용', req.experience.experience_id), (req.answer, 'other')]:
        fact = Evidence(evidence_id='origin', experience_id=owner, fact_type='implementation',
            normalized_fact=quote, evidence_quote=quote, source_type='user_answer',
            source_id=req.answer_source_id, assertion_state='user_asserted')
        with pytest.raises(ContractError):
            prepare_review(req, ExtractionOutput(experience_id=req.experience.experience_id, extracted_evidence=[fact]))


def test_changed_original_cannot_revive_a_withdrawn_claim():
    req, extraction = continued()
    req.experience.existing_evidence[0].assertion_state = AssertionState.RETRACTED
    with pytest.raises(ContractError, match='persisted claim'):
        prepare_review(req, extraction)


def test_analysis_receives_meaning_history_and_target_without_extra_call():
    req, _ = continued()
    req.question_history = ['왜 이 업무인가요?']
    req.job_requirements = [JobRequirement(requirement_id='r1', text='데이터 품질', posting_quote='데이터 품질 관리')]
    calls = []
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    client._call = lambda system, payload, schema: calls.append(payload)
    client.analyze(req)
    assert len(calls) == 1
    assert calls[0]['question_history'] == req.question_history
    assert calls[0]['user_answer'] == req.answer
    assert calls[0]['target_context'][0]['requirement_id'] == 'r1'


def test_metric_selection_is_not_misclassified_as_unsupported_design_ownership():
    from app.resume_review_v2.section_semantics import agency_issues
    from app.resume_review_v2.models import RevisionSentence
    fact = Evidence(evidence_id='choice', experience_id='exp', fact_type='technical_decision',
        normalized_fact='평가 기준 재선정', evidence_quote='불균형에 맞는 평가 기준을 다시 선정했습니다.',
        source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    sentence = RevisionSentence(text=fact.evidence_quote, evidence_ids=['choice'], claim_types=['decision_made'])
    assert agency_issues(sentence, {'choice': fact}) == []
    sentence.text = '평가 시스템 설계를 총괄했습니다.'
    assert agency_issues(sentence, {'choice': fact})


def test_failed_followup_keeps_state_and_answer_for_retry_and_reaches_writer(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    req, extraction, valid, _ = golden_case('B-2')
    db.get_owned_resume.return_value['content'] = {'selfIntroduction': {'motivation': {'body': req.experience.current_text}}}
    count = 0
    captured = []
    def invoke(self, system, payload, schema):
        nonlocal count
        rows = {}
        for key, item in payload.get('items', payload).items():
            if schema.__name__ == 'BatchExtractionOutput':
                count += 1
                captured.append(item)
                if count == 1:
                    out = extraction.model_copy(deep=True)
                    out.question = candidate(req)
                elif count == 2:
                    out = ExtractionOutput(experience_id=req.experience.experience_id,
                        extracted_evidence=[extraction.extracted_evidence[0].model_copy(update={'evidence_quote': 'not in source'})])
                else:
                    # Full echo of approved state, formerly rejected as duplicate.
                    out = extraction.model_copy(deep=True)
                    out.extracted_evidence.append(Evidence(evidence_id='new-answer',
                        experience_id=req.experience.experience_id, fact_type='implementation',
                        normalized_fact=item['user_answer'], evidence_quote=item['user_answer'],
                        source_type='user_answer', source_id=item['answer_source_id'], assertion_state='user_asserted'))
                rows[key] = out
            elif schema.__name__ == 'BatchWriterDraft':
                calls.append(('writer', item))
                rows[key] = WriterDraft(experience_id=req.experience.experience_id, sentences=valid)
            else:
                rows[key] = FactVerification()
        return schema.model_validate(rows), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    first = post(client, 'initial')
    q = first['questions'][0]
    failed = post(client, 'failed', previous_review_id='initial', answers=[{
        'question_id': q['question_id'], 'field_path': q['field_path'], 'question': q['question'],
        'answer': '비교 화면을 구현했습니다.'}])
    record = failed['telemetry']['v2_results'][0]
    assert record['candidate'] is None
    assert record['intent_claims'] == first['telemetry']['v2_results'][0]['intent_claims']
    assert record['section_profile'] == first['telemetry']['v2_results'][0]['section_profile']
    before = len(calls)
    retried = post(client, 'retry', previous_review_id='failed', review_phase='gap_audit')
    assert len(calls) > before
    assert captured[-1]['user_answer'] == '비교 화면을 구현했습니다.'
    assert captured[-1]['question_history'] == [q['question']]
    assert len(captured[-1]['existing_intents']) == 2
    assert retried['questions'] == []
    assert retried['telemetry']['v2_results'][0]['candidate'] is not None
