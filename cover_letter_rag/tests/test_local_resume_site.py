from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from app.local_resume_site_adapter import LocalReviewService, require_local, targets, experience_sources
from app.models import FirestoreResumeReviewRequest
from app.review_workflow import digest, ReviewConflict
from app.resume_review_v2.models import (
    Experience, ReviewResult, RevisionPlan, RevisionCandidate, RevisionSentence,
    ValidationResult, Usage, Evidence, FactType, AssertionState,
)
from app.resume_apply import ApplyRequest, build_application


@pytest.fixture(autouse=True)
def local(monkeypatch):
    monkeypatch.setenv('DB_HOST', '127.0.0.1')
    monkeypatch.setenv('RESUME_REVIEW_ENGINE', 'v2-local')


def setup_service(status='READY'):
    content = {'projects': [{'id': 'p1', 'name': '테스트', 'description': 'API를 구현했습니다.'}]}
    db = Mock()
    db.get_owned_resume.return_value = {'content': content}
    db.claim_review.return_value = {}
    db.get_ai_review.return_value = {}
    def run(request):
        ev = Evidence(evidence_id='e1', experience_id=request.experience.experience_id,
            fact_type=FactType.ACTION, normalized_fact='API 구현', evidence_quote='API를 구현했습니다.',
            source_type='resume_text', source_id=request.experience.experience_id,
            assertion_state=AssertionState.RESUME_STATED)
        validation = ValidationResult(status=status)
        return ReviewResult(experience=request.experience, question='', answer='',
            extracted_evidence=[ev], selected_evidence=[ev], omitted_evidence=[],
            plan=RevisionPlan(objective='기여 명확화', operation='replace_field', core_evidence_ids=['e1']),
            proposed_question=None, candidate=RevisionCandidate(experience_id=request.experience.experience_id,
                field_path=request.experience.field_path, content_hash=request.experience.content_hash,
                original_quote=request.experience.current_text, suggested_text='API 구현을 담당했습니다.',
                sentences=[RevisionSentence(text='API 구현을 담당했습니다.', evidence_ids=['e1'])], validation=validation),
            validation=validation, usage=Usage(calls=3))
    engine = Mock(run_many=Mock(side_effect=lambda requests: [run(r) for r in requests]))
    settings = SimpleNamespace(openai_model='test-model', openai_reasoning_effort='medium')
    service = LocalReviewService(settings, db, engine)
    request = FirestoreResumeReviewRequest(cohort_id='local', resume_id='1', review_mode='general', request_id='review1')
    return service, db, engine, request, content


def test_cloud_db_refused(monkeypatch):
    monkeypatch.setenv('DB_HOST', 'example.rds.amazonaws.com')
    with pytest.raises(RuntimeError): require_local()


def test_v1_mode_refused(monkeypatch):
    monkeypatch.setenv('RESUME_REVIEW_ENGINE', 'v1')
    with pytest.raises(RuntimeError): require_local()


def test_regular_response_and_apply_contract():
    service, db, engine, request, content = setup_service()
    response = service.review_as('student', request)
    assert response.telemetry['engine'] == 'v2-local-ui-2'
    assert response.input_hash == digest(content)
    assert engine.run_many.call_args.args[0][0].experience.experience_id == 'projects:p1'
    assert db.complete_review.call_count == 1
    after, changed = build_application(content, response.model_dump(), ApplyRequest(
        cohort_id='local', resume_id='1', request_id='apply1', review_id='review1',
        expected_input_hash=response.input_hash, selected_indices=[0]))
    assert after['projects'][0]['description'] == 'API 구현을 담당했습니다.'
    assert content['projects'][0]['description'] == 'API를 구현했습니다.'


@pytest.mark.parametrize('status', ['REJECTED', 'UNCHANGED', 'NEEDS_EVIDENCE'])
def test_rejected_candidate_not_applyable(status):
    service, _, _, request, _ = setup_service(status)
    assert service.review_as('student', request).sentence_reviews[0].suggested_revision is None


def test_initial_candidates_returned_together_without_edit_type_relabeling():
    service, db, engine, request, content = setup_service()
    content['projects'].extend([
        {'id': 'p2', 'name': '두 번째', 'description': 'API를 구현했습니다.'},
        {'id': 'p3', 'name': '세 번째', 'description': 'API를 구현했습니다.'},
    ])
    response = service.review_as('student', request)
    assert len(response.sentence_reviews) == 3
    assert all(item.validation_status == 'READY' for item in response.sentence_reviews)
    assert all(item.edit_type == 'content' for item in response.sentence_reviews)
    assert all(item.suggested_revision for item in response.sentence_reviews)
    assert engine.run_many.call_count == 1
    assert db.complete_review.call_count == 1


def test_request_replay_no_model_call():
    service, db, engine, request, _ = setup_service()
    response = service.review_as('student', request)
    db.claim_review.return_value = {'response': response.model_dump()}
    engine.reset_mock()
    assert service.review_as('student', request).review_id == request.request_id
    engine.run_many.assert_not_called()


def test_stale_content_no_model_call():
    service, _, engine, request, _ = setup_service()
    request.expected_input_hash = 'stale'
    with pytest.raises(ReviewConflict): service.review_as('student', request)
    engine.run_many.assert_not_called()


def test_failure_claim_marked_not_silently_retried():
    service, db, engine, request, _ = setup_service()
    engine.run_many.side_effect = RuntimeError('model unavailable')
    with pytest.raises(RuntimeError): service.review_as('student', request)
    db.fail_review.assert_called_once()
    assert engine.run_many.call_count == 1


def test_targets_do_not_edit_identity_or_technology_fields():
    rows = targets({'projects[0].name': 'title', 'projects[0].description': 'action', 'projects[0].techStack': 'Python'})
    assert len(rows) == 1
    assert next(iter(rows.values()))[0] == 'projects[0].description'


def test_training_course_label_preserves_identity_and_owning_sources():
    identity = 'trainingExperience:training-one'
    content = {'trainingExperience': [{'id': 'training-one',
        'course': '교육 과정 이름', 'description': 'API를 구현했습니다.'}]}
    label, sources = experience_sources(content, 'trainingExperience[0].description', identity)
    assert label == '교육 과정 이름'
    assert next(iter(targets({'trainingExperience[0].description': 'API를 구현했습니다.'}).values()))[0] == 'trainingExperience[0].description'
    assert all(s.source_id.startswith(identity + ':') for s in sources)


def test_replayed_question_label_comes_from_current_resume_not_old_internal_id():
    from app.resume_review_v2.models import GapQuestion
    service, db, engine, request, content = setup_service()
    content.clear()
    content['trainingExperience'] = [{'id': 'training-one', 'course': '교육 과정 이름',
                                      'description': 'API를 구현했습니다.'}]
    old_run = engine.run_many.side_effect
    def with_question(inputs):
        results = old_run(inputs)
        result = results[0]
        owner = result.experience.experience_id
        result.experience.title = owner  # Old stored display mapping.
        result.gap_questions = [GapQuestion(experience_id=owner, experience_title=owner,
            question='실습에서 확인한 점은 무엇인가요?', gap_type='missing', target_slot='outcome',
            priority='MEDIUM', why_needed='실습 내용은 확인됐고 배운 점을 보완할 수 있습니다.',
            dedupe_key=owner + ':value:learning')]
        return results
    engine.run_many.side_effect = with_question
    response = service.review_as('student', request)
    assert response.questions[0].experience_id == 'trainingExperience:training-one'
    assert response.questions[0].experience_title == '교육 과정 이름'
