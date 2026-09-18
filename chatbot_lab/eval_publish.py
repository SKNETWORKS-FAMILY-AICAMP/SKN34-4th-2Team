"""오프라인 supervisor 평가 요약을 Firestore에 올린다. 질문 원문은 포함하지 않는다."""

from __future__ import annotations

from typing import Any

FORBIDDEN_KEYS = {
    "question",
    "answer",
    "content",
    "messages",
    "page_content",
    "excerpt",
    "query",
}


def assert_no_plaintext(data: Any, path: str = "payload") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise ValueError(f"원문 키 금지: {path}.{key}")
            assert_no_plaintext(value, f"{path}.{key}")
        return
    if isinstance(data, list):
        for index, value in enumerate(data):
            assert_no_plaintext(value, f"{path}[{index}]")


def build_eval_run_payload(
    *,
    prompt_version: str,
    model: str,
    total_cases: int,
    passed: int,
    avg_latency_ms: int,
    failed_ids: list[str],
    source: str = "chatbot_lab",
) -> dict[str, Any]:
    accuracy = round(passed / total_cases, 4) if total_cases else 0.0
    payload: dict[str, Any] = {
        "promptVersion": (prompt_version or "student_chatbot_v2")[:80],
        "model": (model or "unknown")[:80],
        "totalCases": int(total_cases),
        "passed": int(passed),
        "accuracy": accuracy,
        "avgLatencyMs": max(0, int(avg_latency_ms)),
        "failedIds": [str(item)[:80] for item in failed_ids[:80]],
        "source": (source or "chatbot_lab")[:80],
    }
    assert_no_plaintext(payload)
    return payload


def write_eval_run(db: Any, payload: dict[str, Any]) -> str:
    from firebase_admin import firestore

    assert_no_plaintext(payload)
    ref = db.collection("aiEvalRuns").document()
    data = dict(payload)
    data["createdAt"] = firestore.SERVER_TIMESTAMP
    ref.set(data)
    return ref.id
