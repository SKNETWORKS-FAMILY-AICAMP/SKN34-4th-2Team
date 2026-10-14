"""STAR 판정 확정, 지원 자격 요건 분류, 답해도 소용없는 질문 거르기. 모델 없이 서버 규칙만 본다."""
from app.job_requirements import JobRequirement, classify_requirement, classify_requirements
from app.models import ConfirmationAnswer, ResumeReviewGeneration, ReviewQuestion, SentenceReview, StarJudgementOut
from app.review_workflow import (
    add_requirement_questions, add_thin_self_introduction_questions, assign_review_stages,
    filter_questions_by_resume_facts, humanize_internal_terms, prefer_project_evidence_over_surface_edit,
)
from app.star_checks import ground_star_judgements

FIELDS = {
    'projects[0].name': '온도 센서 모니터링 장치',
    'projects[0].description': 'I2C 센서 드라이버 작성, 수집값을 MQTT로 서버에 전송. 24시간 연속 동작 검증.',
    'awards[0].name': '전국 대학생 임베디드 경진대회 본선 진출',
    'awards[0].description': '자율주행 소형 로봇으로 참가. 모터 제어와 센서 필터링 펌웨어를 담당했습니다.',
    'selfIntroduction.challenge.body': '자동화한 케이스가 열 번에 한 번씩 실패했습니다. 로그를 모아 보니 대기 조건이 원인이었고, '
                                       '요소 기준으로 바꿔 실패율을 0으로 만들었습니다.',
    'selfIntroduction.growth.body': '어릴때부터 컴퓨터를 좋아했습니다.',
    'coreCompetencies.text': 'C/C++로 센서 드라이버를 구현.',
}


def _question(path, topic, text, requirement_id=None, reason='r'):
    return ReviewQuestion(field_path=path, topic=topic, question=text, reason=reason, priority=2,
                          requirement_id=requirement_id)


def test_star_element_is_present_only_with_a_verified_quote():
    checks, warnings = ground_star_judgements([
        StarJudgementOut(field_path='projects[0].description', action_quote='I2C 센서 드라이버 작성',
                         result_quote='24시간 연속 동작 검증', situation_quote='센서 값이 자주 끊겨서',  # 원문에 없다
                         missing_reason='왜 만들었는지가 없어요.'),
        StarJudgementOut(field_path='awards[0].description', task_quote='모터 제어와 센서 필터링 펌웨어를 담당'),
    ], FIELDS, [])
    by_path = {c.field_path: c for c in checks}
    assert by_path['projects[0].description'].present == ['action', 'result']
    assert by_path['projects[0].description'].missing == ['situation', 'task']
    assert by_path['awards[0].description'].present == ['task']
    assert any('STAR 인용 불일치' in w for w in warnings)


def test_star_answer_quote_counts_and_unjudged_items_keep_previous_judgement():
    answer = ConfirmationAnswer(question_id='q1', field_path='awards[0].description', question='어떻게 제어했나요?',
                                answer='바퀴 모터 속도를 PID로 제어하고 게인을 직접 튜닝했어요')
    previous = [{'field_path': 'projects[0].description', 'present': ['action', 'result'],
                 'missing': ['situation', 'task'], 'reason': '', 'quotes': {}}]
    checks, _ = ground_star_judgements([
        StarJudgementOut(field_path='awards[0].description', task_quote='센서 필터링 펌웨어를 담당',
                         action_quote='PID로 제어하고 게인을 직접 튜닝'),
    ], FIELDS, [answer], previous, judged_paths=['awards[0].description'])
    by_path = {c.field_path: c for c in checks}
    assert by_path['awards[0].description'].present == ['task', 'action'], '확인 답변의 인용도 근거다'
    assert by_path['projects[0].description'].present == ['action', 'result'], '답하지 않은 항목은 이전 판정을 잇는다'


def test_eligibility_requirements_are_classified_from_the_label():
    assert classify_requirement('신입 또는 경력 2년 이하', {'career_type': 'ENTRY', 'min_career_years': 0}) == \
        ('eligibility', '공고 조건: 신입')
    assert classify_requirement('관련 전공')[0] == 'eligibility'
    assert classify_requirement('운전면허')[0] == 'eligibility'
    assert classify_requirement('주 5일 풀타임 근무 가능')[0] == 'eligibility'
    for label in ('백엔드 실무 경험', 'C/C++ 개발 역량', 'Git 협업', 'RTOS·Linux 경험', '정보처리기사'):
        assert classify_requirement(label)[0] == 'skill', label
    classified = classify_requirements([JobRequirement(id='req-1', group='must', label='경력 3년 이상', posting_quote='경력 3년 이상')])
    assert classified[0].kind == 'eligibility'


def test_eligibility_requirement_is_never_asked_and_task_without_evidence_is_dropped():
    rows = [
        {'id': 'req-1', 'group': 'must', 'label': '신입 또는 경력 2년 이하', 'status': 'unconfirmed', 'kind': 'eligibility'},
        {'id': 'req-2', 'group': 'must', 'label': 'AVR·ESPRESSIF 개발', 'status': 'unconfirmed', 'kind': 'skill'},
        {'id': 'req-3', 'group': 'task', 'label': '소프트웨어 배포(OTA)', 'status': 'unconfirmed', 'kind': 'skill'},
        {'id': 'req-4', 'group': 'task', 'label': '임베디드 테스트', 'status': 'partial', 'kind': 'skill',
         'evidence_paths': ['projects[0].description']},
    ]
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        _question('coreCompetencies.text', 'scope', "'산업체 현장실습'이 관련 경력으로 인정되나요?", 'req-1'),
        _question('coreCompetencies.text', 'scope', 'OTA 배포를 해 봤나요?', 'req-3'),
        _question('projects[0].description', 'scope', '24시간 검증에서 시험 코드를 직접 짰나요?', 'req-4'),
    ])
    add_requirement_questions(generation, FIELDS, rows)
    assign_review_stages(generation, rows)
    linked = [q.requirement_id for q in generation.questions]
    assert 'req-1' not in linked, '지원 자격은 묻지 않는다'
    assert 'req-3' not in linked, '근거 없는 주요 업무는 묻지 않는다'
    assert 'req-4' in linked and 'req-2' in linked
    avr = next(q for q in generation.questions if q.requirement_id == 'req-2')
    assert '어느 항목' in avr.question and '온도 센서' not in avr.question, '기술 요건은 특정 항목을 지목하지 않는다'


def test_questions_about_conditions_or_already_written_elements_are_filtered():
    stars = [
        {'field_path': 'projects[0].description', 'present': ['action', 'result'], 'missing': ['situation', 'task']},
        {'field_path': 'awards[0].description', 'present': ['task'], 'missing': ['situation', 'action', 'result']},
    ]
    generation = ResumeReviewGeneration(summary='coreCompetencies.text 필드를 보완하세요.', section_reviews=[], questions=[
        _question('projects[0].description', 'result', "'온도 센서 모니터링 장치' 프로젝트의 결과는 무엇인가요?"),
        _question('projects[0].description', 'situation', "'온도 센서 모니터링 장치' 프로젝트는 어떤 문제를 풀려고 만들었나요?"),
        _question('awards[0].description', 'action', 'projects[0].description의 모터 제어를 어떤 방식으로 했나요?'),
        _question('coreCompetencies.text', 'other', '6개월 풀타임 근무가 가능한가요?'),
        _question('coreCompetencies.text', 'scope', "공고 필수 요건 'Git 협업' 경험이 있나요?", 'req-9'),
    ])
    filter_questions_by_resume_facts(generation, FIELDS, stars)
    texts = [q.question for q in generation.questions]
    assert not any('결과는 무엇' in t for t in texts), '결과가 이미 적힌 항목에 결과를 묻지 않는다'
    assert not any('어떤 문제' in t for t in texts), '행동·결과가 모두 적힌 항목은 상황도 되묻지 않는다'
    assert not any('풀타임' in t for t in texts), '근무 조건은 묻지 않는다'
    assert any('Git 협업' in t for t in texts), '요건 질문은 그대로'
    assert texts[0].startswith("'온도 센서 모니터링 장치' 프로젝트의 모터 제어"), \
        '행동이 빠진 항목은 묻고, 내부 경로는 항목 이름으로 바꾼다'
    assert generation.summary == '핵심역량 필드를 보완하세요.'


def test_internal_terms_are_humanized():
    assert humanize_internal_terms('coreCompetencies.text의 field_path', FIELDS) == '핵심역량의 항목'
    assert humanize_internal_terms('awards[0].description 필드 경로', FIELDS) == "'전국 대학생 임베디드 경진대회 본선 진출' 수상 항목"


def test_template_question_skips_bodies_with_action_and_result_and_is_capped_for_job_review():
    stars = [{'field_path': 'selfIntroduction.challenge.body', 'present': ['situation', 'action', 'result'],
              'missing': ['task']}]
    fields = {**FIELDS, 'selfIntroduction.intro.body': '성실합니다.', 'selfIntroduction.aspiration.body': '열심히 하겠습니다.',
              'selfIntroduction.motivation.body': '귀사의 비전에 공감합니다.',
              'selfIntroduction.strengthsWeaknesses.body': '꼼꼼합니다.'}
    generation = ResumeReviewGeneration(summary='', section_reviews=[])
    add_thin_self_introduction_questions(generation, fields, stars, job_review=True)
    paths = [q.field_path for q in generation.questions]
    assert 'selfIntroduction.challenge.body' not in paths, '행동·결과가 적힌 문항에는 틀 질문을 붙이지 않는다'
    assert not {'selfIntroduction.motivation.body', 'selfIntroduction.aspiration.body'} & set(paths),         '공고 맞춤 첨삭은 지원동기·포부에 틀 질문을 붙이지 않는다'
    assert len(paths) == 2, '공고 맞춤 첨삭은 두 개까지'
    general = ResumeReviewGeneration(summary='', section_reviews=[])
    add_thin_self_introduction_questions(general, fields, stars)
    assert 'selfIntroduction.motivation.body' in [q.field_path for q in general.questions], '일반 첨삭은 예전대로'


def test_short_project_edit_does_not_add_digging_question_when_star_is_complete():
    generation = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='projects[0].description', original_quote='24시간 연속 동작 검증.',
        suggested_revision='24시간 연속 동작을 검증했습니다.', reason='종결', edit_type='clarity')])
    stars = [{'field_path': 'projects[0].description', 'present': ['situation', 'action', 'result'], 'missing': ['task']}]
    prefer_project_evidence_over_surface_edit(generation, FIELDS, [], stars)
    assert generation.sentence_reviews[0].confirmation_question is None


def test_review_response_carries_star_checks_and_eligibility_rows(monkeypatch):
    import app.matching_handoff as handoff
    from app.config import Settings
    from app.job_requirements import JobRequirementOut, JobRequirementProfileOut
    from app.models import FirestoreResumeReviewRequest, RequirementMatchOut
    from app.resume_review import ResumeReviewService
    from tests.test_job_requirements import JOB, _Firebase

    job_text = JOB['text'] + '\n- 신입 또는 관련 경력 2년 이하'
    monkeypatch.setattr(handoff, 'load_selected_job', lambda _p, _j: {
        **JOB, 'text': job_text, 'conditions': {'career_type': 'ENTRY', 'min_career_years': 0}})

    def extractor(_text, _source):
        return JobRequirementProfileOut(requirements=[
            JobRequirementOut(group='must', label='신입 또는 경력 2년 이하', posting_quote='신입 또는 관련 경력 2년 이하'),
            JobRequirementOut(group='must', label='Git 협업', posting_quote='Git 브랜치 전략 기반 협업 경험'),
        ])

    def generator(inputs):
        assert 'projects[0].description' in inputs['star_targets']
        return ResumeReviewGeneration(summary='검토', section_reviews=[], requirement_matches=[
            RequirementMatchOut(requirement_id='req-1', status='unconfirmed'),
            RequirementMatchOut(requirement_id='req-2', status='unconfirmed'),
        ], star_judgements=[StarJudgementOut(
            field_path='projects[0].description', action_quote='N+1 제거와 Redis 캐시로 조회 개선',
            missing_reason='해결하려던 문제와 결과가 없어요.')], questions=[
            ReviewQuestion(field_path='projects[0].description', topic='action', reason='r', priority=1,
                           question="'주문 조회 성능 개선' 프로젝트에서 직접 한 방법은?"),
            ReviewQuestion(field_path='projects[0].description', topic='result', reason='r', priority=1,
                           question="'주문 조회 성능 개선' 프로젝트에서 확인한 결과는?"),
        ])

    service = ResumeReviewService(Settings(openai_api_key='test'), _Firebase(), generator, extractor)
    first = service.review('x', FirestoreResumeReviewRequest(
        cohort_id='c', resume_id='r', review_mode='job', tailored_resume_id='t1', selected_job_id='SARAMIN-1'))
    rows = {row['label']: row for row in first.requirement_map}
    assert (rows['신입 또는 경력 2년 이하']['kind'], rows['신입 또는 경력 2년 이하']['kind_basis']) == \
        ('eligibility', '공고 조건: 신입')
    assert rows['Git 협업']['kind'] == 'skill'
    assert [c.present for c in first.star_checks] == [['action']]
    questions = [q.question for q in first.questions]
    assert not any('직접 한 방법' in q for q in questions), '행동이 이미 적힌 항목에 방법을 묻지 않는다'
    assert any('확인한 결과' in q for q in questions)
    assert all(q.requirement_id != 'req-1' for q in first.questions)
    assert any(q.requirement_id == 'req-2' for q in first.questions)


def test_followup_marks_the_asked_element_present_only_when_the_answer_became_a_revision():
    from app.star_checks import mark_answered_star_elements
    checks = [{'field_path': 'awards[0].description', 'present': ['task'], 'missing': ['situation', 'action', 'result'],
               'reason': '방법과 결과가 없어요.', 'quotes': {}}]
    answer = ConfirmationAnswer(question_id='q1', field_path='awards[0].description', question='어떻게 했나요?',
                                answer='바퀴 모터 속도를 PID로 제어했어요')
    questions = {'q1': {'topic': 'action'}}
    untouched = mark_answered_star_elements(checks, [answer], questions, [])
    assert untouched[0]['present'] == ['task'], '수정안이 없으면 바꾸지 않는다'
    revision = SentenceReview(field_path='awards[0].description', original_quote='모터 제어', reason='답변 반영',
                              suggested_revision='바퀴 모터 속도를 PID로 제어', edit_type='content')
    updated = mark_answered_star_elements(checks, [answer], questions, [revision])
    assert updated[0]['present'] == ['task', 'action'] and updated[0]['missing'] == ['situation', 'result']


def test_partial_requirement_with_only_tech_stack_evidence_asks_where_not_the_name_field():
    from app.review_workflow import MISSING_JOB_TECH_REASON
    fields = {**FIELDS, 'techStack[4].name': 'Fastlane'}
    rows = [{'id': 'req-5', 'group': 'preferred', 'label': 'Fastlane 배포 자동화', 'status': 'partial', 'kind': 'skill',
             'evidence_paths': ['techStack[4].name']}]
    generation = ResumeReviewGeneration(summary='', section_reviews=[])
    add_requirement_questions(generation, fields, rows)
    question = generation.questions[0]
    assert question.field_path != 'techStack[4].name'
    assert question.reason == MISSING_JOB_TECH_REASON and '어느 항목' in question.question


def test_model_question_on_tech_stack_name_moves_to_a_description_field():
    from app.review_workflow import MISSING_JOB_TECH_REASON
    fields = {**FIELDS, 'techStack[4].name': 'Fastlane', 'projects[0].role': '펌웨어 개발'}
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        _question('techStack[4].name', 'scope', 'Fastlane을 실제로 사용한 항목이 있나요?', 'req-5'),
        _question('projects[0].role', 'action', "'온도 센서 모니터링 장치' 프로젝트에서 맡은 역할은?"),
    ])
    filter_questions_by_resume_facts(generation, fields, [])
    tech, role = generation.questions
    assert tech.field_path == 'projects[0].description' and tech.reason == MISSING_JOB_TECH_REASON
    assert role.field_path == 'projects[0].description'


def test_item_with_action_and_result_is_not_dug_into_even_with_other_topic():
    stars = [{'field_path': 'projects[0].description', 'present': ['situation', 'task', 'action', 'result'], 'missing': []}]
    generation = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        _question('projects[0].description', 'other', "'온도 센서 모니터링 장치' 프로젝트에서 24시간 검증 외에 추가로 확인한 결과가 있나요?"),
        _question('projects[0].description', 'scope', "'온도 센서 모니터링 장치' 프로젝트에서 Docker를 써 봤나요?", 'req-1'),
    ])
    filter_questions_by_resume_facts(generation, FIELDS, stars)
    assert [q.requirement_id for q in generation.questions] == ['req-1'], '요건 질문만 남고 파고드는 질문은 빠진다'


def test_action_quote_with_only_role_or_learning_words_is_not_an_action():
    # 모델이 "데이터 수집과 시각화를 맡았습니다", "개발을 본격적으로 배웠습니다"를 행동으로 봤다(2026-09-15 개발용 기록).
    from app.models import StarJudgementOut
    fields = {'awards[0].description': '배차 개선안을 제안. 데이터 수집과 시각화를 맡았습니다.',
              'projects[0].description': '목록 조회에 select_related를 적용해 쿼리 수를 줄이는 일을 맡았습니다.'}
    checks, warnings = ground_star_judgements([
        StarJudgementOut(field_path='awards[0].description', action_quote='데이터 수집과 시각화를 맡았습니다'),
        StarJudgementOut(field_path='projects[0].description', action_quote='select_related를 적용해'),
    ], fields, [])
    by_path = {check.field_path: check for check in checks}
    assert 'action' not in by_path['awards[0].description'].present
    assert 'action' in by_path['projects[0].description'].present, '방법이 있으면 그대로 행동이다'
    assert any('방법이 없음' in warning for warning in warnings)


def test_result_quote_counts_only_when_the_model_says_it_is_a_result():
    # 낱말 목록 대신 모델이 결과 인용의 종류를 고른다. 한 일만 적은 인용("3학기 동안 운영했습니다")은 결과가 아니다.
    fields = {'otherActivities[0].description': '주 1회 문제 풀이 모임을 3학기 동안 운영했습니다.',
              'projects[0].description': '실패율을 0으로 만들었습니다.'}
    checks, warnings = ground_star_judgements([
        StarJudgementOut(field_path='otherActivities[0].description', result_quote='3학기 동안 운영했습니다',
                         result_kind='activity'),
        StarJudgementOut(field_path='projects[0].description', result_quote='실패율을 0으로 만들었습니다',
                         result_kind='metric_change'),
    ], fields, [])
    by_path = {check.field_path: check for check in checks}
    assert 'result' not in by_path['otherActivities[0].description'].present
    assert 'result' in by_path['projects[0].description'].present
    assert any('결과가 아님' in warning for warning in warnings)
    # 종류를 내지 않은 예전 판정은 그대로 받는다.
    checks, _ = ground_star_judgements([StarJudgementOut(
        field_path='projects[0].description', result_quote='실패율을 0으로 만들었습니다')], fields, [])
    assert 'result' in checks[0].present
