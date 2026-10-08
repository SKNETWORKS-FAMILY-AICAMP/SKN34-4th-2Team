"""회사 자기소개서 문항 답변 — 근거 없는 문장 · 틀 문장 · 부풀린 숫자를 코드가 빼고, 글자 수를 넘기지 않는다."""
import pytest

from app.job_requirements import JobRequirement
from app.question_answers import (
    AnswerSourceRef,
    AnswerSentenceOut,
    GapQuestionOut,
    QuestionAnswerOut,
    ground_answer,
    write_question_answer,
    _experience_options,
    _selected_experience,
)
from app.review_workflow import ReviewInputError

FIELDS = {
    'coreCompetencies.text': 'Python REST API 개발',
    'projects[0].description': 'Django로 출결 API를 만들고 응답 시간을 1.2초에서 0.4초로 줄였습니다.',
}
JOB_TEXT = '회사: 테스트랩\n공고: 백엔드 개발자\n\n자격요건\n- Python, Django 기반 웹 서비스 개발 경험\n주요업무\n- 사내 플랫폼 API 개발'
REQUIREMENTS = [
    JobRequirement(id='req-1', group='must', label='Django 웹 개발', posting_quote='Python, Django 기반 웹 서비스 개발 경험'),
    JobRequirement(id='req-2', group='preferred', label='AWS 배포', posting_quote='AWS 배포 경험'),
]


def sentence(text, basis, quote, reqs=()):
    return AnswerSentenceOut(text=text, basis=basis, quote=quote, requirement_ids=list(reqs))


def cited(text, *refs):
    return AnswerSentenceOut(text=text, sources=[AnswerSourceRef(**ref) for ref in refs])


def ground(generated, *, answers=(), limit=None):
    return ground_answer(generated, fields=FIELDS, answers=list(answers), job_text=JOB_TEXT,
                         requirement_ids={'req-1', 'req-2'}, limit=limit)


def test_keeps_only_sentences_whose_quote_is_in_the_source():
    result = ground(QuestionAnswerOut(sentences=[
        sentence('Django로 출결 API를 만들며 응답 시간을 1.2초에서 0.4초로 줄였습니다.', 'resume',
                 '응답 시간을 1.2초에서 0.4초로 줄였습니다', ['req-1', 'req-9']),
        sentence('대규모 트래픽을 처리하는 MSA를 설계했습니다.', 'resume', 'MSA 설계 경험'),
        sentence('사내 플랫폼 API를 만드는 일에 기여하고 싶습니다.', 'posting', '사내 플랫폼 API 개발'),
    ]))
    assert [s['basis'] for s in result['sentences']] == ['resume', 'posting']
    assert result['sentences'][0]['requirement_ids'] == ['req-1']
    assert result['dropped'] == 1
    assert result['char_count'] == len(result['draft'])


def test_drops_template_sentences_and_numbers_not_in_the_evidence():
    result = ground(QuestionAnswerOut(sentences=[
        sentence('테스트랩에 지원한 이유는 다음과 같습니다.', 'posting', '공고: 백엔드 개발자'),
        sentence('Django로 출결 API를 만들어 응답 시간을 80% 줄였습니다.', 'resume', 'Django로 출결 API를 만들고'),
        sentence('Python으로 REST API를 개발했습니다.', 'resume', 'Python REST API 개발'),
    ]))
    assert [s['text'] for s in result['sentences']] == ['Python으로 REST API를 개발했습니다.']
    assert result['dropped'] == 2


def test_user_answers_are_evidence_and_are_not_asked_again():
    answers = [{'question': 'AWS에 배포해 본 적이 있나요?', 'answer': 'EC2에 Django 서버를 직접 배포했습니다.'}]
    result = ground(QuestionAnswerOut(
        sentences=[sentence('EC2에 Django 서버를 직접 배포했습니다.', 'answer', 'EC2에 Django 서버를 직접 배포', ['req-2'])],
        gaps=[GapQuestionOut(requirement_id='req-2', question='AWS에 배포해 본 적이 있나요?'),
              GapQuestionOut(requirement_id='req-x', question='팀에서 맡은 역할은 무엇이었나요?')],
    ), answers=answers)
    assert result['sentences'][0]['basis'] == 'answer'
    assert result['gaps'] == [{'requirement_id': '', 'question': '팀에서 맡은 역할은 무엇이었나요?',
                               'kind': 'clarification'}]


def test_never_goes_over_the_limit():
    first = 'Python으로 REST API를 개발했습니다.'
    result = ground(QuestionAnswerOut(sentences=[
        sentence(first, 'resume', 'Python REST API 개발'),
        sentence('Django로 출결 API를 만들었습니다.', 'resume', 'Django로 출결 API를 만들고'),
    ]), limit=len(first) + 5)
    assert result['draft'] == first
    assert result['char_count'] <= result['limit']
    assert result['dropped'] == 1


def test_writes_for_the_chosen_company_question():
    seen = {}

    def generator(variables):
        seen.update(variables)
        return QuestionAnswerOut(sentences=[sentence('Python으로 REST API를 개발했습니다.', 'resume', 'Python REST API 개발')])

    tailored = {'content': {
        'coreCompetencies': {'text': 'Python REST API 개발'},
        'companyQuestions': [{'id': 'cq1', 'question': '직무 역량을 쓰시오.', 'limit': 500, 'answer': ''}],
    }}
    job = {'text': JOB_TEXT, 'source': {'company': '테스트랩', 'title': '백엔드 개발자'}}
    result = write_question_answer(tailored=tailored, question_id='cq1', answers=[], job=job,
                                   requirements=REQUIREMENTS, generator=generator)
    assert seen['question'] == '직무 역량을 쓰시오.'
    assert seen['limit'] == '500자 (공백 포함)'
    assert 'req-1 · 필수 · Django 웹 개발' in seen['requirements']
    # 회사 문항 칸은 근거(이력서)로 넘기지 않는다 — 앞서 쓴 답이 근거가 되면 안 된다
    assert 'companyQuestions' not in seen['resume']
    assert result['draft'] == 'Python으로 REST API를 개발했습니다.'
    assert result['limit'] == 500

    with pytest.raises(ReviewInputError):
        write_question_answer(tailored=tailored, question_id='nope', answers=[], job=job,
                              requirements=REQUIREMENTS, generator=generator)


def test_sentence_provenance_is_scoped_to_exact_source_and_allows_multiple_refs():
    fields={'projects[0].name':'AlphaService','projects[0].description':'첫 프로젝트의 F1은 0.26입니다.',
            'projects[1].name':'BetaService','projects[1].description':'둘째 프로젝트의 F1은 0.91입니다.'}
    generated=QuestionAnswerOut(sentences=[
        cited('첫 프로젝트의 F1은 0.91입니다.',dict(basis='resume',source_id='projects[0].description',
            quote='첫 프로젝트의 F1은 0.26입니다.')),
        cited('첫 프로젝트의 F1은 0.91입니다.',dict(basis='resume',source_id='projects[1].description',
            quote='둘째 프로젝트의 F1은 0.91입니다.')),
        cited('첫 프로젝트의 F1은 0.26입니다.',dict(basis='resume',source_id='projects[0].description',
            quote='첫 프로젝트의 F1은 0.26입니다.'),
            dict(basis='answer',source_id='answer:0',quote='직접 비교했습니다.')),
        cited('첫 프로젝트의 F1은 0.91입니다.',dict(basis='resume',source_id='projects[0].description',
            quote='첫 프로젝트의 F1은 0.26입니다.'),
            dict(basis='answer',source_id='answer:1',quote='BetaService F1은 0.91입니다.')),
    ])
    result=ground_answer(generated,fields=fields,answers=[{'question':'비교했나요?','answer':'직접 비교했습니다.'},
        {'question':'다른 프로젝트는?','answer':'BetaService F1은 0.91입니다.'}],
        job_text='',requirement_ids=set(),limit=None,selected_project='projects:p1',
        experience_options={'projects:p1': {'label': 'AlphaService', 'prefix': 'projects[0]'},
                            'projects:p2': {'label': 'BetaService', 'prefix': 'projects[1]'}})
    assert result['dropped']==3 and len(result['sentences'])==1
    assert [ref['source_id'] for ref in result['sentences'][0]['sources']]==['projects[0].description','answer:0']


def test_single_experience_conflict_asks_choice_then_uses_explicit_selection():
    tailored={'content':{'projects':[
        {'id':'kkbox','name':'KKBOX 분석','techStack':'XGBoost','description':'XGBoost threshold를 분석했습니다.'},
        {'id':'lms','name':'AI LMS 개발','techStack':'Django','description':'Django로 첨삭 기능을 구현했습니다.'}],
        'companyQuestions':[{'id':'q','question':'가장 성취감을 느낀 경험은 무엇인가요?','limit':600}]}}
    job={'text':'공고 본문','source':{'company':'회사','title':'공고'}}
    answers=[{'question':'메모','answer':'AI LMS 개발에서 첨삭 기능을 개선','source_type':'memo'},
             {'question':'기존 질문','answer':'XGBoost threshold를 살펴봤습니다.','source_type':'answer'}]
    def generator(_):
        return QuestionAnswerOut(focus_mode='single',focus_source_ids=['projects:kkbox'],
            focus_reason='분석 결과를 중심으로 선택',sentences=[cited('XGBoost threshold를 분석했습니다.',
                dict(basis='resume',source_id='projects[0].description',quote='XGBoost threshold를 분석했습니다.'))])
    first=write_question_answer(tailored=tailored,question_id='q',answers=answers,job=job,requirements=[],generator=generator)
    assert first['draft']=='' and first['gaps'][0]['kind']=='experience_choice'
    assert {option['id'] for option in first['gaps'][0]['options']} == {'projects:kkbox', 'projects:lms'}
    assert first['requirements_status']=='unavailable'

    answers.append({'question':first['gaps'][0]['question'],'answer':'AI LMS 개발',
                    'source_type':'selection','selected_experience_id':'projects:lms'})
    def after_choice(variables):
        assert variables['selected_experience']=='projects:lms · AI LMS 개발'
        return QuestionAnswerOut(focus_mode='single',focus_source_ids=['projects:lms'],
            sentences=[cited('Django로 첨삭 기능을 구현했습니다.',
                dict(basis='resume',source_id='projects[1].description',quote='Django로 첨삭 기능을 구현했습니다.'))])
    second=write_question_answer(tailored=tailored,question_id='q',answers=answers,job=job,
        requirements=[],generator=after_choice)
    assert second['draft']=='Django로 첨삭 기능을 구현했습니다.' and not second['gaps']
    assert second['focus']['labels']==['AI LMS 개발']


def test_existing_growth_plan_is_a_source_and_absent_job_requirements_are_reported():
    tailored={'content':{'selfIntroduction':{'aspiration':{'body':'입사 초기 데이터 구조와 업무 흐름을 파악하겠습니다.'}},
        'companyQuestions':[{'id':'q','question':'지원동기와 성장 계획','limit':600}]}}
    def generator(variables):
        assert 'selfIntroduction.aspiration.body:' in variables['resume']
        assert variables['requirements']=='정리된 요건 없음'
        return QuestionAnswerOut(sentences=[cited('입사 초기 데이터 구조와 업무 흐름을 파악하겠습니다.',
            dict(basis='resume',source_id='selfIntroduction.aspiration.body',
                 quote='입사 초기 데이터 구조와 업무 흐름을 파악하겠습니다.'))])
    result=write_question_answer(tailored=tailored,question_id='q',answers=[],job={'text':'공고','source':{}},
        requirements=[],generator=generator)
    assert result['draft'] and result['requirements_status']=='unavailable'
    assert not result['gaps'] and result['char_count'] < 600


def test_selection_never_infers_identity_from_negated_free_text():
    fields = {'projects[0].name': 'Apollo 서비스', 'projects[1].name': 'Beacon 분석'}
    options = _experience_options({'projects': [
        {'id': 'apollo', 'name': 'Apollo 서비스'}, {'id': 'beacon', 'name': 'Beacon 분석'}]}, fields)
    legacy = [{'source_type': 'selection', 'question': '어떤 경험으로 쓸까요?',
               'answer': 'Apollo 말고 다른 경험으로 작성해주세요.'}]
    assert _selected_experience(legacy, options) is None
    assert _selected_experience(legacy + [{'source_type': 'selection', 'answer': 'Beacon 분석',
        'selected_experience_id': 'projects:beacon'}], options) == 'projects:beacon'
    assert _selected_experience([{'source_type': 'selection', 'answer': 'Apollo 서비스',
        'selected_experience_id': 'projects:apollo'}] + legacy, options) is None


def test_choice_options_cover_named_experiences_but_not_generic_sections():
    content = {'projects': [{'id': 'p', 'name': '서비스 프로젝트'}],
        'experience': [{'id': 'e', 'company': '개발팀'}],
        'education': [{'id': 'u', 'school': '대학교'}],
        'trainingExperience': [{'id': 't', 'course': 'AI 과정'}],
        'otherActivities': [{'id': 'a', 'name': '봉사활동'}]}
    fields = {f'{section}[0].{title_key}': items[0][title_key]
              for section, (title_key, items) in {
                  'projects': ('name', content['projects']),
                  'experience': ('company', content['experience']),
                  'education': ('school', content['education']),
                  'trainingExperience': ('course', content['trainingExperience']),
                  'otherActivities': ('name', content['otherActivities']),
              }.items()}
    assert set(_experience_options(content, fields)) == {
        'projects:p', 'experience:e', 'education:u', 'trainingExperience:t', 'otherActivities:a'}


def test_selection_id_survives_reorder_and_rejects_missing_or_foreign_id():
    job = {'text': '공고', 'source': {}}
    question = [{'id': 'q', 'question': '경험을 설명하세요.', 'limit': 500}]
    projects = [
        {'id': 'apollo', 'name': 'Apollo 서비스', 'description': 'Apollo API를 구현했습니다.'},
        {'id': 'beacon', 'name': 'Beacon 분석', 'description': 'Beacon 데이터를 분석했습니다.'},
    ]
    answers = [{'source_type': 'selection', 'question': '중심 경험', 'answer': 'Beacon 분석',
                'selected_experience_id': 'projects:beacon'}]
    def generator(variables):
        assert variables['selected_experience'] == 'projects:beacon · Beacon 분석'
        return QuestionAnswerOut(focus_mode='single', focus_source_ids=['projects:beacon'], sentences=[
            cited('Beacon 데이터를 분석했습니다.', dict(basis='resume',
                  source_id=variables['beacon_path'], quote='Beacon 데이터를 분석했습니다.'))])
    for reordered in (projects, list(reversed(projects))):
        path = f"projects[{next(i for i, p in enumerate(reordered) if p['id'] == 'beacon')}].description"
        result = write_question_answer(tailored={'content': {'projects': reordered, 'companyQuestions': question}},
            question_id='q', answers=answers, job=job, requirements=[],
            generator=lambda variables: generator(dict(variables, beacon_path=path)))
        assert result['draft'] == 'Beacon 데이터를 분석했습니다.'
    for invalid in ('projects:deleted', 'projects:foreign-resume', 'experience:beacon'):
        with pytest.raises(ReviewInputError, match='selected_experience_not_found'):
            write_question_answer(tailored={'content': {'projects': projects, 'companyQuestions': question}},
                question_id='q', answers=answers + [dict(answers[0], selected_experience_id=invalid)], job=job,
                requirements=[], generator=lambda _: pytest.fail('invalid choice must not call the LLM'))


def test_legacy_choice_reasks_without_llm_or_using_choice_as_evidence():
    tailored = {'content': {'projects': [
        {'id': 'apollo', 'name': 'Apollo 서비스', 'description': 'API 구현'},
        {'id': 'beacon', 'name': 'Beacon 분석', 'description': '분석 수행'}],
        'companyQuestions': [{'id': 'q', 'question': '경험은?', 'limit': 500}]}}
    answer = {'source_type': 'selection', 'question': '중심 경험',
              'answer': 'Apollo 말고 다른 경험으로 작성해주세요.'}
    result = write_question_answer(tailored=tailored, question_id='q', answers=[answer],
        job={'text': '', 'source': {}}, requirements=[],
        generator=lambda _: pytest.fail('legacy selection must not trigger a draft'))
    assert result['draft'] == '' and result['gaps'][0]['kind'] == 'experience_choice'
    assert {item['id'] for item in result['gaps'][0]['options']} == {'projects:apollo', 'projects:beacon'}
    assert ground_answer(QuestionAnswerOut(sentences=[cited('Apollo 말고 다른 경험으로 작성해주세요.',
        dict(basis='answer', source_id='answer:0', quote=answer['answer']))]), fields={},
        answers=[answer], job_text='', requirement_ids=set(), limit=None)['dropped'] == 1


def test_ai_proxy_request_preserves_selected_experience_id():
    from app.main import ProxyQuestionAnswerRequest
    request = ProxyQuestionAnswerRequest.model_validate({
        'uid': 'u', 'cohort_id': 'cohort', 'resume_id': 'base', 'tailored_resume_id': 'tailored',
        'question_id': 'q', 'answers': [{'question': '선택', 'answer': 'Beacon 분석',
            'source_type': 'selection', 'selected_experience_id': 'projects:beacon'}],
    })
    assert request.answers[0].model_dump()['selected_experience_id'] == 'projects:beacon'
