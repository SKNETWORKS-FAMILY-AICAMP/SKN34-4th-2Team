"""저장된 기대 결과와 supervisor 라우팅을 비교한다.

기본은 Luna 실험판만 호출한다. 운영 Sol은 `--production`을 명시할 때만 쓴다.
`--publish`는 질문 원문 없이 Firestore `aiEvalRuns` 1건을 남긴다.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from chatbot.ops_log import chatbot_prompt_version, supervisor_model_name
from chatbot.student_chatbot import (
    SUPERVISOR_PROMPT,
    RoutingGuardrailMiddleware,
    SupervisorDecision,
    SupervisorGuardrailMiddleware,
)
from chatbot_lab.bot import create_supervisor_harness
from chatbot_lab.eval_publish import build_eval_run_payload, write_eval_run

DEFAULT_CASES = Path(__file__).with_name("eval_cases.json")


def _decision(bot: Any, question: str) -> tuple[dict[str, Any], int]:
    started = time.perf_counter()
    result = bot.supervisor_middleware.invoke(
        {"messages": [HumanMessage(content=question)]},
        bot.supervisor_chain,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    return result.model_dump(), elapsed_ms


def _matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        actual.get("route") == expected["route"]
        and set(actual.get("namespaces", [])) == set(expected["namespaces"])
        and set(actual.get("student_scopes", [])) == set(expected["student_scopes"])
    )


def create_production_supervisor_harness() -> Any:
    """운영 `chatbot.student_chatbot` 프롬프트 + reconcile 기준으로 supervisor만 돈다."""
    model = supervisor_model_name()
    llm = ChatOpenAI(model=model, temperature=0, max_retries=2)
    chain = (
        ChatPromptTemplate.from_messages([
            ("system", SUPERVISOR_PROMPT),
            MessagesPlaceholder("messages"),
        ])
        | llm.with_structured_output(SupervisorDecision)
    )
    middleware = RoutingGuardrailMiddleware(SupervisorGuardrailMiddleware())
    return SimpleNamespace(
        supervisor_chain=chain,
        supervisor_middleware=middleware,
        model=model,
    )


def _publish_summary(
    *,
    prompt_version: str,
    model: str,
    rows: list[dict[str, Any]],
    variant: str,
) -> dict[str, Any]:
    passed_rows = [row for row in rows if row[variant]["passed"]]
    latencies = [int(row[variant]["elapsed_ms"]) for row in rows]
    avg = round(sum(latencies) / len(latencies)) if latencies else 0
    return build_eval_run_payload(
        prompt_version=prompt_version,
        model=model,
        total_cases=len(rows),
        passed=len(passed_rows),
        avg_latency_ms=avg,
        failed_ids=[row["id"] for row in rows if not row[variant]["passed"]],
        source="chatbot_lab",
    )


def _firebase_db() -> Any:
    import firebase_admin
    from firebase_admin import credentials, firestore

    try:
        app = firebase_admin.get_app()
    except ValueError:
        project_id = os.getenv("FIREBASE_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
        options = {"projectId": project_id} if project_id else None
        app = firebase_admin.initialize_app(credentials.ApplicationDefault(), options)
    return firestore.client(app=app)


def main() -> None:
    parser = argparse.ArgumentParser(description="학생 챗봇 라우팅 평가")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, default=Path("chatbot_lab/eval_result.json"))
    parser.add_argument(
        "--production",
        action="store_true",
        help="운영 chatbot supervisor+reconcile 기준으로 평가 (Sol 호출)",
    )
    parser.add_argument(
        "--publish",
        action="store_true",
        help="평가 요약을 Firestore aiEvalRuns에 기록 (질문 원문 제외)",
    )
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))

    if args.production:
        harness = create_production_supervisor_harness()
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = [
                (case, executor.submit(_decision, harness, case["question"]))
                for case in cases
            ]
        rows = []
        for case, future in pending:
            actual, elapsed_ms = future.result()
            rows.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "expected": {
                        key: case[key]
                        for key in ("route", "namespaces", "student_scopes")
                    },
                    "production": {
                        "decision": actual,
                        "elapsed_ms": elapsed_ms,
                        "passed": _matches(actual, case),
                    },
                }
            )
        summary = {
            "case_count": len(rows),
            "production_passed": sum(row["production"]["passed"] for row in rows),
        }
        publish_payload = _publish_summary(
            prompt_version=chatbot_prompt_version(),
            model=getattr(harness, "model", supervisor_model_name()),
            rows=rows,
            variant="production",
        )
    else:
        baseline = create_supervisor_harness(improved=False)
        candidate = create_supervisor_harness(improved=True)
        with ThreadPoolExecutor(max_workers=4) as executor:
            pending = [
                (
                    case,
                    executor.submit(_decision, baseline, case["question"]),
                    executor.submit(_decision, candidate, case["question"]),
                )
                for case in cases
            ]
        rows = []
        for case, original_future, candidate_future in pending:
            original, original_ms = original_future.result()
            luna, luna_ms = candidate_future.result()
            rows.append(
                {
                    "id": case["id"],
                    "question": case["question"],
                    "expected": {
                        key: case[key]
                        for key in ("route", "namespaces", "student_scopes")
                    },
                    "original_luna": {
                        "decision": original,
                        "elapsed_ms": original_ms,
                        "passed": _matches(original, case),
                    },
                    "luna_lab": {
                        "decision": luna,
                        "elapsed_ms": luna_ms,
                        "passed": _matches(luna, case),
                    },
                }
            )
        summary = {
            "case_count": len(rows),
            "original_luna_passed": sum(row["original_luna"]["passed"] for row in rows),
            "luna_lab_passed": sum(row["luna_lab"]["passed"] for row in rows),
        }
        publish_payload = _publish_summary(
            prompt_version="student_chatbot_lab",
            model="gpt-5.6-luna",
            rows=rows,
            variant="luna_lab",
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps({"summary": summary, "cases": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    print(f"상세 결과: {args.output}")

    if args.publish:
        run_id = write_eval_run(_firebase_db(), publish_payload)
        print(json.dumps({"published": run_id, **publish_payload}, ensure_ascii=False))


if __name__ == "__main__":
    main()
