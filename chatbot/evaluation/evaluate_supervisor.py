"""저장된 분류 기대값과 현재 운영 supervisor를 비교한다.

명시적으로 실행할 때에만 OpenAI API를 호출한다. DB에는 기록하지 않는다.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from chatbot.ops_log import supervisor_model_name
from chatbot.student_chatbot import (
    SUPERVISOR_PROMPT,
    RoutingGuardrailMiddleware,
    SupervisorDecision,
    SupervisorGuardrailMiddleware,
)

DEFAULT_CASES = Path(__file__).with_name("eval_cases.json")


def matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    return (
        actual.get("route") == expected["route"]
        and set(actual.get("namespaces", [])) == set(expected["namespaces"])
        and set(actual.get("student_scopes", [])) == set(expected["student_scopes"])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="운영 학생 챗봇 supervisor 분류 평가")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path, help="상세 결과를 저장할 로컬 JSON 경로")
    args = parser.parse_args()

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    model = supervisor_model_name()
    llm = ChatOpenAI(model=model, max_retries=2)
    chain = (
        ChatPromptTemplate.from_messages([
            ("system", SUPERVISOR_PROMPT),
            MessagesPlaceholder("messages"),
        ])
        | llm.with_structured_output(SupervisorDecision)
    )
    middleware = RoutingGuardrailMiddleware(SupervisorGuardrailMiddleware())
    results = []
    for case in cases:
        started = time.perf_counter()
        decision = middleware.invoke(
            {"messages": [HumanMessage(content=case["question"])]}, chain,
        )
        actual = decision.model_dump()
        row = {
            "id": case["id"],
            "passed": matches(actual, case),
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "expected": {key: case[key] for key in ("route", "namespaces", "student_scopes")},
            "actual": actual,
        }
        results.append(row)
        print(f'{case["id"]}: {"PASS" if row["passed"] else "FAIL"} ({row["elapsed_ms"]} ms)')

    summary = {
        "model": model,
        "total": len(results),
        "passed": sum(row["passed"] for row in results),
        "failed_ids": [row["id"] for row in results if not row["passed"]],
    }
    print(json.dumps(summary, ensure_ascii=False))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps({"summary": summary, "cases": results}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
