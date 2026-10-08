"""R13 source/transition reproduction; scripted models, memory-only storage.

Failed R13 raw Analyze is unavailable. New extraction is explicit test data,
not a recovery of its normalized facts or a model-quality measurement.
"""
import json
from pathlib import Path
from copy import deepcopy
import pytest
from test_project_live_pipeline import pipeline,post
from test_verified_apply_audit import apply_ready
from test_stage_checkpoints import staged
from app.resume_review_v2.models import (Evidence, EvidenceFacet, ExtractionOutput,
    QuestionNeed, QuestionTarget, RevisionSentence, WriterDraft, FactVerification, Usage, SemanticUnit, SourceRef)
from app.resume_review_v2.llm import LangChainReviewLLM

DATA=json.loads(Path(__file__).with_name('r13_apply_sources.json').read_text(encoding='utf-8'))


def finish(client,rid,**kwargs):
    for _ in range(8):
        result=post(client,rid,**kwargs)
        if result['telemetry']['execution']['state']=='verified':return result
    raise AssertionError('continuation did not terminate')


def answer(q,text):
    return {**{k:q[k] for k in ['question_id','experience_id','field_path','question']},'answer':text}


@pytest.fixture
def r13(pipeline,monkeypatch):
    client,reviews,calls,db=pipeline
    db.get_owned_resume.return_value['content']={'projects':deepcopy(DATA['projects'])}
    db.verified_operations={}
    db.get_verified_application.side_effect=lambda c,r,u,op,t=None:deepcopy(db.verified_operations.get(op))
    rows={r['experience']['experience_id']:r for r in DATA['initial']}
    def invoke(self,prompt,payload,schema):
        calls.append((schema.__name__,prompt,payload));items=payload.get('items',payload);result={}
        for name,item in items.items():
            if schema.__name__=='BatchFactVerification':
                result[name]=FactVerification();continue
            owner=item['experience']['experience_id'];row=rows[owner]
            if schema.__name__=='BatchExtractionOutput':
                if item['experience']['existing_evidence']:
                    fresh=Evidence(evidence_id='answer-fact',experience_id=owner,fact_type='result',
                        normalized_fact=item['user_answer'],evidence_quote=item['user_answer'],source_type='user_answer',
                        source_id=item['answer_source_id'],assertion_state='user_asserted')
                    # References that were lost at the R13 apply/reset boundary.
                    basis=['e0-imbalance','e0-evaluation'] if owner==DATA['initial'][0]['experience']['experience_id'] else ['e2-validator']
                    result[name]=ExtractionOutput(experience_id=owner,extracted_evidence=[fresh],
                        facets=[EvidenceFacet(evidence_id=eid,slots=['actions']) for eid in basis],
                        semantic_units=[SemanticUnit(id='continued-meaning',semantic_role='outcome',meaning=fresh.normalized_fact,
                            source_refs=[SourceRef(type='applicant_evidence',id=eid) for eid in [*basis,fresh.evidence_id]])])
                    if owner==DATA['initial'][0]['experience']['experience_id'] and not any(f['evidence_id']=='answer-fact' for f in item['experience']['existing_evidence']):
                        result[name].question=QuestionNeed(experience_id=owner,gap_type='clarification',
                            target_slot='insight_or_learning',evidence_basis=['e0-feature'],
                            targets=[QuestionTarget(evidence_id='e0-feature',anchor='days_to_expire')],request_aspect='relationship_interpretation',
                            priority='MEDIUM',dedupe_key='direction-clarification',why_needed='변수의 관계를 설명할 수 있는 추가 정보를 확인합니다.')
                else:
                    result[name]=ExtractionOutput(experience_id=owner,
                        extracted_evidence=[Evidence.model_validate(f) for f in row['facts']],
                        facets=[EvidenceFacet.model_validate(f) for f in row['facets']],
                        question=QuestionNeed.model_validate(row['question']) if row['question'] else None)
            elif schema.__name__=='BatchWriterDraft':
                facts=item['approved_evidence'];text=row['writer_text']
                text+=' '+ ' '.join(f['evidence_quote'] for f in facts if f['source_type']=='user_answer')
                result[name]=WriterDraft(experience_id=owner,sentences=[RevisionSentence(text=text,
                    evidence_ids=[f['evidence_id'] for f in facts],
                    semantic_unit_ids=[u['id'] for u in item['editorial_brief']['must_express']])])
            else:result[name]=FactVerification()
        return schema.model_validate(result),Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    return pipeline


def test_r13_apply_answer_continuation_and_untouched_question_sources(r13):
    client,reviews,calls,db=r13
    saved=staged(db,reviews)
    initial=finish(client,'initial')
    assert all(s['validation_status']=='READY' for s in initial['sentence_reviews']),[(r['experience']['title'],r['validation']) for r in initial['telemetry']['v2_results']]
    apply_ready(r13,'initial',[0,1,2])
    question=next(q for q in initial['questions'] if q['field_path']=='projects[0].description')
    lms=next(q for q in initial['questions'] if q['field_path']=='projects[2].description')
    answered=finish(client,'kkbox',previous_review_id='initial',answers=[answer(question,DATA['answers'][0]['answer'])])
    raw=saved['kkbox']['checkpoint']['states'][question['experience_id']]
    assert raw['request']['historical_resume_sources']
    analyze=next(p for stage,_,p in calls if stage=='BatchExtractionOutput' and next(iter(p.get('items',p).values()))['user_answer'])
    item=next(iter(analyze.get('items',analyze).values()))
    ids={f['evidence_id'] for f in item['experience']['existing_evidence']}
    assert {'e0-imbalance','e0-evaluation'}<=ids
    assert item['experience']['current_text']==DATA['projects'][0]['description']
    assert 'target_evidence_id' not in item['question'] and '"evidence_ids"' not in item['question']
    record=answered['telemetry']['v2_results'][0]
    assert record['debug_trace']['writer_attempts']>0
    assert {f['evidence_id'] for f in record['evidence_state']}>=ids|{'answer-fact'}
    assert record['source_provenance']
    carried=next(q for q in answered['questions'] if q['experience_id']==lms['experience_id'])
    assert carried['target_contexts']==lms['target_contexts']
    before=len(calls)
    audit=finish(client,'audit',previous_review_id='kkbox',review_phase='gap_audit')
    assert len(calls)==before
    assert next(q for q in audit['questions'] if q['experience_id']==lms['experience_id'])['target_contexts']==lms['target_contexts']
    lmsq=next(q for q in audit['questions'] if q['experience_id']==lms['experience_id'])
    final=finish(client,'lms',previous_review_id='audit',answers=[answer(lmsq,DATA['answers'][1]['answer'])])
    lms_calls=[p for stage,_,p in calls[before:] if stage=='BatchExtractionOutput']
    assert len(lms_calls)==1
    incoming=next(iter(lms_calls[0].get('items',lms_calls[0]).values()))
    assert 'e2-validator' in {f['evidence_id'] for f in incoming['experience']['existing_evidence']}
    assert final['telemetry']['v2_results'][2]['debug_trace']['writer_attempts']>0
    assert not any('analysis_contract_invalid' in str(r['validation']) for r in final['telemetry']['v2_results'])
    print('R13 scripted calls:',[(s,len(p.get('items',p))) for s,_,p in calls])


@pytest.mark.parametrize('invalid',['missing','other_owner','bad_quote'])
def test_r13_unproven_references_and_sources_still_fail(r13,monkeypatch,invalid):
    client,reviews,calls,db=r13
    initial=finish(client,'initial');apply_ready(r13,'initial',[0,1,2])
    original=LangChainReviewLLM._call
    def broken(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput' and result.item_0.extracted_evidence[0].source_type=='user_answer':
            if invalid=='missing':result.item_0.facets[0].evidence_id='unproved-display-only-id'
            elif invalid=='other_owner':result.item_0.extracted_evidence[0].experience_id=DATA['initial'][2]['experience']['experience_id']
            else:result.item_0.extracted_evidence[0].evidence_quote='없는 사용자 답변 근거'
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',broken)
    q=initial['questions'][0]
    result=finish(client,'failed',previous_review_id='initial',answers=[answer(q,DATA['answers'][0]['answer'])])
    record=result['telemetry']['v2_results'][0]
    assert record['validation']['status']=='REJECTED' and record['candidate'] is None
    assert record['debug_trace']['writer_attempts']==0
    approved=record['debug_trace']['extraction_failure']['facts_approved']
    assert approved==(invalid=='missing')
    assert ('answer-fact' in {f['evidence_id'] for f in record['evidence_state']})==(invalid=='missing')
    before=len(calls)
    repeated=finish(client,'audit-failed',previous_review_id='failed',review_phase='gap_audit')
    assert len(calls)==before
    assert repeated['telemetry']['v2_results'][0]['validation']['status']=='REJECTED'


def test_next_apply_and_answer_keep_roots_and_undo_checks_parent_operation(r13):
    from app.resume_apply import rebase_review_response
    client,reviews,calls,db=r13
    initial=finish(client,'initial');apply_ready(r13,'initial',[0,1,2])
    q=initial['questions'][0]
    first=finish(client,'first-answer',previous_review_id='initial',answers=[answer(q,DATA['answers'][0]['answer'])])
    assert first['telemetry']['v2_results'][0]['validation']['status']=='READY'
    before=apply_ready(r13,'first-answer',[0])
    receipt=reviews['first-answer']['telemetry']['v2_results'][0]['verified_apply']
    assert receipt['fact_sources'][0]['text']==DATA['projects'][0]['description']
    follow=next(q for q in first['questions'] if q['experience_id']==DATA['initial'][0]['experience']['experience_id'])
    second=finish(client,'second-answer',previous_review_id='first-answer',answers=[answer(follow,'추가 측정값은 없습니다.')])
    record=second['telemetry']['v2_results'][0]
    assert record['debug_trace']['writer_attempts']>0
    assert 'e0-evaluation' in {f['evidence_id'] for f in record['evidence_state']}
    assert record['source_provenance']['fact_sources']==receipt['fact_sources']
    db.verified_operations['applyfirst-answer']['undone_by']='undo-second-apply'
    db.get_owned_resume.return_value['content']=before
    reviews['first-answer']=rebase_review_response(reviews['first-answer'],before)
    restored=finish(client,'undo-audit',previous_review_id='first-answer',review_phase='gap_audit')
    # Parent receipt is not approved by text similarity; original apply is checked.
    assert restored['telemetry']['v2_results'][0]['source_provenance']['operation_id']=='applyinitial'
    db.verified_operations['applyinitial']['undone_by']='undo-original'
    copied=finish(client,'unproved',previous_review_id='undo-audit',review_phase='gap_audit')
    assert 'source_provenance' not in copied['telemetry']['v2_results'][0]


@pytest.mark.parametrize('bad_quote',[False,True])
def test_single_engine_and_batch_share_fact_approval_boundary(bad_quote):
    from unittest.mock import Mock
    from app.resume_review_v2.models import Experience,ReviewInput
    from app.resume_review_v2.engine import ReviewEngineV2
    from app.resume_review_v2.batch import BatchReviewEngine
    req=ReviewInput(experience=Experience(experience_id='owner',kind='project',title='경험',
        current_text='API를 구현했습니다.',field_path='projects[0].description',content_hash='h'))
    fact=Evidence(evidence_id='fact',experience_id='owner',fact_type='implementation',normalized_fact='API 구현',
        evidence_quote='없는 인용' if bad_quote else req.experience.current_text,
        source_type='resume_text',source_id='owner',assertion_state='resume_stated')
    extraction=ExtractionOutput(experience_id='owner',extracted_evidence=[fact],
        facets=[EvidenceFacet(evidence_id='unknown',slots=['actions'])])
    llm=Mock();llm.analyze.return_value=(extraction,Usage(calls=1))
    single=ReviewEngineV2(llm).run(req)
    batch=BatchReviewEngine('fake','medium');batch._batch=Mock(return_value={'owner':extraction})
    grouped=batch.run_many([req])[0]
    for result in [single,grouped]:
        assert result.validation.status=='REJECTED' and result.candidate is None
        assert bool(result.extracted_evidence)==(not bad_quote)
        assert result.debug_trace['extraction_failure']['facts_approved']==(not bad_quote)
    llm.write.assert_not_called();llm.verify.assert_not_called()
    assert [call.args[0] for call in batch._batch.call_args_list]==['analyze']


def test_answer_retraction_keeps_source_proof_but_not_answer_facts_or_completion(r13):
    from app.models import AnswerChange
    from app.resume_review_v2.answer_recovery import repair_answer
    from app.resume_review_v2.audit_resume import applied_provenance,applied_record
    from app.resume_review_v2.models import Experience,ReviewInput
    from app.local_resume_site_adapter import experience_sources
    client,reviews,calls,db=r13
    initial=finish(client,'initial');apply_ready(r13,'initial',[0,1,2]);q=initial['questions'][0]
    after=finish(client,'answered',previous_review_id='initial',answers=[answer(q,DATA['answers'][0]['answer'])])
    text=db.get_owned_resume.return_value['content']['projects'][0]['description'];owner=q['experience_id'];path=q['field_path']
    repaired=repair_answer(after,AnswerChange(question_id=q['question_id'],operation='retract',expected_answer=DATA['answers'][0]['answer']),
        {**q,'_answer_source_text':DATA['projects'][0]['description']},{path:text},{path:owner})
    record=repaired['telemetry']['v2_results'][0]
    assert record['source_provenance'] and record['answer_state_invalidated']
    assert next(f for f in record['evidence_state'] if f['evidence_id']=='answer-fact')['assertion_state']=='retracted'
    content=db.get_owned_resume.return_value['content'];title,sources=experience_sources(content,path,owner)
    req=ReviewInput(experience=Experience.model_validate(record['experience']).model_copy(update={'current_text':text}),resume_sources=sources)
    args=(req,record,repaired,{},record['requirement_context_hash'], 'fake','medium',db.verified_operations['applyinitial'])
    assert applied_provenance(*args) and applied_record(*args) is None
