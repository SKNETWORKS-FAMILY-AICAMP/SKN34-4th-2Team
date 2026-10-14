"""STAR is a read-only, original-source projection. No DB or real LLM."""
import copy
import pytest
from test_project_live_pipeline import pipeline, post
from app.resume_review_v2.star_diagnostics import original_star_checks


def record(quote='조회가 정상 동작함을 확인했습니다.', kind='verification', role='validation'):
    return {'experience':{'experience_id':'projects:p1','kind':'project','title':'조회 서비스',
        'field_path':'projects[0].description','current_text':quote,'content_hash':'h'},
        'evidence_state':[{'evidence_id':'e','experience_id':'projects:p1','fact_type':kind,
            'normalized_fact':quote,'evidence_quote':quote,'source_type':'resume_text',
            'source_id':'projects:p1','assertion_state':'resume_stated'}],
        'section_profile':{'original_semantic_units':[{'semantic_role':role,
            'source_refs':[{'type':'applicant_evidence','id':'e'}]}]},
        'validation':{'factual_issues':[]}}


def diagnose(row, text=None, hash='h'):
    fields={row['experience']['field_path']:text or row['experience']['current_text']}
    return original_star_checks([row],fields,hash,lambda path,identity:(row['experience']['title'],[]))[0]


@pytest.mark.parametrize('quote,kind,role,present', [
    ('조회가 정상 동작함을 확인했습니다.','verification','validation',['result']),
    ('테스트를 수행했습니다.','verification','validation',[]),
    ('테스트를 수행했습니다.','result','outcome',[]),
    ('오류가 사라졌습니다.','result','outcome',['result']),
    ('FastAPI로 조회 API를 구현했습니다.','implementation','action',['action']),
])
def test_typed_meaning_and_exact_quotes_without_facet_mapping(quote,kind,role,present):
    row=record(quote,kind,role)
    row['evidence_facets']=[{'evidence_id':'e','slots':['outcome','actions','personal_role']}]
    check=diagnose(row)
    assert check.diagnostic_status=='complete' and check.present==present
    assert all(q in quote for q in check.quotes.values())


@pytest.mark.parametrize('change', ['owner','answer','source','retracted','uncertain','conflict'])
def test_non_current_applicant_source_cannot_support_star(change):
    row=record();fact=row['evidence_state'][0]
    if change=='owner':fact['experience_id']='projects:p2'
    elif change=='answer':fact.update(source_type='user_answer',source_id='answer')
    elif change=='source':fact['source_id']='projects:p1:techStack'
    elif change=='conflict':
        fact['conflicts_with_evidence_ids']=['other']
        other=copy.deepcopy(fact);other.update(evidence_id='other',conflicts_with_evidence_ids=[],assertion_state='uncertain')
        row['evidence_state'].append(other)
    else:fact['assertion_state']=change
    assert diagnose(row).present==[]


@pytest.mark.parametrize('mode', ['changed','failed','no-profile'])
def test_unknown_analysis_is_pending_not_star_missing(mode):
    row=record()
    if mode=='failed':row['validation']['factual_issues']=[{'code':'analysis_contract_invalid'}]
    if mode=='no-profile':row['section_profile']=None
    check=diagnose(row,hash='new' if mode=='changed' else 'h')
    assert check.diagnostic_status=='pending' and not check.present and not check.missing


@pytest.mark.parametrize('section', ['motivation','aspiration'])
def test_section_purpose_excludes_star(section):
    row=record();row['experience'].update(field_path=f'selfIntroduction.{section}.body',kind='other')
    check=diagnose(row)
    assert check.diagnostic_status=='not_applicable' and not check.missing


def test_same_prose_at_reordered_project_path_does_not_authorize_old_identity():
    row=record();path=row['experience']['field_path']
    check=original_star_checks([row],{path:row['experience']['current_text']},'h',
        lambda path,identity:(row['experience']['title'],[]),{path:'projects:another'})[0]
    assert check.diagnostic_status=='pending' and not check.present


def test_mounted_adapter_and_completed_cache_reuse_do_not_add_calls(pipeline):
    client,reviews,calls,db=pipeline
    first=post(client,'initial')
    assert first['star_checks'][0]['present']==['action']
    assert first['star_checks'][0]['diagnostic_status']=='complete'
    assert first['star_checks'][0]['experience_id']=='projects:p1'
    assert [s for s,_,_ in calls]==['BatchExtractionOutput','BatchWriterDraft','BatchFactVerification']
    cached=copy.deepcopy(first);cached['star_checks']=[]
    db.claim_review.return_value={'response':cached}
    reused=post(client,'cached')
    assert reused['star_checks']==first['star_checks'] and len(calls)==3
    content=db.get_owned_resume.return_value['content']
    content['projects'][0]['description']='수동으로 변경한 원문입니다.'
    changed=post(client,'changed')
    assert changed['star_checks'][0]['diagnostic_status']=='pending' and len(calls)==3
