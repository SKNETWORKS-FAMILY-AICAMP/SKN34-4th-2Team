"""Answer repair through the actual B API; all storage/model transport mocked."""
from copy import deepcopy
import pytest
from test_project_live_pipeline import pipeline,post
from test_stage_checkpoints import staged
from app.models import AnswerChange
from app.resume_review_v2.answer_recovery import repair_answer,repeats_question


def history(pipeline,two=False):
    client,reviews,calls,db=pipeline
    if two:
        db.get_owned_resume.return_value['content']['projects'].append({'id':'p2','name':'다른 경험','description':'API를 구현했습니다.'})
    first=post(client,'first');q=next(q for q in first['questions'] if q['field_path']=='projects[0].description')
    response=post(client,'answered',previous_review_id='first',answers=[{
        'question_id':q['question_id'],'field_path':q['field_path'],'question':q['question'],'answer':'정상 조회 결과를 대조했습니다.'}])
    db.latest_review_response.side_effect=lambda *args:reviews[next(reversed(reviews))]
    db.answer_was_applied.return_value=False
    return client,reviews,calls,db,q,response


def mutation(q,operation='retract',answer=None):
    return dict(question_id=q['question_id'],operation=operation,expected_answer='정상 조회 결과를 대조했습니다.',answer=answer)


def test_question_copy_is_rejected_before_claim_or_llm_but_quoted_answer_is_allowed(pipeline):
    client,reviews,calls,db=pipeline
    initial=post(client,'first');q=initial['questions'][0];before=len(calls);claims=db.claim_review.call_count
    response=client.post('/resume-review/api/v1/resumes/reviews/proxy',json=dict(uid='student',cohort_id='local',resume_id='1',
        review_mode='general',request_id='copy',previous_review_id='first',answers=[dict(question_id=q['question_id'],
        field_path=q['field_path'],question=q['question'],answer=q['question'])]))
    assert response.status_code==422 and response.json()['detail']=='answer_repeats_question'
    assert len(calls)==before and db.claim_review.call_count==claims
    assert not repeats_question(q['question'],q['question']+' 정상 조회 결과를 대조했습니다.')


def test_cancel_retracts_only_dependent_sources_and_restores_question_with_zero_llm(pipeline):
    client,reviews,calls,db,q,response=history(pipeline,two=True)
    unaffected=deepcopy(response['telemetry']['v2_results'][1]);before=len(calls)
    repaired=post(client,'cancel',previous_review_id='answered',answer_changes=[mutation(q)])
    assert len(calls)==before and repaired['telemetry']['calls']==0
    assert repaired['confirmed_answers']==[]
    assert any(x['question_id']==q['question_id'] for x in repaired['questions'])
    record=next(r for r in repaired['telemetry']['v2_results'] if r['experience']['experience_id']=='projects:p1')
    states={f['evidence_id']:f['assertion_state'] for f in record['evidence_state']}
    assert states['check']=='retracted' and states['action']=='resume_stated'
    assert record['candidate'] is None and record['section_profile'] is None
    assert record['validation']['status']=='NEEDS_EVIDENCE' and record['requirement_matches'] is None
    assert repaired['telemetry']['v2_results'][1]==unaffected


def test_replace_reanalysis_is_incremental_and_other_experience_is_reused(pipeline):
    client,reviews,calls,db,q,response=history(pipeline,two=True)
    before=len(calls)
    repaired=post(client,'edit',previous_review_id='answered',answer_changes=[mutation(q,'replace','정상 조회 결과를 다시 대조했습니다.')])
    assert len(calls)==before
    assert repaired['confirmed_answers'][0]['answer']=='정상 조회 결과를 다시 대조했습니다.'
    final=post(client,'reanalyze',previous_review_id='edit',review_phase='gap_audit')
    analyze=[payload for stage,_,payload in calls[before:] if stage=='BatchExtractionOutput']
    assert len(analyze)==1
    assert len(analyze[0].get('items',analyze[0]))==1
    assert analyze[0]['item_0']['experience']['experience_id']=='projects:p1'
    assert analyze[0]['item_0']['user_answer']=='정상 조회 결과를 다시 대조했습니다.'
    assert final['telemetry']['audit_resume']['reused_experiences']==1


def test_applied_document_stays_but_cannot_be_reapproved_until_restored(pipeline):
    client,reviews,calls,db,q,response=history(pipeline)
    record=response['telemetry']['v2_results'][0]
    text=record['candidate']['suggested_text']
    db.get_owned_resume.return_value['content']['projects'][0]['description']=text
    db.answer_was_applied.return_value=True
    before=len(calls)
    repaired=post(client,'cancel',previous_review_id='answered',answer_changes=[mutation(q)])
    assert repaired['telemetry']['answer_recovery']['requires_document_undo']
    assert db.get_owned_resume.return_value['content']['projects'][0]['description']==text
    held=post(client,'held',previous_review_id='cancel',review_phase='gap_audit')
    assert len(calls)==before
    assert held['telemetry']['v2_results'][0]['validation']['status']=='NEEDS_EVIDENCE'
    assert held['telemetry']['answer_recovery']['requires_document_undo']
    db.get_owned_resume.return_value['content']['projects'][0]['description']='API를 구현했습니다.'
    final=post(client,'after-undo',previous_review_id='held',review_phase='gap_audit')
    assert len(calls)>before and not final['telemetry']['answer_recovery']['requires_document_undo']
    state=final['telemetry']['v2_results'][0]['evidence_state']
    assert any(e['evidence_id']=='action' and e['assertion_state']=='resume_stated' for e in state)
    assert any(e['evidence_id']=='check' and e['assertion_state']=='retracted' for e in state)


def test_same_quote_in_another_active_answer_keeps_its_evidence(pipeline):
    client,reviews,calls,db,q,response=history(pipeline)
    previous=deepcopy(response)
    previous['confirmed_answers'].append({**previous['confirmed_answers'][0],'question_id':'other'})
    issued={**q,'_answer_source_text':'API를 구현했습니다.','_answer_dedupe_key':'projects:p1:value:validation-evidence'}
    repaired=repair_answer(previous,AnswerChange(**mutation(q)),issued,
        {'projects[0].description':'API를 구현했습니다.'},{'projects[0].description':'projects:p1'})
    check=next(f for f in repaired['telemetry']['v2_results'][0]['evidence_state'] if f['evidence_id']=='check')
    assert check['assertion_state']=='user_asserted'


def test_quoting_old_answer_in_a_correction_does_not_keep_its_evidence(pipeline):
    client,reviews,calls,db,q,response=history(pipeline)
    corrected=repair_answer(deepcopy(response),AnswerChange(**mutation(q,'replace',
        '“정상 조회 결과를 대조했습니다”라고 답했지만 실제로는 대조하지 않았습니다.')),
        {**q,'_answer_source_text':'API를 구현했습니다.'},
        {'projects[0].description':'API를 구현했습니다.'},
        {'projects[0].description':'projects:p1'})
    facts={f['evidence_id']:f for f in corrected['telemetry']['v2_results'][0]['evidence_state']}
    assert facts['check']['assertion_state']=='retracted'
    assert facts['action']['assertion_state']=='resume_stated'


@pytest.mark.parametrize('relation',['correction','conflict'])
def test_withdrawn_relations_are_retired_without_reactivating_superseded_sources(pipeline,relation):
    client,reviews,calls,db,q,response=history(pipeline)
    previous=deepcopy(response);record=previous['telemetry']['v2_results'][0]
    facts={e['evidence_id']:e for e in record['evidence_state']}
    if relation=='correction':
        facts['action']['assertion_state']='superseded';facts['check']['supersedes_evidence_ids']=['action']
    else:
        facts['check']['conflicts_with_evidence_ids']=['action'];facts['action']['conflicts_with_evidence_ids']=['check']
    repaired=repair_answer(previous,AnswerChange(**mutation(q)),{**q,'_answer_source_text':'API를 구현했습니다.'},
        {'projects[0].description':'API를 구현했습니다.'},{'projects[0].description':'projects:p1'})
    facts={e['evidence_id']:e for e in repaired['telemetry']['v2_results'][0]['evidence_state']}
    assert facts['check']['assertion_state']=='retracted'
    assert facts['check']['supersedes_evidence_ids']==facts['check']['conflicts_with_evidence_ids']==[]
    assert facts['action']['conflicts_with_evidence_ids']==[]
    assert facts['action']['assertion_state']==('superseded' if relation=='correction' else 'resume_stated')


def test_stale_edit_is_rejected(pipeline):
    client,reviews,calls,db,q,response=history(pipeline)
    db.latest_review_response.return_value={'review_id':'newer'};db.latest_review_response.side_effect=None
    result=client.post('/resume-review/api/v1/resumes/reviews/proxy',json=dict(uid='student',cohort_id='local',resume_id='1',
        review_mode='general',request_id='edit',previous_review_id='answered',answer_changes=[mutation(q)]))
    assert result.status_code==409 and result.json()['detail']=='answer_state_changed'


def test_application_lookup_joins_scoped_review_to_short_request_id():
    """Exercise the real SELECT against an isolated in-memory SQL fixture.

    The API fixture mocks answer_was_applied itself and cannot catch a broken
    JOIN. Only PostgreSQL's left() spelling is adapted for SQLite here.
    """
    import json
    import sqlite3
    from contextlib import contextmanager
    from unittest.mock import Mock
    from app.local_resume_site_adapter import LocalGateway
    gateway = LocalGateway.__new__(LocalGateway)
    gateway._cohort_user = Mock(return_value={'user_pk': 7})
    prefix = gateway._resume_legacy('r1', 'tail') + '/'
    response = json.dumps({'confirmed_answers':[{'question_id':'q1','field_path':'body'}],
        'sentence_reviews':[{'field_path':'body'}]})
    payload = json.dumps({'selected_indices':[0]})
    with sqlite3.connect(':memory:') as conn:
        conn.execute('CREATE TABLE resume_ai_reviews (legacy_id TEXT, user_id INTEGER, resume_id INTEGER, response TEXT)')
        conn.execute('CREATE TABLE resume_ai_applications (legacy_id TEXT, user_id INTEGER, resume_id INTEGER, source_id TEXT, kind TEXT, undone_by TEXT, payload TEXT)')
        conn.execute('INSERT INTO resume_ai_reviews VALUES (?,?,?,?)', (prefix+'review1',7,28,response))
        conn.execute('INSERT INTO resume_ai_applications VALUES (?,?,?,?,?,?,?)', (prefix+'op1',7,28,'review1','apply',None,payload))
        class Reader:
            def execute(self, sql, args):
                sql = sql.replace('left(a.legacy_id,length(%s))', 'substr(a.legacy_id,1,length(%s))').replace('%s','?')
                rows = conn.execute(sql,args).fetchall()
                return Mock(fetchall=lambda:[(json.loads(r),json.loads(p)) for r,p in rows])
        @contextmanager
        def memory_pg():
            yield Reader()
        gateway._pg = memory_pg
        lookup = lambda:gateway.answer_was_applied('c','r1','u','q1','body','tail')
        assert lookup()
        assert not gateway.answer_was_applied('c','r1','u','other','body','tail')
        assert not gateway.answer_was_applied('c','r1','u','q1','other','tail')
        assert not gateway.answer_was_applied('c','r1','u','q1','body','other-tail')
        conn.execute('UPDATE resume_ai_reviews SET user_id=8')
        assert not lookup()
        conn.execute('UPDATE resume_ai_reviews SET user_id=7, resume_id=29')
        assert not lookup()
        conn.execute('UPDATE resume_ai_reviews SET resume_id=28')
        conn.execute("UPDATE resume_ai_applications SET undone_by='undo1'")
        assert not lookup()


def test_duplicate_cancel_reuses_saved_response_without_another_state_edit(pipeline):
    client,reviews,calls,db,q,response=history(pipeline)
    claimed={}
    def claim(cohort,resume,uid,rid,fingerprint,tail=None):
        if rid in claimed:
            assert claimed[rid]==fingerprint
            return {'response':reviews[rid]}
        claimed[rid]=fingerprint
        return {}
    db.claim_review.side_effect=claim
    before=db.complete_review.call_count
    first=post(client,'cancel',previous_review_id='answered',answer_changes=[mutation(q)])
    second=post(client,'cancel',previous_review_id='answered',answer_changes=[mutation(q)])
    assert first['review_id']==second['review_id']
    assert len(second['telemetry']['answer_changes'])==1
    assert db.complete_review.call_count==before+1


def test_old_answer_candidate_cannot_be_applied_but_document_undo_is_separate(monkeypatch):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from unittest.mock import Mock
    from app.local_resume_site_adapter import LocalGateway
    from app.firebase_gateway import FirebaseGateway
    from app.review_workflow import ReviewConflict
    gateway=LocalGateway.__new__(LocalGateway)
    gateway.review_execution=Mock(side_effect=lambda *args:nullcontext())
    gateway.latest_review_response=Mock(return_value={'telemetry':{'answer_changes':[{'field_path':'projects[0].description'}]},'confirmed_answers':[]})
    gateway.get_ai_review=Mock(return_value={'sentence_reviews':[{'field_path':'projects[0].description'}],
        'confirmed_answers':[{'field_path':'projects[0].description','answer':'취소한 답변'}]})
    base=Mock(return_value='undo-result');monkeypatch.setattr(FirebaseGateway,'apply_or_undo',base)
    request=SimpleNamespace(cohort_id='c',resume_id='r',tailored_resume_id=None,review_id='old',selected_indices=[0])
    with pytest.raises(ReviewConflict,match='answer_state_changed'):gateway.apply_or_undo('u',request)
    base.assert_not_called()
    assert gateway.apply_or_undo('u',request,undo=True)=='undo-result'
    assert gateway.review_execution.call_count==2
    gateway.review_execution.assert_called_with('c','r','u',None)


@pytest.mark.parametrize('operation',['replace','retract'])
def test_unassigned_answer_repair_never_injects_experience_evidence(pipeline,operation):
    client,reviews,calls,db,q,response=history(pipeline)
    previous=deepcopy(response);original=deepcopy(previous['telemetry']['v2_results'])
    heldq={**q,'question_id':'held:v2gap:q','experience_id':None,'owner_scope':'unassigned',
        'field_path':'__requirement_owner__','requirement_id':'req','requirement_context_hash':'context'}
    previous['telemetry']['requirement_answers']=[dict(requirement_id='req',experience_id=None,
        question_data=heldq,answer='이전 보류 답변',disposition='provided',context_hash='context')]
    change=AnswerChange(question_id=heldq['question_id'],operation=operation,expected_answer='이전 보류 답변',answer='수정한 보류 답변')
    repaired=repair_answer(previous,change,heldq,{'projects[0].description':'API를 구현했습니다.'},{'projects[0].description':'projects:p1'})
    assert repaired['telemetry']['v2_results']==original
    assert repaired['confirmed_answers']==previous['confirmed_answers']
    if operation=='retract':assert repaired['telemetry']['requirement_answers']==[]
    else:
        assert repaired['telemetry']['requirement_answers'][0]['answer']=='수정한 보류 답변'
        assert repaired['questions'][-1]['owner_scope']=='unassigned'
