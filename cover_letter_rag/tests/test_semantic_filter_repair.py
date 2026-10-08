"""R7 step 2 transmission contracts, not a model writing-quality evaluation."""
import pytest
from app.resume_review_v2.models import (Experience,ReviewInput,Evidence,EvidenceFacet,ExtractionOutput,
    SemanticUnit,SourceRef,RevisionSentence,WriterOutput,ValidationIssue)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.section_semantics import editorial_brief
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.validation import validate_candidate


def mixed_selection():
    original='분류 모델을 비교했습니다. 보조 도구는 Python입니다.'
    answer='비교 후 후보 B를 최종 선택했습니다. 정확한 평가 수치는 기억나지 않습니다.'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='분류 비교',
        field_path='projects[0].description',current_text=original,content_hash='h'),answer=answer,answer_source_id='answer')
    facts=[]
    for eid,kind,text,source,state in [
        ('compare','action','분류 모델을 비교했습니다.','resume_text','resume_stated'),
        ('tool','technology','보조 도구는 Python입니다.','resume_text','resume_stated'),
        ('choice','result','비교 후 후보 B를 최종 선택했습니다.','user_answer','user_asserted'),
        ('score','result','정확한 평가 수치는 기억나지 않습니다.','user_answer','uncertain')]:
        facts.append(Evidence(evidence_id=eid,experience_id='p',fact_type=kind,normalized_fact=text,
            evidence_quote=text,source_type=source,source_id='p' if source=='resume_text' else 'answer',assertion_state=state))
    extraction=ExtractionOutput(experience_id='p',extracted_evidence=facts,
        facets=[EvidenceFacet(evidence_id='compare',slots=['actions']),
                EvidenceFacet(evidence_id='tool',slots=['technologies'],material=False),
                EvidenceFacet(evidence_id='choice',slots=['outcome'])],
        semantic_units=[SemanticUnit(id='mixed',semantic_role='outcome',meaning='도구와 후보 선택을 연결한 의미',
            source_refs=[SourceRef(type='applicant_evidence',id=i) for i in ['tool','choice']])])
    return prepare_review(req,extraction)


def test_filtered_mixed_unit_cannot_hide_selected_atomic_choice():
    p=mixed_selection()
    assert 'choice' in p.analysis.plan.core_evidence_ids
    assert 'tool' not in p.analysis.plan.core_evidence_ids+p.analysis.plan.supporting_evidence_ids
    units=p.section_profile.original_semantic_units
    assert all(u.id!='mixed' for u in units)  # No invented half-relationship.
    assert any(any(r.id=='choice' for r in u.source_refs) for u in units)
    brief=editorial_brief(p.request)
    assert any(any(r['id']=='choice' for r in u['source_refs']) for u in brief['must_express'])
    assert not any(r.id=='score' for u in units for r in u.source_refs)
    excluded=p.semantic_preparation['excluded_units']
    assert any(r['category']=='active_not_selected' for unit in excluded for r in unit['references'])


def inactive_mixed(state):
    original='검색 API를 구현했습니다. 출력값을 비교했습니다. 성능은 0.905입니다.'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='서비스',
        field_path='projects[0].description',current_text=original,content_hash='h'))
    facts=[Evidence(evidence_id=eid,experience_id='p',fact_type=kind,normalized_fact=text,
        evidence_quote=text,source_type='resume_text',source_id='p',assertion_state=assertion)
        for eid,kind,text,assertion in [
            ('action','implementation','검색 API를 구현했습니다.','resume_stated'),
            ('check','verification','출력값을 비교했습니다.','resume_stated'),
            ('blocked','result','성능은 0.905입니다.',state if state!='conflict' else 'resume_stated')]]
    if state=='conflict':
        req.answer='성능 측정은 확실하지 않습니다.';req.answer_source_id='answer'
        facts.append(Evidence(evidence_id='conflict',experience_id='p',fact_type='context',
            normalized_fact=req.answer,evidence_quote=req.answer,source_type='user_answer',source_id='answer',
            assertion_state='uncertain',conflicts_with_evidence_ids=['blocked']))
    extraction=ExtractionOutput(experience_id='p',extracted_evidence=facts,
        facets=[EvidenceFacet(evidence_id='action',slots=['actions']),
                EvidenceFacet(evidence_id='check',slots=['validation_method'])],
        semantic_units=[SemanticUnit(id='mixed',semantic_role='outcome',
            meaning='검색 API 구현으로 전체 모델 성능 0.905를 달성했습니다.',
            source_refs=[SourceRef(type='applicant_evidence',id=eid) for eid in ['action','blocked']])])
    return req,extraction


@pytest.mark.parametrize('state',['uncertain','contradicted','retracted','superseded','conflict'])
def test_inactive_mixed_meaning_is_removed_and_only_independent_atoms_recovered(state):
    req,extraction=inactive_mixed(state)
    p=prepare_review(req,extraction)
    units=p.section_profile.original_semantic_units
    assert all(u.id!='mixed' and '0.905' not in u.meaning for u in units)
    assert any(u.meaning=='검색 API를 구현했습니다.' for u in units)
    assert any(u.meaning=='출력값을 비교했습니다.' for u in units)
    assert {'fact:action','fact:check'} <= set(p.section_profile.required_semantics)
    assert 'blocked' not in p.section_profile.evidence_claim_ids
    diagnostic=p.semantic_preparation
    assert diagnostic['state']=='atomic_fallback'
    rejected=diagnostic['excluded_units'][0]
    assert rejected['semantic_unit_id']=='mixed'
    assert rejected['references'][0]['category']=='inactive_evidence'
    assert rejected['references'][0]['assertion_state']==('resume_stated' if state=='conflict' else state)
    writer=WriterOutput(experience_id='p',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='전체 모델 성능은 0.905입니다.',evidence_ids=['action','blocked'])])
    assert validate_candidate(p.request,writer,p.analysis.plan,p.evidence).factual_issues


@pytest.mark.parametrize('order',[['blocked','missing'],['missing','blocked']])
def test_inactive_reference_cannot_hide_a_missing_reference(order):
    from app.resume_review_v2.validation import ContractError
    req,extraction=inactive_mixed('uncertain')
    extraction.semantic_units[0].source_refs=[SourceRef(type='applicant_evidence',id=eid) for eid in order]
    with pytest.raises(ContractError) as caught:prepare_review(req,extraction)
    assert caught.value.diagnostics['reference_category']=='missing_reference'
    assert caught.value.diagnostics['unknown_reference_ids']==['missing']


@pytest.mark.parametrize('broken,category',[('owner','wrong_experience'),('source','wrong_source'),('quote','quote_absent')])
def test_inactive_reference_does_not_bypass_owning_source_validation(broken,category):
    from app.resume_review_v2.validation import ContractError
    req,extraction=inactive_mixed('uncertain')
    fact=extraction.extracted_evidence[-1]
    if broken=='owner':fact.experience_id='other'
    elif broken=='source':fact.source_id='other'
    else:fact.evidence_quote='原文にない引用'
    with pytest.raises(ContractError) as caught:prepare_review(req,extraction)
    assert caught.value.diagnostics['reference_category']==category


def integrated_experiment():
    original='분류 모델을 비교했습니다.'
    answer=('LightGBM을 최종 모델로 선정했습니다. XGBoost의 threshold는 0.5, 0.3, 0.2, 0.1을 시험했고 '
        'F1은 0.2257, 0.2538, 0.2612, 0.2592였으며 시험한 값 중 0.2에서 가장 높았습니다.')
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='분석',
        current_text=original,field_path='projects[0].description',content_hash='h'),answer=answer,answer_source_id='answer')
    choice='LightGBM을 최종 모델로 선정했습니다.'
    experiment=answer[len(choice)+1:]
    facts=[Evidence(evidence_id=eid,experience_id='p',fact_type=kind,normalized_fact=text,
        evidence_quote=text,source_type=source,source_id='p' if source=='resume_text' else 'answer',
        assertion_state='resume_stated' if source=='resume_text' else 'user_asserted')
        for eid,kind,text,source in [('compare','action',original,'resume_text'),
            ('choice','result',choice,'user_answer'),('experiment','verification',experiment,'user_answer')]]
    extraction=ExtractionOutput(experience_id='p',extracted_evidence=facts,
        facets=[EvidenceFacet(evidence_id='compare',slots=['actions']),
            EvidenceFacet(evidence_id='choice',slots=['outcome']),EvidenceFacet(evidence_id='experiment',slots=['validation_method'])],
        semantic_units=[SemanticUnit(id='selection',semantic_role='outcome',meaning=choice,
            source_refs=[SourceRef(type='applicant_evidence',id='choice')]),
            SemanticUnit(id='experiment-conclusion',semantic_role='validation',
                meaning='XGBoost에서 시험한 threshold 중 0.2의 F1이 약 0.2612로 가장 높았습니다.',
                source_refs=[SourceRef(type='applicant_evidence',id='experiment')],
                optional_details=['0.5, 0.3, 0.2, 0.1','0.2257, 0.2538, 0.2612, 0.2592'])])
    return req,extraction


def test_experiment_inventory_is_optional_without_losing_bounded_conclusion():
    from app.resume_review_v2.models import FactVerification
    req,extraction=integrated_experiment();p=prepare_review(req,extraction)
    brief=editorial_brief(p.request)
    required=next(u for u in brief['must_express'] if u['id']=='experiment-conclusion')
    original_unit=next(u for u in p.request.section_profile.original_semantic_units if u.id=='experiment-conclusion')
    assert '시험한' in original_unit.meaning and 'XGBoost' in original_unit.meaning
    assert '0.2612' in original_unit.meaning and 'optional_details' not in required
    assert 'meaning' not in required and required['source_refs']==[{'type':'applicant_evidence','id':'experiment'}]
    assert brief['compressible_details'][0]['details']==extraction.semantic_units[1].optional_details
    assert p.evidence['experiment'].evidence_quote==extraction.extracted_evidence[2].evidence_quote
    writer=WriterOutput(experience_id='p',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='분류 모델을 비교해 LightGBM을 최종 선정했습니다.',
            evidence_ids=['compare','choice'],semantic_unit_ids=['fact:compare','selection']),
            RevisionSentence(text=original_unit.meaning,evidence_ids=['experiment'],semantic_unit_ids=['experiment-conclusion'])])
    verdict=validate_candidate(p.request,writer,p.analysis.plan,p.evidence,FactVerification())
    assert verdict.status=='READY',verdict
    # The same meaning gate still blocks omitting the experiment conclusion.
    writer.sentences.pop()
    assert validate_candidate(p.request,writer,p.analysis.plan,p.evidence).section_issues


def test_optional_detail_cannot_introduce_an_unquoted_experiment_value():
    req,extraction=integrated_experiment()
    extraction.semantic_units[1].optional_details=['F1은 0.999였습니다.']
    prepared=prepare_review(req,extraction)
    assert prepared.semantic_preparation['excluded_optional_details']==[dict(
        semantic_unit_id='experiment-conclusion',reason='quote_absent',details=['F1은 0.999였습니다.'])]
    assert not prepared.request.section_profile.original_semantic_units[-1].optional_details
    assert '0.999' not in str(editorial_brief(prepared.request))


def test_integrated_limitation_meaning_remains_required():
    text='문항 분석과 근거 추적을 구현했습니다. 출력 오류를 비교해 재시험했고 일부 개선됐지만 잔존 오류가 있습니다.'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='서비스',current_text=text,
        field_path='projects[0].description',content_hash='h'))
    facts=[Evidence(evidence_id=eid,experience_id='p',fact_type=kind,normalized_fact=quote,evidence_quote=quote,
        source_type='resume_text',source_id='p',assertion_state='resume_stated') for eid,kind,quote in [
            ('implementation','implementation','문항 분석과 근거 추적을 구현했습니다.'),
            ('verification','verification','출력 오류를 비교해 재시험했고 일부 개선됐지만 잔존 오류가 있습니다.')]]
    extraction=ExtractionOutput(experience_id='p',extracted_evidence=facts,semantic_units=[
        SemanticUnit(id='flow',semantic_role='action',meaning=facts[0].normalized_fact,
            source_refs=[SourceRef(type='applicant_evidence',id='implementation')]),
        SemanticUnit(id='bounded-validation',semantic_role='validation',meaning=facts[1].normalized_fact,
            source_refs=[SourceRef(type='applicant_evidence',id='verification')])])
    p=prepare_review(req,extraction);brief=editorial_brief(p.request)
    assert {u['id'] for u in brief['must_express']}=={'flow','bounded-validation'}
    assert any('잔존 오류' in u.meaning for u in p.request.section_profile.original_semantic_units if u.id in {r['id'] for r in brief['must_express']})
    assert brief['compressible_details']==[]


def test_rewrite_source_focus_uses_same_brief_without_optional_quota_or_duplicate_quotes():
    p=mixed_selection();client=LangChainReviewLLM.__new__(LangChainReviewLLM)
    calls=[];client._call=lambda system,payload,schema:calls.append((system,payload))
    facts=[p.evidence[i] for i in p.analysis.plan.core_evidence_ids+p.analysis.plan.supporting_evidence_ids]
    client.write(p.request,p.analysis.plan,facts)
    client.write(p.request,p.analysis.plan,facts,[ValidationIssue(code='quality',detail='중복 설명을 통합')],
        '분류 모델을 비교하고 후보 B를 최종 선택했습니다.')
    first,repair=calls[0][1],calls[1][1]
    assert first['rewrite_source_review'] is None
    assert first['editorial_brief']==repair['editorial_brief']
    review=repair['rewrite_source_review']
    assert review['prior_draft_is_not_approved'] is True
    assert {'type':'applicant_evidence','id':'choice'} in review['source_refs_to_recheck']
    assert all(ref['id'] not in {'tool','score'} for ref in review['source_refs_to_recheck'])
    assert all('quote' not in ref for ref in review['source_refs_to_recheck'])
    assert 'user_answer' not in repair


@pytest.mark.parametrize('text',[
    '후보 B의 최종 성능은 0.999였습니다.',
    '모든 모델의 개발을 총괄했습니다.',
])
def test_uncertain_score_and_new_responsibility_are_still_blocked(text):
    p=mixed_selection()
    writer=WriterOutput(experience_id='p',operation='replace_field',original_quote=p.request.experience.current_text,
        sentences=[RevisionSentence(text=text,evidence_ids=['choice'])])
    result=validate_candidate(p.request,writer,p.analysis.plan,p.evidence)
    assert result.factual_issues and result.status!='READY'
