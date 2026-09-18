"""Streamlit과 CLI가 함께 쓰는 Luna A/B 실행기."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Sequence

from chatbot.student_chatbot import StudentContextLoader
from chatbot_lab.bot import ImprovedPromptLunaChatbot, OriginalPromptLunaChatbot
from chatbot_lab.mock_firebase import load_mock_student_context


def create_pair(
    student_context_loader: StudentContextLoader = load_mock_student_context,
) -> tuple[OriginalPromptLunaChatbot, ImprovedPromptLunaChatbot]:
    return (
        OriginalPromptLunaChatbot(student_context_loader=student_context_loader),
        ImprovedPromptLunaChatbot(student_context_loader=student_context_loader),
    )


def _run_one(
    bot: OriginalPromptLunaChatbot | ImprovedPromptLunaChatbot,
    *,
    question: str,
    thread_id: str,
    cohort: str,
    history: Sequence[dict[str, str]],
    supervisor_only: bool,
    student_uid: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    if supervisor_only:
        result = bot.classify_debug(question, cohort=cohort, history=history)
        result["answer"] = "Supervisor만 평가하여 답변과 Pinecone 검색은 실행하지 않았습니다."
        result["sources"] = []
    else:
        result = bot.invoke_debug(
            {
                "question": question,
                "thread_id": thread_id,
                "cohort": cohort,
                "student_uid": student_uid,
            }
        )
    result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    result["variant"] = bot.variant_name
    return result


def compare(
    pair: tuple[OriginalPromptLunaChatbot, ImprovedPromptLunaChatbot],
    *,
    question: str,
    thread_id: str,
    cohort: str = "",
    left_history: Sequence[dict[str, str]] = (),
    right_history: Sequence[dict[str, str]] = (),
    supervisor_only: bool = True,
    student_uid: str = "mock-student-001",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """같은 입력을 독립 checkpointer를 가진 두 Luna 챗봇에 동시에 보낸다."""
    left, right = pair
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _run_one,
                bot=bot,
                question=question,
                thread_id=f"{thread_id}.{suffix}",
                cohort=cohort,
                history=history,
                supervisor_only=supervisor_only,
                student_uid=student_uid,
            )
            for bot, suffix, history in (
                (left, "original", left_history),
                (right, "improved", right_history),
            )
        ]
        return futures[0].result(), futures[1].result()
