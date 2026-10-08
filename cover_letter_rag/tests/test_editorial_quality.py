"""Product contracts, not assertions of live writing quality."""
import pytest
from test_section_golden import golden_case, ScriptedTransport
from app.resume_review_v2.engine import ReviewEngineV2
from app.resume_review_v2.models import (Evidence, RevisionSentence, WriterOutput,
    FactVerification, ApplicantIntentClaim, SourceRef, EditorialAdvice, ValidationIssue)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.section_semantics import editorial_brief, agency_issues
from app.resume_review_v2.validation import validate_candidate, ContractError, validate_apply_snapshot
from app.resume_review_v2.llm import LangChainReviewLLM


def test_minor_editorial_advice_does_not_override_verified_improvement():
    req, extraction, valid, _ = golden_case('B-1')
    prepared = prepare_review(req, extraction)
    candidate = WriterOutput(experience_id=req.experience.experience_id, operation='replace_field',
        original_quote=req.experience.current_text, sentences=valid)
    advice = [EditorialAdvice(kind='redundancy', detail='검증 기능 설명이 다소 반복됩니다.')]
    verdict = validate_candidate(prepared.request, candidate, prepared.analysis.plan, prepared.evidence,
        FactVerification(editorial_advice=advice, revision_quality='improved'))
    assert verdict.status == 'READY' and verdict.editorial_advice == advice
    for unsafe in (FactVerification(quality_issues=[ValidationIssue(code='unknown_defect', detail='검토 필요')]),
                   FactVerification(unsupported_claims=['근거 없는 인과']),
                   FactVerification(section_meaning_loss=['핵심 단계 누락'])):
        assert validate_candidate(prepared.request, candidate, prepared.analysis.plan,
            prepared.evidence, unsafe).status == 'REWRITE'
    assert validate_candidate(prepared.request, candidate, prepared.analysis.plan, prepared.evidence,
        FactVerification(editorial_advice=advice, revision_quality='no_better')).status == 'UNCHANGED'


@pytest.mark.parametrize('text', [
    '초기 계획보다 구현 범위가 커지는 경우가 있어 완료 조건을 먼저 정해 보완하고 있습니다.',
    '목표 처리량과 실제 결과를 비교했습니다.',
    '동료의 데이터 확인 업무를 지원하며 성장한 경험입니다.',
])
def test_fact_descriptions_are_not_intentions_because_of_nouns(text):
    from app.resume_review_v2.validation import validate_intent_sentence
    sentence = RevisionSentence(text=text, claim_types=['action_performed'])
    assert not validate_intent_sentence(sentence,{})


@pytest.mark.parametrize('text,types', [
    ('분석을 서비스 개선에 활용하고 싶습니다.', []),
    ('반복 확인을 자동화할 계획입니다.', []),
    ('분석가로 성장하겠습니다.', []),
    ('새 업무에 기여하겠습니다.', []),
    ('산업의 혁신이 지원 이유입니다.', ['motivation']),
    ('업무를 자동화합니다.', ['future_plan']),
])
def test_explicit_or_typed_intentions_still_require_active_intent(text,types):
    from app.resume_review_v2.validation import validate_intent_sentence
    sentence = RevisionSentence(text=text,claim_types=types)
    assert validate_intent_sentence(sentence,{})[0].code=='unsupported_intent'


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


def test_composition_groups_reuse_plan_without_becoming_a_second_preservation_gate():
    req,extraction,valid,_=golden_case('B-1')
    p=prepare_review(req,extraction)
    brief=editorial_brief(p.request)
    expected=[dict(purpose=i.purpose,semantic_unit_ids=i.semantic_unit_ids) for i in p.sentence_plan.items]
    assert brief['meaning_groups']==expected
    required=set(p.section_profile.required_semantics)
    assert {u['id'] for u in brief['must_express']}==required
    client=LangChainReviewLLM.__new__(LangChainReviewLLM);captured=[]
    client._call=lambda prompt,payload,schema:captured.append(payload)
    candidate=WriterOutput(experience_id=req.experience.experience_id,operation='replace_field',
        original_quote=req.experience.current_text,sentences=valid)
    client.write(p.request,p.analysis.plan,list(p.evidence.values()))
    client.verify(p.request,candidate,list(p.evidence.values()),[],[])
    assert captured[0]['editorial_brief']==captured[1]['editorial_brief']
    assert 'core_evidence_ids' not in captured[1] and 'preserved_evidence_ids' not in captured[1]
    # Hints can be ignored/reordered without modifying actual source coverage.
    p.request.sentence_plan.items=[]
    assert not validate_candidate(p.request,candidate,p.analysis.plan,p.evidence).section_issues
    assert set(p.section_profile.required_semantics)==required


def test_future_plan_double_extraction_uses_validated_intent_not_performed_fact():
    from app.resume_review_v2.models import Experience, ExtractionOutput, ReviewInput, SemanticUnit
    quote='입사 초기에는 데이터 구조를 이해하고 업무 흐름을 파악하는 데 집중하겠습니다.'
    req=ReviewInput(experience=Experience(experience_id='future',kind='other',
        title='입사 후 포부',current_text=quote,field_path='selfIntroduction.aspiration.body',content_hash='hash'))
    claim=ApplicantIntentClaim(id='plan',source_section_id='future',intent_type='short_term_plan',
        text=quote,source_type='resume_text',source_id='future',evidence_quote=quote,state='resume_stated')
    wrong=Evidence(evidence_id='performed',experience_id='future',fact_type='action',
        normalized_fact='데이터 구조를 파악했다',evidence_quote=quote,source_type='resume_text',
        source_id='future',assertion_state='resume_stated')
    extraction=ExtractionOutput(experience_id='future',extracted_evidence=[wrong],intent_claims=[claim],
        semantic_units=[SemanticUnit(id='future-plan',semantic_role='early_adaptation',meaning=quote,
            source_refs=[SourceRef(type='applicant_intent',id='plan')])])
    prepared=prepare_review(req,extraction)
    assert not prepared.evidence
    assert prepared.intents[0].id=='plan'
    assert prepared.semantic_preparation['future_fact_recovery']['dropped_fact_ids']==['performed']
    # A fact used by another semantic assertion cannot be silently discarded.
    extraction.semantic_units.append(SemanticUnit(id='performed-work',semantic_role='action',meaning=quote,
        source_refs=[SourceRef(type='applicant_evidence',id='performed')]))
    with pytest.raises(ContractError,match='applicant intent cannot be a performed factual claim'):
        prepare_review(req,extraction)


def test_one_sentence_can_integrate_multiple_required_meanings_but_not_drop_limits():
    from app.resume_review_v2.models import Experience,ExtractionOutput,ReviewInput,SemanticUnit
    quotes=['출력 검사 기능을 구현했습니다.','원문과 출력값을 대조해 재시험했습니다.',
        '일부 오류는 줄었지만 의미 누락과 반복은 남았습니다.']
    req=ReviewInput(experience=Experience(experience_id='exp',kind='project',title='검사 도구',
        current_text=' '.join(quotes),field_path='projects[0].description',content_hash='h'))
    facts=[Evidence(evidence_id=str(i),experience_id='exp',fact_type=kind,normalized_fact=quote,
        evidence_quote=quote,source_type='resume_text',source_id='exp',assertion_state='resume_stated')
        for i,(kind,quote) in enumerate(zip(['implementation','verification','result'],quotes))]
    units=[SemanticUnit(id=str(i),semantic_role=role,meaning=quote,
        source_refs=[SourceRef(type='applicant_evidence',id=str(i))])
        for i,(role,quote) in enumerate(zip(['action','validation','outcome'],quotes))]
    p=prepare_review(req,ExtractionOutput(experience_id='exp',extracted_evidence=facts,semantic_units=units))
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='출력 검사 기능을 구현해 원문과 출력값을 대조·재시험했으며 일부 오류는 줄었지만 의미 누락과 반복은 남았습니다.',
            evidence_ids=['0','1','2'],semantic_unit_ids=['0','1','2'])])
    assert validate_candidate(p.request,writer,p.analysis.plan,p.evidence).status=='READY'
    # A successful citation gate is not semantic approval. Independent findings
    # about actual test/result/limitation changes remain blocking.
    findings=FactVerification(unsupported_claims=['재시험 수행을 성공 입증으로 확대'],
        weakened_original_facts=['잔존 의미 누락 범위를 축소'],section_meaning_loss=['잔존 한계 유실'])
    v=validate_candidate(p.request,writer,p.analysis.plan,p.evidence,findings)
    assert {'semantic_unsupported_claim','weakened_original_fact'} <= {i.code for i in v.factual_issues}
    assert 'SECTION_MEANING_LOSS' in {i.code for i in v.section_issues}
    assert v.status=='REWRITE'


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
