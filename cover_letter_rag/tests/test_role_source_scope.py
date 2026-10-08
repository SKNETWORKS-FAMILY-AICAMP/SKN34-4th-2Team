"""Explicit role-field meaning versus stronger responsibility. No DB/model."""
import pytest
from app.resume_review_v2.models import Experience, ReviewInput, Evidence, SourceDocument, RevisionPlan, RevisionSentence, WriterOutput, SectionSemanticProfile
from app.resume_review_v2.validation import validate_candidate
from app.resume_review_v2.llm import scoped_evidence


def role_case(kind='role'):
    exp=Experience(experience_id='p1',kind='project',title='연동 서비스',
        field_path='projects[0].description',current_text='데이터를 서비스에 연결했습니다.',content_hash='h')
    scope='데이터 수집 및 API 연동'
    fact=Evidence(evidence_id='role',experience_id='p1',fact_type=kind,
        normalized_fact='데이터 수집 및 API 연동 역할을 맡았습니다.',evidence_quote=scope,
        source_type='resume_text',source_id='p1:role',assertion_state='resume_stated')
    req=ReviewInput(experience=exp,resume_sources=[SourceDocument(source_id='p1:role',text=scope)],
        section_profile=SectionSemanticProfile(section_type='project',evidence_claim_ids=['role']))
    plan=RevisionPlan(objective='명시된 역할의 재서술',operation='replace_field',core_evidence_ids=['role'])
    return req,fact,plan


def verdict(req,fact,plan,text,tag):
    writer=WriterOutput(experience_id='p1',operation='replace_field',original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=text,evidence_ids=['role'],claim_types=[tag])])
    return validate_candidate(req,writer,plan,{'role':fact})


@pytest.mark.parametrize('tag',['action_performed','role_owned'])
@pytest.mark.parametrize('kind',['role','implementation','technology'])
def test_explicit_role_scope_survives_labels_and_writer_context(kind,tag):
    req,fact,plan=role_case(kind)
    context=scoped_evidence(req,[fact])[0]['source_context']
    assert context['field']=='role' and context['experience_id']=='p1'
    check=verdict(req,fact,plan,'프로젝트 역할은 데이터 수집 및 API 연동이었습니다.',tag)
    assert not check.factual_issues


@pytest.mark.parametrize('text',[
    '데이터 수집 및 API 연동을 담당했습니다.',
    '저는 데이터 수집 및 API 연동을 맡았습니다.',
    '데이터 수집과 API 연동을 맡아 서비스를 구현했습니다.',
    '데이터 수집 및 API 연동 역할을 수행하며 서비스를 구현했습니다.',
    '프로젝트에서 데이터 수집 및 API 연동 역할을 맡아 서비스를 구현했습니다.',
    '해당 프로젝트에서 데이터 수집 및 API 연동 역할로 참여했습니다.',
    '사용자 요청을 데이터와 연결하는 프로젝트에서 데이터 수집 및 API 연동 역할을 맡아 구현했습니다.',
])
@pytest.mark.parametrize('tag',['action_performed','role_owned'])
def test_assigned_scope_restatement_not_whole_project_ownership(text,tag):
    req,fact,plan=role_case()
    assert not verdict(req,fact,plan,text,tag).factual_issues


@pytest.mark.parametrize('text',['프로젝트 역할은 데이터 수집 및 API 연동이었습니다.',
    '프로젝트에서 데이터 수집 및 API 연동 역할을 수행했습니다.'])
def test_explicit_role_declaration_in_current_prose_keeps_its_original_support(text):
    req,fact,plan=role_case()
    req.experience.current_text=text
    fact.source_id='p1';fact.evidence_quote=text
    for tag in ['action_performed','role_owned']:
        assert not verdict(req,fact,plan,text,tag).factual_issues


@pytest.mark.parametrize('text',[
    '프로젝트 역할은 데이터 수집 및 API 연동과 서비스 전체 책임이었습니다.',
    '데이터 수집 및 API 연동을 주도했습니다.',
    '서비스 전체를 총괄했습니다.',
    '데이터 수집 및 API 연동을 맡아 전체 서비스 운영을 책임졌습니다.',
    '데이터 수집과 API 연동 및 서비스 전체 운영을 맡았습니다.',
    '프로젝트에서 데이터 수집 및 API 연동과 전체 서비스 운영 역할을 수행했습니다.',
    '다른 프로젝트에서 데이터 수집 및 API 연동 역할을 수행했습니다.',
    '전체 운영을 담당하는 프로젝트에서 데이터 수집 및 API 연동 역할을 맡았습니다.',
    '보안 감사 역할을 수행하는 프로젝트에서 데이터 수집 및 API 연동 역할을 맡았습니다.',
    '전체 조직을 총괄한 프로젝트에서 데이터 수집 및 API 연동 역할을 맡았습니다.',
    '다른 프로젝트에서 작업했던 프로젝트에서 데이터 수집 및 API 연동 역할을 맡았습니다.',
    '사용자 요청을 연결하는 프로젝트에서 데이터 수집 및 API 연동과 운영 책임 역할을 맡았습니다.',
])
@pytest.mark.parametrize('tag',['action_performed','role_owned'])
def test_explicit_role_does_not_authorize_broader_claim(text,tag):
    req,fact,plan=role_case()
    assert any(i.code=='unsupported_agency' for i in verdict(req,fact,plan,text,tag).factual_issues)


@pytest.mark.parametrize('mode',['inventory','other_owner','wrong_source','inactive'])
@pytest.mark.parametrize('tag',['action_performed','role_owned'])
@pytest.mark.parametrize('text',['프로젝트 역할은 데이터 수집 및 API 연동이었습니다.',
    '프로젝트에서 데이터 수집 및 API 연동 역할을 수행했습니다.'])
def test_source_scope_and_activity_state_are_required_even_with_same_words(mode,tag,text):
    req,fact,plan=role_case()
    if mode=='inventory':
        fact.source_id='p1:techStack';req.resume_sources=[SourceDocument(source_id='p1:techStack',text=fact.evidence_quote)]
    elif mode=='other_owner':
        fact.experience_id='p2';fact.source_id='p2:role';req.resume_sources=[SourceDocument(source_id='p2:role',text=fact.evidence_quote)]
    elif mode=='wrong_source':req.resume_sources[0].text='문서 작성'
    else:fact.assertion_state='retracted'
    check=verdict(req,fact,plan,text,tag)
    assert any(i.code=='unsupported_agency' for i in check.factual_issues)


@pytest.mark.parametrize('tag',['action_performed','role_owned'])
def test_plain_performed_work_is_not_reclassified_by_a_role_tag(tag):
    req,fact,plan=role_case('implementation')
    fact.source_id='p1';fact.evidence_quote=req.experience.current_text
    fact.normalized_fact=req.experience.current_text
    assert not verdict(req,fact,plan,req.experience.current_text,tag).factual_issues
