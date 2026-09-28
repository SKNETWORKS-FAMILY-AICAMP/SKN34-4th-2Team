"""회사 자기소개서 문항 답변 — 근거 없는 문장 · 틀 문장 · 부풀린 숫자를 코드가 빼고, 글자 수를 넘기지 않는다."""
import pytest

from app.job_requirements import JobRequirement
from app.question_answers import (
    AnswerSentenceOut,
    GapQuestionOut,
    QuestionAnswerOut,
    ground_answer,
    write_question_answer,
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
    assert result['gaps'] == [{'requirement_id': '', 'question': '팀에서 맡은 역할은 무엇이었나요?'}]


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
