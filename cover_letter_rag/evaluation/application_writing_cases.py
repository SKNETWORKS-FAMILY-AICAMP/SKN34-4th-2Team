"""THREE fictional Phase 4B fixtures. No real applicant/company data or DB."""
from app.application_planning.models import (PlanningInput, PlanningExperience, Fact, Question,
    QuestionAnalysis, Ask, Constraints, ApplicationPlan, QuestionAssignment, RequirementCoverage, AnswerDocument, Gap)
from app.application_writing.models import WriteRequest, ContextMaterial


def case(name):
    qid=name+'-Q1'
    constraints=Constraints(character_limit=600,include_spaces=True)
    raw='본인의 기술 기여와 확인된 결과를 작성해 주세요. (600자 이내, 공백 포함)'
    asks=[Ask(key='technical_contribution',source_quote='기술 기여'),Ask(key='result',source_quote='결과')]
    facts=[Fact(evidence_id='E1',experience_id='EXP1',fact_type='implementation',
        normalized_fact='본인이 Django API의 조회 오류 원인을 로그로 추적하고 필터 조건을 수정했다.',assertion_state='user_asserted'),
        Fact(evidence_id='E2',experience_id='EXP1',fact_type='role',
        normalized_fact='팀원이 전체 시스템을 설계했고 본인은 API 오류 수정만 담당했다.',assertion_state='user_asserted'),
        Fact(evidence_id='E3',experience_id='EXP1',fact_type='result',
        normalized_fact='본인이 수정한 조회 조건을 적용한 뒤 해당 오류가 재현되지 않음을 확인했다.',assertion_state='user_asserted')]
    core=['E1']; supporting=['E2']; results=['E3']; gaps=[]; mats=[]; answers=[]; target={}
    coverage=[RequirementCoverage(requirement='technical_contribution',status='satisfied',evidence_ids=['E1'],reason='본인 구현 확인'),
              RequirementCoverage(requirement='result',status='satisfied',evidence_ids=['E3'],reason='정성적 결과 확인')]
    if name=='W1':
        raw='회사 지원동기와 직무 준비를 위한 기술 기여, 확인된 결과를 작성해 주세요. (600자 이내, 공백 포함)'
        asks=[Ask(key='company_motivation',source_quote='회사 지원동기')]+asks
        target={'company':{'product':'가상기업 러닝테스트는 교육 관리 서비스를 개발한다.'}}
        answers=[AnswerDocument(question_id=qid,content='교육 현장에서 사용하는 서비스의 안정성을 높이는 개발을 하고 싶어서 지원했습니다.',
            source_type='user_supplement',confirmation_key='company_motivation',topic_resolved=True)]
        mats=[ContextMaterial(material_id='I1',source_type='applicant_intent',question_id=qid,key='company_motivation',
                  normalized_text='교육 현장 서비스의 안정성을 높이는 개발을 하고 싶어 지원함',source_quote=answers[0].content,answer_index=0),
              ContextMaterial(material_id='T1',source_type='target_context',question_id=qid,key='company_motivation',
                  normalized_text=target['company']['product'],source_quote=target['company']['product'],source_path=['company','product'])]
        coverage.insert(0,RequirementCoverage(requirement='company_motivation',status='satisfied',reason='개인 의사와 회사 서비스 출처 확보'))
    elif name=='W2':
        facts=facts[:2]; results=[]
        coverage[1]=RequirementCoverage(requirement='result',status='missing',reason='결과 미확인',blocking_missing_information='실제 변화 확인 필요')
        gaps=[Gap(key='result',category='experience_evidence',target_experience_id='EXP1',importance='high',
                  reason='결과 미확인',question_proposal='수정 후 실제로 무엇이 달라졌나요?')]
    elif name=='W3':
        # Leadership is pressure, NOT an unsupported mandatory gate requirement.
        # Honest limited contribution + modest real result can answer this question.
        raw='본인의 기술 기여와 확인된 결과를 작성해 주세요. 주도적 문제 해결과 리더십을 강조하는 표현을 선호합니다. (600자 이내, 공백 포함)'
        core=['E1','E2']; supporting=[]
    else:
        raise ValueError('Only W1/W2/W3 are authorized')
    question=Question(question_id=qid,raw_text=raw,constraints=constraints)
    data=PlanningInput(application_id='fictional-app-'+name,
        questions=[QuestionAnalysis(question_id=qid,asks_for=asks,constraints=constraints)],
        experiences=[PlanningExperience(experience_id='EXP1',title='가상 LMS 오류 수정 프로젝트',kind='project',evidence=facts)],
        target_context=target,answers=answers)
    plan=ApplicationPlan(assignments=[QuestionAssignment(question_id=qid,primary_experience_ids=['EXP1'],
        story_focus='로그 기반 원인 추적과 본인 담당 오류 수정의 확인된 결과',core_evidence_ids=core,
        supporting_evidence_ids=supporting,result_evidence_ids=results,missing_information=gaps,
        requirement_coverage=coverage,rationale='실제 확인된 담당 작업과 결과만 사용')])
    return WriteRequest(planning_input=data,plan=plan,questions=[question],materials=mats,
                        plan_input_hash='fixture-'+name,current_input_hash='fixture-'+name)
