"""Production entrypoint selection; reuse the scripted pipeline, never external I/O."""
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main, resume_apply, resume_review_runtime
from app.config import Settings
from app.firebase_gateway import FirebaseAuthenticationError
from app.review_runtime_factory import build_review_gateway, build_review_service
from test_project_live_pipeline import pipeline, post
from test_stage_checkpoints import staged


# The B entrypoint temporarily replaces this function when its fixture imports it.
production_service_factory = main.build_resume_review_service


def settings(**overrides):
    return Settings(_env_file=None, openai_api_key='test-only',
                    firebase_project_id=None, resume_review_engine='v2', **overrides)


def test_production_gateway_is_lazy_and_shared_by_context_and_apply(monkeypatch):
    configured = settings()
    monkeypatch.setattr(main, 'get_settings', lambda: configured)
    monkeypatch.setattr(resume_apply, 'get_settings', lambda: configured)
    initialize = Mock(side_effect=AssertionError('must not initialize Firebase for Django proxy'))
    monkeypatch.setattr(resume_review_runtime.PostgresReviewGateway, '_initialize_app', initialize)
    for gateway in (build_review_gateway(configured), main.get_context_gateway(), resume_apply.gateway_dependency()):
        assert isinstance(gateway, resume_review_runtime.PostgresReviewGateway)
        assert gateway.supports_stage_checkpoints is True
        with pytest.raises(FirebaseAuthenticationError):
            gateway.verify_id_token('untrusted')
    initialize.assert_not_called()
    assert isinstance(build_review_service(configured), resume_review_runtime.ResumeReviewV2Service)


def test_b_mode_retains_local_database_guard(monkeypatch):
    monkeypatch.setenv('RESUME_REVIEW_ENGINE', 'v2-local')
    monkeypatch.setenv('DB_HOST', 'database.example.invalid')
    configured = settings().model_copy(update={'resume_review_engine': 'v2-local'})
    with pytest.raises(RuntimeError):
        build_review_gateway(configured)


def test_integrated_route_uses_production_factory_and_resumes_checkpoint(pipeline, monkeypatch):
    _, reviews, calls, db = pipeline
    staged(db, reviews)
    configured = settings(openai_model='fake', openai_reasoning_effort='medium')
    monkeypatch.setattr(main, 'get_settings', lambda: configured)
    monkeypatch.setattr(main, 'build_resume_review_service', production_service_factory)
    monkeypatch.setattr(resume_review_runtime, 'PostgresReviewGateway', lambda settings: db)
    from app.integrated import app
    client = TestClient(app)
    states = [post(client, 'production-initial')['telemetry']['execution']['state'] for _ in range(3)]
    assert states == ['processing', 'verification_pending', 'verified']
    post(client, 'production-initial')
    assert [stage for stage, _, _ in calls] == ['BatchExtractionOutput', 'BatchWriterDraft', 'BatchFactVerification']
    assert reviews['production-initial']['telemetry']['answer_edit_supported'] is True


def test_requirements_reuse_cache_and_bound_cold_extraction(monkeypatch):
    from app import job_requirements
    service = resume_review_runtime.ResumeReviewV2Service(settings(), Mock())
    loader = Mock(return_value=['cached'])
    extractor = Mock(return_value=object())
    monkeypatch.setattr(job_requirements, 'load_or_extract_requirements', loader)
    monkeypatch.setattr(job_requirements, 'build_requirement_extractor', extractor)
    job = {'text': 'posting', 'source': {'job_id': '1'}}
    assert service.load_requirements(job) == ['cached']
    extractor.assert_not_called()
    loader.side_effect = [[], ['extracted']]
    assert service.load_requirements(job) == ['extracted']
    extractor.assert_called_once_with(service.settings, timeout=45)
