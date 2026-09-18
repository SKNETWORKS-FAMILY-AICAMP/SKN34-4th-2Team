"""LLMOps 관측용 프롬프트/모델 버전.

Flutter·Functions 로그의 promptVersion/model 과 맞춘다.
원문 로그는 남기지 않고 버전 문자열만 응답 메타로 내려보낸다.
"""

from __future__ import annotations

import os

JOB_CHAT_PROMPT_VERSION = os.environ.get("JOB_CHAT_PROMPT_VERSION", "job_chat_v1")
JOB_RECOMMEND_PROMPT_VERSION = os.environ.get(
    "JOB_RECOMMEND_PROMPT_VERSION", "job_recommend_v1"
)
RESUME_REVIEW_PROMPT_VERSION = os.environ.get(
    "RESUME_REVIEW_PROMPT_VERSION", "resume_review_v1"
)


def openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-5.6-luna")


def reasoning_effort() -> str:
    return os.environ.get("OPENAI_REASONING_EFFORT", "medium")
