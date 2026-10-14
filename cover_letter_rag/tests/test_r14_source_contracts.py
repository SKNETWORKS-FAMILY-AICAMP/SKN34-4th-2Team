"""Saved R14 sources/derived states, not recovered missing raw Analyze or live QA."""
import json
from pathlib import Path
from copy import deepcopy
import pytest
from app.resume_review_v2.models import (Experience,ReviewInput,Evidence,EvidenceFacet,ExtractionOutput,
    SemanticUnit,SourceRef,RevisionSentence,WriterOutput,FactVerification,QuestionNeed,GapQuestion)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.section_semantics import editorial_brief
from app.resume_review_v2.llm import scoped_evidence,LangChainReviewLLM
from app.resume_review_v2.validation import validate_candidate,validate_intent_sentence,ContractError
from app.resume_review_v2.question_planning import select_question,approved_question

DATA=json.loads(Path(__file__).with_name('r14_contract_sources.json').read_text(encoding='utf-8'))


def saved(rid,path):
    case=next(c for c in DATA if c['review_id']==rid and c['experience']['field_path']==path)
    facts=[Evidence.model_validate(f) for f in case['facts']]
    roots=case['historical_sources']
    exp=Experience.model_validate(case['experience']).model_copy(update={'existing_evidence':facts})
    req=ReviewInput(experience=exp,answer=case['answer'],answer_source_id='saved-answer' if case['answer'] else '',
        historical_resume_sources=roots,
        resume_sources=[s for s in roots if s['source_id']!=exp.experience_id],existing_intents=case['intents'])
    extraction=ExtractionOutput(experience_id=exp.experience_id,extracted_evidence=[],facets=case['facets'],semantic_units=case['units'])
    return case,req,extraction


@pytest.mark.parametrize('path,eid',[('coreCompetencies.text','ev3-5'),('selfIntroduction.intro.body','ev4-4')])
@pytest.mark.parametrize('label',['direction','intended_contribution'])
def test_raw_role_unavailable_manual_labels_cannot_block_actual_sourced_current_or_performed_claim(path,eid,label):
    # R131 raw semantic role/meaning is unavailable. This is an explicit manual
    # reconstruction of the failing structural gate using its saved real facts.
    case,req,extraction=saved(131,path)
    fact=next(f for f in req.experience.existing_evidence if f.evidence_id==eid)
    extraction.semantic_units=[SemanticUnit(id='manual-label',semantic_role=label,meaning=fact.normalized_fact,
        source_refs=[SourceRef(type='applicant_evidence',id=eid)])]
    prepared=prepare_review(req,extraction)
    assert prepared.analysis.plan.operation=='replace_field'
    unit=next(u for u in prepared.section_profile.original_semantic_units if u.id=='manual-label')
    assert unit.semantic_role not in {'direction','intended_contribution'}
    sentence=RevisionSentence(text=fact.evidence_quote,evidence_ids=[eid],claim_types=['motivation'])
    assert validate_intent_sentence(sentence,{})==[]
    sentence.text='앞으로 서비스를 총괄하고자 합니다.'
    assert validate_intent_sentence(sentence,{})[0].code=='unsupported_intent'


def test_r134_derived_implementation_is_not_a_mandatory_claim_but_checked_condition_remains_protected():
    case,req,extraction=saved(134,'projects[1].description')
    p=prepare_review(req,extraction);brief=editorial_brief(p.request)
    unit=next(u for u in brief['must_express'] if u['id'].endswith('su1-3') and len(u['source_refs'])==2)
    assert 'meaning' not in unit
    assert {r['id'] for r in unit['source_refs']}=={'ev1-4','ev2-3'}
    facts={f.evidence_id:f for f in req.experience.existing_evidence}
    assert facts['ev2-3'].evidence_quote.endswith('확인했습니다.')
    permitted=[p.evidence[eid] for eid in dict.fromkeys(p.analysis.plan.core_evidence_ids+p.analysis.plan.supporting_evidence_ids+p.analysis.plan.preserved_evidence_ids)]
    rows=scoped_evidence(p.request,permitted)
    assert next(r for r in rows if r['evidence_id']=='ev1-4')['source_context']['source_basis']=='verified_historical_source'
    first=WriterOutput(experience_id=req.experience.experience_id,operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence.model_validate(s) for s in case['writer_sentences'][0]])
    # Construct verifier verdict from the saved substantive finding, not raw replay.
    rejected=validate_candidate(p.request,first,p.analysis.plan,p.evidence,
        FactVerification(unsupported_claims=['없는 운영시간 처리의 확인을 직접 구현으로 확대'],weakened_original_facts=['실제 확인 단계 누락']))
    assert rejected.status!='READY' and rejected.factual_issues
    repaired=first.model_copy(update={'sentences':[RevisionSentence.model_validate(s) for s in case['writer_sentences'][1]]})
    # Configuration vs filtering interpretation remains the real verifier's job;
    # no string exception approves R134's second candidate here.
    assert not validate_candidate(p.request,repaired,p.analysis.plan,p.evidence).factual_issues
    assert validate_candidate(p.request,repaired,p.analysis.plan,p.evidence,
        FactVerification(unsupported_claims=['근거보다 넓은 실제 작업 범위 주장'])).status!='READY'


def test_r133_actual_question_analysis_stage_reaches_source_contract_even_when_summary_omitted_it():
    case,req,extraction=saved(133,'projects[2].description');p=prepare_review(req,extraction)
    brief=editorial_brief(p.request)
    protected={r['id'] for u in brief['must_express'] for r in u['source_refs']}
    assert 'ev2-3' in protected
    source=p.evidence['ev2-3'].evidence_quote
    assert '지원 문항을 분석하고' in source
    assert all('meaning' not in u for u in brief['must_express'])
    current=WriterOutput(experience_id=req.experience.experience_id,operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=req.experience.current_text,evidence_ids=list(p.evidence),
            semantic_unit_ids=p.section_profile.required_semantics)])
    verdict=validate_candidate(p.request,current,p.analysis.plan,p.evidence,
        FactVerification(section_meaning_loss=['독립적인 문항 분석 수행 단계가 누락됨']))
    assert any(i.code=='SECTION_MEANING_LOSS' for i in verdict.section_issues)


def test_normalized_fact_cannot_authorize_a_number_missing_from_its_quote():
    case,req,extraction=saved(132,'projects[0].description');p=prepare_review(req,extraction)
    eid='ev0-1';p.evidence[eid].normalized_fact+=' 성능 0.9999'
    writer=WriterOutput(experience_id=req.experience.experience_id,operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='성능 0.9999를 확인했습니다.',evidence_ids=[eid])])
    assert 'unsupported_number' in {i.code for i in validate_candidate(p.request,writer,p.analysis.plan,p.evidence).factual_issues}


@pytest.mark.parametrize('same',[True,False])
def test_duplicate_semantic_rows_are_exactly_deduped_or_diagnosed_without_erasing_approved_new_facts(same):
    case,req,extraction=saved(132,'projects[0].description')
    fact=Evidence(evidence_id='manual-new-answer',experience_id=req.experience.experience_id,fact_type='result',
        normalized_fact=req.answer,evidence_quote=req.answer,source_type='user_answer',source_id=req.answer_source_id,assertion_state='user_asserted')
    unit=SemanticUnit(id='manual-duplicate',semantic_role='outcome',meaning='선택 결과',source_refs=[SourceRef(type='applicant_evidence',id=fact.evidence_id)])
    extraction=ExtractionOutput(experience_id=req.experience.experience_id,extracted_evidence=[fact],
        semantic_units=[unit,unit.model_copy(update={} if same else {'meaning':'다른 주장'})])
    if same:
        p=prepare_review(req,extraction)
        assert len([u for u in p.section_profile.original_semantic_units if u.id==unit.id])==1
        assert p.semantic_preparation['duplicate_rows'][0]['relation']=='identical'
    else:
        with pytest.raises(ContractError) as error:prepare_review(req,extraction)
        assert error.value.diagnostics['namespace']=='semantic'
        assert error.value.diagnostics['duplicate_ids']==[unit.id]
        assert error.value.diagnostics['duplicate_rows'][0]['positions']==[0,1]
        assert fact.evidence_id in error.value.approved_evidence
        from app.resume_review_v2.planning_state import extraction_diagnostics
        diag=extraction_diagnostics(req,extraction,error.value)
        assert len(diag['semantic_source_rows'])==2 and len(diag['semantic_sources'])==1
        assert req.answer not in str(diag)


def test_actual_known_choice_and_unknown_basis_have_distinct_public_requests_and_legacy_is_read_only():
    case,req,extraction=saved(132,'projects[0].description');facts={f.evidence_id:f for f in req.experience.existing_evidence}
    need=QuestionNeed(experience_id=req.experience.experience_id,gap_type='clarification',target_slot='technical_decisions',
        evidence_basis=['ev0-8'],request_aspect='decision_basis',priority='MEDIUM',dedupe_key='basis',why_needed='선택은 알려졌지만 추가 판단 근거가 편집에 유용한 경우만 확인')
    q=select_question(req,need,facts,{})[0]
    assert '무엇을' not in q.question and '기준' in q.question and '정확한 점수' in q.question
    req.previous_question_keys=[q.information_fingerprint]
    assert not select_question(req,need.model_copy(update={'dedupe_key':'renamed'}),facts,{})
    from pydantic import ValidationError
    with pytest.raises(ValidationError):QuestionNeed.model_validate({**need.model_dump(),'request_aspect':'selection_and_basis'})
    legacy=q.model_copy(update={'request_aspect':'selection_and_basis'})
    from app.resume_review_v2.question_planning import render_question
    rendered,_=render_question(legacy,facts,request=req)
    legacy=legacy.model_copy(update=rendered)
    assert approved_question(legacy,facts,request=req)


def test_rewrite_delta_only_identifies_changed_sources_not_safety_or_approval():
    case,req,extraction=saved(134,'projects[1].description');p=prepare_review(req,extraction)
    writer=WriterOutput(experience_id=req.experience.experience_id,operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence.model_validate(s) for s in case['writer_sentences'][1]])
    previous={'writer':{'sentences':case['writer_sentences'][0]},'validation':{'status':'REWRITE'}}
    collector=LangChainReviewLLM.__new__(LangChainReviewLLM);captured=[]
    collector._call=lambda prompt,payload,schema:captured.append(payload)
    collector.verify(p.request,writer,list(p.evidence.values()),[],[],previous_attempt=previous)
    changes=captured[0]['candidate_change_review']
    assert changes['changed_sentence_indices'] and changes['changes_are_not_factual_verdicts']
    assert captured[0]['previous_attempt']==previous


@pytest.mark.parametrize('namespace',['evidence','intent','semantic'])
def test_duplicate_namespace_diagnostics_and_exact_only_dedup(namespace):
    from app.resume_review_v2.models import ApplicantIntentClaim
    from app.resume_review_v2.planning_state import reconcile_extraction
    exp=Experience(experience_id='exp',kind='project',title='경험',field_path='projects[0].description',
        current_text='API를 구현했습니다. 안전성을 중요하게 생각합니다.',content_hash='h')
    req=ReviewInput(experience=exp)
    fact=Evidence(evidence_id='e',experience_id='exp',fact_type='implementation',normalized_fact='API 구현',
        evidence_quote='API를 구현했습니다.',source_type='resume_text',source_id='exp',assertion_state='resume_stated')
    intention=ApplicantIntentClaim(id='i',source_section_id='exp',intent_type='work_value',text='안전성을 중요하게 생각합니다.',
        evidence_quote='안전성을 중요하게 생각합니다.',source_type='resume_text',source_id='exp',state='resume_stated')
    unit=SemanticUnit(id='s',semantic_role='action',meaning='API 구현',source_refs=[SourceRef(type='applicant_evidence',id='e')])
    name={'evidence':'extracted_evidence','intent':'intent_claims','semantic':'semantic_units'}[namespace]
    row={'evidence':fact,'intent':intention,'semantic':unit}[namespace]
    extraction=ExtractionOutput(experience_id='exp',extracted_evidence=[fact],intent_claims=[intention],semantic_units=[unit])
    setattr(extraction,name,[row,row.model_copy(deep=True)])
    normalized,_=reconcile_extraction(req,extraction,with_replacements=True)
    assert len(getattr(normalized,name))==1
    field={'evidence':'normalized_fact','intent':'text','semantic':'meaning'}[namespace]
    setattr(extraction,name,[row,row.model_copy(update={field:'충돌하는 다른 내용'})])
    with pytest.raises(ContractError) as error:prepare_review(req,extraction)
    assert error.value.diagnostics['namespace']==namespace
    assert error.value.diagnostics['duplicate_rows'][0]['relation']=='conflicting'
    assert hasattr(error.value,'approved_evidence')==(namespace!='evidence')


def test_requirement_reassessment_retains_same_direct_grounds_as_partial_pending_not_sticky_met():
    from app.resume_review_v2.models import RequirementEvidenceMatch,JobRequirement as TargetRequirement
    from app.job_requirements import JobRequirement
    from app.resume_review_v2.requirement_matching import reconcile_matches,aggregate,context_hash
    from app.resume_review_v2.audit_resume import source_signature
    prior_case,req,_=saved(131,'projects[2].description')
    current_case,_,_=saved(133,'projects[2].description')
    requirement=JobRequirement.model_validate({k:v for k,v in prior_case['requirement'].items() if k in JobRequirement.model_fields})
    req.job_requirements=[TargetRequirement(requirement_id=requirement.id,text=requirement.label,posting_quote=requirement.posting_quote)]
    old=[Evidence.model_validate(f) for f in prior_case['facts']]
    facts={f['evidence_id']:Evidence.model_validate(f) for f in current_case['facts']}
    prior=[RequirementEvidenceMatch.model_validate(m) for m in prior_case['matches']]
    current=[RequirementEvidenceMatch.model_validate(m) for m in current_case['matches']]
    matches,warnings=reconcile_matches(req,prior,current,old,facts)
    assert len(matches)==1 and matches[0].status=='partial' and matches[0].evidence_ids
    assert warnings==['req-7: assessment_changed_with_unchanged_grounds']
    record={'experience':req.experience.model_dump(mode='json'),'answer':req.answer,
        'evidence_state':[f.model_dump(mode='json') for f in facts.values()],
        'requirement_matches':[m.model_dump(mode='json') for m in matches],'requirement_warnings':warnings,
        'audit_source_hash':source_signature(req),'requirement_context_hash':context_hash({},[requirement])}
    path=req.experience.field_path
    result=aggregate([requirement],[record],{path:req.experience.current_text},'h',{},
        lambda *_:(req.experience.title,req.resume_sources),{path:req.experience.experience_id},
        provenance_for=lambda *_:req.historical_resume_sources)
    assert result[0].status=='partial' and result[0].assessment_state=='pending' and result[0].evidence_refs
    # Retraction is a real change, not a missing reassessment.
    for eid in matches[0].evidence_ids:facts[eid].assertion_state='retracted'
    lost,notes=reconcile_matches(req,prior,current,old,facts)
    assert lost[0].status=='unconfirmed' and lost[0].evidence_ids==[] and notes==[]
