"""Current-policy verified apply/undo/audit boundaries, all DB/model I/O mocked."""
from copy import deepcopy
import pytest
from test_project_live_pipeline import pipeline,post
from app.resume_apply import ApplyRequest,build_application,rebase_review_response
from app.resume_review_v2.llm import LangChainReviewLLM
from app.review_workflow import digest


@pytest.fixture
def applied_pipeline(pipeline,monkeypatch):
    client,reviews,calls,db=pipeline
    db.verified_operations={}
    db.get_verified_application.side_effect=lambda cohort,resume,uid,op,tail=None:deepcopy(db.verified_operations.get(op))
    original=LangChainReviewLLM._call
    def invoke(self,system,payload,schema):
        result,usage=original(self,system,payload,schema)
        if schema.__name__=='BatchWriterDraft':
            for name in type(result).model_fields:
                draft=getattr(result,name)
                draft.sentences[0].text='API 구현을 완료했습니다.'
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    return pipeline


def apply_ready(pipeline,rid,indices):
    client,reviews,calls,db=pipeline
    before=deepcopy(db.get_owned_resume.return_value['content'])
    request=ApplyRequest(cohort_id='local',resume_id='1',review_id=rid,request_id='apply'+rid,
        expected_input_hash=digest(before),selected_indices=indices)
    after,_=build_application(before,reviews[rid],request)
    db.verified_operations[request.request_id]=dict(kind='apply',undone_by=None,source_id=rid,
        before=before,after_hash=digest(after),payload=request.model_dump(mode='json'))
    reviews[rid]=rebase_review_response(reviews[rid],after,before=before,applied_request=request)
    db.get_owned_resume.return_value['content']=after
    return before


def test_undone_operation_cannot_be_reused_after_manual_paste_of_same_candidate(applied_pipeline):
    client,reviews,calls,db=applied_pipeline
    post(client,'initial');apply_ready(applied_pipeline,'initial',[0])
    db.verified_operations['applyinitial']['undone_by']='undo'
    result=post(client,'copied-after-undo',previous_review_id='initial',review_phase='gap_audit')
    assert result['telemetry']['applied_reused_experiences']==0 and result['telemetry']['calls']>0


def test_exact_apply_reuses_writing_keeps_sources_and_pending_questions(applied_pipeline):
    client,reviews,calls,db=applied_pipeline
    initial=post(client,'initial')
    assert initial['sentence_reviews'][0]['validation_status']=='READY'
    original_quote=initial['telemetry']['v2_results'][0]['evidence_state'][0]['evidence_quote']
    apply_ready(applied_pipeline,'initial',[0]);before=len(calls)
    audit=post(client,'audit',previous_review_id='initial',review_phase='gap_audit')
    assert len(calls)==before and audit['telemetry']['calls']==0
    assert audit['telemetry']['applied_reused_experiences']==1
    assert all(s['suggested_revision'] is None for s in audit['sentence_reviews'])
    record=audit['telemetry']['v2_results'][0]
    assert record['verified_apply']['origin_experience']['current_text']==original_quote
    assert record['experience']['current_text']!=original_quote
    assert record['evidence_state'][0]['evidence_quote']==original_quote
    assert audit['questions']  # Applying a candidate does not answer its gap.
    again=post(client,'again',previous_review_id='audit',review_phase='gap_audit')
    assert again['telemetry']['calls']==0 and again['telemetry']['applied_reused_experiences']==1


@pytest.mark.parametrize('change',['manual','new_answer','retraction','policy','role','receipt'])
def test_changed_contract_cannot_reuse_applied_completion(applied_pipeline,change):
    client,reviews,calls,db=applied_pipeline
    first=post(client,'initial');apply_ready(applied_pipeline,'initial',[0])
    extra={}
    if change=='manual':db.get_owned_resume.return_value['content']['projects'][0]['description']+=' 새 기능을 구현했습니다.'
    elif change=='role':db.get_owned_resume.return_value['content']['projects'][0]['role']='역할 변경'
    elif change=='retraction':reviews['initial']['telemetry']['v2_results'][0]['evidence_state'][0]['assertion_state']='retracted'
    elif change=='policy':reviews['initial']['telemetry']['v2_results'][0]['verified_apply']['policy_version']='old-policy'
    elif change=='receipt':reviews['initial']['telemetry']['v2_results'][0]['verified_apply']['operation_id']='forged'
    else:
        q=first['questions'][0]
        extra['answers']=[dict(question_id=q['question_id'],question=q['question'],field_path=q['field_path'],answer='정상 조회 결과를 대조했습니다.')]
    before=len(calls)
    result=post(client,'changed',previous_review_id='initial',review_phase='gap_audit',**extra)
    assert any(stage=='BatchExtractionOutput' for stage,_,_ in calls[before:])
    assert result['telemetry']['applied_reused_experiences']==0


def test_one_manual_edit_keeps_other_applied_and_unmodified_experiences(applied_pipeline,monkeypatch):
    client,reviews,calls,db=applied_pipeline
    db.get_owned_resume.return_value['content']['projects']=[dict(id=f'p{i}',name=f'서비스 {i}',description='API를 구현했습니다.') for i in range(11)]
    original_call=LangChainReviewLLM._call
    def invoke(self,system,payload,schema):
        result,usage=original_call(self,system,payload,schema)
        if schema.__name__=='BatchWriterDraft':
            for name in type(result).model_fields:
                draft=getattr(result,name)
                if draft.experience_id in {'projects:p8','projects:p9','projects:p10'}:
                    draft.sentences[0].text='API를 구현했습니다.'
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    initial=post(client,'initial');apply_ready(applied_pipeline,'initial',list(range(8)))
    bound=deepcopy(reviews['initial'])
    reviews['initial']=rebase_review_response(initial,db.get_owned_resume.return_value['content'])
    legacy=post(client,'unlinked-audit',previous_review_id='initial',review_phase='gap_audit')
    assert legacy['telemetry']['audit_resume']['reprocessed_experiences']==8
    assert legacy['telemetry']['calls']==3
    reviews['initial']=bound
    audit=post(client,'audit',previous_review_id='initial',review_phase='gap_audit')
    assert audit['telemetry']['calls']==0
    assert audit['telemetry']['applied_reused_experiences']==8
    assert audit['telemetry']['audit_resume']['reused_experiences']==11
    assert db.get_verified_application.call_count==1  # Eight scopes share one apply event.
    db.get_owned_resume.return_value['content']['projects'][0]['description']+=' 점검했습니다.'
    second=post(client,'second',previous_review_id='audit',review_phase='gap_audit')
    assert second['telemetry']['applied_reused_experiences']==7
    assert second['telemetry']['audit_resume']['reprocessed_experiences']==1


def test_previous_policy_cannot_bind_a_current_verified_apply(applied_pipeline):
    client,reviews,calls,db=applied_pipeline
    post(client,'initial')
    reviews['initial']['telemetry']['policy_version']='resume-policy-9-paragraph-recomposition'
    apply_ready(applied_pipeline,'initial',[0])
    assert 'verified_apply' not in reviews['initial']['telemetry']['v2_results'][0]


@pytest.mark.parametrize('change',['job','profile'])
def test_changed_job_or_profile_invalidates_applied_checkpoint(applied_pipeline,monkeypatch,change):
    client,reviews,calls,db=applied_pipeline
    from app import main,matching_handoff,job_requirements
    main.build_resume_review_service().settings.matching_job_store_path='mock'
    source={'job_id':'job','snapshot_hash':'s'};requirements=[]
    monkeypatch.setattr(matching_handoff,'load_selected_job',lambda *_:{'text':'공고','source':source})
    monkeypatch.setattr(job_requirements,'load_or_extract_requirements',lambda *_:requirements)
    post(client,'initial',review_mode='job',selected_job_id='job')
    apply_ready(applied_pipeline,'initial',[0])
    if change=='job':source['snapshot_hash']='new'
    else:requirements.append(job_requirements.JobRequirement(id='req',group='must',label='Python 활용',posting_quote='Python 활용 경험'))
    result=post(client,'changed-job',review_mode='job',selected_job_id='job',previous_review_id='initial',review_phase='gap_audit')
    assert result['telemetry']['applied_reused_experiences']==0 and result['telemetry']['calls']>0


def test_current_requirement_uncertainty_remains_pending_after_applied_reuse(applied_pipeline,monkeypatch):
    client,reviews,calls,db=applied_pipeline
    from app import main,matching_handoff,job_requirements
    main.build_resume_review_service().settings.matching_job_store_path='mock'
    source={'job_id':'job','snapshot_hash':'s'}
    requirements=[job_requirements.JobRequirement(id='r',group='must',label='Python 활용',posting_quote='Python 활용 경험')]
    monkeypatch.setattr(matching_handoff,'load_selected_job',lambda *_:{'text':'공고','source':source})
    monkeypatch.setattr(job_requirements,'load_or_extract_requirements',lambda *_:requirements)
    post(client,'initial',review_mode='job',selected_job_id='job');apply_ready(applied_pipeline,'initial',[0])
    result=post(client,'audit',review_mode='job',selected_job_id='job',previous_review_id='initial',review_phase='gap_audit')
    assert result['telemetry']['calls']==0
    assert result['requirement_map'][0]['assessment_state']=='pending'
    assert result['requirement_map'][0]['status'] not in {'met','absent'}


def test_undo_restores_original_checkpoint_without_certifying_applied_source(applied_pipeline):
    client,reviews,calls,db=applied_pipeline
    post(client,'initial');before=apply_ready(applied_pipeline,'initial',[0])
    db.get_owned_resume.return_value['content']=before
    reviews['initial']=rebase_review_response(reviews['initial'],before)
    assert 'verified_apply' not in reviews['initial']['telemetry']['v2_results'][0]
    result=post(client,'undo-audit',previous_review_id='initial',review_phase='gap_audit')
    assert result['telemetry']['applied_reused_experiences']==0 and result['telemetry']['calls']==0


def test_rejected_candidate_and_unproven_text_copy_do_not_create_apply_receipt(applied_pipeline):
    client,reviews,calls,db=applied_pipeline
    first=post(client,'initial');before=deepcopy(db.get_owned_resume.return_value['content'])
    after=deepcopy(before);after['projects'][0]['description']=first['sentence_reviews'][0]['suggested_revision']
    reviews['initial']=rebase_review_response(reviews['initial'],after)
    db.get_owned_resume.return_value['content']=after
    audit=post(client,'unproven',previous_review_id='initial',review_phase='gap_audit')
    assert audit['telemetry']['applied_reused_experiences']==0 and audit['telemetry']['calls']>0
    first['telemetry']['v2_results'][0]['validation']['status']='REJECTED'
    req=ApplyRequest(cohort_id='local',resume_id='1',request_id='x',review_id='initial',expected_input_hash=digest(before),selected_indices=[0])
    rebased=rebase_review_response(first,after,before=before,applied_request=req)
    assert 'verified_apply' not in rebased['telemetry']['v2_results'][0]
