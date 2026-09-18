"""학생 챗봇 관측 로그. 질문·답변 원문 없이 메타만 남긴다."""

from __future__ import annotations

import hashlib
import os
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

DEFAULT_PROMPT_VERSION = "student_chatbot_v2"
DEFAULT_SUPERVISOR_MODEL = "gpt-5.6-sol"


def chatbot_prompt_version() -> str:
    return (
        os.getenv("LMS_CHATBOT_PROMPT_VERSION", DEFAULT_PROMPT_VERSION).strip()
        or DEFAULT_PROMPT_VERSION
    )


def supervisor_model_name() -> str:
    return (
        os.getenv("LMS_SUPERVISOR_MODEL")
        or os.getenv("LMS_NODE_MODEL")
        or DEFAULT_SUPERVISOR_MODEL
    ).strip() or DEFAULT_SUPERVISOR_MODEL


def request_id_hash(thread_id: str) -> str:
    return hashlib.sha256(thread_id.encode("utf-8")).hexdigest()[:16]


def join_csv(values: Any) -> str:
    if values is None:
        return ""
    if isinstance(values, str):
        return values[:200]
    if isinstance(values, (list, tuple, set)):
        return ",".join(str(item) for item in values if item)[:200]
    return str(values)[:200]


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


def strip_forbidden(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if str(key).lower() not in FORBIDDEN_KEYS and value is not None
    }


def build_generation_log_payload(
    *,
    cohort_id: str,
    created_by: str,
    latency_ms: int,
    status: str,
    snapshot: dict[str, Any] | None = None,
    error_message: str | None = None,
    thread_id: str = "",
) -> dict[str, Any]:
    snap = snapshot or {}
    route = str(snap.get("route") or "")[:200]
    version = (
        str(snap.get("promptVersion") or snap.get("prompt_version") or "").strip()
        or chatbot_prompt_version()
    )[:80]
    model = str(snap.get("model") or "").strip()[:80] or "unknown"
    payload: dict[str, Any] = {
        "type": "student_chatbot",
        "promptVersion": version,
        "model": model,
        "cohortId": str(cohort_id)[:80],
        "latencyMs": max(0, int(latency_ms)),
        "status": "error" if status == "error" else "success",
        "generatedCount": 0 if status == "error" else 1,
        "createdBy": str(created_by)[:128],
        "route": route,
        "namespaces": join_csv(snap.get("namespaces")),
        "studentScopes": join_csv(
            snap.get("studentScopes") or snap.get("student_scopes"),
        ),
        "blocked": bool(snap.get("blocked")) or route == "blocked",
        "requestIdHash": str(
            snap.get("requestIdHash") or snap.get("request_id_hash") or request_id_hash(thread_id)
        )[:200],
    }
    retrieval_ms = snap.get("retrievalMs", snap.get("retrieval_ms"))
    llm_ms = snap.get("llmMs", snap.get("llm_ms"))
    if retrieval_ms is not None:
        payload["retrievalMs"] = max(0, int(retrieval_ms))
    if llm_ms is not None:
        payload["llmMs"] = max(0, int(llm_ms))
    token_in = snap.get("tokenIn", snap.get("token_in"))
    token_out = snap.get("tokenOut", snap.get("token_out"))
    if token_in is not None:
        payload["tokenIn"] = max(0, int(token_in))
    if token_out is not None:
        payload["tokenOut"] = max(0, int(token_out))
    if status == "error" and error_message:
        payload["errorMessage"] = str(error_message)[:500]
    clean = strip_forbidden(payload)
    assert_no_plaintext(clean)
    return clean


def build_done_event(log_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = {
        "type": "done",
        "ops": {
            "logId": log_id,
            "promptVersion": str(payload.get("promptVersion") or ""),
            "route": str(payload.get("route") or ""),
            "status": str(payload.get("status") or ""),
        },
    }
    assert_no_plaintext(event)
    return event


def write_generation_log(db: Any, payload: dict[str, Any]) -> str:
    from firebase_admin import firestore

    clean = strip_forbidden(payload)
    assert_no_plaintext(clean)
    ref = db.collection("aiGenerationLogs").document()
    clean["createdAt"] = firestore.SERVER_TIMESTAMP
    ref.set(clean)
    return ref.id
