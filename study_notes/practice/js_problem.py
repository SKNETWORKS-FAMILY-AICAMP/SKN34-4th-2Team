"""JS 코드 문제 — 종류는 파이썬 코드 문제와 같고(code_output · code_blank · code_fix · code_write · code_scratch)
packages 가 ["js"] 다. 출제 검증은 Node vm(practice_verifier/js.mjs), 학생 채점은 브라우저 Web Worker(jsRunner.ts).

- 테스트는 assert(조건, '문장'); 한 줄에 하나. assert 는 실행 환경이 준다.
- 코드와 테스트는 한 스크립트로 이어 돈다 — const/let 으로 만든 함수를 테스트가 볼 수 있다.
- 핵심 JS 만(자료형 · 연산자 · 스코프 · 함수 · 배열 · 객체). 페이지를 다루는 수업(DOM)은 web_task + <script>(web_problem.py).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from study_notes.practice.runner import Job

if TYPE_CHECKING:
    from study_notes.practice.models import PracticeProblem

JS_MARK = ["js"]
MIN_TESTS = 2
SCRATCH_MIN_LINES = 4
SCRATCH_MIN_TESTS = 3
# 채점 환경에 없는 것 — 쓰면 출제 때나 학생 브라우저에서 결과가 달라진다
BLOCKED = re.compile(
    r"\b(require|import|process|fetch|XMLHttpRequest|setTimeout|setInterval|document|window|localStorage|"
    r"eval|Function|Date\.now|Math\.random|prompt|alert)\b"
)
FUNCTION_NAME = re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)|\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:function|\()")


def is_js(problem: PracticeProblem) -> bool:
    return problem.packages == JS_MARK


def static_check(problem: PracticeProblem) -> str:
    """실행 전에 거를 이유. 비어 있으면 통과."""
    codes = [problem.starter_code] if problem.kind != "code_blank" else []
    if problem.kind != "code_output":
        codes += [problem.reference_solution, problem.hidden_tests]
    for code in codes:
        found = BLOCKED.search(code)
        if found:
            return f"채점 환경에 없는 것: {found.group(0)}"
    if problem.kind == "code_output":
        return ""
    if problem.hidden_tests.count("assert(") < MIN_TESTS:
        return f"테스트가 assert( {MIN_TESTS}개 미만"
    if problem.kind == "code_scratch":
        names = [a or b for a, b in FUNCTION_NAME.findall(problem.starter_code)]
        if not names:
            return "뼈대에 함수 정의가 없음"
        missing = [n for n in names if n not in problem.prompt]
        if missing:
            return f"문제 문장에 함수 이름이 없음: {', '.join(missing)} (학생은 뼈대를 못 봄)"
        body = [line for line in problem.reference_solution.splitlines() if line.strip() and not line.strip().startswith("//")]
        if len(body) < SCRATCH_MIN_LINES:
            return f"모범답안이 {len(body)}줄로 짧음 (처음부터 짤 거리가 아님)"
        if problem.hidden_tests.count("assert(") < SCRATCH_MIN_TESTS:
            return f"테스트가 assert( {SCRATCH_MIN_TESTS}개 미만"
    return ""


def jobs_for(key: str, problem: PracticeProblem, timeout_ms: int) -> list[Job]:
    """verify._jobs_for 와 같은 이름의 작업 — 판정(_judge_output · _judge_tests)을 그대로 쓴다"""
    from study_notes.practice.models import fill_blanks

    if problem.kind == "code_output":
        return [Job(f"{key}:run1", [problem.starter_code], timeout_ms, kind="js"),
                Job(f"{key}:run2", [problem.starter_code], timeout_ms, kind="js")]
    starter = problem.starter_code
    if problem.kind == "code_blank":
        # 아무 값이나 넣어도 통과하는 테스트인지 본다
        starter = fill_blanks(starter, ["null"] * len(problem.blank_answers))
    return [Job(f"{key}:starter", [starter, problem.hidden_tests], timeout_ms, kind="js"),
            Job(f"{key}:reference", [problem.reference_solution, problem.hidden_tests], timeout_ms, kind="js")]
