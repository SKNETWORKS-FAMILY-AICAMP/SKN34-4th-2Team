"""Product contracts, not assertions of live writing quality."""
import pytest
from test_section_golden import golden_case, ScriptedTransport
from app.resume_review_v2.engine import ReviewEngineV2
from app.resume_review_v2.models import (Evidence, RevisionSentence, WriterOutput,
    FactVerification, ApplicantIntentClaim, SourceRef)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.section_semantics import editorial_brief, agency_issues
from app.resume_review_v2.validation import validate_candidate, ContractError, validate_apply_snapshot
from app.resume_review_v2.llm import LangChainReviewLLM


def test_live_extractor_aliases_are_metadata_not_cross_experience_permission():
    req, extraction, _, _ = golden_case('B-1')
    extraction.intent_claims[0].source_section_id = req.experience.field_path
    prepared = prepare_review(req, extraction)
    assert prepared.intents[0].source_section_id == req.experience.experience_id
    extraction.intent_claims[0].source_section_id = 'selfIntroduction.motivation.body'
    with pytest.raises(ContractError):
        prepare_review(req, extraction)


def test_actual_profile_vocabulary_does_not_reject_valid_project_sources():
    req, extraction, _, _ = golden_case('B-3')
    from app.resume_review_v2.models import SemanticUnit
    extraction.semantic_units = [SemanticUnit(id='action', semantic_role='actions',
        meaning='거리 계산 구현', source_refs=[SourceRef(type='applicant_evidence', id='distance')])]
    assert prepare_review(req, extraction).section_profile.original_semantic_units[0].semantic_role == 'action'
    extraction.semantic_units[0].source_refs[0].id = 'another-project-fact'
    with pytest.raises(ContractError):
        prepare_review(req, extraction)


def test_motivation_support_is_optional_but_reason_and_origin_are_protected():
    req, extraction, _, _ = golden_case('B-2')
    prepared = prepare_review(req, extraction)
    brief = editorial_brief(prepared.request)
    assert brief['support_required']
    assert {'reason', 'origin', 'direction'} <= {u['id'] for u in brief['must_express']}
    assert 'projects' not in {u['id'] for u in brief['must_express']}
    assert 'projects' in {u['id'] for u in brief['optional_support']}


def test_missing_extracted_meaning_still_reaches_independent_original_audit():
    req, extraction, valid, _ = golden_case('B-1')
    extraction.intent_claims = extraction.intent_claims[1:]
    extraction.semantic_units = extraction.semantic_units[1:]
    prepared = prepare_review(req, extraction)
    captured = []
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    client._call = lambda prompt, payload, schema: captured.append(payload)
    candidate = WriterOutput(experience_id=req.experience.experience_id, operation='replace_field',
        original_quote=req.experience.current_text, sentences=valid[1:])
    client.verify(prepared.request, candidate, [], [], [])
    assert captured[0]['original_experience_text'] == req.experience.current_text
    verdict = validate_candidate(prepared.request, candidate, prepared.analysis.plan, prepared.evidence,
        FactVerification(section_meaning_loss=['입사 초기 환경 이해가 삭제됨']))
    assert verdict.status == 'REWRITE'
    assert any('환경 이해' in i.detail for i in verdict.section_issues)


@pytest.mark.parametrize('quality', ['no_better', 'worse'])
def test_unhelpful_revision_is_non_applyable_without_forced_rewrite(quality):
    transport = ScriptedTransport('B-1', first_bad=False)
    call = transport._call
    def judged(system, payload, schema):
        if schema is FactVerification:
            from app.resume_review_v2.models import Usage
            return FactVerification(revision_quality=quality, comparison_reason='변경 이점 없음'), Usage(calls=1)
        return call(system, payload, schema)
    transport._call = judged
    result = ReviewEngineV2(transport).run(transport.request)
    assert result.validation.status == 'UNCHANGED'
    assert transport.writes == 1
    with pytest.raises(ContractError, match='not apply-ready'):
        validate_apply_snapshot(result.candidate, transport.request.experience)


def test_grounded_future_leadership_is_not_past_ownership():
    quote = '장기적으로 분석 업무를 주도하고 싶습니다.'
    intent = ApplicantIntentClaim(id='goal', source_section_id='s', intent_type='long_term_goal',
        text=quote, source_type='resume_text', source_id='s', evidence_quote=quote, state='resume_stated')
    sentence = RevisionSentence(text=quote, intent_ids=['goal'], claim_types=['future_plan'])
    assert not agency_issues(sentence, {}, [intent])
    sentence.evidence_ids = ['tool']
    sentence.text = 'Python 분석 업무를 주도했습니다.'
    fact = Evidence(evidence_id='tool', experience_id='s', fact_type='technology',
        normalized_fact='Python 사용', evidence_quote='Python 사용', source_type='resume_text',
        source_id='s', assertion_state='resume_stated')
    assert agency_issues(sentence, {'tool': fact}, [intent])


def test_context_type_does_not_falsely_reject_stated_learning():
    req, extraction, valid, _ = golden_case('B-2')
    prepared = prepare_review(req, extraction)
    valid[1].claim_types = ['action_performed', 'learning']
    candidate = WriterOutput(experience_id=req.experience.experience_id, operation='replace_field',
        original_quote=req.experience.current_text, sentences=valid)
    result = validate_candidate(prepared.request, candidate, prepared.analysis.plan, prepared.evidence, FactVerification())
    assert not result.factual_issues


def test_unchanged_adapter_does_not_publish_an_improved_candidate(monkeypatch):
    monkeypatch.setenv('DB_HOST', '127.0.0.1')
    monkeypatch.setenv('RESUME_REVIEW_ENGINE', 'v2-local')
    from test_local_resume_site import setup_service
    service, _, _, request, _ = setup_service('UNCHANGED')
    row = service.review_as('student', request).sentence_reviews[0]
    assert row.status == 'unchanged'
    assert row.suggested_revision is None


def test_evidence_id_renaming_does_not_change_project_selection():
    req, extraction, _, _ = golden_case('B-3')
    first = prepare_review(req, extraction)
    selected = {first.evidence[e].evidence_quote for e in first.analysis.plan.core_evidence_ids}
    for index, fact in enumerate(extraction.extracted_evidence):
        fact.evidence_id = 'reverse-' + str(100 - index)
    second = prepare_review(req, extraction)
    assert selected == {second.evidence[e].evidence_quote for e in second.analysis.plan.core_evidence_ids}


def test_known_action_and_validation_do_not_trigger_role_or_context_slot_questions():
    from app.resume_review_v2.models import EvidenceFacet
    req, extraction, _, _ = golden_case('B-3')
    extraction.facets = [EvidenceFacet(evidence_id=f.evidence_id, slots=(
        ['actions'] if f.fact_type == 'implementation' else
        ['validation_method'] if f.fact_type == 'verification' else ['technologies']))
        for f in extraction.extracted_evidence]
    assert prepare_review(req, extraction).questions == []


def test_role_label_and_expanded_normalization_do_not_authorize_ownership():
    fact = Evidence(evidence_id='role', experience_id='project', fact_type='role',
        normalized_fact='데이터 처리 및 서비스 구현 역할을 맡았다.',
        evidence_quote='데이터 처리 및 서비스 구현', source_type='resume_text',
        source_id='project:role', assertion_state='resume_stated')
    sentence = RevisionSentence(text='데이터 처리와 서비스 구현을 맡았습니다.',
        evidence_ids=['role'], claim_types=['role_owned'])
    assert agency_issues(sentence, {'role': fact})


def test_motivation_does_not_reask_an_already_explained_reason_and_support():
    req, extraction, _, _ = golden_case('B-2')
    assert prepare_review(req, extraction).questions == []
