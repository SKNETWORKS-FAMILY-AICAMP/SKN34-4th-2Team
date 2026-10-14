from copy import deepcopy
import pytest
from pydantic import ValidationError
from app.application_writing.models import WriterOutput, AnswerSentence, SupportRef, SemanticResult, AnswerResult
from app.application_writing.engine import readiness, writer_input, deterministic_validation, run_answer, merge_semantic
from evaluation.application_writing_cases import case


def output(qid='W1-Q1',text='Django API의 로그를 추적해 조회 조건을 수정하고 해당 오류가 재현되지 않음을 확인했습니다.',ids=('E1','E3')):
    return WriterOutput(question_id=qid,sentences=[AnswerSentence(text=text,
        support_refs=[SupportRef(source_type='evidence',source_id=i) for i in ids],claim_types=['evidence'])])


class FakeClient:
    def __init__(self,outputs=None,fact_issues=None,quality_issues=None):
        self.outputs=outputs or [output()]; self.fact_issues=fact_issues or []; self.quality_issues=quality_issues or []
        self.writes=[]; self.verifies=[]
    def write(self,payload,*,rewrite=None):
        self.writes.append((deepcopy(payload),deepcopy(rewrite)))
        return self.outputs[min(len(self.writes)-1,len(self.outputs)-1)]
    def verify(self,payload):
        self.verifies.append(payload)
        w=payload['writer_input']
        return SemanticResult(question_id=w['question']['question_id'],factual_issues=self.fact_issues,quality_issues=self.quality_issues,
            expressed_core_evidence_ids=[e['evidence_id'] for e in w['core']],
            covered_requirements=[a['key'] for a in w['requirements']],story_focus_preserved=True)


@pytest.mark.parametrize('name,expected',[('W1','READY'),('W2','NEEDS_INPUT'),('W3','READY')])
def test_readiness_fixtures(name,expected):
    assert readiness(case(name),name+'-Q1').status==expected


def test_missing_result_zero_writer_calls():
    client=FakeClient(); result=run_answer(case('W2'),'W2-Q1',client)
    assert result.status=='NEEDS_INPUT' and not client.writes and not client.verifies and not result.final_text


@pytest.mark.parametrize('mutation', ['stale','unknown','scope','coverage','overlap','quote','mixed','result_type','unknown_question'])
def test_contract_blockers_never_call_writer(mutation):
    r=case('W1'); row=r.plan.assignments[0]
    if mutation=='stale': r.current_input_hash='new'
    if mutation=='unknown': row.core_evidence_ids=['not-owned']
    if mutation=='scope': row.primary_experience_ids=[]
    if mutation=='coverage': row.requirement_coverage=[]
    if mutation=='overlap': row.supporting_evidence_ids=['E1']
    if mutation=='quote': r.materials[0].source_quote='untrue source'
    if mutation=='mixed': r.materials[0].source_path=['company']
    if mutation=='result_type': row.result_evidence_ids=['E1']
    if mutation=='unknown_question': r.questions[0].question_id='OTHER'
    client=FakeClient(); result=run_answer(r,'W1-Q1',client)
    assert result.status=='BLOCKED' and not client.writes


def test_inactive_state_schema_rejects():
    value=case('W1').model_dump(); value['planning_input']['experiences'][0]['evidence'][0]['assertion_state']='superseded'
    with pytest.raises(ValidationError): type(case('W1')).model_validate(value)


@pytest.mark.parametrize('kind',['applicant_intent','target_context'])
def test_missing_context_needs_input(kind):
    r=case('W1'); r.materials=[m for m in r.materials if m.source_type!=kind]
    assert readiness(r,'W1-Q1').status=='NEEDS_INPUT'


def test_no_raw_answers_or_unselected_facts_writer_input():
    r=case('W1'); payload=writer_input(r,'W1-Q1')
    assert 'answers' not in payload and all('source_quote' not in m for m in payload['context'])
    assert r.planning_input.answers[0].content not in str(payload)
    assert set(payload)=={'question','story_focus','requirements','experience_scope','core','supporting','result','context'}


def test_supporting_optional_core_required():
    r=case('W1'); valid=deterministic_validation(r,'W1-Q1',output())
    assert valid.passed
    invalid=deterministic_validation(r,'W1-Q1',output(text='해당 오류가 재현되지 않았습니다.',ids=('E3',)))
    assert 'core contribution unused' in invalid.quality_issues and 'critical technical signal loss' in invalid.quality_issues


@pytest.mark.parametrize('text,ids,issue',[
    ('Django로 수정했습니다.',('NO',),'unapproved'),
    ('Django로 응답 시간을 50% 개선했습니다.',('E1',),'unsupported number'),
    ('Redis 캐시를 구축했습니다.',('E1',),'unsupported technology')])
def test_sentence_fact_blockers(text,ids,issue):
    checked=deterministic_validation(case('W1'),'W1-Q1',output(text=text,ids=ids))
    assert any(issue in e for e in checked.factual_issues)


def test_three_source_sentence_provenance_and_assembly():
    r=case('W1'); candidate=output(text='교육 서비스를 개발하는 회사에서 안정성을 높이는 개발을 하고 싶습니다.',ids=())
    candidate.sentences[0].support_refs=[SupportRef(source_type='target_context',source_id='T1'),SupportRef(source_type='applicant_intent',source_id='I1')]
    candidate.sentences[0].claim_types=['target_context','applicant_intent']
    candidate.sentences+=output().sentences
    assert deterministic_validation(r,'W1-Q1',candidate).passed
    assert candidate.final_text==' '.join(s.text.strip() for s in candidate.sentences)
    assert 'final_text' not in candidate.model_dump()


def test_cross_question_duplicate_not_same_experience():
    r=case('W1'); prior=output(qid='OTHER')
    assert any('duplication' in e for e in deterministic_validation(r,'W1-Q1',output(),[prior]).quality_issues)
    different=output(qid='OTHER',text='팀원이 전체 시스템 설계를 담당한 프로젝트에서 저는 API 오류 수정 역할을 맡았습니다.',ids=('E2',))
    assert not deterministic_validation(r,'W1-Q1',output(),[different]).quality_issues


def test_maximum_one_combined_rewrite_then_blocked():
    r=case('W1'); client=FakeClient(fact_issues=['unsupported leadership'],quality_issues=['generic prose'])
    result=run_answer(r,'W1-Q1',client)
    assert result.status=='BLOCKED' and result.rewrite_count==1 and not result.final_text
    assert len(client.writes)==len(client.verifies)==2
    assert client.writes[0][0]==client.writes[1][0]
    assert client.writes[1][1]['factual_issues']==['unsupported leadership']


def test_invalid_reference_targeted_rewrite_without_first_semantic_call():
    client=FakeClient(outputs=[output(ids=('NO',)),output()])
    result=run_answer(case('W1'),'W1-Q1',client)
    assert result.status=='READY' and result.rewrite_count==1
    assert len(client.writes)==2 and len(client.verifies)==1


def test_normal_two_calls_and_quality_can_reject_grounded_prose():
    client=FakeClient(); result=run_answer(case('W1'),'W1-Q1',client)
    assert result.status=='READY' and len(client.writes)==len(client.verifies)==1
    result=run_answer(case('W1'),'W1-Q1',FakeClient(quality_issues=['manual rewrite needed']))
    assert result.status=='BLOCKED' and not result.validation.factual_issues


def test_explicit_limit_and_no_arbitrary_limit():
    r=case('W1'); r.questions[0].constraints.character_limit=30
    assert any('length' in s for s in deterministic_validation(r,'W1-Q1',output()).quality_issues)
    r.questions[0].constraints.character_limit=None
    assert deterministic_validation(r,'W1-Q1',output()).passed


def test_byte_space_policy():
    r=case('W1'); r.questions[0].constraints.count_unit='bytes'; r.questions[0].constraints.character_limit=20
    assert any('length' in s for s in deterministic_validation(r,'W1-Q1',output()).quality_issues)


def test_transport_failure_no_paid_resampling():
    class Broken(FakeClient):
        def write(self,payload,*,rewrite=None): self.writes.append(payload); raise TimeoutError()
    client=Broken(); result=run_answer(case('W1'),'W1-Q1',client)
    assert result.status=='BLOCKED' and len(client.writes)==1 and result.error=='TimeoutError'


def test_verifier_contract_error_does_not_rewrite_writer():
    class Broken(FakeClient):
        def verify(self,payload):
            result=super().verify(payload); result.expressed_core_evidence_ids.append('E3'); return result
    client=Broken(); result=run_answer(case('W1'),'W1-Q1',client)
    assert result.status=='BLOCKED' and result.error=='VerifierContractError'
    assert len(client.writes)==len(client.verifies)==1 and result.rewrite_count==0


def test_semantic_wire_schema_limits_core_ids_and_question():
    from app.application_writing.llm import StructuredWritingClient
    class Model:
        def with_structured_output(self,schema):
            self.schema=schema
            class Call:
                def invoke(self,messages): return None
            return Call()
    model=Model(); r=case('W1'); candidate=output()
    StructuredWritingClient(model).verify(dict(writer_input=writer_input(r,'W1-Q1'),candidate=candidate.model_dump()))
    base=dict(question_id='W1-Q1',factual_issues=[],quality_issues=[],expressed_core_evidence_ids=['E1'],
              covered_requirements=['result'],story_focus_preserved=True)
    assert model.schema.model_validate(base)
    with pytest.raises(ValidationError): model.schema.model_validate({**base,'expressed_core_evidence_ids':['E3']})
    with pytest.raises(ValidationError): model.schema.model_validate({**base,'question_id':'OTHER'})


def test_optional_detail_does_not_block_but_important_partial_gap_does():
    from app.application_planning.models import Gap
    r=case('W1'); row=r.plan.assignments[0]
    row.requirement_coverage[1].status='partial'
    assert readiness(r,'W1-Q1').status=='READY'
    row.requirement_coverage[1].blocking_missing_information='핵심 구현이 부족'
    row.missing_information=[Gap(key='technical_contribution',category='experience_evidence',target_experience_id='EXP1',
        reason='본인 구현 추가 확인',importance='high',question_proposal='담당한 구현은 무엇인가요?')]
    assert readiness(r,'W1-Q1').status=='NEEDS_INPUT'


def test_company_source_cannot_be_referenced_as_applicant_evidence():
    candidate=output(ids=('T1',))
    assert any('unapproved' in i for i in deterministic_validation(case('W1'),'W1-Q1',candidate).factual_issues)


def test_unreferenced_claim_requires_semantic_check():
    client=FakeClient(fact_issues=['unreferenced applicant leadership'])
    result=run_answer(case('W1'),'W1-Q1',client)
    assert result.status=='BLOCKED'


def test_required_result_cannot_disappear_from_provenance():
    checked=deterministic_validation(case('W1'),'W1-Q1',output(ids=('E1',)))
    assert 'required result not expressed' in checked.quality_issues


def test_missing_result_gap_not_repeated_by_gate():
    gate=readiness(case('W2'),'W2-Q1')
    assert len([g for g in gate.missing_information if g['key']=='result'])==1


def test_fact_source_parent_cannot_be_changed_to_another_experience():
    r=case('W1'); r.planning_input.experiences[0].evidence[0].experience_id='OTHER'
    client=FakeClient(); result=run_answer(r,'W1-Q1',client)
    assert result.status=='BLOCKED' and not client.writes


def test_rhetorical_connectors_cannot_smuggle_technology():
    candidate=output(text='Redis로 문제를 해결했습니다.',ids=())
    candidate.sentences[0].claim_types=[]
    assert any('unsupported technology' in e for e in deterministic_validation(case('W1'),'W1-Q1',candidate).factual_issues)
