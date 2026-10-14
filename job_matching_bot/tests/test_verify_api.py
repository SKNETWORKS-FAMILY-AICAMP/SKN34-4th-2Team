"""`/api/v1/jobs/verify` — 링크로 골라 온 공고 하나를 지금 열어 본다.

확인이 실패해도 오류로 막지 않는다(alive=None). 공고 맞춤 지원 화면은 저장소 상태로 판정한다.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from job_matching_bot.api import main


class _Liveness:
    def __init__(self, result):
        self.result = result
        self.asked: list[str] = []

    def verify(self, job_id: str):
        self.asked.append(job_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Service:
    def __init__(self, liveness):
        self.liveness = liveness


def _post(monkeypatch, result, body):
    liveness = _Liveness(result)
    monkeypatch.setattr(main, "_service", _Service(liveness))
    return TestClient(main.app).post("/api/v1/jobs/verify", json=body), liveness


def test_reports_what_the_page_says(monkeypatch):
    response, liveness = _post(monkeypatch, True, {"job_id": "SARAMIN-1"})
    assert response.status_code == 200
    assert response.json() == {"job_id": "SARAMIN-1", "alive": True}
    assert liveness.asked == ["SARAMIN-1"]


def test_check_failure_is_unknown_not_an_error(monkeypatch):
    response, _ = _post(monkeypatch, RuntimeError("blocked"), {"job_id": "SARAMIN-1"})
    assert response.status_code == 200
    assert response.json()["alive"] is None


def test_job_id_is_required(monkeypatch):
    response, liveness = _post(monkeypatch, True, {})
    assert response.status_code == 422
    assert liveness.asked == []
