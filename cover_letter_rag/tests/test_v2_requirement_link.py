"""Requirement references/routing/state on the actual mounted B path, all I/O mocked."""
import copy
import pytest
from test_project_live_pipeline import pipeline, post
from app import main
from app.job_requirements import JobRequirement
from app.resume_review_v2.models import Evidence, EvidenceFacet, RequirementEvidenceMatch
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.requirement_matching import ground_matches, aggregate, context_hash
from app.resume_review_v2.models import ReviewInput, Experience, SourceDocument


@pytest.fixture
def job_pipeline(pipeline, monkeypatch):
    client,reviews,calls,db=pipeline
    original_service=main.build_resume_review_service
    def service():
        s=original_service();s.settings.matching_job_store_path='mock';return s
    monkeypatch.setattr(main,'build_resume_review_service',service)
    from app import matching_handoff, job_requirements
    requirements=[JobRequirement(id='r1',group='must',label='FastAPI 활용',posting_quote='FastAPI 활용 경험'),
        JobRequirement(id='r2',group='preferred',label='Redis 활용',posting_quote='Redis 활용 경험')]
    source={'job_id':'job','snapshot_hash':'snapshot-1','company':'회사','title':'개발'}
    monkeypatch.setattr(matching_handoff,'load_selected_job',lambda *a:{'source':source,'text':'공고'})
    monkeypatch.setattr(job_requirements,'load_or_extract_requirements',lambda *a:requirements)
    db.get_owned_resume.return_value['content']['projects'][0]['description']='FastAPI로 API를 구현했습니다.'
    behavior={'owner':'unassigned','matches':True,'bad_ref':False,'reject':False}
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            for key,item in payload.get('items',payload).items():
                out=getattr(result,key)
                exp=item['experience'];answer=item['user_answer']
                if 'Redis' in answer:
                    fact=Evidence(evidence_id='action',experience_id=exp['experience_id'],fact_type='implementation',
                        normalized_fact='Redis 캐싱 구현',evidence_quote=answer,source_type='user_answer',
                        source_id=item['answer_source_id'],assertion_state='user_asserted')
                    out.extracted_evidence.append(fact)
                    out.facets.append(EvidenceFacet(evidence_id='action',slots=['actions']))
                all_facts=exp['existing_evidence']+[e.model_dump(mode='json') for e in out.extracted_evidence]
                redis=next((e for e in reversed(all_facts) if 'Redis' in e['evidence_quote']),None)
                if behavior['matches']:
                    out.requirement_matches=[RequirementEvidenceMatch(requirement_id='r1',status='met',evidence_ids=['action'],assertion_scope='used')]
                    if redis:out.requirement_matches.append(RequirementEvidenceMatch(requirement_id='r2',status='met',evidence_ids=[redis['evidence_id']],assertion_scope='used'))
                    if behavior['bad_ref']:out.requirement_matches[0].evidence_ids=['unknown']
                if out.question and not redis:
                    out.question=out.question.model_copy(update={'requirement_id':'r2','owner_scope':behavior['owner'],
                        'dedupe_key':'redis-use','evidence_basis':[]})
                elif redis:out.question=None
        if schema.__name__=='BatchFactVerification' and behavior['reject']:
            for key in type(result).model_fields:getattr(result,key).unsupported_claims=['scripted writer error']
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    def request(rid,**kw):return post(client,rid,review_mode='job',selected_job_id='job',**kw)
    return request,client,reviews,calls,db,behavior,requirements,source


def test_analyze_matching_owner_choice_and_answer_canonical_remapping(job_pipeline):
    request,client,reviews,calls,db,behavior,_,_=job_pipeline
    first=request('first');rows={r['id']:r for r in first['requirement_map']}
    assert rows['r1']['status']=='met' and rows['r1']['assessment_state']=='complete'
    q=first['questions'][0]
    assert q['requirement_id']=='r2' and q['experience_id'] is None and q['field_path']=='__requirement_owner__'
    assert q['owner_options'][0]['experience_id']=='projects:p1'
    option=q['owner_options'][0]
    behavior['reject']=True
    second=request('second',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=option['field_path'],experience_id=option['experience_id'],answer='Redis로 캐싱을 구현했습니다.')])
    rows={r['id']:r for r in second['requirement_map']}
    assert rows['r2']['status']=='met'
    ref=rows['r2']['evidence_refs'][0]
    assert ref['experience_id']=='projects:p1' and ref['evidence_id'].startswith('turn:')
    assert second['telemetry']['v2_results'][0]['validation']['status']=='REJECTED'
    assert not second['questions']  # No repeated presence question after supported use.


def test_ownerless_positive_answer_is_preserved_without_model_or_first_project_injection(job_pipeline):
    request,client,reviews,calls,db,*_=job_pipeline
    first=request('first');q=first['questions'][0];before=len(calls)
    second=request('unassigned',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=q['field_path'],answer='Redis로 캐싱을 구현했습니다.')])
    assert len(calls)==before
    assert all('Redis' not in e['evidence_quote'] for e in second['telemetry']['v2_results'][0]['evidence_state'])
    assert second['confirmed_answers'][-1]['experience_id'] is None
    q2=second['questions'][0];assert ':owner:' in q2['question_id']
    option=q2['owner_options'][0]
    third=request('bound',previous_review_id='unassigned',answers=[dict(question_id=q2['question_id'],question=q2['question'],
        field_path=option['field_path'],experience_id=option['experience_id'],answer='제가 직접 수행했습니다.')])
    assert any('Redis' in e['evidence_quote'] for e in third['telemetry']['v2_results'][0]['evidence_state'])


@pytest.mark.parametrize('scope,text,expected',[('unassigned','없음','absent'),('unassigned','모르겠습니다','unconfirmed'),('experience','없음','unconfirmed')])
def test_negative_scope_unknown_and_no_slot_blocking(job_pipeline,scope,text,expected):
    request,client,reviews,calls,db,behavior,*_=job_pipeline
    behavior['owner']=scope
    first=request('first');q=first['questions'][0];before=len(calls)
    result=request('answer',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=q['field_path'],experience_id=q['experience_id'],answer=text)])
    row=next(r for r in result['requirement_map'] if r['id']=='r2')
    assert row['status']==expected
    assert not result['telemetry']['v2_results'][0]['unavailable_slots']
    if scope=='unassigned':assert len(calls)==before


def test_unissued_owner_and_changed_job_question_are_rejected(job_pipeline):
    request,client,reviews,calls,db,behavior,requirements,source=job_pipeline
    first=request('first');q=first['questions'][0]
    payload=dict(uid='student',cohort_id='local',resume_id='1',review_mode='job',selected_job_id='job',
        request_id='bad',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path='projects[0].description',experience_id='projects:fake',answer='Redis 사용')])
    before=len(calls)
    assert client.post('/resume-review/api/v1/resumes/reviews/proxy',json=payload).status_code==422
    payload['answers'][0].update(field_path=q['field_path'],experience_id=None)
    source['snapshot_hash']='new'
    assert client.post('/resume-review/api/v1/resumes/reviews/proxy',json=payload).status_code==409
    assert len(calls)==before


def test_invalid_match_reference_is_pending_not_writer_failure_and_legacy_is_pending(job_pipeline):
    request,client,reviews,calls,db,behavior,*_=job_pipeline
    behavior['bad_ref']=True
    first=request('first')
    row=first['requirement_map'][0]
    assert row['status']=='unconfirmed' and row['assessment_state']=='pending'
    assert not any(i['code']=='analysis_contract_invalid' for i in first['telemetry']['v2_results'][0]['validation']['factual_issues'])
    assert [s for s,_,_ in calls]==['BatchExtractionOutput','BatchWriterDraft','BatchFactVerification']
    behavior['bad_ref']=False;behavior['matches']=False
    second=request('legacy')
    assert all(r['assessment_state']=='pending' for r in second['requirement_map'])


def test_duplicate_requirements_across_experiences_have_one_question_and_other_match_reused(job_pipeline):
    request,client,reviews,calls,db,*_=job_pipeline
    db.get_owned_resume.return_value['content']['projects'].append(dict(id='p2',name='별도 서비스',description='FastAPI로 API를 구현했습니다.'))
    first=request('first')
    assert len(first['questions'])==1
    q=first['questions'][0];option=q['owner_options'][1]
    before=len(calls)
    second=request('second',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=option['field_path'],experience_id=option['experience_id'],answer='Redis로 캐싱을 구현했습니다.')])
    extraction=[p for s,_,p in calls[before:] if s=='BatchExtractionOutput'][0]
    assert len(extraction.get('items',extraction))==1
    refs=next(r for r in second['requirement_map'] if r['id']=='r1')['evidence_refs']
    assert any(r['experience_id']=='projects:p1' for r in refs)
    assert all(r['experience_id']=='projects:p2' for r in next(r for r in second['requirement_map'] if r['id']=='r2')['evidence_refs'])


@pytest.mark.parametrize('quote,kind,scope,expected',[
    ('Redis','technology','used','partial'),
    ('Redis를 사용했습니다.','implementation','owned','partial'),
    ('Redis를 사용했습니다.','implementation','proficiency','partial'),
    ('팀원이 Redis를 사용했습니다.','implementation','used','partial'),
    ('Redis를 사용할 계획입니다.','technology','used',None),
    ('Redis 사용 경험이 없습니다.','technology','used',None),
    ('PostgreSQL을 활용했습니다.','implementation','used',None),
    ('Redis를 활용해 캐싱을 구현했습니다.','implementation','used','met'),
])
def test_matching_scope_does_not_expand_listing_to_capability(quote,kind,scope,expected):
    exp=Experience(experience_id='p',kind='project',title='서비스',field_path='projects[0].description',current_text=quote,content_hash='h')
    req=ReviewInput(experience=exp,job_requirements=[dict(requirement_id='r',text='Redis 활용',posting_quote='Redis 활용 경험')])
    fact=Evidence(evidence_id='e',experience_id='p',fact_type=kind,normalized_fact=quote,evidence_quote=quote,
        source_type='resume_text',source_id='p',assertion_state='resume_stated')
    matches,warnings=ground_matches(req,[RequirementEvidenceMatch(requirement_id='r',status='met',evidence_ids=['e'],assertion_scope=scope)],{'e':fact})
    assert (matches[0].status if matches else None)==expected
    if scope=='owned':assert matches[0].assertion_scope!='owned'


def test_compound_requirement_and_retracted_uncertain_evidence():
    quote='Redis를 활용했습니다.'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='서비스',field_path='projects[0].description',current_text=quote,content_hash='h'),
        job_requirements=[dict(requirement_id='r',text='Redis와 PostgreSQL 활용',posting_quote='Redis와 PostgreSQL 활용')])
    fact=Evidence(evidence_id='e',experience_id='p',fact_type='implementation',normalized_fact=quote,evidence_quote=quote,
        source_type='resume_text',source_id='p',assertion_state='resume_stated')
    match=RequirementEvidenceMatch(requirement_id='r',status='met',evidence_ids=['e'],assertion_scope='used')
    assert ground_matches(req,[match],{'e':fact})[0][0].status=='partial'
    for state in ['uncertain','retracted','superseded','contradicted']:
        assert ground_matches(req,[match],{'e':fact.model_copy(update={'assertion_state':state})})[0]==[]


def test_direct_use_requirement_does_not_need_an_extra_result_or_ownership_claim():
    from app.resume_review_v2.prompts import ANALYST_SYSTEM_PROMPT
    quote='백엔드 코드에서 Redis API를 직접 호출해 사용했습니다.'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='서비스',
        field_path='projects[0].description',current_text=quote,content_hash='h'),
        job_requirements=[dict(requirement_id='r',text='Redis API 직접 사용 경험',
            posting_quote='Redis API를 코드에서 직접 호출해 본 경험')])
    fact=Evidence(evidence_id='e',experience_id='p',fact_type='implementation',normalized_fact=quote,
        evidence_quote=quote,source_type='resume_text',source_id='p',assertion_state='resume_stated')
    match=RequirementEvidenceMatch(requirement_id='r',status='met',evidence_ids=['e'],assertion_scope='used')
    grounded,warnings=ground_matches(req,[match],{'e':fact})
    assert not warnings and grounded[0].status=='met'
    assert 'without\nan additional result, leadership or proficiency claim' in ANALYST_SYSTEM_PROMPT


def test_missing_fresh_match_reuses_valid_prior_basis_and_correction_removes_it(job_pipeline):
    request,client,reviews,calls,db,behavior,*_=job_pipeline
    first=request('first');q=first['questions'][0]
    option=q['owner_options'][0]
    second=request('second',previous_review_id='first',answers=[dict(question_id=q['question_id'],question=q['question'],field_path=option['field_path'],
        experience_id=option['experience_id'],answer='Redis로 캐싱을 구현했습니다.')])
    row=next(r for r in second['requirement_map'] if r['id']=='r2')
    assert row['status']=='met'
    records=copy.deepcopy(second['telemetry']['v2_results'])
    for e in records[0]['evidence_state']:
        if 'Redis' in e['evidence_quote']:e['assertion_state']='superseded'
    from app.local_resume_site_adapter import experience_sources
    content=db.get_owned_resume.return_value['content'];fields=second['input_fields']
    rows=aggregate(job_pipeline[-2],records,fields,second['input_hash'],job_pipeline[-1],
        lambda p,i:experience_sources(content,p,i),second['item_refs'])
    assert next(r for r in rows if r.id=='r2').status=='unconfirmed'


def test_no_analysis_is_pending_and_global_inventory_is_not_project_evidence():
    r=JobRequirement(id='r',group='must',label='Redis 활용',posting_quote='Redis 활용 경험')
    rows=aggregate([r],[],{'techStack[0].name':'Redis'},'h',{'snapshot_hash':'s'},lambda *a:('',[]),{})
    assert rows[0].assessment_state=='pending' and rows[0].status=='partial'
    assert 'experience_id' not in rows[0].evidence_refs[0]


def test_requirement_analyze_state_survives_stage_boundaries_without_reanalysis(job_pipeline):
    request,client,reviews,calls,db,*_=job_pipeline
    checkpoint={}
    db.supports_stage_checkpoints=True
    from contextlib import nullcontext
    db.review_execution.side_effect=lambda *a:nullcontext()
    db.claim_review.side_effect=lambda *a:{'checkpoint':copy.deepcopy(checkpoint)}
    def progress(*args):
        checkpoint.clear();checkpoint.update(copy.deepcopy(args[4].get('stage_checkpoint',{})))
    db.review_progress.side_effect=progress
    one=request('staged');assert one['telemetry']['execution']['state']=='processing'
    saved=next(iter(checkpoint['states'].values()))['result']
    assert saved['requirement_matches'][0]['requirement_id']=='r1'
    request('staged');final=request('staged')
    assert final['requirement_map'][0]['status']=='met'
    assert [s for s,_,_ in calls]==['BatchExtractionOutput','BatchWriterDraft','BatchFactVerification']
