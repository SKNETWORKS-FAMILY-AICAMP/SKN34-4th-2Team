from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app, get_context_gateway, get_resume_review_service
from app.matching_handoff import load_selected_job
from job_matching_bot.env import ensure_loaded
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from app.models import FirestoreResumeReviewRequest, ResumeReviewGeneration, ReviewQuestion, SentenceReview
from app.resume_review import ResumeReviewService
from app.review_workflow import ReviewConflict, ReviewInputError, apply_selected_job_identity_revisions, digest, job_role_title
from test_resume_review import FakeFirebase, SAMPLE_CONTENT


@pytest.fixture
def store(tmp_path):
    # 경로마다 다른 스키마가 잡혀 테스트끼리 섞이지 않는다(sqlite_store._schema_for_path)
    ensure_loaded()
    path = tmp_path / 'jobs.sqlite'
    with open_store(path) as db:
        db.execute('DELETE FROM jobs')
        # first_seen_at · last_seen_at 은 Postgres 표에서 필수다(수집 시각)
        seen = datetime.now(timezone.utc)
        db.execute(
            '''INSERT INTO jobs (job_id, status, description, company, title, deadline,
                   body_is_image, content_hash, source_url, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            ('saramin:1', 'OPEN', 'Python API 개발 경험\n' + '공고 원문 전체 ' * 250,
             '테스트 회사', '백엔드', None, False, 'hash1', 'https://example.com/job', seen, seen))
    return path


@contextmanager
def open_store(path):
    """임시 경로에 딸린 격리 스키마를 열어 준다. 예전 `sqlite3.connect(path)` 자리."""
    store = SqliteJobStore(Path(path))
    try:
        yield store.conn
    finally:
        store.close()


def test_reads_full_text_and_rejects_unknown_job(store, tmp_path):
    assert len(load_selected_job(store, 'saramin:1')['text']) > 1200
    # 저장소가 비어 있거나 그 공고가 없으면 「못 찾았다」로 막는다. 예전에는 sqlite 파일이
    # 없다는 뜻이었지만, 이제 저장소는 Postgres 스키마라 파일 유무가 조건이 아니다.
    with pytest.raises(ReviewInputError): load_selected_job(tmp_path / 'other.sqlite', 'saramin:1')
    with pytest.raises(ReviewInputError): load_selected_job(store, "' OR 1=1 --")


def test_legacy_company_ui_noise_is_not_handed_to_review(store):
    with open_store(store) as db:
        db.execute("UPDATE jobs SET company = ?", ("(주)엣지크로스 관심기업 등록",))
    selected = load_selected_job(store, 'saramin:1')
    assert selected['source']['company'] == '(주)엣지크로스'
    assert '회사: (주)엣지크로스\n' in selected['text']
    assert '관심기업 등록' not in selected['text']


@pytest.mark.parametrize('field,value,error', [
    ('status', 'CLOSED', ReviewConflict), ('deadline', '2020-01-01', ReviewConflict),
    ('deadline', '알 수 없음', ReviewInputError), ('description', '', ReviewInputError),
])
def test_unusable_jobs_fail_closed(store, field, value, error):
    with open_store(store) as db: db.execute(f'UPDATE jobs SET {field} = ?', (value,))
    with pytest.raises(error): load_selected_job(store, 'saramin:1')


def test_legacy_image_flag_with_text_detail_is_reviewable(store):
    """본문이 충분히 저장된 구 레코드는 이미지 플래그를 보정한다."""
    with open_store(store) as db:
        db.execute('UPDATE jobs SET body_is_image = true')
    assert 'Python API 개발 경험' in load_selected_job(store, 'saramin:1')['text']


def test_image_only_detail_still_fails_closed(store):
    with open_store(store) as db:
        db.execute('UPDATE jobs SET description = ?, body_is_image = true', ('상세요강 자격요건',))
    with pytest.raises(ReviewInputError):
        load_selected_job(store, 'saramin:1')


def test_handoff_auth_versions_and_full_source(store):
    db, calls = FakeFirebase(), []
    def generate(data):
        calls.append(data)
        return ResumeReviewGeneration(summary='검토', section_reviews=[])
    service = ResumeReviewService(Settings(openai_api_key='test', matching_job_store_path=store), db, generate)
    request = FirestoreResumeReviewRequest(cohort_id='cohort-1', resume_id='resume-1', selected_job_id='saramin:1',
        expected_input_hash=digest(SAMPLE_CONTENT), expected_job_hash=load_selected_job(store, 'saramin:1')['source']['snapshot_hash'])
    result = service.review('valid-token', request)
    assert len(calls[0]['job_posting_text']) > 1200
    assert '[선택 공고 식별 정보' in calls[0]['job_posting_text']
    assert '회사명: 테스트 회사' in calls[0]['job_posting_text']
    assert '직무명: 백엔드' in calls[0]['job_posting_text']
    assert result.job_source['job_id'] == 'saramin:1'
    assert db.saved['job_source'] == result.job_source
    assert service.review('valid-token', request) == result
    assert len(calls) == 1
    with pytest.raises(ReviewConflict):
        service.review('valid-token', request.model_copy(update={'expected_input_hash': 'stale'}))
    with pytest.raises(ReviewInputError):
        service.review('valid-token', request.model_copy(update={'job_posting_text': 'client fake'}))
    with open_store(store) as connection:
        connection.execute("UPDATE jobs SET description = '수정된 공고'")
    with pytest.raises(ReviewConflict):
        service.review('valid-token', request)
    assert len(calls) == 1


def test_selected_job_identity_replaces_resume_placeholders_without_question():
    generated = ResumeReviewGeneration(
        summary='',
        section_reviews=[],
        questions=[ReviewQuestion(
            field_path='selfIntroduction.aspiration.body',
            topic='other',
            question='지원 회사명과 직무명을 실제 값으로 확정해 주세요.',
            reason='자리표시자',
        )],
    )
    fields = {
        'selfIntroduction.aspiration.body': '[회사명]의 [직무명]으로 성장하고 싶습니다.',
    }
    apply_selected_job_identity_revisions(
        generated,
        fields,
        {'company': '테스트 회사', 'title': '백엔드 개발자'},
    )
    assert generated.questions == []
    assert generated.sentence_reviews[0].suggested_revision == '테스트 회사의 백엔드 개발자로 성장하고 싶습니다.'


def test_posting_title_is_reduced_to_resume_role_title():
    assert job_role_title(
        '(주)토마토에이아이',
        '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
    ) == 'AI 엔지니어'
    assert job_role_title(
        '(주)디더블유아이',
        '(주)디더블유아이에서 AI 분석 서비스 개발자 모십니다',
    ) == 'AI 분석 서비스 개발자'


def test_identity_placeholder_uses_role_title_not_full_posting_title():
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.aspiration.body': '[회사명]의 [직무명]으로 성장하고 싶습니다.'},
        {
            'company': '(주)토마토에이아이',
            'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
        },
    )
    assert generated.sentence_reviews[0].suggested_revision == (
        '(주)토마토에이아이의 AI 엔지니어로 성장하고 싶습니다.'
    )


def test_job_subject_placeholder_uses_natural_role_particle():
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': '[회사명]의 [직무명]은 제가 학습해 온 방향과 맞닿아 있습니다.'},
        {'company': '(주)토마토에이아이', 'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요'},
    )
    assert generated.sentence_reviews[0].suggested_revision == (
        '(주)토마토에이아이의 AI 엔지니어 직무는 제가 학습해 온 방향과 맞닿아 있습니다.'
    )


def test_tailored_resume_adds_safe_job_identity_without_placeholders():
    generated = ResumeReviewGeneration(
        summary='',
        section_reviews=[],
        sentence_reviews=[SentenceReview(
            field_path='selfIntroduction.motivation.body',
            original_quote='데이터로 사용자의 문제를 해결하고 싶습니다.',
            reason='표현 정리',
            suggested_revision='데이터를 활용해 사용자의 문제를 해결하고 싶습니다.',
            evidence_quotes=['데이터로 사용자의 문제를 해결하고 싶습니다.'],
        )],
    )
    original = '데이터로 사용자의 문제를 해결하고 싶습니다.'

    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': original},
        {
            'company': '(주)토마토에이아이',
            'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
        },
        insert_missing_identity=True,
    )

    assert len(generated.sentence_reviews) == 1
    assert generated.sentence_reviews[0].suggested_revision == (
        '(주)토마토에이아이의 AI 엔지니어 직무에 지원한 이유는 다음과 같습니다.\n'
        '데이터로 사용자의 문제를 해결하고 싶습니다.'
    )


def test_tailored_resume_weaves_identity_into_existing_application_sentence():
    """지원 사실만 적힌 마무리 문장이 있으면 문장을 더 붙이지 않고 그 안에 넣는다.

    앞에 독립 문장을 붙이면 "…지원한 이유는 다음과 같습니다. / …지원하게 되었습니다."처럼 지원
    얘기가 두 번 나와, 사용자가 다음 첨삭에서 합치는 수정안을 한 번 더 받아야 했다.
    """
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    original = '사람들이 매일 쓰는 서비스에 AI 기능을 넣는 일을 하고 싶어서 지원하게 되었습니다.'

    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': original},
        {
            'company': '(주)토마토에이아이',
            'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
        },
        insert_missing_identity=True,
    )

    assert len(generated.sentence_reviews) == 1
    # 회사명·직무명이 들어가 문장이 길어지므로 "싶어서"는 "싶어"로 줄인다. 그대로 두면 "-어서"와
    # "지원하게 되었습니다"가 둘 다 이유를 짚어 늘어진다.
    assert generated.sentence_reviews[0].suggested_revision == (
        '사람들이 매일 쓰는 서비스에 AI 기능을 넣는 일을 하고 싶어 '
        '(주)토마토에이아이의 AI 엔지니어 직무에 지원하게 되었습니다.'
    )


def _weave(original):
    """지원동기 한 칸만 주고 끼워 넣은 결과를 돌려준다. 어미 줄이기를 여러 경우로 보려는 것이다."""
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': original},
        {'company': '테스트 회사', 'title': '백엔드 개발자'},
        insert_missing_identity=True,
    )
    return generated.sentence_reviews[0].suggested_revision


@pytest.mark.parametrize('original,head', [
    ('회사가 가는 방향이 제 관심과 맞아서 지원했습니다.', '회사가 가는 방향이 제 관심과 맞아'),
    ('사용자 경험을 개선하기 위해서 지원했습니다.', '사용자 경험을 개선하기 위해'),
    ('새로운 기술을 배워서 지원했습니다.', '새로운 기술을 배워'),
    ('직접 만들어서 지원했습니다.', '직접 만들어'),
])
def test_causal_ending_is_shortened_when_weaving(original, head):
    """이유를 잇는 "-아서/어서"는 "-아/어"로 줄인다. 회사명·직무명이 들어가 문장이 길어지기 때문이다."""
    assert _weave(original) == f'{head} 테스트 회사의 백엔드 개발자 직무에 지원했습니다.'


@pytest.mark.parametrize('original,head', [
    # 접속부사. 조건에는 걸리지만 "서"를 떼면 말이 안 된다.
    ('그래서 지원했습니다.', '그래서'),
    ('팀 문화가 좋다고 들었고 따라서 지원했습니다.', '팀 문화가 좋다고 들었고 따라서'),
    # 조사 "에서"(ㅔ), 연결어미 "-면서"(받침 있음), "로서"(ㅗ)는 애초에 조건에 걸리지 않는다.
    ('여러 회사에서 지원했습니다.', '여러 회사에서'),
    ('학교를 다니면서 지원했습니다.', '학교를 다니면서'),
    ('한 사람의 개발자로서 지원했습니다.', '한 사람의 개발자로서'),
])
def test_endings_that_must_not_be_shortened_are_left_alone(original, head):
    """"서"로 끝난다고 다 떼면 뜻이 바뀌거나 말이 망가지는 것들."""
    assert _weave(original) == f'{head} 테스트 회사의 백엔드 개발자 직무에 지원했습니다.'


def test_identity_is_not_woven_when_role_is_already_written():
    """직무명이 이미 적힌 문장에 또 넣으면 같은 말이 두 번 나온다. 그때는 독립 문장을 앞에 붙인다."""
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    original = 'AI 엔지니어로 성장하고 싶어 지원합니다.'

    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': original},
        {
            'company': '(주)토마토에이아이',
            'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
        },
        insert_missing_identity=True,
    )

    assert generated.sentence_reviews[0].suggested_revision == (
        '(주)토마토에이아이의 AI 엔지니어 직무에 지원한 이유는 다음과 같습니다.\n'
        + original
    )


def test_identity_is_not_inserted_without_explicit_tailored_resume_rule():
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': '데이터로 문제를 해결하고 싶습니다.'},
        {'company': '테스트 회사', 'title': '백엔드 개발자'},
    )
    assert generated.sentence_reviews == []


def test_identity_is_inserted_only_once_when_already_written():
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    original = '테스트 회사의 백엔드 개발자 직무에 지원합니다.'
    apply_selected_job_identity_revisions(
        generated,
        {'selfIntroduction.motivation.body': original},
        {'company': '테스트 회사', 'title': '백엔드 개발자'},
        insert_missing_identity=True,
    )
    assert generated.sentence_reviews == []


def test_previously_applied_full_posting_title_is_repaired():
    generated = ResumeReviewGeneration(summary='', section_reviews=[])
    apply_selected_job_identity_revisions(
        generated,
        {
            'selfIntroduction.aspiration.body': (
                '(주)토마토에이아이의 (주)토마토에이아이와 함께할 '
                'AI엔지니어를 찾고 있어요로 성장하고 싶습니다.'
            ),
        },
        {
            'company': '(주)토마토에이아이',
            'title': '(주)토마토에이아이와 함께할 AI엔지니어를 찾고 있어요',
        },
    )
    assert generated.sentence_reviews[0].suggested_revision == (
        '(주)토마토에이아이의 AI 엔지니어로 성장하고 싶습니다.'
    )


def test_context_requires_owner_and_disables_cache(store):
    app.dependency_overrides[get_context_gateway] = lambda: FakeFirebase()
    app.dependency_overrides[get_settings] = lambda: Settings(matching_job_store_path=store)
    client = TestClient(app)
    params = {'cohort_id': 'cohort-1', 'resume_id': 'resume-1'}
    try:
        assert client.get('/api/v1/resumes/review-context', params=params).status_code == 401
        ok = client.get('/api/v1/resumes/review-context', params=params, headers={'Authorization': 'Bearer valid-token'})
        assert ok.status_code == 200
        assert ok.headers['cache-control'] == 'no-store'
        assert ok.json()['input_hash'] == digest(SAMPLE_CONTENT)
        selected = client.get('/api/v1/resumes/review-context', params={**params, 'job_id': 'saramin:1'}, headers={'Authorization': 'Bearer valid-token'})
        assert selected.status_code == 200
        assert selected.json()['job_source']['job_id'] == 'saramin:1'
        foreign = client.get('/api/v1/resumes/review-context', params={**params, 'resume_id': 'another'}, headers={'Authorization': 'Bearer valid-token'})
        assert foreign.status_code == 404
    finally: app.dependency_overrides.clear()


def test_integrated_routes_preserve_matching_contract():
    from app.integrated import app as integrated
    client = TestClient(integrated)
    matching = client.get('/openapi.json').json()
    review = client.get('/resume-review/openapi.json').json()
    assert '/api/v1/jobs/recommend' in matching['paths']
    assert 'RecommendRequest' in matching['components']['schemas']
    assert '/api/v1/resumes/reviews' in review['paths']
    assert '/api/v1/resumes/reviews/apply' in review['paths']
    assert client.post('/api/v1/jobs/recommend', json={}).status_code == 422
