"""Planner contracts only; no DB, credentials, or network."""
import pytest
from app.application_planning.models import (PlanningInput, PlanningExperience, Fact, QuestionAnalysis,
    Ask, Constraints, QuestionAssignment, ApplicationPlan, Gap, AnswerDocument, RequirementCoverage)
from app.application_planning.engine import validate_plan, scoped_plan_schema


def data(key='technical_contribution', facts=None):
    return PlanningInput(application_id='app', questions=[QuestionAnalysis(question_id='q',
        asks_for=[Ask(key=key, source_quote='quote')], constraints=Constraints())],
        experiences=[PlanningExperience(experience_id=exp, title=exp, kind='project', evidence=[
            Fact(evidence_id=f'{exp}-{kind}', experience_id=exp, fact_type=kind,
                 normalized_fact=f'{exp} {kind}', assertion_state='user_asserted')
            for kind in (facts or ['action','verification','result'])]) for exp in ['A','B']])


def plan(scope=None, core=None, results=None, gaps=None):
    return ApplicationPlan(assignments=[QuestionAssignment(question_id='q',
        primary_experience_ids=['A'] if scope is None else scope, story_focus='Direct contribution',
        core_evidence_ids=['A-action'] if core is None else core,
        result_evidence_ids=results or [], missing_information=gaps or [], rationale='Actual facts')])


def gap(category, key='result', target=None, proposal='Please clarify', importance='high'):
    return Gap(category=category,key=key,target_experience_id=target,reason='Missing',
               question_proposal=proposal,importance=importance)


def wire_plan(d, p):
    # Current model-facing contract requires coverage; historical plans remain readable.
    p.assignments[0].requirement_coverage = [RequirementCoverage(requirement=a.key,
        status='partial', reason='Fixture coverage assessment', blocking_missing_information='Essential material missing')
        for a in d.questions[0].asks_for]
    return p.model_dump()


@pytest.mark.parametrize('tier', ['core_evidence_ids','supporting_evidence_ids','result_evidence_ids'])
def test_other_experience_in_any_tier_rejected(tier):
    p=plan()
    setattr(p.assignments[0],tier,['B-result' if tier=='result_evidence_ids' else 'B-action'])
    with pytest.raises(ValueError,match='wrong-experience'): validate_plan(data(),p)


def test_explicit_multiple_experience_scope_allowed():
    result=validate_plan(data(),plan(scope=['A','B'],core=['A-action','B-action'],results=['B-result']))
    assert result.plan.assignments[0].primary_experience_ids==['A','B']


@pytest.mark.parametrize('kind',['action','verification','implementation'])
def test_non_result_fact_cannot_be_promoted(kind):
    with pytest.raises(ValueError,match='approved result'):
        validate_plan(data(facts=[kind]),plan(core=[f'A-{kind}'],results=[f'A-{kind}']))


def test_real_qualitative_result_allowed():
    d=data('result')
    d.experiences[0].evidence[2].normalized_fact='수정 후 API 요청이 정상 처리됨'
    assert validate_plan(d,plan(results=['A-result'])).plan.assignments[0].result_evidence_ids==['A-result']


def test_missing_result_creates_experience_gap():
    r=validate_plan(data('result',facts=['action','verification']),plan())
    g=r.plan.assignments[0].missing_information[0]
    assert (g.category,g.key,g.target_experience_id)==('experience_evidence','result','A')


def test_required_result_never_replaced_by_intent_gap():
    with pytest.raises(ValueError,match='different information source'):
        validate_plan(data('result',facts=['action']),plan(gaps=[gap('applicant_intent')]))


def test_experience_gap_always_needs_real_target():
    with pytest.raises(ValueError,match='needs target'):
        validate_plan(data(),plan(gaps=[gap('experience_evidence')]))


def test_intent_has_no_experience_target():
    d=data('company_motivation')
    r=validate_plan(d,plan(gaps=[gap('applicant_intent','company_motivation')]))
    assert r.next_question.target_experience_id is None
    with pytest.raises(ValueError,match='not Experience'):
        validate_plan(d,plan(gaps=[gap('applicant_intent','company_motivation','A')]))


def test_strength_is_experience_not_intent():
    with pytest.raises(ValueError,match='different information source'):
        validate_plan(data('differentiating_strength'),plan(gaps=[gap('applicant_intent','differentiating_strength')]))


def test_company_intent_is_not_experience():
    with pytest.raises(ValueError,match='different information source'):
        validate_plan(data('company_motivation'),plan(gaps=[gap('experience_evidence','company_motivation','A')]))


def test_target_context_gap_does_not_hide_missing_intent_or_get_asked_as_experience():
    d=data('company_motivation');d.target_context={'recruit_role':{'role_description':'AI','requirements':{'required':['Kubernetes']}}}
    r=validate_plan(d,plan(gaps=[gap('target_context','company_motivation')]))
    assert {g.category for g in r.plan.assignments[0].missing_information}=={'target_context','applicant_intent'}
    assert r.next_question.category=='applicant_intent'


def test_target_context_gap_is_not_a_user_question():
    r=validate_plan(data(),plan(gaps=[gap('target_context','technical_contribution')]))
    assert r.next_question is None


def test_target_context_id_cannot_be_selected_as_applicant_fact():
    d=data();d.target_context={'evidence_id':'job-python','requirements':['Python']}
    with pytest.raises(ValueError,match='Unapproved'):
        validate_plan(d,plan(core=['job-python']))


@pytest.mark.parametrize('state',['uncertain','retracted','contradicted','superseded'])
def test_mutated_input_inactive_fact_rejected(state):
    d=data();d.experiences[0].evidence[0].assertion_state=state
    with pytest.raises(ValueError,match='Inactive'): validate_plan(d,plan())


def test_one_next_question_even_with_multiple_high_gaps():
    r=validate_plan(data(facts=['action']),plan(gaps=[gap('experience_evidence','result','A'),
        gap('experience_evidence','challenge','A')]))
    assert r.next_question.key=='result'


def test_existing_preparation_selected_independently_of_company_motivation_gap():
    d=data('company_motivation');d.questions[0].asks_for.append(Ask(key='preparation_effort',source_quote='quote'))
    r=validate_plan(d,plan())
    assert r.plan.assignments[0].core_evidence_ids==['A-action']
    assert {g.key for g in r.plan.assignments[0].missing_information}=={'company_motivation'}


def test_legacy_gap_is_readable_but_schema_only_exposes_new_category():
    assert gap('applicant_evidence',target='A').category=='experience_evidence'
    schema=Gap.model_json_schema()
    assert schema['properties']['category']['enum']==['experience_evidence','applicant_intent','target_context']


def test_legacy_dedupe_key_still_suppresses_repeated_question():
    d=data(facts=['action']);d.previous_question_keys=['applicant_evidence:A:result']
    assert validate_plan(d,plan(gaps=[gap('experience_evidence','result','A')])).next_question is None


def test_intent_only_workspace_does_not_require_synthetic_experience():
    d=data('desired_work');d.experiences=[]
    r=validate_plan(d,plan(scope=[],core=[]))
    assert r.next_question.category=='applicant_intent'


def test_wire_schema_rejects_packed_and_unknown_evidence_ids():
    schema=scoped_plan_schema(data())
    for value in ['A-action, B-action','job-python']:
        with pytest.raises(ValueError):
            schema.model_validate(wire_plan(data(), plan(core=[value])))


def test_wire_schema_allows_only_real_result_ids_and_preserves_base_contract():
    d=data('result')
    schema=scoped_plan_schema(d)
    valid=schema.model_validate(wire_plan(d,plan(results=['A-result'])))
    assert validate_plan(d,valid).plan.assignments[0].result_evidence_ids==['A-result']
    with pytest.raises(ValueError): schema.model_validate(wire_plan(d,plan(results=['A-verification'])))


def test_no_result_wire_schema_requires_empty_result_list():
    d=data(facts=['action'])
    schema=scoped_plan_schema(d)
    assert schema.model_validate(wire_plan(d,plan())).assignments[0].result_evidence_ids==[]
    with pytest.raises(ValueError): schema.model_validate(wire_plan(d,plan(results=['A-action'])))


def test_no_experience_wire_schema_is_valid_for_intent_only_plan():
    d=data('desired_work');d.experiences=[]
    p=scoped_plan_schema(d).model_validate(wire_plan(d,plan(scope=[],core=[])))
    assert validate_plan(d,p).next_question.category=='applicant_intent'


def covered(p, key, status='satisfied', evidence=('A-action',), missing=''):
    p.assignments[0].requirement_coverage = [RequirementCoverage(requirement=key, status=status,
        evidence_ids=list(evidence), reason='Requirement-specific semantic assessment', blocking_missing_information=missing)]
    return p


def test_sufficient_preparation_has_no_gap_but_company_intent_remains_missing():
    d=data('preparation_effort', facts=['action','implementation'])
    d.experiences[0].evidence[0].normalized_fact='Python 데이터 분석 프로젝트 수행'
    d.questions[0].asks_for.append(Ask(key='company_motivation', source_quote='quote'))
    p=covered(plan(),'preparation_effort')
    p.assignments[0].requirement_coverage.append(RequirementCoverage(requirement='company_motivation',
        status='missing', reason='Personal company motivation absent', blocking_missing_information='Why this company'))
    r=validate_plan(d,p)
    assert [(g.key,g.category) for g in r.plan.assignments[0].missing_information]==[('company_motivation','applicant_intent')]


def test_satisfied_and_gap_for_same_requirement_rejected_not_silently_deleted():
    with pytest.raises(ValueError, match='cannot also have a missing gap'):
        validate_plan(data('preparation_effort'), covered(plan(gaps=[gap('experience_evidence','preparation_effort','A')]),'preparation_effort'))


def test_partial_improvable_does_not_require_gap():
    r=validate_plan(data('preparation_effort'), covered(plan(),'preparation_effort','partial'))
    assert r.plan.assignments[0].missing_information==[]


def test_optional_detail_is_not_valid_gap():
    with pytest.raises(ValueError,match='optional clarification'):
        validate_plan(data('preparation_effort'), covered(plan(gaps=[gap('experience_evidence','preparation_effort','A')]),'preparation_effort','partial'))


def test_some_evidence_does_not_automatically_remove_real_role_gap():
    p=covered(plan(core=['A-context'],gaps=[gap('experience_evidence','personal_action','A')]),
        'personal_action','partial',evidence=['A-context'],
        missing='Participation is known but own contribution is not established')
    r=validate_plan(data('personal_action',facts=['context']),p)
    assert r.next_question.key=='personal_action'


def test_result_required_action_only_still_has_gap_with_new_coverage():
    p=covered(plan(),'result','missing',missing='No confirmed result')
    r=validate_plan(data('result',facts=['action']),p)
    assert r.next_question.key=='result'


def test_satisfied_result_without_result_fact_rejected():
    with pytest.raises(ValueError,match='selected result Evidence'):
        validate_plan(data('result',facts=['action']),covered(plan(),'result'))


def test_experience_does_not_satisfy_personal_intent():
    with pytest.raises(ValueError,match='confirmed applicant intent'):
        validate_plan(data('company_motivation'),covered(plan(),'company_motivation'))


def test_paraphrased_question_uses_existing_topic_dedupe():
    d=data('personal_action',facts=['context']);d.previous_question_keys=['experience_evidence:A:personal_action']
    p=plan(core=['A-context'],gaps=[gap('experience_evidence','personal_action','A',proposal='해당 프로젝트에서 직접 담당한 부분을 알려주세요.')])
    r=validate_plan(d,p)
    assert r.next_question is None
    assert r.plan.assignments[0].missing_information[0].question_proposal==''


def test_missing_coverage_in_new_wire_contract_rejected():
    with pytest.raises(ValueError): scoped_plan_schema(data()).model_validate(plan().model_dump())


def test_coverage_requires_complete_asks_and_selected_ids():
    d=data('preparation_effort')
    with pytest.raises(ValueError,match='selected approved'):
        validate_plan(d,covered(plan(),'preparation_effort',evidence=['B-action']))
    d.questions[0].asks_for.append(Ask(key='company_motivation',source_quote='quote'))
    with pytest.raises(ValueError,match='every ask'):
        validate_plan(d,covered(plan(),'preparation_effort'))


def test_fact_type_presence_does_not_override_partial_essential_gap_assessment():
    p=covered(plan(gaps=[gap('experience_evidence','personal_action','A')]),'personal_action','partial',
        missing='Known action does not establish own role in the requested project')
    assert validate_plan(data('personal_action',facts=['action']),p).next_question.key=='personal_action'
