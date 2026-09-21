"""초안을 실제로 실행해 통과시키거나 버린다.

규칙은 여기에만 있다. 실행기(runner)는 「코드를 돌려 결과를 준다」만 안다.

  code_output  시작 코드를 두 번 돌려 출력이 같아야 한다 → 그 출력이 정답
  code_blank   빈칸을 None으로 채우면 테스트 실패, 모범 답으로 채우면 통과
  code_fix     버그 코드 + 테스트는 실패, 모범답안 + 테스트는 통과
  code_write   빈 함수 + 테스트는 실패, 모범답안 + 테스트는 통과
  concept      실행하지 않는다 (models.parse_draft 가 모양만 본다)

실행 전에 ast로 한 번 거른다. 파일·네트워크·입력·현재 시각을 쓰는 코드는 브라우저에서
안 돌거나 매번 결과가 달라서, 돌려 보기 전에 버린다.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from study_notes.practice.models import RUNNABLE, PracticeProblem, fill_blanks
from study_notes.practice.runner import Job, RunResult, Runner

ALLOWED_THIRD_PARTY = {"numpy", "pandas"}
BLOCKED_MODULES = {
    "os", "sys", "subprocess", "socket", "shutil", "pathlib", "glob", "io",
    "urllib", "http", "requests", "threading", "multiprocessing", "asyncio",
    "ctypes", "importlib", "builtins", "js", "pyodide", "micropip",
}
BLOCKED_CALLS = {"open", "input", "exec", "eval", "compile", "__import__", "breakpoint"}
BLOCKED_ATTRS = {"now", "today", "utcnow", "time", "perf_counter", "sleep"}
STDLIB_HINT = {
    "collections", "itertools", "functools", "math", "statistics", "random", "re",
    "string", "json", "dataclasses", "typing", "heapq", "bisect", "datetime",
    "decimal", "fractions", "operator", "copy", "enum", "abc", "textwrap", "time",
}

MAX_OUTPUT_LINES = 4
MAX_OUTPUT_CHARS = 160
LONG_DECIMAL = re.compile(r"\d\.\d{4,}")
RUN_TIMEOUT_MS = 3000


@dataclass
class Verdict:
    problem: PracticeProblem
    passed: bool
    reason: str = ""


def static_check(code: str) -> tuple[list[str], str]:
    """(쓰는 패키지, 문제 이유). 이유가 비어 있으면 통과."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [], f"문법 오류 {exc.lineno}행: {exc.msg}"
    packages: set[str] = set()
    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules = [node.module]
        for module in modules:
            root = module.split(".")[0]
            if root in BLOCKED_MODULES:
                return [], f"쓸 수 없는 모듈: {root}"
            if root in ALLOWED_THIRD_PARTY:
                packages.add(root)
            elif root not in STDLIB_HINT:
                return [], f"허용하지 않은 모듈: {root}"
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in BLOCKED_CALLS:
                return [], f"쓸 수 없는 함수: {func.id}()"
            if isinstance(func, ast.Attribute) and func.attr in BLOCKED_ATTRS:
                return [], f"실행할 때마다 결과가 달라지는 호출: .{func.attr}()"
            if isinstance(func, ast.Attribute) and func.attr.startswith("read_") \
                    and func.attr != "read_json":
                return [], f"파일을 읽는 호출: .{func.attr}()"
    return sorted(packages), ""


def _clean_stdout(stdout: str) -> str:
    return "\n".join(line.rstrip() for line in stdout.strip("\n").splitlines())


def _jobs_for(index: int, problem: PracticeProblem) -> list[Job]:
    key = f"p{index}"
    if problem.kind == "code_output":
        return [
            Job(f"{key}:run1", [problem.starter_code], RUN_TIMEOUT_MS),
            Job(f"{key}:run2", [problem.starter_code], RUN_TIMEOUT_MS),
        ]
    # 버그 코드가 무한 루프일 수 있다. 그 경우 시간 제한에 걸리는 것이 「실패」다.
    starter = problem.starter_code
    if problem.kind == "code_blank":
        # 아무 값이나 넣어도 통과하는 테스트인지 본다.
        starter = fill_blanks(starter, ["None"] * len(problem.blank_answers))
    return [
        Job(f"{key}:starter", [starter, problem.hidden_tests], RUN_TIMEOUT_MS),
        Job(f"{key}:reference", [problem.reference_solution, problem.hidden_tests], RUN_TIMEOUT_MS),
    ]


def _judge_output(problem: PracticeProblem, r1: RunResult, r2: RunResult) -> Verdict:
    if r1.timed_out:
        return Verdict(problem, False, "시간 제한 초과")
    if not r1.ok:
        return Verdict(problem, False, f"실행 오류 — {r1.describe()}")
    first, second = _clean_stdout(r1.stdout), _clean_stdout(r2.stdout)
    if not r2.ok or first != second:
        return Verdict(problem, False, "두 번 실행한 출력이 다름 (랜덤·시간 의존)")
    if not first:
        return Verdict(problem, False, "출력이 없음")
    if len(first.splitlines()) > MAX_OUTPUT_LINES or len(first) > MAX_OUTPUT_CHARS:
        return Verdict(problem, False, "출력이 너무 길어 학생이 적기 어려움")
    if LONG_DECIMAL.search(first):
        return Verdict(problem, False, "소수점 아래가 너무 길어 학생이 적기 어려움")
    problem.expected_stdout = first
    problem.verified = True
    return Verdict(problem, True)


def _judge_tests(problem: PracticeProblem, starter: RunResult, reference: RunResult) -> Verdict:
    if reference.timed_out:
        return Verdict(problem, False, "모범답안이 시간 제한 초과")
    if not reference.ok:
        where = "모범답안" if reference.error_step == 0 else "모범답안이 테스트에서"
        return Verdict(problem, False, f"{where} 실패 — {reference.describe()}")
    if starter.ok:
        what = {"code_fix": "버그 코드", "code_blank": "빈칸을 None으로 둔 코드"}.get(problem.kind, "빈 함수")
        return Verdict(problem, False, f"{what}도 테스트를 통과함 (테스트가 약함)")
    problem.verified = True
    return Verdict(problem, True)


def verify_problems(problems: list[PracticeProblem], runner: Runner) -> list[Verdict]:
    """문제 목록을 검증한다. 순서는 입력 순서 그대로."""
    verdicts: list[Verdict | None] = [None] * len(problems)
    jobs: list[Job] = []
    for i, problem in enumerate(problems):
        if problem.kind not in RUNNABLE:
            problem.verified = True
            verdicts[i] = Verdict(problem, True)
            continue
        # 빈칸 문제는 빈칸이 남은 원본이 문법상 안 맞을 수 있다(`i __1__ step`). 채운 코드만 본다.
        codes = [] if problem.kind == "code_blank" else [problem.starter_code]
        if problem.kind != "code_output":
            codes += [problem.reference_solution, problem.hidden_tests]
        packages: set[str] = set()
        reason = ""
        for code in codes:
            found, reason = static_check(code)
            if reason:
                break
            packages.update(found)
        if reason:
            verdicts[i] = Verdict(problem, False, f"실행 전 거름 — {reason}")
            continue
        if problem.kind != "code_output" and problem.hidden_tests.count("assert") < 2:
            verdicts[i] = Verdict(problem, False, "테스트가 assert 2개 미만")
            continue
        problem.packages = sorted(packages)
        jobs += _jobs_for(i, problem)

    results = runner.run(jobs)
    for i, problem in enumerate(problems):
        if verdicts[i] is not None:
            continue
        key = f"p{i}"
        if problem.kind == "code_output":
            verdicts[i] = _judge_output(problem, results[f"{key}:run1"], results[f"{key}:run2"])
        else:
            verdicts[i] = _judge_tests(problem, results[f"{key}:starter"], results[f"{key}:reference"])
    return [v for v in verdicts if v is not None]
