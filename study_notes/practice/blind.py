"""문제만 보고 푼 풀이로 숨긴 테스트를 한 번 더 본다 — 테스트가 문제 문장에 없는 조건을 검사하는지.

verify.py 는 「모범답안은 통과, 시작 코드는 실패」만 본다. 그래서 모범답안에 맞춰 좁게 짠 테스트는 거르지 못한다.
2026-09-29 코드 문제 138개를 문제 문장 · 시작 코드만 주고 다시 풀게 하니 10개(7%)가 맞게 풀어도 떨어졌다
(문장에 없는 키 이름 · 형식 · 자료형, 수업 코드의 값 · 공식 외우기, 시작 코드 설명과 어긋난 테스트).

여기서는 모범답안 · 테스트 · 수업 자료를 보지 않은 LLM 이 학생처럼 푼다(하루치를 한 번에). 그 풀이가 테스트에서
떨어지면 이유와 풀이를 붙여 고치기(repair_drafts)로 보낸다. 풀이를 못 받은 문제는 판단하지 않고 그대로 둔다.
"""

from __future__ import annotations

import json
from typing import Protocol

from langchain_core.prompts import ChatPromptTemplate

from study_notes.pipeline import response_text
from study_notes.practice.generate import Usage, _llm
from study_notes.practice.models import PracticeProblem
from study_notes.practice.runner import Job, Runner
from study_notes.practice.verify import RUN_TIMEOUT_MS

BLIND_KINDS = ("code_blank", "code_fix", "code_write", "code_scratch")
MAX_SHOWN_SOLUTION = 1200

WHAT_TO_WRITE = {
    "code_blank": "빈칸(__1__ 등)을 채운 전체 코드",
    "code_fix": "버그를 고친 전체 코드",
    "code_write": "함수를 완성한 전체 코드",
    "code_scratch": "문제의 함수를 처음부터 작성한 전체 코드",
}

BLIND_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 파이썬을 배우는 부트캠프 학생입니다. 문제 문장과 시작 코드만 보고 풉니다.\n"
        "표준 라이브러리와 numpy, pandas만 씁니다. 응답은 JSON 객체 하나입니다.",
    ),
    (
        "human",
        "문제들:\n{problems}\n\n"
        '문제마다 code 에 무엇을 쓸지는 write 에 적혀 있습니다. 응답 형식: {{"solutions": [{{"index": 0, "code": "..."}}]}}',
    ),
])


class Solver(Protocol):
    def __call__(self, problems: list[PracticeProblem], usage: Usage) -> dict[int, str]: ...


def solve_blind(problems: list[PracticeProblem], usage: Usage) -> dict[int, str]:
    """{문제 번호: 풀이 코드}. 모범답안 · 테스트는 보여 주지 않는다. 처음부터 문제는 뼈대도 안 보인다(학생처럼)."""
    listing = [
        {"index": i, "write": WHAT_TO_WRITE[p.kind], "prompt": p.prompt,
         **({} if p.kind == "code_scratch" else {"starterCode": p.starter_code})}
        for i, p in enumerate(problems)
    ]
    response = (BLIND_PROMPT | _llm()).invoke({"problems": json.dumps(listing, ensure_ascii=False, indent=1)})
    usage.add(response)
    try:
        data = json.loads(response_text(response))
    except json.JSONDecodeError:
        return {}
    out: dict[int, str] = {}
    for item in data.get("solutions") or []:
        if isinstance(item, dict) and isinstance(item.get("index"), int) and isinstance(item.get("code"), str):
            out[item["index"]] = item["code"]
    return out


def blind_failures(problems: list[PracticeProblem], runner: Runner, usage: Usage,
                   solver: Solver = solve_blind) -> dict[int, str]:
    """{problems 안의 번호: 고치기에 넘길 이유}. 검증을 통과한 문제만 넘긴다. 대상이 아닌 종류는 보지 않는다."""
    targets = [(i, p) for i, p in enumerate(problems) if p.kind in BLIND_KINDS]
    if not targets:
        return {}
    solutions = solver([p for _, p in targets], usage)
    jobs = [Job(f"b{n}", [solutions[n], p.hidden_tests], RUN_TIMEOUT_MS)
            for n, (_i, p) in enumerate(targets) if solutions.get(n, "").strip()]
    results = runner.run(jobs)
    failures: dict[int, str] = {}
    for n, (i, _p) in enumerate(targets):
        result = results.get(f"b{n}")
        if result is None or result.ok:
            continue
        code = solutions[n][:MAX_SHOWN_SOLUTION]
        failures[i] = (
            f"문제 문장과 시작 코드만 보고 푼 다른 풀이가 숨긴 테스트에서 떨어짐 — {result.describe()}\n"
            f"그 풀이:\n{code}\n"
            "테스트가 문제에 적히지 않은 조건(키 이름 · 데이터 값 · 형식 · 자료형 · 수업 코드의 세부)을 요구하는지, "
            "시작 코드 설명과 테스트가 어긋나는지 보고 문제 문장에 필요한 정보를 적거나 테스트를 문제 문장에 맞게 고칠 것"
        )
    return failures
