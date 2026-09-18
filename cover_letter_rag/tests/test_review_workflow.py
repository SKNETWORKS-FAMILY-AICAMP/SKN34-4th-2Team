import json
from copy import deepcopy
import pytest

from app.models import ConfirmationAnswer, FirestoreResumeReviewRequest, ResumeReviewGeneration, SentenceReview, ReviewQuestion
from app.config import Settings
from app.resume_review import ResumeReviewService, ground_sentences
from app.review_workflow import (ReviewConflict, ReviewInputError, redact, prepare_answers,
                                 normalize_diagnostics, normalize_questions, item_references, digest,
                                 focused_followup_context, focused_time_context,
                                 add_thin_self_introduction_questions,
                                 prefer_project_evidence_over_surface_edit,
                                 add_missing_job_technology_question,
                                 carry_forward_unanswered_questions)
from test_resume_review import FakeFirebase, SAMPLE_CONTENT


def generation(_):
    return ResumeReviewGeneration(summary='검토', section_reviews=[], questions=[
        ReviewQuestion(field_path='projects[0].description', topic='action', question='어떤 행동을 했나요?', reason='행동 부족', priority=1)])


def test_duplicate_request_returns_one_generation():
    db = FakeFirebase()
    calls = []
    def generate(data):
        calls.append(data)
        return generation(data)
    service = ResumeReviewService(Settings(openai_api_key='test'), db, generate)
    request = FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1', request_id='once')
    first = service.review('valid-token', request)
    assert service.review('valid-token', request) == first
    assert len(calls) == 1
    assert first.telemetry['input_tokens'] is None
    with pytest.raises(ReviewConflict):
        service.review('valid-token', request.model_copy(update={'review_focus': '다른 요청'}))


def test_followup_is_bound_to_question_and_version():
    db = FakeFirebase()
    service = ResumeReviewService(Settings(openai_api_key='test'), db, generation)
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    q = first.questions[0]
    answer = ConfirmationAnswer(question_id=q.question_id, field_path=q.field_path, question=q.question, answer='캐싱을 적용했습니다.')
    request = FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1', previous_review_id=first.review_id, expected_input_hash=first.input_hash, answers=[answer])
    result = service.review('valid-token', request)
    assert result.confirmed_answers[0].answer == answer.answer
    assert not result.questions
    with pytest.raises(ReviewConflict):
        service.review('valid-token', request.model_copy(update={'expected_input_hash': 'old'}))
    with pytest.raises(ReviewInputError):
        prepare_answers(request.model_copy(update={'answers': [answer.model_copy(update={'question_id': 'fake'})]}), first.model_dump(), first.input_hash, first.item_refs)


def test_gap_audit_allows_questions_but_never_rewrites_resume():
    calls = []

    def generate(data):
        calls.append(data)
        if len(calls) == 1:
            return ResumeReviewGeneration(summary='첫 검토', section_reviews=[])
        return ResumeReviewGeneration(
            summary='누락 점검',
            section_reviews=[],
            sentence_reviews=[SentenceReview(
                field_path='projects[0].description',
                original_quote='API 응답 시간을 20% 개선했습니다.',
                reason='다른 표현 제안',
                suggested_revision='API 응답 성능을 20% 개선했습니다.',
                evidence_quotes=['API 응답 시간을 20% 개선했습니다.'],
            )],
            questions=[ReviewQuestion(
                field_path='projects[0].description',
                topic='scope',
                question='본인이 직접 담당한 API 범위는 어디까지인가요?',
                reason='담당 범위가 아직 확인되지 않았습니다.',
                priority=1,
            )],
        )

    service = ResumeReviewService(
        Settings(openai_api_key='test'), FakeFirebase(), generate,
    )
    first = service.review(
        'valid-token',
        FirestoreResumeReviewRequest(
            cohort_id='cohort-1', resume_id='resume-1', request_id='initial-audit-test',
        ),
    )
    audited = service.review(
        'valid-token',
        FirestoreResumeReviewRequest(
            cohort_id='cohort-1',
            resume_id='resume-1',
            request_id='gap-audit-test',
            previous_review_id=first.review_id,
            expected_input_hash=first.input_hash,
            review_phase='gap_audit',
        ),
    )

    assert '누락 점검 단계' in calls[1]['review_scope']
    assert audited.sentence_reviews == []
    assert [question.topic for question in audited.questions] == ['scope']


def test_gap_audit_carries_forward_unanswered_questions():
    """누락 점검도 남은 질문에 새 번호를 물려줘야 한다.

    첨삭마다 question_id를 새로 매기므로, 이어받지 않으면 화면에 떠 있는 질문의 번호를 서버가
    모르게 된다. 그러면 앱이 그 질문을 죽은 것으로 보고 답을 보내지 않고 넘겨, 사용자가 친 답이
    입력칸에 남은 채 다음 질문만 쌓였다(2026-09-16 앱).
    """
    calls = []

    def generate(data):
        calls.append(data)
        if len(calls) == 1:
            return ResumeReviewGeneration(
                summary='첫 검토',
                section_reviews=[],
                questions=[ReviewQuestion(
                    field_path='projects[0].description',
                    topic='scope',
                    question='본인이 직접 담당한 API 범위는 어디까지인가요?',
                    reason='담당 범위가 아직 확인되지 않았습니다.',
                    priority=1,
                )],
            )
        # 누락 점검은 새 질문만 낸다. 앞서 띄운 질문은 서버가 이어받아야 한다.
        return ResumeReviewGeneration(summary='누락 점검', section_reviews=[])

    service = ResumeReviewService(
        Settings(openai_api_key='test'), FakeFirebase(), generate,
    )
    first = service.review(
        'valid-token',
        FirestoreResumeReviewRequest(
            cohort_id='cohort-1', resume_id='resume-1', request_id='carry-initial',
        ),
    )
    assert len(first.questions) == 1

    audited = service.review(
        'valid-token',
        FirestoreResumeReviewRequest(
            cohort_id='cohort-1',
            resume_id='resume-1',
            request_id='carry-gap-audit',
            previous_review_id=first.review_id,
            expected_input_hash=first.input_hash,
            review_phase='gap_audit',
        ),
    )

    carried = [q for q in audited.questions if q.topic == 'scope']
    assert len(carried) == 1, '남은 질문이 누락 점검 응답에서 사라졌다'
    # 번호는 이 첨삭 것으로 새로 매겨진다. 빈 번호로 나가면 앱이 답을 보낼 수 없다.
    assert carried[0].question_id
    assert carried[0].question_id != first.questions[0].question_id


def test_gap_audit_requires_previous_review_and_no_answers():
    service = ResumeReviewService(
        Settings(openai_api_key='test'), FakeFirebase(), generation,
    )
    with pytest.raises(ReviewInputError):
        service.review(
            'valid-token',
            FirestoreResumeReviewRequest(
                cohort_id='cohort-1',
                resume_id='resume-1',
                review_phase='gap_audit',
            ),
        )


def test_followup_prompt_is_limited_to_the_answered_resume_item():
    fields = {
        'projects[0].description': '첫 번째 프로젝트 설명',
        'projects[0].techStack': 'Python',
        'projects[1].description': '두 번째 프로젝트 설명',
        'selfIntroduction.aspiration.body': '지원 동기',
    }
    current = ConfirmationAnswer(
        question_id='q1', field_path='projects[0].description', question='무엇을 했나요?', answer='API를 구현했습니다.',
    )
    prior_other_item = ConfirmationAnswer(
        question_id='q2', field_path='projects[1].description', question='무엇을 했나요?', answer='다른 답변',
    )
    scoped_fields, scoped_answers, focused = focused_followup_context(
        fields, [prior_other_item, current], [current],
    )
    assert focused
    assert set(scoped_fields) == {'projects[0].description', 'projects[0].techStack'}
    assert scoped_answers == [current]
    assert focused_time_context(
        'projects[0] 첫 프로젝트: 2025.01 ~ 2025.02 (이력서 기록값)\n'
        'projects[1] 둘째 프로젝트: 2025.03 ~ 2025.04 (이력서 기록값)',
        [current],
    ) == 'projects[0] 첫 프로젝트: 2025.01 ~ 2025.02 (이력서 기록값)'


def test_followup_job_prompt_keeps_bounded_job_context_for_motivation():
    from app.review_workflow import followup_job_prompt_text

    text = '주요업무: AI 서비스 개발 및 데이터 처리 API 개발'
    prompt = followup_job_prompt_text(text, {
        'company': '(주)토마토에이아이',
        'title': 'AI 엔지니어 채용',
        'role_title': 'AI 엔지니어',
    })

    assert text in prompt
    assert '회사·직무 맥락에만 사용' in prompt
    assert '지원자의 경험으로 쓰지 마세요' in prompt


def test_legacy_ids_block_answers_and_reordering_changes_version():
    content = deepcopy(SAMPLE_CONTENT)
    del content['projects'][0]['id']
    refs = item_references(content, {'projects[0].description': '내용'})
    assert refs['projects[0].description'].startswith('legacy:')
    original = {'projects': [{'id': 'one'}, {'id': 'two'}]}
    assert digest(original) != digest({'projects': list(reversed(original['projects']))})


def test_same_experience_technology_is_grounded():
    result = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='projects[0].description', original_quote='API 개발', reason='기술 연결',
        suggested_revision='Python API 개발', evidence_quotes=['API 개발', '파이썬'])])
    assert not ground_sentences({'projects[0].description': 'API 개발', 'projects[0].techStack': '파이썬'}, [], result)
    assert result.sentence_reviews[0].status == 'improved'
    assert 'projects[0].techStack' in result.sentence_reviews[0].evidence_sources


def test_identical_revision_and_privacy():
    result = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='projects[0].description', original_quote='개발했습니다.', reason='정리',
        suggested_revision='개발했습니다.', evidence_quotes=['개발했습니다.'])])
    ground_sentences({'projects[0].description': '개발했습니다.'}, [], result)
    assert result.sentence_reviews[0].status == 'unchanged'
    assert result.sentence_reviews[0].suggested_revision is None
    assert redact('연락 a@example.com 010-1234-5678') == '연락 [연락처 삭제] [연락처 삭제]'


def test_fixed_diagnostics_and_priority_questions():
    result = generation({})
    normalize_diagnostics(result, {'projects[0].description': '설명'}, False, None)
    assert len(result.diagnostics) == 7
    assert all(d.status == 'not_evaluated' for d in result.diagnostics)
    result.questions.append(result.questions[0].model_copy(update={'priority': 3}))
    normalize_questions(result, {'projects[0].description': '설명'}, [], 'r')
    assert len(result.questions) == 1


def test_thin_self_introduction_sections_receive_followup_questions():
    result = ResumeReviewGeneration(summary='검토', section_reviews=[])
    fields = {
        'selfIntroduction.intro.body': '데이터를 다루는 일이 좋습니다.',
        'selfIntroduction.motivation.body': 'AI 엔지니어로 성장하고 싶습니다.',
        'selfIntroduction.growth.body': '프로젝트를 통해 배웠습니다.' * 14,
    }

    add_thin_self_introduction_questions(result, fields)

    assert [question.field_path for question in result.questions] == [
        'selfIntroduction.intro.body',
        'selfIntroduction.motivation.body',
        'selfIntroduction.growth.body',
    ]


def test_short_project_description_prefers_evidence_question_to_surface_edit():
    result = ResumeReviewGeneration(
        summary='검토',
        section_reviews=[],
        sentence_reviews=[
            SentenceReview(
                field_path='projects[0].description',
                original_quote='공고 크롤 결과를 정규화·중복 제거해 일 단위로 적재.',
                suggested_revision='공고 크롤 결과를 정규화하고 중복 제거한 뒤 일 단위로 적재했습니다.',
                reason='문장 종결을 정리했습니다.',
                edit_type='clarity',
            ),
        ],
    )

    prefer_project_evidence_over_surface_edit(
        result,
        {
            'projects[0].name': '채용공고 수집 파이프라인',
            'projects[0].description': '공고 크롤 결과를 정규화·중복 제거해 일 단위로 적재.',
        },
        [],
    )

    review = result.sentence_reviews[0]
    # 다듬은 문장은 남기고, 프로젝트의 문제·담당 범위·결과를 묻는 질문을 함께 붙인다.
    assert review.suggested_revision == '공고 크롤 결과를 정규화하고 중복 제거한 뒤 일 단위로 적재했습니다.'
    assert review.confirmation_question.startswith("'채용공고 수집 파이프라인' 프로젝트에서"), '어느 프로젝트인지 이름을 넣는다'


def test_missing_job_technology_becomes_a_confirmation_question():
    result = ResumeReviewGeneration(summary='검토', section_reviews=[])
    fields = {
        'projects[0].description': 'Python으로 데이터 처리 API를 구현했습니다.',
    }

    add_missing_job_technology_question(
        result,
        fields,
        '필수 요건: Python과 FastAPI 기반의 API 개발 경험',
    )

    assert result.questions[0].field_path == 'projects[0].description'
    assert 'FastAPI' in result.questions[0].question


def test_missing_job_technology_question_does_not_point_at_one_project():
    # 특정 항목을 지목하거나 목록을 늘어놓지 않고 "어느 항목에서 했나요?"로 묻는다. 답에 적힌 이름으로 옮긴다.
    result = ResumeReviewGeneration(summary='검토', section_reviews=[])
    fields = {
        'projects[0].name': '쇼핑몰 API',
        'projects[0].description': '상품 API를 구현했습니다.',
        'projects[1].name': 'AI 취업 코치',
        'projects[1].description': '이력서 첨삭 기능을 구현했습니다.',
    }

    add_missing_job_technology_question(result, fields, '필수 요건: Docker 경험')

    question = result.questions[0].question
    assert '쇼핑몰 API' not in question and 'AI 취업 코치' not in question
    assert '어느 항목' in question and '항목 이름' in question


def test_technology_answer_resolves_item_by_partial_name_in_any_experience_section():
    from app.review_workflow import resolve_missing_technology_project

    fields = {
        'projects[0].name': '온도 센서 모니터링 장치',
        'projects[0].description': 'I2C 센서 드라이버 작성.',
        'awards[0].name': '전국 대학생 임베디드 경진대회 본선 진출',
        'awards[0].description': '모터 제어 펌웨어를 담당했습니다.',
        'trainingExperience[0].course': '산업체 현장실습 (펌웨어 개발)',
        'trainingExperience[0].description': 'UART 통신 모듈 유지보수.',
    }
    assert resolve_missing_technology_project('임베디드 경진대회 로봇에서 PID로 제어했어요', fields) == 'awards[0].description'
    assert resolve_missing_technology_project('현장실습 때 UART 파형을 봤어요', fields) == 'trainingExperience[0].description'
    assert resolve_missing_technology_project('개발할 때 UART를 썼어요', fields) is None, '어느 항목에나 붙는 낱말로는 고르지 않는다'
    assert resolve_missing_technology_project('산업체 현장실습에서 썼어요', fields) == 'trainingExperience[0].description'
    assert resolve_missing_technology_project('1번 프로젝트에서 썼어요', fields) == 'projects[0].description'


def test_missing_technology_answer_resolves_selected_project_by_number_or_name():
    from app.review_workflow import resolve_missing_technology_project

    fields = {
        'projects[0].name': '쇼핑몰 API',
        'projects[0].description': '상품 API를 구현했습니다.',
        'projects[1].name': 'AI 취업 코치',
        'projects[1].description': '이력서 첨삭 기능을 구현했습니다.',
    }

    assert resolve_missing_technology_project(
        '2번 프로젝트에서 Dockerfile을 작성했습니다.', fields,
    ) == 'projects[1].description'
    assert resolve_missing_technology_project(
        'AI 취업 코치에서 Dockerfile을 작성했습니다.', fields,
    ) == 'projects[1].description'
    assert resolve_missing_technology_project(
        'Dockerfile을 작성했습니다.', fields,
    ) is None


def test_followup_reissues_unanswered_questions_on_its_latest_snapshot():
    result = ResumeReviewGeneration(summary='후속', section_reviews=[])
    previous = {
        'questions': [
            {
                'question_id': 'answered',
                'field_path': 'projects[0].description',
                'topic': 'action',
                'question': '어떤 구현을 했나요?',
                'reason': '행동 확인',
                'priority': 1,
            },
            {
                'question_id': 'queued',
                'field_path': 'selfIntroduction.motivation.body',
                'topic': 'scope',
                'question': '직무와 연결되는 경험이 있나요?',
                'reason': '직무 연결 확인',
                'priority': 1,
            },
        ],
    }
    answered = [
        ConfirmationAnswer(
            question_id='answered',
            field_path='projects[0].description',
            question='어떤 구현을 했나요?',
            answer='API를 구현했습니다.',
        ),
    ]

    carry_forward_unanswered_questions(result, previous, answered)

    assert [question.question_id for question in result.questions] == ['']
    assert result.questions[0].field_path == 'selfIntroduction.motivation.body'


def test_general_review_sends_no_job_and_keeps_content_questions():
    seen = []

    def generate(data):
        seen.append(data)
        return ResumeReviewGeneration(
            summary='문장을 검토했습니다.',
            section_reviews=[],
            sentence_reviews=[
                SentenceReview(
                    field_path='coreCompetencies.text',
                    original_quote='Python REST API 개발',
                    suggested_revision='Python REST API를 개발했습니다.',
                    reason='명사형 표현을 서술형으로 정리했습니다.',
                    edit_type='content',
                ),
            ],
            questions=[
                ReviewQuestion(
                    field_path='coreCompetencies.text',
                    topic='other',
                    question='구현한 API의 범위나 검증 방식이 있나요?',
                    reason='일반 첨삭에서도 사실 확인 질문을 반환합니다.',
                ),
            ],
        )

    response = ResumeReviewService(
        Settings(openai_api_key='test'), FakeFirebase(), generate,
    ).review(
        'valid-token',
        FirestoreResumeReviewRequest(
            cohort_id='cohort-1',
            resume_id='resume-1',
            review_mode='general',
        ),
    )

    assert seen[0]['review_mode'].startswith('일반 이력서 첨삭')
    assert response.sentence_reviews[0].suggested_revision == 'Python REST API를 개발했습니다.'
    assert response.questions[0].question == '구현한 API의 범위나 검증 방식이 있나요?'
    assert all(
        diagnostic.criterion not in {'relevance', 'company_fit'} or
        diagnostic.status == 'not_evaluated'
        for diagnostic in response.diagnostics
    )


def test_failed_call_is_not_automatically_rebilled():
    db = FakeFirebase()
    calls = []
    def fail(data):
        calls.append(1)
        raise RuntimeError('model unavailable')
    service = ResumeReviewService(Settings(openai_api_key='test'), db, fail)
    request = FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1', request_id='failed')
    with pytest.raises(RuntimeError):
        service.review('valid-token', request)
    with pytest.raises(ReviewConflict):
        service.review('valid-token', request)
    assert len(calls) == 1


def test_masking_applies_to_model_input_and_saved_fields():
    class PrivateDB(FakeFirebase):
        def get_owned_resume(self, *args):
            data = deepcopy(super().get_owned_resume(*args))
            data['content']['projects'][0]['description'] = '문의 a@example.com 010-1234-5678'
            return data
    seen = []
    def generate(data):
        seen.append(data)
        return generation(data)
    db = PrivateDB()
    response = ResumeReviewService(Settings(openai_api_key='test'), db, generate).review('valid-token',
        FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1', review_focus='b@example.com'))
    assert 'a@example.com' not in seen[0]['resume_text']
    assert 'b@example.com' not in seen[0]['review_focus']
    assert '[연락처 삭제]' in response.input_fields['projects[0].description']


def test_firebase_gateway_denies_inactive_or_foreign_owner():
    from app.firebase_gateway import FirebaseGateway, ResumeAccessError, ResumeNotFoundError
    class Snapshot:
        exists = True
        def __init__(self, data): self.data = data
        def to_dict(self): return self.data
    class Ref:
        def __init__(self, data): self.data = data
        def document(self, _): return self
        def get(self): return Snapshot(self.data)
    class Database:
        user = {'isActive': False, 'cohortId': 'c'}
        def collection(self, _): return Ref(self.user)
    gateway = FirebaseGateway.__new__(FirebaseGateway)
    gateway._db = Database()
    gateway._resume_ref = lambda *args: Ref({'userId': 'another'})
    with pytest.raises(ResumeAccessError):
        gateway.get_owned_resume('c', 'r', 'me')
    gateway._db.user = {'isActive': True, 'cohortId': 'c'}
    with pytest.raises(ResumeNotFoundError):
        gateway.get_owned_resume('c', 'r', 'me')


def test_model_questions_come_before_thin_self_introduction_questions():
    # 문항마다 같은 문장으로 묻는 질문이 앱의 질문 7칸을 먼저 차지하면 공고 요건 질문이 밀린다.
    result = generation({})
    fields = {
        'projects[0].description': '설명',
        'selfIntroduction.intro.body': '성실합니다.',
        'selfIntroduction.growth.body': '컴퓨터를 좋아했습니다.',
    }
    add_thin_self_introduction_questions(result, fields)
    normalize_questions(result, fields, [], 'r')
    assert [q.field_path for q in result.questions] == [
        'projects[0].description', 'selfIntroduction.intro.body', 'selfIntroduction.growth.body',
    ]


def test_empty_and_near_duplicate_questions_are_dropped():
    result = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(field_path='projects[0].description', original_quote='배포 전환', reason='정리',
                       confirmation_question='없음'),
    ], questions=[
        ReviewQuestion(field_path='projects[0].description', topic='action', priority=1, reason='r',
                       question='주문 목록 API에서 개선을 시작하게 된 구체적인 문제 상황이나 조회 조건은 무엇이었나요?'),
        ReviewQuestion(field_path='projects[0].description', topic='situation', priority=2, reason='r',
                       question='주문 목록 API에서 성능 문제가 발생한 구체적인 상황이나 조회 조건을 설명할 수 있나요?'),
        ReviewQuestion(field_path='projects[0].description', topic='scope', priority=2, reason='r',
                       question='N+1 제거, 커버링 인덱스, Redis 캐시 도입 중 본인이 직접 구현한 범위는 무엇인가요?'),
        ReviewQuestion(field_path='projects[0].role', topic='other', priority=2, reason='r', question='없습니다.'),
    ])
    normalize_questions(result, {'projects[0].description': '설명', 'projects[0].role': '팀원'}, [], 'r')
    assert [q.topic for q in result.questions] == ['action', 'scope']
    assert result.sentence_reviews[0].confirmation_question is None


def test_recruiting_conditions_in_brackets_are_not_part_of_role_title():
    from app.review_workflow import job_role_title
    assert job_role_title('(주)한결정보기술', '공공 SI 사업 Java 개발자 (신입)') == '공공 SI 사업 Java 개발자'
    assert job_role_title('(주)루멘커머스', 'Web 백엔드 개발자 (Java/Spring, 경력 3년 이상)') == 'Web 백엔드 개발자'
    assert job_role_title('(주)데이터온', '데이터 엔지니어(Python)') == '데이터 엔지니어(Python)'


def test_answered_question_is_not_asked_again_in_other_words():
    from app.models import ConfirmationAnswer
    answered = ConfirmationAnswer(
        question_id='q1', field_path='projects[0].description', answer='Socket.io로 채팅을 직접 구현했습니다.',
        question='중고거래 커뮤니티에서 채팅 기능을 본인이 직접 구현한 범위는 어디까지인가요?')
    result = ResumeReviewGeneration(summary='', section_reviews=[], questions=[
        ReviewQuestion(field_path='projects[0].description', topic='scope', priority=1, reason='r',
                       question='중고거래 커뮤니티에서 채팅 기능 중 본인이 직접 구현한 범위를 알려 주세요.'),
        ReviewQuestion(field_path='projects[0].description', topic='result', priority=2, reason='r',
                       question='찜 목록 조회를 개선한 뒤 확인한 변화가 있나요?'),
    ])
    normalize_questions(result, {'projects[0].description': '설명'}, [answered], 'r')
    assert [q.topic for q in result.questions] == ['result']


def test_none_answer_is_recorded_without_calling_the_model():
    # 앱의 "없음" 카드. 고칠 사실이 없으니 재첨삭을 돌리지 않고 답만 기록해 다음 질문으로 넘어간다.
    calls = []

    def generate(data):
        calls.append(data)
        return ResumeReviewGeneration(summary='검토', section_reviews=[], questions=[
            ReviewQuestion(field_path='projects[0].description', topic='action', question='어떤 행동을 했나요?', reason='r', priority=1),
            ReviewQuestion(field_path='projects[0].description', topic='result', question='도입 후 확인한 변화가 있나요?', reason='r', priority=2),
        ])

    db = FakeFirebase()
    service = ResumeReviewService(Settings(openai_api_key='test'), db, generate)
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    q = first.questions[0]
    answer = ConfirmationAnswer(question_id=q.question_id, field_path=q.field_path, question=q.question, answer='없음')
    result = service.review('valid-token', FirestoreResumeReviewRequest(
        cohort_id='cohort-1', resume_id='resume-1', previous_review_id=first.review_id,
        expected_input_hash=first.input_hash, answers=[answer]))
    assert len(calls) == 1
    assert result.telemetry['model_skipped'] == 'none_answer'
    assert result.confirmed_answers[0].answer == '없음'
    assert not result.sentence_reviews
    assert [x.question for x in result.questions] == ['도입 후 확인한 변화가 있나요?']


def test_requirement_answer_naming_another_item_moves_there():
    # 모델이 만든 요건 질문(reason이 서버 상수가 아님)에 다른 프로젝트 이름으로 답하면 그 프로젝트로 옮긴다.
    from app.review_workflow import prepare_answers
    fields = {
        'projects[0].name': '재생 화면 SwiftUI 전환', 'projects[0].description': '재생 화면을 SwiftUI로 옮겼습니다.',
        'projects[1].name': '오프라인 다운로드', 'projects[1].description': '오디오 파일을 내려받아 재생합니다.',
    }
    refs = {path: f'p{i}:' for i, path in enumerate(fields)}
    previous = {'input_hash': 'h', 'item_refs': refs, 'questions': [{
        'question_id': 'q1', 'field_path': 'projects[0].description', 'question': 'AVFoundation을 써 봤나요?',
        'reason': '요건 확인', 'requirement_id': 'req-4'}]}
    request = FirestoreResumeReviewRequest(cohort_id='c', resume_id='r', expected_input_hash='h', previous_review_id='p', answers=[
        ConfirmationAnswer(question_id='q1', field_path='projects[0].description', question='AVFoundation을 써 봤나요?',
                           answer='오프라인 다운로드 프로젝트에서 AVPlayer로 내려받은 오디오를 재생했습니다.')])
    moved = prepare_answers(request, previous, 'h', refs, fields)
    assert moved[0].field_path == 'projects[1].description'
    same = prepare_answers(request.model_copy(update={'answers': [request.answers[0].model_copy(
        update={'answer': 'AVPlayer로 오디오를 재생했습니다.'})]}), previous, 'h', refs, fields)
    assert same[0].field_path == 'projects[0].description', '항목 이름이 없으면 질문 칸 그대로'



def _new_project_run(new_project, stuffed_revision=None):
    """첫 첨삭은 질문 하나, 답한 뒤 후속 첨삭에서 모델이 새 프로젝트를 제안한다."""
    from app.models import NewProjectOut
    calls = []

    def generate(data):
        calls.append(data)
        if len(calls) == 1:
            return ResumeReviewGeneration(summary='검토', section_reviews=[], questions=[ReviewQuestion(
                field_path='projects[0].description', topic='scope', question='LMS 프로젝트에서 지도 API를 써 봤나요?',
                reason='요건 확인', priority=1)])
        reviews = []
        if stuffed_revision:
            reviews.append(SentenceReview(
                field_path='projects[0].description', original_quote='API 응답 시간을 20% 개선했습니다.',
                suggested_revision=stuffed_revision, reason='답변 반영', edit_type='content', status='improved',
                evidence_quotes=['API 응답 시간을 20% 개선했습니다.']))
        return ResumeReviewGeneration(summary='검토', section_reviews=[], sentence_reviews=reviews,
                                      new_projects=[NewProjectOut(**new_project)])

    service = ResumeReviewService(Settings(openai_api_key='test'), FakeFirebase(), generate)
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    q = first.questions[0]
    answer = ConfirmationAnswer(
        question_id=q.question_id, field_path=q.field_path, question=q.question,
        answer='부트캠프 개인 과제로 카카오맵 API를 사용해 매물 위치 마커와 마커 클릭 시 매물 요약을 보여주는 화면을 만든 경험이 '
               '있습니다. LMS 프로젝트에서는 지도 API를 담당하지 않았습니다.')
    result = service.review('valid-token', FirestoreResumeReviewRequest(
        cohort_id='cohort-1', resume_id='resume-1', previous_review_id=first.review_id,
        expected_input_hash=first.input_hash, answers=[answer]))
    return result, q, calls


GOOD_NEW_PROJECT = dict(
    answer_quote='부트캠프 개인 과제로 카카오맵 API를 사용해 매물 위치 마커와 마커 클릭 시 매물 요약을 보여주는 화면을 만든',
    name='카카오맵 매물 지도 (부트캠프 개인 과제)', role='개인 과제', tech_stack='카카오맵 API',
    description='카카오맵 API로 매물 위치 마커를 표시하고, 마커를 누르면 매물 요약을 보여 주는 화면을 만들었습니다.',
)


def test_separate_experience_in_answer_becomes_new_project_suggestion():
    # 기존 프로젝트에서는 안 했다는 경험을 그 프로젝트에 끼워 넣지 않고, 새 프로젝트 추가 수정안으로 만든다.
    result, question, calls = _new_project_run(
        GOOD_NEW_PROJECT,
        stuffed_revision='API 응답 시간을 20% 개선했고, 카카오맵 API로 매물 위치 마커를 표시하는 화면을 만들었습니다.')
    from app.prompts import RESUME_REVIEW_SYSTEM_PROMPT
    # 첫 첨삭에는 새 프로젝트 규칙도 출력 칸도 주지 않는다(첫 첨삭 출력이 늘었다).
    assert 'new_projects' not in RESUME_REVIEW_SYSTEM_PROMPT
    assert calls[0]['allow_new_projects'] is False and 'new_projects' not in calls[0]['review_scope']
    assert calls[1]['allow_new_projects'] is True and 'new_projects' in calls[1]['review_scope']
    added = [review for review in result.sentence_reviews if review.new_item]
    assert len(added) == 1
    item = added[0]
    assert item.field_path == 'projects[1].description'
    assert item.original_quote == '' and item.status == 'improved' and not item.validation_issues
    assert item.new_item.question_id == question.question_id
    assert item.new_item.name == GOOD_NEW_PROJECT['name'] and item.new_item.role == '개인 과제'
    assert '새로 추가' in item.reason
    assert not [r for r in result.sentence_reviews if r.field_path == 'projects[0].description' and r.suggested_revision], \
        '같은 경험을 기존 프로젝트 설명에 넣은 수정안은 뺀다'
    assert result.new_projects == []


@pytest.mark.parametrize('change, issue', [
    ({'description': '카카오맵 API로 매물 위치 마커를 표시해 방문 전환율을 30% 높였습니다.'}, 'unsupported_number'),
    ({'name': 'Next.js 매물 지도'}, 'name_not_in_answer'),
    ({'tech_stack': '카카오맵 API, Redux'}, 'unsupported_term'),
    ({'description': '카카오맵 API 연동을 주도해 매물 위치 마커 화면을 만들었습니다.'}, 'unsupported_role'),
    ({'name': 'LMS 프로젝트'}, 'existing_project'),
    ({'answer_quote': '답변에 없는 문장을 인용했습니다'}, None),
])
def test_new_project_suggestion_only_uses_answer_facts(change, issue):
    result, _, _ = _new_project_run({**GOOD_NEW_PROJECT, **change})
    assert not [review for review in result.sentence_reviews if review.new_item]
    if issue:
        assert any(issue in warning for warning in result.grounding_warnings)


def test_first_review_never_adds_new_project():
    from app.models import NewProjectOut
    service = ResumeReviewService(Settings(openai_api_key='test'), FakeFirebase(), lambda _: ResumeReviewGeneration(
        summary='검토', section_reviews=[], new_projects=[NewProjectOut(**GOOD_NEW_PROJECT)]))
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    assert not [review for review in first.sentence_reviews if review.new_item]
    assert first.new_projects == []


def test_tech_answer_about_separate_work_is_not_rejected_for_missing_item_name():
    from app.review_workflow import MISSING_JOB_TECH_REASON
    fields = {'projects[0].name': '매물 검색 서비스', 'projects[0].description': '검색 필터를 맡았습니다.'}
    refs = {path: 'projects:p1' for path in fields}
    previous = {'input_hash': 'h', 'item_refs': refs, 'questions': [{
        'question_id': 'q1', 'field_path': 'projects[0].description', 'question': '지도 API를 써 봤나요?',
        'reason': MISSING_JOB_TECH_REASON}]}

    def ask(text):
        return FirestoreResumeReviewRequest(cohort_id='c', resume_id='r', expected_input_hash='h', previous_review_id='p', answers=[
            ConfirmationAnswer(question_id='q1', field_path='projects[0].description', question='지도 API를 써 봤나요?', answer=text)])

    kept = prepare_answers(ask('부트캠프 개인 과제로 카카오맵 API 마커 화면을 만들었습니다.'), previous, 'h', refs, fields)
    assert kept[0].field_path == 'projects[0].description'
    with pytest.raises(ReviewInputError):
        prepare_answers(ask('카카오맵 API로 마커 화면을 만들었습니다.'), previous, 'h', refs, fields)


def test_new_project_name_made_of_form_words_is_renamed_from_answer_tech():
    # "부트캠프 개인 과제"는 무엇을 만든 과제인지 안 보인다(2026-09-15 새 케이스 v16l).
    result, _, _ = _new_project_run({**GOOD_NEW_PROJECT, 'name': '부트캠프 개인 과제'})
    added = [review for review in result.sentence_reviews if review.new_item]
    assert len(added) == 1 and added[0].new_item.name == '카카오맵 API 개인 과제'
    assert "'카카오맵 API 개인 과제'" in added[0].reason


TWO_PROJECT_CONTENT = {
    **SAMPLE_CONTENT,
    'projects': [
        SAMPLE_CONTENT['projects'][0],
        {'id': 'project-2', 'name': '숙소 예약 클론', 'role': '백엔드', 'techStack': 'Node.js',
         'description': '숙소 예약 API를 구현했습니다.'},
    ],
}


class TwoProjectFirebase(FakeFirebase):
    def get_owned_resume(self, cohort_id, resume_id, uid):
        super().get_owned_resume(cohort_id, resume_id, uid)
        return {'userId': 'user-1', 'content': TWO_PROJECT_CONTENT}


def test_answer_naming_another_item_lets_the_followup_edit_that_item_with_only_its_sentence():
    # "LMS에서 X를 했고, 숙소 예약 클론에서도 Y를 했어요"의 Y는 답한 항목만 보는 재첨삭에서 넣을 곳이 없어 사라졌다.
    calls = []
    answer_text = ('LMS 프로젝트에서 Redis 캐시를 적용해 응답 시간을 20% 개선했습니다. '
                   '숙소 예약 클론에서는 트랜잭션으로 동시 요청 50건의 중복 예약을 0건으로 막았습니다.')

    def generate(data):
        calls.append(data)
        if len(calls) == 1:
            return ResumeReviewGeneration(summary='검토', section_reviews=[], questions=[ReviewQuestion(
                field_path='projects[0].description', topic='action', question='LMS 프로젝트에서 어떻게 개선했나요?',
                reason='r', priority=1)])
        return ResumeReviewGeneration(summary='검토', section_reviews=[], sentence_reviews=[
            SentenceReview(field_path='projects[0].description', original_quote='API 응답 시간을 20% 개선했습니다.',
                           suggested_revision='Redis 캐시를 적용해 API 응답 시간을 20% 개선했습니다.', reason='답변 반영',
                           edit_type='content', evidence_quotes=['Redis 캐시를 적용해']),
            SentenceReview(field_path='projects[1].description', original_quote='숙소 예약 API를 구현했습니다.',
                           suggested_revision='숙소 예약 API를 구현하고, 트랜잭션으로 동시 요청 50건의 중복 예약을 0건으로 막았습니다.',
                           reason='답변 반영', edit_type='content', evidence_quotes=['동시 요청 50건의 중복 예약을 0건으로']),
        ])

    service = ResumeReviewService(Settings(openai_api_key='test'), TwoProjectFirebase(), generate)
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    q = first.questions[0]
    result = service.review('valid-token', FirestoreResumeReviewRequest(
        cohort_id='cohort-1', resume_id='resume-1', previous_review_id=first.review_id,
        expected_input_hash=first.input_hash,
        answers=[ConfirmationAnswer(question_id=q.question_id, field_path=q.field_path, question=q.question,
                                    answer=answer_text)]))

    # 모델은 이름이 나온 항목도 보고, 그 항목에는 그 문장만 받는다. 질문한 칸의 답에서는 그 문장을 뺀다.
    assert '숙소 예약 API를 구현했습니다.' in calls[1]['resume_text']
    turn = {a['field_path']: a['answer'] for a in json.loads(calls[1]['current_turn_answers'])}
    assert turn['projects[1].description'].startswith('숙소 예약 클론에서는')
    assert 'Redis' not in turn['projects[1].description']
    assert '숙소 예약 클론' not in turn['projects[0].description']
    assert result.answer_scope_paths == ['projects[1].description']
    edited = {r.field_path: r.suggested_revision for r in result.sentence_reviews if r.suggested_revision}
    assert '50건' in edited['projects[1].description'], '그 항목의 답 문장이 근거가 되어 수정안이 남는다'
    assert 'Redis' in edited['projects[0].description']
    # 저장되는 확인 답은 사용자가 보낸 답 그대로다.
    assert [(a.field_path, a.answer) for a in result.confirmed_answers] == [('projects[0].description', answer_text)]


def test_other_item_edit_cannot_borrow_facts_from_sentences_about_the_answered_item():
    # 이름이 나온 항목에는 그 항목 문장만 근거로 준다. LMS 문장의 "Redis·20%"를 숙소 예약 클론에 넣으면 버린다.
    from app.review_workflow import mentioned_item_answers
    fields = {'projects[0].name': 'LMS 프로젝트', 'projects[0].description': 'API 응답 시간을 20% 개선했습니다.',
              'projects[1].name': '숙소 예약 클론', 'projects[1].description': '숙소 예약 API를 구현했습니다.'}
    refs = {path: f'projects:p{path[9]}' for path in fields}
    answer = ConfirmationAnswer(question_id='q1', field_path='projects[0].description', question='q',
                                answer='LMS 프로젝트에서 Redis 캐시를 적용했습니다. 숙소 예약 클론에서는 트랜잭션을 적용했습니다.')
    extra = mentioned_item_answers([answer], fields, refs, {'item_refs': refs})
    assert [(a.field_path, a.answer) for a in extra] == [('projects[1].description', '숙소 예약 클론에서는 트랜잭션을 적용했습니다.')]
    result = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='projects[1].description', original_quote='숙소 예약 API를 구현했습니다.', edit_type='content',
        suggested_revision='숙소 예약 API를 Redis 캐시로 구현했습니다.', reason='r')])
    ground_sentences(fields, [answer, *extra], result)
    assert result.sentence_reviews[0].suggested_revision is None
    # 이름이 없거나 "없음" 답이면 만들지 않는다.
    assert mentioned_item_answers([answer.model_copy(update={'answer': '캐시를 적용했습니다.'})], fields, refs, {'item_refs': refs}) == []
    assert mentioned_item_answers([answer.model_copy(update={'answer': '없어요'})], fields, refs, {'item_refs': refs}) == []


def test_sentence_moved_to_another_item_is_withheld_from_the_answered_field():
    # 교육 칸 질문에 회사 프로젝트에서 한 일을 답했더니, 그 문장이 교육 설명 수정안에도 들어가 교육 과정에서 한 일처럼
    # 읽혔다(2026-09-15 한 번도 안 본 케이스). 질문한 칸 수정안에 떼어 낸 문장이 들어가면 뺀다.
    from app.review_workflow import withhold_moved_sentences
    fields = {'trainingExperience[0].course': '데이터 엔지니어링 과정', 'trainingExperience[0].description': 'Airflow를 배웠습니다.',
              'projects[0].name': '물류 대시보드', 'projects[0].description': '물류 지표 대시보드를 만들었습니다.'}
    moved = ConfirmationAnswer(question_id=None, field_path='projects[0].description', question='q',
                               answer='물류 대시보드에서 Airflow로 매일 적재 작업을 자동화했습니다.')
    generation = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(field_path='trainingExperience[0].description', original_quote='Airflow를 배웠습니다.',
                       suggested_revision='Airflow를 배우고 매일 적재 작업을 자동화했습니다.', reason='r', status='improved'),
        SentenceReview(field_path='projects[0].description', original_quote='물류 지표 대시보드를 만들었습니다.',
                       suggested_revision='물류 지표 대시보드를 만들고 Airflow로 매일 적재 작업을 자동화했습니다.', reason='r',
                       status='improved'),
    ])
    warnings = withhold_moved_sentences(generation, {'trainingExperience[0].description'}, [moved], fields)
    training, project = generation.sentence_reviews
    assert training.suggested_revision is None and 'moved_to_other_item' in training.validation_issues
    assert training.confirmation_question is None and warnings
    assert project.suggested_revision, '떼어 낸 문장이 원래 속한 항목의 수정안은 그대로 둔다'
    # 질문한 칸만의 사실을 더한 수정안은 그대로 둔다.
    generation.sentence_reviews[0] = SentenceReview(
        field_path='trainingExperience[0].description', original_quote='Airflow를 배웠습니다.',
        suggested_revision='Airflow로 DAG를 짜는 실습을 3주 동안 했습니다.', reason='r', status='improved')
    withhold_moved_sentences(generation, {'trainingExperience[0].description'}, [moved], fields)
    assert generation.sentence_reviews[0].suggested_revision


def test_first_review_lists_noun_fragments_and_counts_unjoined_ones():
    # 끊긴 문장과 온전한 문장이 섞인 칸을 모델이 건너뛰어 개발용 30칸 중 25칸만 이었다(2026-09-15). 첫 첨삭에만 목록을 준다.
    calls = []

    def generate(data):
        calls.append(data)
        return ResumeReviewGeneration(summary='검토', section_reviews=[], questions=[ReviewQuestion(
            field_path='projects[0].description', topic='action', question='LMS 프로젝트에서 어떻게 했나요?',
            reason='r', priority=1)], sentence_reviews=[SentenceReview(
                field_path='coreCompetencies.text', original_quote='Python REST API 개발',
                suggested_revision='Python으로 REST API를 개발했습니다.', reason='명사형 잇기', edit_type='clarity')])

    service = ResumeReviewService(Settings(openai_api_key='test'), FakeFirebase(), generate)
    first = service.review('valid-token', FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1'))
    listed = json.loads(calls[0]['noun_fragments'])
    assert {'field_path': 'coreCompetencies.text', 'sentence': 'Python REST API 개발'} in listed
    assert all(item['sentence'] != 'API 응답 시간을 20% 개선했습니다.' for item in listed), '온전한 문장은 넣지 않는다'
    assert first.telemetry['noun_fragments'] == len(listed)
    assert first.telemetry['noun_fragments_unjoined'] == 0
    q = first.questions[0]
    service.review('valid-token', FirestoreResumeReviewRequest(
        cohort_id='cohort-1', resume_id='resume-1', previous_review_id=first.review_id, expected_input_hash=first.input_hash,
        answers=[ConfirmationAnswer(question_id=q.question_id, field_path=q.field_path, question=q.question,
                                    answer='캐시를 적용했습니다.')]))
    assert json.loads(calls[1]['noun_fragments']) == [], '후속 첨삭에는 주지 않는다'


def test_one_sentence_about_two_items_is_split_at_the_item_names():
    # 경력 칸 질문에 "X에서 처리 시간을 줄였고, Y에서는 테스트로 검증했습니다"라고 한 문장으로 답했더니, 문장째 Y에 붙어 X의
    # 숫자 성과가 Y 칸 수정안에 들어갔다(2026-09-15 한 번도 안 본 케이스). 항목 이름이 나오는 자리에서 나눈다.
    from app.review_workflow import mentioned_item_answers, without_mentioned_sentences
    fields = {'experience[0].company': '(주)예시물류', 'experience[0].description': '물류 시스템 백엔드를 개발했습니다.',
              'projects[0].name': '주문 정산 배치', 'projects[0].description': '주문 정산 배치를 만들었습니다.',
              'projects[1].name': '재고 동기화', 'projects[1].description': '재고 동기화 API를 만들었습니다.'}
    refs = {path: f'ref:{path}' for path in fields}
    answer = ConfirmationAnswer(
        question_id='q1', field_path='experience[0].description', question='회사에서 한 일은?',
        answer='주문 정산 배치에서 처리 시간을 40분에서 10분으로 줄였고, 재고 동기화에서는 통합 테스트로 결과를 검증했습니다.')
    extra = {a.field_path: a.answer for a in mentioned_item_answers([answer], fields, refs, {'item_refs': refs})}
    assert extra['projects[0].description'] == '주문 정산 배치에서 처리 시간을 40분에서 10분으로 줄였고'
    assert extra['projects[1].description'] == '재고 동기화에서는 통합 테스트로 결과를 검증했습니다.'
    # 질문한 경력 칸에는 두 조각 모두 떼어 낸 것이라 근거로 남기지 않는다.
    assert without_mentioned_sentences([answer], [a for a in mentioned_item_answers([answer], fields, refs, {'item_refs': refs})],
                                       fields) == []
    # Y 칸 수정안에 X의 숫자가 들어가면 근거가 없어 버린다.
    mentioned = mentioned_item_answers([answer], fields, refs, {'item_refs': refs})
    result = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='projects[1].description', original_quote='재고 동기화 API를 만들었습니다.', edit_type='content',
        suggested_revision='재고 동기화 API를 만들고 처리 시간을 40분에서 10분으로 줄였으며 통합 테스트로 검증했습니다.', reason='r')])
    ground_sentences(fields, mentioned, result)
    assert result.sentence_reviews[0].suggested_revision is None
    assert 'unsupported_number' in result.sentence_reviews[0].validation_issues


def test_self_introduction_may_point_to_a_named_project_without_being_withheld():
    # 자기소개 답에 프로젝트 이름과 성과를 말했더니, 자기소개 수정안이 "다른 항목 이야기"로 막혔다(2026-09-15 개발용 v16v).
    # 경험 칸끼리 섞이는 것만 막는다. 자기소개서는 경험을 가리키며 쓰는 칸이다.
    from app.review_workflow import withhold_moved_sentences, without_mentioned_sentences, mentioned_item_answers
    fields = {'projects[0].name': '사내 규정 질의응답 챗봇', 'projects[0].description': 'RAG 챗봇 개발에 참여했습니다.',
              'selfIntroduction.intro.body': '생성형 AI로 불편을 해결하는 개발자입니다.'}
    refs = {path: f'ref:{path}' for path in fields}
    answer = ConfirmationAnswer(question_id='q1', field_path='selfIntroduction.intro.body', question='q',
                                answer='사내 규정 질의응답 챗봇에서 청크를 조항 단위로 바꿔 정답률을 62%에서 81%로 높였습니다.')
    mentioned = mentioned_item_answers([answer], fields, refs, {'item_refs': refs})
    assert [a.field_path for a in mentioned] == ['projects[0].description']
    assert without_mentioned_sentences([answer], mentioned, fields) == [answer], '자기소개 근거에서는 빼지 않는다'
    generation = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[SentenceReview(
        field_path='selfIntroduction.intro.body', original_quote=fields['selfIntroduction.intro.body'], reason='r',
        status='improved', suggested_revision='사내 규정 질의응답 챗봇에서 정답률을 62%에서 81%로 높인 경험으로, 생성형 AI로 불편을 해결하는 개발자입니다.')])
    withhold_moved_sentences(generation, {'selfIntroduction.intro.body'}, mentioned, fields)
    assert generation.sentence_reviews[0].suggested_revision


def test_answer_revision_drops_superseded_vague_sentence():
    # 모델이 "'여러 방법을 시도해 해결했습니다'를 구체화했다"고 적고도 그 문장을 그대로 두어,
    # "제가 직접 만들었습니다" 뒤에 "팀원들과 여러 방법을 시도해"가 붙어 앞뒤가 어긋났다(2026-09-16 앱).
    from app.resume_review import _drop_superseded_vague_sentence

    original = ('LMS 챗봇을 만들때 공지를 물어봤는데 규정 문서가 검색되는 문제가 있었습니다. '
                '팀원들과 여러 방법을 시도해서 해결했습니다.')
    revision = ('LMS 챗봇을 만들 때 공지를 물어보면 규정 문서가 검색되는 문제가 있었습니다. '
                '문서를 종류별 네임스페이스로 나눠 다시 적재하고 질문 분류 라우터를 제가 직접 만들었습니다. '
                '팀원들과 여러 방법을 시도해서 해결했습니다. '
                '평가 질문 40개로 확인했더니 맞는 문서를 가져온 질문이 25개에서 36개로 늘었습니다.')

    repaired = _drop_superseded_vague_sentence(original, revision)
    assert '여러 방법을 시도' not in repaired
    assert '제가 직접 만들었습니다' in repaired
    assert '25개에서 36개로' in repaired

    # 원문을 그대로 돌려준 수정안에서 문장을 빼면 고치지도 않은 사실이 사라진다.
    assert _drop_superseded_vague_sentence(original, original) == original
    # 답변으로 새로 들어온 문장이면 막연해 보여도 남긴다.
    added = '원문입니다. 여러 방법을 시도했습니다. 새 사실을 적었습니다.'
    assert '여러 방법' in _drop_superseded_vague_sentence('원문입니다. 다른 문장입니다.', added)
