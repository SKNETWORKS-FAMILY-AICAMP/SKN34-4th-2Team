from fastapi.testclient import TestClient

from app.config import Settings
from app.review_workflow import PROMPT_VERSION
from app.firebase_gateway import FirebaseAuthenticationError, ResumeNotFoundError
from app.main import app, get_resume_review_service
from app.models import (
    FirestoreResumeReviewRequest,
    ResumeReviewGeneration,
    ResumeSectionReview,
)
from app.resume_review import (
    ResumeReviewService,
    enforce_resume_review_grounding,
    render_resume_content,
)


SAMPLE_CONTENT = {
    "basicInfo": {
        "name": "홍길동",
        "phone": "010-1234-5678",
        "email": "private@example.com",
        "birthDate": "2000-01-01",
        "githubUrl": "https://github.com/private",
    },
    "coreCompetencies": {"text": "Python REST API 개발"},
    "techStack": [{"id": "skill-1", "name": "Python", "level": "중"}],
    "projects": [
        {
            "id": "project-1",
            "name": "LMS 프로젝트",
            "role": "백엔드 개발",
            "techStack": "FastAPI",
            "description": "API 응답 시간을 20% 개선했습니다.",
            "url": "https://private.example.com",
        }
    ],
}


class FakeFirebase:
    def __init__(self) -> None:
        self.saved: dict | None = None
        self.states = {}

    def claim_review(self, cohort_id, resume_id, uid, request_id, fingerprint):
        from app.review_workflow import ReviewConflict
        if request_id in self.states:
            state = self.states[request_id]
            if state['fingerprint'] != fingerprint or not state.get('response'):
                raise ReviewConflict('duplicate')
            return state
        self.states[request_id] = {'fingerprint': fingerprint}
        return {}

    def complete_review(self, cohort_id, resume_id, uid, request_id, response):
        self.saved = response
        self.states[request_id]['response'] = response

    def fail_review(self, *args):
        pass

    def get_ai_review(self, cohort_id, resume_id, uid, review_id):
        self.get_owned_resume(cohort_id, resume_id, uid)
        return self.states[review_id]['response']

    def verify_id_token(self, id_token: str) -> str:
        if id_token != "valid-token":
            raise FirebaseAuthenticationError()
        return "user-1"

    def get_owned_resume(self, cohort_id: str, resume_id: str, uid: str) -> dict:
        if (cohort_id, resume_id, uid) != ("cohort-1", "resume-1", "user-1"):
            raise ResumeNotFoundError()
        return {"userId": "user-1", "content": SAMPLE_CONTENT}

    def save_ai_review(self, cohort_id: str, resume_id: str, uid: str, payload: dict) -> str:
        self.saved = payload
        return "review-1"


def _generation(_: dict[str, str]) -> ResumeReviewGeneration:
    return ResumeReviewGeneration(
        summary="프로젝트 성과 근거가 명확하며 역할을 더 구체화할 수 있습니다.",
        section_reviews=[
            ResumeSectionReview(
                section_key="projects",
                strengths=["성과 수치가 있습니다."],
                issues=["구체 행동이 부족합니다."],
                resume_quotes=["API 응답 시간을 20% 개선했습니다."],
                suggested_revision="API 응답 시간을 20% 개선했습니다.",
                confirmation_questions=["어떤 방법으로 개선했나요?"],
            )
        ],
    )


def test_renderer_excludes_personal_information_and_internal_fields() -> None:
    rendered = render_resume_content(SAMPLE_CONTENT)

    assert "홍길동" not in rendered
    assert "010-1234-5678" not in rendered
    assert "private@example.com" not in rendered
    assert "project-1" not in rendered
    assert "private.example.com" not in rendered
    assert "Python REST API 개발" in rendered
    assert "API 응답 시간을 20% 개선했습니다." in rendered


def test_review_reads_owned_resume_and_saves_separate_review() -> None:
    firebase = FakeFirebase()
    service = ResumeReviewService(Settings(openai_api_key="test"), firebase, generator=_generation)

    response = service.review(
        "valid-token",
        FirestoreResumeReviewRequest(cohort_id="cohort-1", resume_id="resume-1"),
    )

    assert response.review_id
    assert response.section_reviews[0].suggested_revision is None
    assert response.input_fields['projects[0].description'] == SAMPLE_CONTENT['projects'][0]['description']
    assert 'basicInfo' in response.excluded_fields
    assert firebase.saved is not None
    assert firebase.saved['telemetry']['prompt_version'] == PROMPT_VERSION
    assert "content" not in firebase.saved


def test_sentence_cannot_borrow_another_projects_number():
    from app.models import SentenceReview
    from app.resume_review import ground_sentences
    fields = {'projects[0].description': 'API 개발', 'projects[1].description': '50% 개선'}
    generated = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(field_path='projects[0].description', original_quote='API 개발',
                       reason='구체화', suggested_revision='API 50% 개선', evidence_quotes=['API 개발', '50% 개선'])
    ])
    assert ground_sentences(fields, [], generated)
    assert generated.sentence_reviews[0].suggested_revision is None


def test_confirmed_answer_allows_grounded_revision():
    from app.models import ConfirmationAnswer, SentenceReview
    from app.resume_review import ground_sentences
    answer = ConfirmationAnswer(field_path='projects[0].description', question='변화는?', answer='독립적으로 확인하는 환경을 구축했습니다.')
    generated = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(field_path=answer.field_path, original_quote='QA 개선', reason='구체화',
                       suggested_revision=answer.answer, evidence_quotes=[answer.answer])
    ])
    assert ground_sentences({answer.field_path: 'QA 개선'}, [answer], generated) == []
    assert generated.sentence_reviews[0].suggested_revision == answer.answer


def test_confirmed_answer_allows_grounded_paraphrase_without_verbatim_evidence():
    from app.models import ConfirmationAnswer, SentenceReview
    from app.resume_review import ground_sentences, require_answer_reflection

    path = 'selfIntroduction.challenge.body'
    original = '추천 목록을 불러올 때 응답이 느려지는 문제가 있었습니다.'
    answer = ConfirmationAnswer(
        field_path=path,
        question='직접 수행한 행동과 결과를 알려 주세요.',
        answer=(
            '구간별 서버 응답 시간을 측정해 병목을 찾고 캐시를 적용했으며, '
            '응답 시간을 약 220ms까지 줄였습니다.'
        ),
    )
    revision = (
        '구간별 응답 시간을 측정해 병목 지점을 확인하고 캐시를 적용하여 '
        '응답 시간을 약 220ms까지 단축했습니다.'
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(
            field_path=path,
            original_quote=original,
            reason='행동과 결과 구체화',
            suggested_revision=revision,
            evidence_quotes=[original],
        ),
    ])

    assert ground_sentences({path: original}, [answer], generated) == []
    assert require_answer_reflection(generated, [answer]) == []
    assert generated.sentence_reviews[0].suggested_revision == revision
    assert 'answer:0' in generated.sentence_reviews[0].evidence_sources


def test_follow_up_revision_that_ignores_confirmed_answer_is_removed():
    from app.models import ConfirmationAnswer, SentenceReview
    from app.resume_review import ground_sentences, require_answer_reflection

    path = 'selfIntroduction.challenge.body'
    original = '추천 목록을 불러올 때 응답이 느려지는 문제가 있었습니다.'
    answer = ConfirmationAnswer(
        field_path=path,
        question='직접 수행한 행동과 결과를 알려 주세요.',
        answer='캐시를 적용해 응답 시간을 약 220ms까지 줄였습니다.',
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(
            field_path=path,
            original_quote=original,
            reason='표현 정리',
            suggested_revision='추천 목록 조회 시 응답이 지연되는 문제가 있었습니다.',
            evidence_quotes=[original],
        ),
    ])

    assert ground_sentences({path: original}, [answer], generated) == []
    warnings = require_answer_reflection(generated, [answer])
    assert generated.sentence_reviews[0].suggested_revision is None
    assert 'answer_not_reflected' in generated.sentence_reviews[0].validation_issues
    assert warnings


def test_substantive_support_motivation_answer_gets_safe_fallback():
    from app.models import ConfirmationAnswer
    from app.resume_review import add_substantive_answer_fallback

    path = 'selfIntroduction.motivation.body'
    original = '데이터를 활용해 사용자 문제를 해결하는 백엔드 개발자가 되고 싶습니다.'
    answer = ConfirmationAnswer(
        field_path=path,
        question='본인이 직접 한 행동이나 경험을 구체적으로 알려 주세요.',
        answer=(
            '프로젝트에서 사용자 요구사항과 데이터를 바탕으로 기능을 설계하고, '
            'Django REST API를 직접 구현했습니다. 익숙한 기술에 머무르지 않고 '
            '새로운 기술을 작은 기능에 적용하며 문제 해결 방법을 넓혔습니다.'
        ),
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    add_substantive_answer_fallback(generated, {path: original}, [answer])

    assert len(generated.sentence_reviews) == 1
    suggestion = generated.sentence_reviews[0]
    assert suggestion.original_quote == original
    assert suggestion.suggested_revision == answer.answer
    assert suggestion.evidence_sources == [path, 'answer:0']


def test_fallback_merges_answer_without_repeating_original_story():
    from app.models import ConfirmationAnswer
    from app.resume_review import add_substantive_answer_fallback

    path = 'selfIntroduction.challenge.body'
    original = (
        '팀 프로젝트에서 추천 목록이 느리다는 피드백을 받았습니다. '
        '처음엔 벡터 검색이 문제라고 짐작했는데, 구간별로 시간을 재 보니 '
        '실제 병목은 후보마다 공고를 한 건씩 조회하는 부분이었습니다. '
        '한 번에 가져오도록 바꾸고 자주 쓰는 결과를 캐시해 220ms까지 줄였습니다. '
        '짐작으로 고치지 않고 먼저 재는 습관이 여기서 생겼습니다.'
    )
    confirmed = (
        '추천 목록이 느리다는 피드백을 받고 제가 직접 어디서 시간이 오래 걸리는지 '
        '확인했습니다. 처음에는 코드를 바로 수정하기보다 처리 단계별로 시간을 측정했고, '
        '구간별로 서버 요청을 여러 번 보내는 부분이 가장 오래 걸린다는 걸 찾았습니다. '
        '그래서 데이터를 한 번에 가져오도록 수정하고 자주 사용하는 결과는 캐시하도록 '
        '바꿨습니다. 수정 후에는 응답 시간이 220ms 정도까지 줄었습니다. 이 경험을 통해 '
        '문제가 생겼을 때 바로 이것저것 고치기보다는 원인을 먼저 확인하고 하나씩 해결하는 '
        '습관이 생겼습니다.'
    )
    answer = ConfirmationAnswer(
        field_path=path,
        question='직접 수행한 행동과 결과를 알려 주세요.',
        answer=confirmed,
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    add_substantive_answer_fallback(generated, {path: original}, [answer])

    revision = generated.sentence_reviews[0].suggested_revision
    assert revision == confirmed
    assert revision.count('220ms') == 1
    assert '팀 프로젝트에서 추천 목록이 느리다는 피드백을 받았습니다.' not in revision


def test_fallback_edits_only_relevant_paragraph_and_preserves_other_paragraphs():
    from app.models import ConfirmationAnswer
    from app.resume_apply import ApplyRequest, build_application
    from app.resume_review import add_substantive_answer_fallback
    from app.review_workflow import digest

    path = 'projects[0].description'
    first = 'Pinecone 벡터 검색으로 채용공고 후보를 찾고 원문 DB와 대조했습니다.'
    second = '사용자 답변을 근거로 자기소개서 수정안을 생성하고 검증했습니다.'
    original = f'{first}\n\n{second}'
    confirmed = (
        '개발 환경을 통일하기 위해 Docker로 애플리케이션을 컨테이너화했고 '
        'Dockerfile을 작성해 이미지를 빌드하고 실행했습니다. 팀원도 같은 '
        '환경에서 애플리케이션을 실행할 수 있도록 사용 방법을 정리했습니다.'
    )
    answer = ConfirmationAnswer(
        field_path=path,
        question='Docker를 실제로 어떻게 사용했나요?',
        answer=confirmed,
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    add_substantive_answer_fallback(generated, {path: original}, [answer])

    suggestion = generated.sentence_reviews[0]
    assert suggestion.original_quote == second
    assert suggestion.suggested_revision == f'{second}\n\n{confirmed}'

    content = {'projects': [{'description': original}]}
    review = {
        'input_hash': digest(content),
        'sentence_reviews': [suggestion.model_dump()],
    }
    request = ApplyRequest(
        cohort_id='c', resume_id='r', request_id='apply-paragraph',
        review_id='review-paragraph', expected_input_hash=digest(content),
        selected_indices=[0],
    )
    updated, _ = build_application(content, review, request)
    assert updated['projects'][0]['description'] == f'{first}\n\n{second}\n\n{confirmed}'
    assert updated['projects'][0]['description'].count('\n\n') == 2


def test_fallback_skips_ambiguous_duplicate_paragraph_scope():
    from app.models import ConfirmationAnswer
    from app.resume_review import add_substantive_answer_fallback

    path = 'projects[0].description'
    repeated = 'API를 구현하고 테스트했습니다.'
    original = f'{repeated}\n\n{repeated}'
    answer = ConfirmationAnswer(
        field_path=path,
        question='직접 수행한 행동을 알려 주세요.',
        answer=(
            'Dockerfile을 작성해 애플리케이션 이미지를 빌드하고 실행하여 '
            '팀의 개발 환경을 동일하게 구성했습니다. 팀원이 같은 환경에서 '
            '실행할 수 있도록 필요한 명령과 사용 방법도 함께 정리했습니다.'
        ),
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    warnings = add_substantive_answer_fallback(generated, {path: original}, [answer])

    assert generated.sentence_reviews == []
    assert warnings == [f'ambiguous_fallback_scope:{path}']


def test_company_fit_fallback_keeps_company_duty_and_one_evidence_sentence():
    from app.models import ConfirmationAnswer
    from app.resume_review import add_substantive_answer_fallback

    path = 'selfIntroduction.motivation.body'
    original = (
        '데이터에서 의미를 찾는 일에 흥미를 느꼈습니다.\n\n'
        'AI 기술로 사용자의 문제를 해결하는 엔지니어로 성장하고 싶습니다.'
    )
    answer = ConfirmationAnswer(
        field_path=path,
        question='(주)토마토에이아이의 주요업무 중 실제 경험과 연결되는 업무는 무엇인가요?',
        answer=(
            '주요 업무 중 AI 서비스 개발과 데이터 처리 업무가 제 경험과 가장 연결됩니다. '
            '프로젝트에서 Python과 FastAPI로 채용공고 데이터를 처리하는 API를 구현했습니다. '
            '또한 여러 화면을 설계하고 테스트했으며 이 과정에서 많은 것을 배웠습니다.'
        ),
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    add_substantive_answer_fallback(generated, {path: original}, [answer])

    revision = generated.sentence_reviews[0].suggested_revision
    assert '(주)토마토에이아이의 주요 업무 중 AI 서비스 개발' in revision
    assert 'Python과 FastAPI로 채용공고 데이터를 처리하는 API를 구현했습니다.' in revision
    assert '여러 화면을 설계하고 테스트' not in revision


def test_fallback_does_not_offer_answer_already_present_in_resume():
    from app.models import ConfirmationAnswer
    from app.resume_review import add_substantive_answer_fallback

    path = 'selfIntroduction.challenge.body'
    content = (
        '처리 단계별로 시간을 측정해 반복되는 서버 요청을 병목으로 확인했습니다. '
        '데이터를 한 번에 가져오고 결과를 캐시하도록 수정해 응답 시간을 '
        '220ms 정도까지 줄였습니다.'
    )
    answer = ConfirmationAnswer(
        field_path=path,
        question='직접 수행한 행동과 결과를 알려 주세요.',
        answer=content,
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[])

    add_substantive_answer_fallback(generated, {path: content}, [answer])

    assert generated.sentence_reviews == []


def test_appended_paragraph_that_repeats_existing_content_is_removed():
    from app.models import SentenceReview
    from app.resume_review import ground_sentences
    original = (
        '공고 검색에는 Pinecone 벡터 검색을 활용하고, 검색 결과를 원문 DB와 다시 대조해 텍스트 공고가 '
        '이미지 공고로 잘못 제외되지 않도록 보완했습니다. 선택한 공고의 회사명·직무명으로만 자리표시자를 '
        '치환해 잘못된 공고 제목 전체 삽입과 조사 오류를 방지했습니다.\n\n'
        '자기소개서 첨삭에서는 이력서에 없는 기술·경험·성과를 생성하지 않고, 근거가 부족하면 사용자에게 '
        '확인 질문을 반환하도록 설계했습니다.'
    )
    repeated_addition = (
        '공고 검색과 원문 대조를 테스트하며 이미지 공고와 원문 누락 공고를 구분해 근거 없는 첨삭을 '
        '막는 동작을 확인했습니다. 회사명·직무명 자리표시자가 공고 제목 전체로 잘못 치환되던 문제와 '
        '조사 오류를 수정했고, 사용자 답변 후에는 해당 프로젝트 항목만 재첨삭했습니다.'
    )
    generated = ResumeReviewGeneration(summary='', section_reviews=[], sentence_reviews=[
        SentenceReview(
            field_path='selfIntroduction.motivation.body', original_quote=original,
            reason='테스트 사례 보완', suggested_revision=f'{original}\n\n{repeated_addition}',
            evidence_quotes=[original],
        ),
    ])
    warnings = ground_sentences(
        {'selfIntroduction.motivation.body': original}, [], generated,
    )
    assert generated.sentence_reviews[0].suggested_revision is None
    assert 'duplicate_existing_content' in generated.sentence_reviews[0].validation_issues
    assert any('중복된 수정안' in warning for warning in warnings)


def test_revision_with_invented_number_is_removed() -> None:
    resume_text = render_resume_content(SAMPLE_CONTENT)
    generated = _generation({})
    generated.section_reviews[0].suggested_revision = "API 응답 시간을 50% 개선했습니다."

    grounded, warnings = enforce_resume_review_grounding(resume_text, generated)

    assert grounded.section_reviews[0].suggested_revision is None
    assert warnings
    assert grounded.confirmation_questions


def test_korean_section_label_is_normalized_and_questions_are_limited() -> None:
    resume_text = render_resume_content(SAMPLE_CONTENT)
    generated = ResumeReviewGeneration(
        summary="요약",
        section_reviews=[
            ResumeSectionReview(
                section_key="프로젝트",
                resume_quotes=["API 응답 시간을 20% 개선했습니다."],
                confirmation_questions=[f"질문 {index}" for index in range(5)],
            )
        ],
        confirmation_questions=[f"전체 질문 {index}" for index in range(35)],
    )

    grounded, warnings = enforce_resume_review_grounding(resume_text, generated)

    assert warnings == []
    assert grounded.section_reviews[0].section_key == "projects"
    assert len(grounded.section_reviews[0].confirmation_questions) == 3
    assert len(grounded.confirmation_questions) == 30


class EndpointService:
    def review(self, id_token: str, request: FirestoreResumeReviewRequest):
        return ResumeReviewService(
            Settings(openai_api_key="test"), FakeFirebase(), generator=_generation
        ).review(id_token, request)


def test_firestore_review_endpoint_requires_bearer_token() -> None:
    app.dependency_overrides[get_resume_review_service] = lambda: EndpointService()
    try:
        response = TestClient(app).post(
            "/api/v1/resumes/reviews",
            json={"cohort_id": "cohort-1", "resume_id": "resume-1"},
        )
    finally:
        app.dependency_overrides.pop(get_resume_review_service, None)

    assert response.status_code == 401


def test_firestore_review_endpoint_contract() -> None:
    app.dependency_overrides[get_resume_review_service] = lambda: EndpointService()
    try:
        response = TestClient(app).post(
            "/api/v1/resumes/reviews",
            headers={"Authorization": "Bearer valid-token"},
            json={"cohort_id": "cohort-1", "resume_id": "resume-1"},
        )
    finally:
        app.dependency_overrides.pop(get_resume_review_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["review_id"]
    assert body["resume_id"] == "resume-1"
    assert "원본 이력서는 변경하지 않았습니다" in body["notice"]
