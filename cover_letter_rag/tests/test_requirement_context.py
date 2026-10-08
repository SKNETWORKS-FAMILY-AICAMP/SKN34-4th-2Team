from copy import deepcopy
import pytest
from app.job_requirements import requirement_cache_key, REQUIREMENT_PROMPT_VERSION
from app.application_writing.models import WriterOutput, AnswerSentence, SupportRef
from app.application_writing.engine import check_sources, writer_input, deterministic_validation, run_answer
from app.application_writing.requirement_context import build_requirement_materials, resolve_requirement
from evaluation.application_writing_cases import case
from tests.test_application_writing import FakeClient


def request():
    r=case('W3'); context=r.planning_input.target_context
    rows=[dict(id='req-1',group='preferred',label='Django 개발 경험',posting_quote='Django 개발 경험 우대',kind='skill',kind_basis=''),
          dict(id='req-2',group='must',label='학사 이상',posting_quote='학사 이상 지원 가능',kind='eligibility',kind_basis='학력 조건'),
          dict(id='req-3',group='task',label='API 조회 오류 수정',posting_quote='API 조회 오류를 수정합니다.',kind='skill',kind_basis=''),
          dict(id='req-4',group='must',label='Kubernetes 운영',posting_quote='Kubernetes 운영 경험 필수',kind='skill',kind_basis='')]
    key=requirement_cache_key(dict(job_id='J1',snapshot_hash='S1'))
    context.update(job_id='J1',snapshot_hash='S1',role_version='R9',requirement_profile_key=key,requirements=rows,
                   requirement_profile_source=dict(job_id='J1',snapshot_hash='S1',profile_key=key,prompt_version=REQUIREMENT_PROMPT_VERSION))
    r.materials=build_requirement_materials(r.planning_input,r.plan,r.questions)
    return r


def test_lossless_relevant_material_and_quote():
    r=request(); assert {m.material_id for m in r.materials}=={'req-1','req-3'}
    m=next(m for m in r.materials if m.material_id=='req-1')
    assert m.source_type=='target_context' and m.source_quote=='Django 개발 경험 우대'
    assert m.requirement_source.requirement.model_dump()==r.planning_input.target_context['requirements'][0]
    assert m.source_path==['requirements','id:req-1','posting_quote']
    assert m.requirement_source.snapshot_hash=='S1' and m.requirement_source.profile_key.endswith('__req-v1')
    check_sources(r)
    payload=writer_input(r,'W3-Q1')
    assert payload['context'][0]['requirement_source']['requirement']['kind']=='skill'


def test_array_order_has_no_effect_on_reference_or_selection():
    r=request(); before=[m.model_dump() for m in r.materials]
    r.planning_input.target_context['requirements'].reverse()
    check_sources(r)
    assert before==[m.model_dump() for m in build_requirement_materials(r.planning_input,r.plan,r.questions)]


@pytest.mark.parametrize('mutation',['quote','profile','snapshot','version','id','namespace','application','payload','hash','duplicate','missing_quote'])
def test_source_mismatch_blocked(mutation):
    r=request(); m=r.materials[0]; c=r.planning_input.target_context
    if mutation=='quote': m.source_quote='invented'
    if mutation=='profile': c['requirement_profile_key']='wrong'
    if mutation=='snapshot': c['snapshot_hash']='S2'
    if mutation=='version': m.requirement_source.prompt_version='req-new'
    if mutation=='id': m.material_id='req-NO'
    if mutation=='namespace': m.source_type='applicant_intent'
    if mutation=='application': m.requirement_source.application_id='OTHER'
    if mutation=='payload': m.requirement_source.requirement.group='must'
    if mutation=='hash': m.requirement_source.requirement_hash='changed'
    if mutation=='duplicate': c['requirements'].append(deepcopy(c['requirements'][0]))
    if mutation=='missing_quote': c['requirements'][0]['posting_quote']=''
    with pytest.raises(ValueError): check_sources(r)
    client=FakeClient(); result=run_answer(r,'W3-Q1',client)
    assert result.status=='BLOCKED' and not client.writes


def test_no_profile_no_material_no_extraction():
    r=case('W3')
    assert build_requirement_materials(r.planning_input,r.plan,r.questions)==[]


def test_eligibility_only_when_question_directly_asks():
    r=request(); assert 'req-2' not in {m.material_id for m in r.materials}
    r.questions[0].raw_text+=' 학사 학위가 있는지 알려 주세요.'
    mats=build_requirement_materials(r.planning_input,r.plan,r.questions)
    assert 'req-2' in {m.material_id for m in mats}


def test_applicant_python_not_created_from_target_python():
    r=request(); c=r.planning_input.target_context; c['requirements'][0].update(label='Python 경험',posting_quote='Python 경험 우대')
    r.plan.assignments[0].story_focus='Python 관련 직무 준비'
    before=deepcopy(r.planning_input.experiences)
    r.materials=build_requirement_materials(r.planning_input,r.plan,r.questions)
    assert r.planning_input.experiences==before
    bad=WriterOutput(question_id='W3-Q1',sentences=[AnswerSentence(text='Python을 사용했습니다.',claim_types=['evidence'],
        support_refs=[SupportRef(source_type='evidence',source_id='E1')])])
    assert any('unsupported technology' in i for i in deterministic_validation(r,'W3-Q1',bad).factual_issues)
    bad.sentences[0].support_refs[0].source_id='req-1'
    assert any('unapproved' in i for i in deterministic_validation(r,'W3-Q1',bad).factual_issues)


def test_preferred_to_must_semantic_failure_blocks():
    r=request()
    candidate=WriterOutput(question_id='W3-Q1',sentences=[AnswerSentence(text='귀사는 Django를 필수로 요구합니다.',
        claim_types=['target_context'],support_refs=[SupportRef(source_type='target_context',source_id='req-1')])])
    client=FakeClient(outputs=[candidate],fact_issues=['unsupported target claim: preferred converted to must'])
    result=run_answer(r,'W3-Q1',client)
    assert result.status=='BLOCKED' and result.rewrite_count==1
    assert any('preferred converted to must' in i for i in result.validation.factual_issues)
    assert next(m for m in client.verifies[0]['source_materials'] if m['material_id']=='req-1')['requirement_source']['requirement']['group']=='preferred'


def test_same_logical_requirement_can_support_two_questions():
    r=request(); q=deepcopy(r.questions[0]); q.question_id='Q2'; r.questions.append(q)
    qa=deepcopy(r.planning_input.questions[0]); qa.question_id='Q2'; r.planning_input.questions.append(qa)
    a=deepcopy(r.plan.assignments[0]); a.question_id='Q2'; r.plan.assignments.append(a)
    r.materials=build_requirement_materials(r.planning_input,r.plan,r.questions)
    check_sources(r)
    assert sum(m.material_id=='req-1' for m in r.materials)==2


def test_context_cap_is_not_must_preferred_scoring():
    r=request(); rows=r.planning_input.target_context['requirements']
    rows.extend(dict(id='extra-'+str(i),group='must',label='Django',posting_quote='Django 경험 필수',kind='skill',kind_basis='') for i in range(8))
    assert len(build_requirement_materials(r.planning_input,r.plan,r.questions))==3


def test_career_project_question_is_not_eligibility_duration_question():
    r=request(); r.planning_input.target_context['requirements'][1].update(label='경력 2년 이하',posting_quote='경력 2년 이하만 지원 가능')
    r.questions[0].raw_text='경력에서 수행한 프로젝트의 Django 기술 기여를 설명하세요.'
    assert 'req-2' not in {m.material_id for m in build_requirement_materials(r.planning_input,r.plan,r.questions)}


def test_existing_cache_hit_does_not_call_extractor_or_save():
    from app.job_requirements import load_or_extract_requirements
    r=request(); rows=r.planning_input.target_context['requirements']
    class Gateway:
        def get_job_requirements(self,key):
            assert key==requirement_cache_key(dict(job_id='J1',snapshot_hash='S1')); return rows
        def save_job_requirements(self,*args): raise AssertionError('No writes on cache hit')
    def extractor(*args): raise AssertionError('No LLM extraction on cache hit')
    assert [v.model_dump() for v in load_or_extract_requirements(Gateway(),extractor,'source',dict(job_id='J1',snapshot_hash='S1'))]==rows


def test_old_cached_default_skill_does_not_bypass_eligibility_guard():
    r=request(); row=r.planning_input.target_context['requirements'][1]; row['kind']='skill'
    r.plan.assignments[0].story_focus+=' 학사 과정의 프로젝트'
    before=deepcopy(row)
    assert 'req-2' not in {m.material_id for m in build_requirement_materials(r.planning_input,r.plan,r.questions)}
    assert row==before  # source record, kind and cache are never rewritten
