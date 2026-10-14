import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_does_not_require_api_key() -> None:
    from app.config import Settings, get_settings
    settings = Settings(_env_file=None, openai_api_key=None)
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["model"] == settings.openai_model
    finally:
        app.dependency_overrides.pop(get_settings, None)


# 자기소개서 RAG 시절 API. 앱이 부르지 않아 걷어냈다(공고 추천은 job_matching_bot, 첨삭은 /api/v1/resumes/reviews).
@pytest.mark.parametrize('path', [
    '/api/v1/jobs/search', '/api/v1/profiles/analyze', '/api/v1/jobs/recommend', '/api/v1/jobs/compare',
    '/api/v1/reviews',
])
def test_legacy_cover_letter_endpoints_are_gone(path) -> None:
    assert client.post(path, json={}).status_code == 404
