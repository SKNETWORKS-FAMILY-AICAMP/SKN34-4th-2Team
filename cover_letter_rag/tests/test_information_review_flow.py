"""Discovery/review/ownership lifecycle. No real model or storage writes."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from test_project_live_pipeline import pipeline,post
from test_stage_checkpoints import staged
from app.resume_review_v2.models import (Experience,ReviewInput,Evidence,ExtractionOutput,
    QuestionNeed,QuestionReview,InformationReview,RequirementEvidenceMatch,EvidenceFacet,Usage)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.llm import LangChainReviewLLM


def test_finished_question_flow_distinguishes_completed_unconfirmed_from_pending_requirement_assessment():
    from app.job_requirements import RequirementStatusRow
    from app.resume_review_v2.question_planning import information_status
    record={'experience':{'experience_id':'projects:p1'},
        'debug_trace':{'question_selection':{'review_state':'reviewed','opportunities':[]}}}
    def row(key,status,assessment):
        return RequirementStatusRow(id=key,group='must',label='요건',posting_quote='요건',
            status=status,assessment_state=assessment)
    requirements=[row('direct','partial','complete'),row('unknown','unconfirmed','complete')]
    result=information_status([record],requirements,[],[],[],'job-snapshot')
    assert result['state']=='resolved' and result['open_opportunities']==0
    assert [(r['state'],r['reason']) for r in result['requirements']]==[
        ('partially_supported','grounded_partial_evidence'),
        ('unconfirmed','assessed_without_direct_evidence')]
    requirements.append(row('invalid','partial','pending'))
    pending=information_status([record],requirements,[],[],[],'job-snapshot')
    assert pending['state']=='pending' and pending['requirements'][-1]['assessment']=='pending'


def test_saved_r15_high_slot_hint_and_null_is_unreviewed_not_a_fabricated_omission_reason():
    old=json.loads(Path(__file__).with_name('r15_lms_review_source.json').read_text(encoding='utf-8'))
    assert old['question_selection']=={'state':'model_not_proposed','reason':'no_candidate_returned','candidate':None,
        'experience_id':old['experience']['experience_id']}
    assert any(g['target_slot']=='validation_method' and g['priority']=='HIGH' for g in old['gaps'])
    exp=Experience.model_validate(old['experience']).model_copy(update={'existing_evidence':[Evidence.model_validate(f) for f in old['facts']]})
    req=ReviewInput(experience=exp)
    # Saved facts are already source-validated. No raw Analyze reason exists.
    result=prepare_review(req,ExtractionOutput(experience_id=exp.experience_id,extracted_evidence=[],facets=old['facets']))
    diagnostic=result.question_selection
    assert not result.questions and diagnostic['review_state']=='not_recorded' and diagnostic['review_reason'] is None
    # Explicit new-model review is manually supplied, not a replay of the old null.
    extraction=ExtractionOutput(experience_id=exp.experience_id,extracted_evidence=[],facets=old['facets'],
        question_review=QuestionReview(experience_state='reviewed',reason='구현과 실제 수행 검증을 구분해 검토',items=[
            InformationReview(state='low_value',target_slot='validation_method',evidence_ids=[old['facts'][0]['evidence_id']],
                reason='이 입력에서는 추가 확인의 편집 가치가 낮다고 판단한 수동 fixture')]))
    reviewed=prepare_review(req,extraction)
    assert not reviewed.questions and reviewed.question_selection['opportunities'][0]['state']=='low_value'
    assert reviewed.question_selection['gap_review_hints'][0]['state']=='reviewed'


def question(owner,key,slot='validation_method',**extra):
    return QuestionNeed(experience_id=owner,gap_type='missing',target_slot=slot,priority='HIGH',
        why_needed='실제 답변으로 구현과 수행 검증을 구분해 기여를 구체화할 수 있음',dedupe_key=key,**extra)


@pytest.mark.parametrize('change,expected', [
    ({}, 'unavailable'),
    ({'evidence_id': 'missing'}, 'not_reviewed'),
    ({'experience_id': 'other'}, 'not_reviewed'),
    ({'source_id': 'other-answer'}, 'not_reviewed'),
    ({'assertion_state': 'retracted'}, 'not_reviewed'),
    ({'linked_answers': ['다른 답변입니다.']}, 'not_reviewed'),
    ({'information_need_id': 'other-need'}, 'not_reviewed'),
])
def test_uncertain_answer_closes_only_its_verified_information_need(change, expected):
    from app.resume_review_v2.question_planning import review_information
    quote='선택 이유는 지금 기억나지 않습니다.'
    question_text='선택 이유를 기억하시나요?'
    owner='projects:one';source='answer:projects[0].description'
    fact=Evidence(evidence_id='uncertain',experience_id=change.get('experience_id',owner),
        fact_type='technical_decision',normalized_fact=quote,evidence_quote=quote,
        source_type='user_answer',source_id=change.get('source_id',source),
        assertion_state=change.get('assertion_state','uncertain'))
    need=dict(information_need_id='need:decision',target_slot='technical_decisions',
        request_aspect='decision_basis',requirement_id=None,owner_scope='experience',
        question=question_text,linked_answers=change.get('linked_answers',[quote]))
    request=ReviewInput(experience=Experience(experience_id=owner,kind='project',title='프로젝트',
        field_path='projects[0].description',current_text='기존 설명',content_hash='hash'),
        answer=quote,answer_source_id=source,question_history=[question_text],prior_information_needs=[need])
    review=QuestionReview(experience_state='reviewed',reason='선택 근거 확인',items=[
        InformationReview(state='unavailable',target_slot='technical_decisions',
            request_aspect='decision_basis',information_need_id=change.get('information_need_id','need:decision'),
            evidence_ids=[change.get('evidence_id','uncertain')],reason='사용자가 기억하지 못함')])
    extraction=ExtractionOutput(experience_id=owner,extracted_evidence=[],question_review=review)
    _,diagnostic=review_information(request,extraction,{'uncertain':fact},[])
    assert diagnostic['opportunities'][0]['state']==expected
    assert fact.assertion_state==change.get('assertion_state','uncertain')


def test_issued_uncertain_answer_closes_its_need_through_b_adapter(pipeline, monkeypatch):
    from app.resume_review_v2 import batch
    client, reviews, calls, db = pipeline
    original = LangChainReviewLLM._call
    original_prepare = batch.prepare_review
    quote = '선택 이유는 지금 기억나지 않습니다.'
    seen = []
    def invoke(self, system, payload, schema):
        result, usage = original(self, system, payload, schema)
        if schema.__name__ == 'BatchExtractionOutput':
            for key, item in payload.get('items', payload).items():
                if item['user_answer']:
                    need = item['prior_information_needs'][0]
                    assert 'linked_answers' not in need  # Server-only linkage is not LLM input.
                    row = getattr(result, key)
                    row.extracted_evidence = [Evidence(evidence_id='forgotten',
                        experience_id=row.experience_id, fact_type='verification',
                        normalized_fact=quote, evidence_quote=quote, source_type='user_answer',
                        source_id=item['answer_source_id'], assertion_state='uncertain')]
                    row.question = None
                    row.question_review = QuestionReview(experience_state='reviewed', reason='답변 확인', items=[
                        InformationReview(state='unavailable', target_slot=need['target_slot'],
                            request_aspect=need.get('request_aspect'),
                            information_need_id=need['information_need_id'],
                            evidence_ids=['forgotten'], reason='기억하지 못한다고 답함')])
        return result, usage
    def prepare(request, extraction):
        if request.answer:
            assert request.prior_information_needs[0]['linked_answers'] == [quote]
            seen.append(request.prior_information_needs[0])
        return original_prepare(request, extraction)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    monkeypatch.setattr(batch, 'prepare_review', prepare)
    first = post(client, 'first')
    q = first['questions'][0]
    answered = post(client, 'answered', previous_review_id='first', answers=[{
        'question_id':q['question_id'],'field_path':q['field_path'],
        'question':q['question'],'answer':quote}])
    assert seen
    record = answered['telemetry']['v2_results'][0]
    opportunity = next(o for o in record['debug_trace']['question_selection']['opportunities']
        if o.get('information_need_id') == q['information_need_id'])
    assert opportunity['state'] == 'unavailable'
    assert next(f for f in record['evidence_state'] if f['evidence_id']=='forgotten')['assertion_state'] == 'uncertain'
    assert 'forgotten' not in {f['evidence_id'] for f in record['selected_evidence']}


def test_deferred_needs_survive_checkpoint_cap_answer_and_zero_call_audit(pipeline,monkeypatch):
    client,reviews,calls,db=pipeline;checkpoints=staged(db,reviews)
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            for key,item in payload.get('items',payload).items():
                out=getattr(result,key);owner=out.experience_id;out.question=None
                out.question_review=QuestionReview(experience_state='reviewed',reason='실제 검증과 결과를 구분해 검토',items=[])
                if not item['user_answer']:
                    out.question_review.items=[InformationReview(state='proposed',need=question(owner,'method')),
                        InformationReview(state='deferred',need=question(owner,'outcome','outcome',request_aspect='verification_result_and_limits'))]
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    first=post(client,'initial');post(client,'initial');first=post(client,'initial')
    assert len(checkpoints['initial']['checkpoint']['states']['projects:p1']['result']['gap_questions'])==2
    assert len(first['questions'])==1
    assert any(d['reason']=='owner_question_cap' for d in first['telemetry']['question_delivery'])
    q=first['questions'][0];request=dict(previous_review_id='initial',answers=[{k:q[k] for k in ['question_id','field_path','question']}|{'answer':'정상 조회 결과를 대조했습니다.'}])
    for _ in range(4):
        answered=post(client,'answered',**request)
        if answered['telemetry']['execution']['state']=='verified':break
    assert len(answered['questions'])==1 and answered['questions'][0]['target_slot']=='outcome'
    decision=next(d for d in answered['telemetry']['information_review']['decisions'] if (d.get('need') or {}).get('dedupe_key','').endswith(':method'))
    assert decision['state']=='answered' and decision['writing_status'] in {'READY','UNCHANGED','REJECTED'}
    before=len(calls);audit=post(client,'audit',previous_review_id='answered',review_phase='gap_audit')
    assert len(calls)==before and audit['questions'][0]['target_slot']=='outcome'
    assert audit['telemetry']['information_review']['state']=='pending'


@pytest.fixture
def requirement_discovery(pipeline,monkeypatch):
    from app import main,matching_handoff,job_requirements
    client,reviews,calls,db=pipeline
    db.get_owned_resume.return_value['content']['projects'].append({'id':'p2','name':'두 번째 경험','description':'API를 구현했습니다.'})
    factory=main.build_resume_review_service
    def service():
        result=factory();result.settings.matching_job_store_path='mock';return result
    monkeypatch.setattr(main,'build_resume_review_service',service)
    requirements=[job_requirements.JobRequirement(id='r',group='must',label='Redis 활용',posting_quote='Redis 활용 경험')]
    monkeypatch.setattr(matching_handoff,'load_selected_job',lambda *_:{'text':'공고','source':{'job_id':'job','snapshot_hash':'s'}})
    monkeypatch.setattr(job_requirements,'load_or_extract_requirements',lambda *_:requirements)
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            for key,item in payload.get('items',payload).items():
                out=getattr(result,key);out.question=None
                out.question_review=QuestionReview(experience_state='reviewed',reason='요건과 실제 경험 대조',items=[])
                out.requirement_matches=[RequirementEvidenceMatch(requirement_id='r',status='unconfirmed',assertion_scope='context')]
                if 'Redis' in item['user_answer']:
                    fresh=Evidence(evidence_id='redis-work',experience_id=out.experience_id,fact_type='implementation',
                        normalized_fact='Redis 캐싱 구현',evidence_quote=item['user_answer'],source_type='user_answer',
                        source_id=item['answer_source_id'],assertion_state='user_asserted')
                    out.extracted_evidence.append(fresh);out.facets.append(EvidenceFacet(evidence_id=fresh.evidence_id,slots=['actions']))
                    out.requirement_matches=[RequirementEvidenceMatch(requirement_id='r',status='met',assertion_scope='used',evidence_ids=[fresh.evidence_id])]
                elif item.get('requirement_review_context',{}).get('resume_scope_delegate'):
                    out.question_review.items=[InformationReview(state='proposed',need=question(out.experience_id,'redis-presence','actions',
                        requirement_id='r',owner_scope='unassigned',request_aspect='experience_presence'))]
        elif schema.__name__=='BatchWriterDraft':
            for key,item in payload.get('items',payload).items():
                row=next((e for e in item['approved_evidence'] if e['evidence_id']=='redis-work'),None)
                if row:
                    from app.resume_review_v2.models import RevisionSentence
                    getattr(result,key).sentences.append(RevisionSentence(text='Redis 캐싱을 구현했습니다.',evidence_ids=['redis-work']))
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    return pipeline


def job(client,rid,**extra):return post(client,rid,review_mode='job',selected_job_id='job',**extra)


def test_global_presence_hold_owner_evidence_writer_validation_requirement_integrated(requirement_discovery):
    client,reviews,calls,db=requirement_discovery
    initial=job(client,'initial');q=initial['questions'][0]
    assert q['owner_scope']=='unassigned' and q['experience_id'] is None and q['information_aspect']=='experience_presence'
    before=len(calls)
    held=job(client,'held',previous_review_id='initial',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=q['field_path'],answer='Redis 캐싱을 구현했습니다.')])
    assert len(calls)==before
    assert not any(f['source_type']=='user_answer' for r in held['telemetry']['v2_results'] for f in r['evidence_state'])
    assert held['telemetry']['information_review']['requirements'][0]['state']=='awaiting_owner'
    owner=held['questions'][0];choice=next(o for o in owner['owner_options'] if o['experience_id']=='projects:p2')
    final=job(client,'bound',previous_review_id='held',answers=[dict(question_id=owner['question_id'],question=owner['question'],
        experience_id=choice['experience_id'],field_path=choice['field_path'],answer='이 항목에서 수행했습니다.')])
    assert final['requirement_map'][0]['status']=='met'
    records={r['experience']['experience_id']:r for r in final['telemetry']['v2_results']}
    assert not any(f['source_type']=='user_answer' for f in records['projects:p1']['evidence_state'])
    assert any(f['evidence_id']=='redis-work' for f in records['projects:p2']['evidence_state'])
    write=next(p for stage,_,p in calls[before:] if stage=='BatchWriterDraft')
    assert any('Redis' in e['evidence_quote'] for e in write['items']['item_0']['approved_evidence'])
    assert records['projects:p2']['validation']['status']=='READY'
    assert final['telemetry']['information_review']['requirements'][0]['state']=='supported'


@pytest.mark.parametrize('answer,state',[('없음','unavailable'),('모름','unavailable')])
def test_global_absence_unknown_stop_without_fact_injection(requirement_discovery,answer,state):
    client,reviews,calls,db=requirement_discovery
    first=job(client,'initial');q=first['questions'][0];before=len(calls)
    final=job(client,'answer',previous_review_id='initial',answers=[dict(question_id=q['question_id'],question=q['question'],field_path=q['field_path'],answer=answer)])
    assert len(calls)==before and not final['questions']
    assert final['telemetry']['information_review']['requirements'][0]['state']==state
    assert final['requirement_map'][0]['status']==('absent' if answer=='없음' else 'unconfirmed')
    assert not any(f['source_type']=='user_answer' for r in final['telemetry']['v2_results'] for f in r['evidence_state'])


def test_collected_answer_is_resolved_even_when_writer_candidate_is_rejected(requirement_discovery,monkeypatch):
    from app.resume_review_v2.models import FactVerification
    client,reviews,calls,db=requirement_discovery;original=LangChainReviewLLM._call
    first=job(client,'initial');q=first['questions'][0]
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchFactVerification':
            for key in type(result).model_fields:setattr(result,key,FactVerification(unsupported_claims=['수동 fixture의 후보 검증 실패']))
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    choice=next(o for o in q['owner_options'] if o['experience_id']=='projects:p2')
    final=job(client,'failed-writing',previous_review_id='initial',answers=[dict(question_id=q['question_id'],question=q['question'],
        experience_id=choice['experience_id'],field_path=choice['field_path'],answer='Redis 캐싱을 구현했습니다.')])
    record=next(r for r in final['telemetry']['v2_results'] if r['experience']['experience_id']=='projects:p2')
    assert record['validation']['status']=='REJECTED' and any(f['evidence_id']=='redis-work' for f in record['evidence_state'])
    assert not any(q['information_aspect']=='experience_presence' for q in final['questions'])
    decision=next(d for d in final['telemetry']['information_review']['decisions'] if d.get('requirement_id')=='r')
    assert decision['state']=='answered' and decision['writing_status']=='REJECTED'


def test_no_existing_owner_is_explicitly_unresolved_not_injected_or_silently_sufficient(requirement_discovery):
    client,reviews,calls,db=requirement_discovery
    db.get_owned_resume.return_value['content']={'coreCompetencies':{'text':'API를 구현했습니다.'}}
    first=job(client,'initial');q=first['questions'][0]
    assert q['owner_options']==[]
    held=job(client,'held',previous_review_id='initial',answers=[dict(question_id=q['question_id'],question=q['question'],
        field_path=q['field_path'],answer='Redis 캐싱을 구현했습니다.')])
    status=held['telemetry']['information_review']['requirements'][0]
    assert status['state']=='awaiting_owner' and status['reason']=='no_existing_owner_item'
    assert not any(f['source_type']=='user_answer' for r in held['telemetry']['v2_results'] for f in r['evidence_state'])


def test_project_absence_does_not_close_global_requirement_review(requirement_discovery):
    client,reviews,calls,db=requirement_discovery
    first=job(client,'initial');q=first['questions'][0];choice=q['owner_options'][0]
    final=job(client,'local-no',previous_review_id='initial',answers=[dict(question_id=q['question_id'],question=q['question'],
        experience_id=choice['experience_id'],field_path=choice['field_path'],answer='없음')])
    assert final['requirement_map'][0]['status']!='absent'
    state=final['telemetry']['information_review']['requirements'][0]
    assert state['state']=='not_reviewed' and state['reason']=='experience_scoped_answer_not_global_absence'


def test_answer_resolves_the_unique_deferred_need_without_resurrecting_question(pipeline,monkeypatch):
    client,reviews,calls,db=pipeline;original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            for key,item in payload.get('items',payload).items():
                out=getattr(result,key);out.question=None;owner=out.experience_id
                if not item['user_answer']:
                    out.question_review=QuestionReview(experience_state='reviewed',reason='검증 방법과 결과 검토',items=[
                        InformationReview(state='proposed',need=question(owner,'method',request_aspect='verification_method')),
                        InformationReview(state='deferred',need=question(owner,'outcome','outcome',request_aspect='verification_result_and_limits'))])
                else:
                    assert any(n['information_need_id'].endswith(':outcome') for n in item['prior_information_needs'])
                    assert all('evidence_ids' not in n for n in item['prior_information_needs'])
                    out.question_review=QuestionReview(experience_state='reviewed',reason='답변으로 결과도 확인됨',items=[
                        InformationReview(state='sufficient',target_slot='outcome',evidence_ids=['check'],reason='이번 답변에 실제 관찰 결과도 포함되어 해결됨')])
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    initial=post(client,'initial');q=initial['questions'][0]
    result=post(client,'answered',previous_review_id='initial',answers=[dict(question_id=q['question_id'],
        field_path=q['field_path'],question=q['question'],answer='정상 조회 결과를 대조했습니다. 세 입력 모두 예상 결과와 일치했습니다.')])
    assert result['questions']==[]
    outcome=[d for d in result['telemetry']['information_review']['decisions'] if d.get('target_slot')=='outcome']
    assert len(outcome)==1 and outcome[0]['state']=='sufficient' and outcome[0]['information_need_id'].endswith(':outcome')
    assert result['telemetry']['information_review']['state']=='resolved'
    assert result['telemetry']['information_review']['open_opportunities']==0
    before=len(calls);audit=post(client,'audit',previous_review_id='answered',review_phase='gap_audit')
    assert len(calls)==before and audit['questions']==[]
    assert audit['telemetry']['information_review']==result['telemetry']['information_review']
    repeated=post(client,'audit-again',previous_review_id='audit',review_phase='gap_audit')
    assert len(calls)==before and repeated['questions']==[]
    assert repeated['telemetry']['information_review']==audit['telemetry']['information_review']


def test_snapshot_change_drops_old_requirement_candidate_and_old_review_decisions(requirement_discovery,monkeypatch):
    from app import matching_handoff
    client,reviews,calls,db=requirement_discovery
    first=job(client,'initial');old_hash=first['questions'][0]['requirement_context_hash']
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            for key,item in payload.get('items',payload).items():
                assert not any(n.get('requirement_id')=='r' for n in item['prior_information_needs'])
                out=getattr(result,key);out.question=None
                out.question_review=QuestionReview(experience_state='reviewed',reason='새 맥락 검토',items=[
                    InformationReview(state='low_value',requirement_id='r',reason='새 맥락에서는 추가 질문 편집 가치가 낮음')])
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    monkeypatch.setattr(matching_handoff,'load_selected_job',lambda *_:{'text':'공고','source':{'job_id':'job','snapshot_hash':'changed'}})
    current=job(client,'new-context',previous_review_id='initial',review_phase='gap_audit')
    assert current['questions']==[]
    assert current['telemetry']['v2_results'][0]['requirement_context_hash']!=old_hash
    assert not any(d['state']=='selected' for d in current['telemetry']['information_review']['decisions'])
    assert current['telemetry']['information_review']['requirements'][0]['state']=='low_value'


def test_same_facet_two_needs_require_identity_and_do_not_blanket_close():
    from app.resume_review_v2.question_planning import reconcile_deferred_needs
    prior={'requirement_context_hash':'ctx','gap_questions':[
        {'dedupe_key':'exp:value:a','information_fingerprint':'a','target_slot':'outcome','request_aspect':'comparison_result','requirement_id':None},
        {'dedupe_key':'exp:value:b','information_fingerprint':'b','target_slot':'outcome','request_aspect':'verification_result_and_limits','requirement_id':None}]}
    current={'debug_trace':{'question_selection':{'opportunities':[{'state':'sufficient','target_slot':'outcome','requirement_id':None}]}},'gap_questions':[]}
    reconcile_deferred_needs(current,prior,'ctx')
    assert len(current['gap_questions'])==2
    assert current['debug_trace']['question_selection']['opportunities'][0]['state']=='not_reviewed'
    exact={'debug_trace':{'question_selection':{'opportunities':[{'state':'low_value','information_need_id':'exp:value:a','reason':'구체적인 편집 가치 판단'}]}},'gap_questions':[]}
    reconcile_deferred_needs(exact,prior,'ctx')
    assert [q['dedupe_key'] for q in exact['gap_questions']]==['exp:value:b']
