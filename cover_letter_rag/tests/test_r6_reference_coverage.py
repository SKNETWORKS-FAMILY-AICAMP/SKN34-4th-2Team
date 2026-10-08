"""R6 reference/snapshot/paragraph regression. No DB or real model calls."""
import pytest
from test_project_live_pipeline import pipeline, post
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, EvidenceFacet, ExtractionOutput,
    SourceDocument, SemanticUnit, SourceRef, RevisionSentence, WriterOutput, FactVerification, AnalystOutput, RevisionPlan)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.validation import validate_candidate, validate_analysis, ContractError


def setup_meaning():
    original = 'Haversine 거리 정렬을 구현했습니다. 브랜드 필터를 구현했습니다.'
    req = ReviewInput(experience=Experience(experience_id='exp', kind='project', title='검색 서비스',
        current_text=original, field_path='projects[0].description', content_hash='h'))
    facts = [Evidence(evidence_id=eid, experience_id='exp', fact_type='implementation',
        normalized_fact=quote, evidence_quote=quote, source_type='resume_text', source_id='exp', assertion_state='resume_stated')
        for eid,quote in [('distance','Haversine 거리 정렬을 구현했습니다.'),('filter','브랜드 필터를 구현했습니다.')]]
    unit = SemanticUnit(id='feature', semantic_role='action', meaning='거리 정렬과 브랜드 필터 구현',
        source_refs=[SourceRef(type='applicant_evidence', id=e.evidence_id) for e in facts])
    p = prepare_review(req, ExtractionOutput(experience_id='exp', extracted_evidence=facts, semantic_units=[unit]))
    return p, facts


@pytest.mark.parametrize('split', [False, True])
def test_one_or_two_sentences_have_identical_paragraph_coverage(split):
    p, facts = setup_meaning()
    sentences = ([RevisionSentence(text=e.evidence_quote, evidence_ids=[e.evidence_id], semantic_unit_ids=['feature']) for e in facts]
        if split else [RevisionSentence(text=' '.join(e.evidence_quote for e in facts), evidence_ids=[e.evidence_id for e in facts], semantic_unit_ids=['feature'])])
    writer = WriterOutput(experience_id='exp', operation='replace_field', original_quote=p.request.experience.current_text, sentences=sentences)
    result = validate_candidate(p.request, writer, p.analysis.plan, p.evidence, FactVerification())
    assert not result.section_issues and not result.factual_issues
    missing = validate_candidate(p.request, writer, p.analysis.plan, p.evidence,
        FactVerification(section_meaning_loss=['필터 구현의 의미가 사라짐']))
    assert missing.status != 'READY' and missing.section_issues
    unsupported = validate_candidate(p.request, writer, p.analysis.plan, p.evidence,
        FactVerification(unsupported_claims=['구현 범위를 확대함']))
    assert unsupported.factual_issues


def test_paragraph_does_not_allow_wrong_sentence_citations_or_missing_basis():
    p, facts = setup_meaning()
    writer = WriterOutput(experience_id='exp', operation='replace_field', original_quote=p.request.experience.current_text,
        sentences=[RevisionSentence(text='Haversine 거리 정렬을 구현했습니다.', evidence_ids=['filter'], semantic_unit_ids=['feature'])])
    result = validate_candidate(p.request, writer, p.analysis.plan, p.evidence)
    assert 'unsupported_technology' in {i.code for i in result.factual_issues}
    assert 'TECHNICAL_SIGNAL_LOSS' in {i.code for i in result.section_issues}


def test_turn_id_reconcile_updates_facets_and_semantic_refs_without_alias_guessing():
    p, facts = setup_meaning()
    req = p.request.model_copy(deep=True)
    req.experience.existing_evidence = facts
    req.answer = '브랜드 필터 기능을 테스트했습니다.'
    req.answer_source_id = 'answer'
    fact = Evidence(evidence_id='filter', experience_id='exp', fact_type='verification',
        normalized_fact=req.answer, evidence_quote=req.answer, source_type='user_answer', source_id='answer', assertion_state='user_asserted')
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[fact],
        facets=[EvidenceFacet(evidence_id='filter', slots=['validation_method'])], semantic_units=[
            SemanticUnit(id='new-check', semantic_role='validation', meaning=req.answer,
                source_refs=[SourceRef(type='applicant_evidence', id='filter')])])
    after = prepare_review(req, extraction)
    eid = after.analysis.extracted_evidence[0].evidence_id
    assert eid != 'filter' and 'filter' in after.evidence
    assert any(f.evidence_id == eid for f in after.facets)
    assert next(u for u in after.section_profile.original_semantic_units if u.id == 'new-check').source_refs[0].id == eid
    extraction.facets[0].evidence_id = 'missing'
    with pytest.raises(ContractError, match='unknown profile evidence') as caught: prepare_review(req, extraction)
    assert caught.value.diagnostics['unknown_reference_ids'] == ['missing']


def test_inventory_optional_and_expanded_meaning_not_accumulated_required():
    p, facts = setup_meaning()
    req = p.request.model_copy(deep=True)
    req.experience.existing_evidence = facts
    req.previous_semantic_units = p.section_profile.original_semantic_units
    req.resume_sources = [SourceDocument(source_id='exp:techStack', text='Python, Redis')]
    stack = Evidence(evidence_id='stack', experience_id='exp', fact_type='technology',
        normalized_fact='기술 스택 Python, Redis', evidence_quote='Python, Redis', source_type='resume_text',
        source_id='exp:techStack', assertion_state='resume_stated')
    expanded = req.previous_semantic_units[0].model_copy(deep=True)
    expanded.meaning += ' 기능을 묶어 표현'
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[stack],
        facets=[EvidenceFacet(evidence_id='stack', slots=['technologies'])], semantic_units=[expanded,
            SemanticUnit(id='inventory', semantic_role='technology', meaning=stack.normalized_fact,
                source_refs=[SourceRef(type='applicant_evidence', id='stack')])])
    after = prepare_review(req, extraction)
    assert 'stack' not in after.analysis.plan.core_evidence_ids
    assert 'inventory' in after.section_profile.optional_semantics
    assert 'feature' in after.section_profile.optional_semantics
    assert any(uid != 'feature' and 'feature' in uid for uid in after.section_profile.required_semantics)


def refinement_case(context=True):
    original='잔여 기간 변수의 방향성을 분석했습니다.'
    answer='잔여 기간을 단일 변수로 측정한 AUC는 0.905였습니다. 잔여 기간이 짧을수록 이탈 가능성이 높아졌습니다.'
    req=ReviewInput(experience=Experience(experience_id='exp',kind='project',title='분석',
        current_text=original,field_path='projects[0].description',content_hash='h'),answer=answer,answer_source_id='answer')
    facts=[Evidence(evidence_id=eid,experience_id='exp',fact_type=kind,normalized_fact=text,evidence_quote=text,
        source_type=source,source_id='exp' if source=='resume_text' else 'answer',
        assertion_state='resume_stated' if source=='resume_text' else 'user_asserted')
        for eid,kind,text,source in [('prior','result',original,'resume_text'),
            ('measure','verification',answer[:answer.index(' 잔여 기간')],'user_answer'),
            ('direction','result',answer[answer.index(' 잔여 기간')+1:],'user_answer')]]
    unit=SemanticUnit(id='refined',semantic_role='outcome',meaning=answer,
        source_refs=[SourceRef(type='applicant_evidence',id=e.evidence_id) for e in facts],
        context_source_refs=[SourceRef(type='applicant_evidence',id='prior')] if context else [])
    extraction=ExtractionOutput(experience_id='exp',extracted_evidence=facts,semantic_units=[unit])
    return req,extraction


@pytest.mark.parametrize('context',[False,True])
def test_explicit_context_contract_does_not_require_duplicate_resume_citation(context):
    req,extraction=refinement_case(context);p=prepare_review(req,extraction)
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=req.answer,evidence_ids=['measure','direction'],semantic_unit_ids=['refined'])])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence)
    assert bool(verdict.section_issues) is not context
    if context:
        diagnostic=p.semantic_preparation['contextual_references'][0]
        assert {r['id'] for r in diagnostic['required_refs']}=={'measure','direction'}
    else:assert 'incomplete_reference_coverage' in verdict.section_issues[0].detail


@pytest.mark.parametrize('missing',['measure','direction'])
def test_complementary_new_clauses_are_still_conjunctive(missing):
    req,extraction=refinement_case();p=prepare_review(req,extraction)
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=req.answer,evidence_ids=[eid for eid in ['measure','direction'] if eid!=missing],semantic_unit_ids=['refined'])])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence)
    assert any('incomplete_reference_coverage' in i.detail and missing in i.detail for i in verdict.section_issues)


def test_context_annotation_never_overrides_independent_meaning_failure():
    req,extraction=refinement_case();p=prepare_review(req,extraction)
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='AUC는 0.905였습니다.',evidence_ids=['measure','direction'],semantic_unit_ids=['refined'])])
    verified=FactVerification(unsupported_claims=['측정 조건이 다름'],section_meaning_loss=['관계 방향 누락'])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence,verified)
    assert 'semantic_unsupported_claim' in {i.code for i in verdict.factual_issues}
    assert 'SECTION_MEANING_LOSS' in {i.code for i in verdict.section_issues}


@pytest.mark.parametrize('bad',['all','new','missing'])
def test_invalid_context_reference_contract_is_rejected(bad):
    req,extraction=refinement_case()
    unit=extraction.semantic_units[0]
    unit.context_source_refs=unit.source_refs if bad=='all' else [SourceRef(type='applicant_evidence',id='measure' if bad=='new' else 'missing')]
    with pytest.raises(ContractError,match='invalid contextual semantic reference'):prepare_review(req,extraction)


@pytest.mark.parametrize('change',['inactive','other_owner','wrong_source'])
def test_restored_context_annotation_is_rechecked_against_current_source_state(change):
    req,extraction=refinement_case();p=prepare_review(req,extraction)
    fact=p.evidence['prior']
    if change=='inactive':fact.assertion_state='superseded'
    elif change=='other_owner':fact.experience_id='other'
    else:fact.source_id='other'
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=req.answer,evidence_ids=['measure','direction'],semantic_unit_ids=['refined'])])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence)
    assert any(i.code=='invalid_context_reference' for i in verdict.section_issues)


def test_mixed_intent_still_requires_its_own_reference():
    from app.resume_review_v2.models import ApplicantIntentClaim
    req,extraction=refinement_case()
    quote='입사 후 분석을 더 공부하고 싶습니다.'
    req.experience.current_text+=' '+quote
    extraction.intent_claims=[ApplicantIntentClaim(id='goal',source_section_id='exp',intent_type='learning_plan',
        text=quote,evidence_quote=quote,source_type='resume_text',source_id='exp',state='resume_stated')]
    unit=extraction.semantic_units[0]
    unit.source_refs.append(SourceRef(type='applicant_intent',id='goal'));unit.meaning+=' '+quote
    p=prepare_review(req,extraction)
    writer=WriterOutput(experience_id='exp',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=req.answer,evidence_ids=['measure','direction'],semantic_unit_ids=['refined'])])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence)
    assert any('applicant_intent:goal' in i.detail for i in verdict.section_issues)
    unit.context_source_refs.append(SourceRef(type='applicant_intent',id='goal'))
    with pytest.raises(ContractError,match='invalid contextual semantic reference'):prepare_review(req,extraction)


def test_inactive_assertion_cannot_reactivate_with_a_new_extraction_id():
    p, facts = setup_meaning()
    req = p.request.model_copy(deep=True)
    old = facts[0].model_copy(update={'assertion_state':'retracted'})
    req.experience.existing_evidence = [old]
    new = facts[0].model_copy(update={'evidence_id':'new-id'})
    with pytest.raises(ContractError, match='reactivated'):
        validate_analysis(req, AnalystOutput(experience_id='exp', extracted_evidence=[new],
            plan=RevisionPlan(objective='확인', operation='no_change')))


def test_mixed_inventory_keeps_atomic_role_without_forcing_tool_list():
    p, facts = setup_meaning()
    req = p.request.model_copy(deep=True)
    req.experience.current_text += ' API 연동을 담당했습니다.'
    req.resume_sources = [SourceDocument(source_id='exp:techStack', text='Python, Redis')]
    role = Evidence(evidence_id='role', experience_id='exp', fact_type='role',
        normalized_fact='API 연동 담당', evidence_quote='API 연동을 담당했습니다.',
        source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    stack = Evidence(evidence_id='stack', experience_id='exp', fact_type='technology',
        normalized_fact='Python, Redis', evidence_quote='Python, Redis',
        source_type='resume_text', source_id='exp:techStack', assertion_state='resume_stated')
    mixed = SemanticUnit(id='role-tools', semantic_role='role', meaning='API 연동 역할과 기술 목록',
        source_refs=[SourceRef(type='applicant_evidence', id=e.evidence_id) for e in [role,stack]])
    after = prepare_review(req, ExtractionOutput(experience_id='exp', extracted_evidence=[role,stack],
        facets=[EvidenceFacet(evidence_id='role', slots=['personal_role']),
                EvidenceFacet(evidence_id='stack', slots=['technologies'])], semantic_units=[mixed]))
    assert 'role-tools' in after.section_profile.optional_semantics
    units = {u.id:u for u in after.section_profile.original_semantic_units}
    assert any(units[uid].semantic_role == 'role' and
        units[uid].source_refs == [SourceRef(type='applicant_evidence', id='role')]
        for uid in after.section_profile.required_semantics)


@pytest.mark.parametrize('broken', ['facet', 'semantic'])
def test_changed_source_failure_keeps_answers_not_stale_derived_snapshot(pipeline, monkeypatch, broken):
    from app.resume_review_v2.llm import LangChainReviewLLM
    from app.resume_apply import rebase_review_response
    client, reviews, calls, db = pipeline
    initial = post(client, 'initial')
    q = initial['questions'][0]
    content = db.get_owned_resume.return_value['content']
    content['projects'][0]['description'] += ' 검색 기능을 개선했습니다.'
    reviews['initial'] = rebase_review_response(reviews['initial'], content)
    original = LangChainReviewLLM._call
    def invoke(self, prompt, payload, schema):
        result, usage = original(self, prompt, payload, schema)
        if schema.__name__ == 'BatchExtractionOutput':
            item = result.item_0
            if broken == 'facet': item.facets.append(EvidenceFacet(evidence_id='unknown', slots=['actions']))
            else: item.semantic_units.append(SemanticUnit(id='bad', semantic_role='action', meaning='테스트',
                source_refs=[SourceRef(type='applicant_evidence', id='unknown')]))
        return result, usage
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    before = len(calls)
    result = post(client, 'answer', previous_review_id='initial', answers=[{
        'question_id':q['question_id'], 'field_path':q['field_path'], 'question':q['question'], 'answer':'정상 조회 결과를 대조했습니다.'}])
    record = result['telemetry']['v2_results'][0]
    assert record['validation']['status'] == 'REJECTED'
    assert record['section_profile'] is None and record['evidence_facets'] == []
    # Source validation succeeded; derived-plan failure cannot erase these facts.
    assert {f['evidence_id'] for f in record['evidence_state']} == {'action','check'}
    assert record['candidate'] is None
    assert result['confirmed_answers'][-1]['answer'] == '정상 조회 결과를 대조했습니다.'
    failure = record['debug_trace']['extraction_failure']
    assert failure['facts_approved'] and failure['failure_boundary']=='planning'
    assert failure['unknown_reference_ids'] == ['unknown']
    assert '정상 조회' not in str(failure)
    assert [stage for stage,_,_ in calls[before:]] == ['BatchExtractionOutput']
