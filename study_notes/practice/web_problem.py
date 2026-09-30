"""웹 실습 문제(web_task) — HTML · CSS 를 요구대로 고친다. 검사는 jsdom(practice_verifier/web.mjs).

- starter_code: 학생이 받는 HTML 문서(<style> 포함). reference_solution: 요구대로 고친 문서.
- hidden_tests: 검사문 한 줄에 하나 — check(조건, '학생에게 보일 문장');
  도우미: $ · $$ · has · count · text · attr · css (web.mjs 의 HELPERS).
- 검증: 모범 문서는 모든 검사를 통과하고, 시작 문서는 하나 이상 떨어져야 한다(verify.py 의 코드 문제와 같은 규칙).
- 학생 채점도 같은 jsdom 으로 서버에서 한다(api.py /proxy/practice/web-grade). 출제 때 통과한 검사가 브라우저 계산값과
  어긋나 떨어지는 일이 없게. 검사문은 DB 에만 있고 화면에는 가지 않는다(lms/practice_service.py).
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from study_notes.practice.runner import Job, RunResult

if TYPE_CHECKING:
    from study_notes.practice.models import PracticeProblem

MIN_CHECKS = 2
MAX_CHECKS = 6
MAX_DOC_CHARS = 4000
# 검사문은 한 줄 식만 — 반복 · 함수 정의 · 바깥으로 나가는 이름은 쓰지 않는다(jsdom vm 을 벗어날 길을 막는다)
FORBIDDEN = re.compile(r"\b(while|for|function|constructor|prototype|process|require|import|eval|Function|globalThis|fetch|setTimeout|__proto__)\b|=>")
SCRIPT_TAG = re.compile(r"<script\b", re.I)


def check_lines(tests: str) -> list[str]:
    return [line.strip() for line in tests.splitlines() if line.strip() and not line.strip().startswith("//")]


def static_check(problem: PracticeProblem) -> str:
    """실행 전에 거를 이유. 비어 있으면 통과."""
    for name, doc in (("시작 문서", problem.starter_code), ("모범 문서", problem.reference_solution)):
        if SCRIPT_TAG.search(doc):
            return f"{name}에 <script> 가 있음 (웹 실습은 HTML · CSS 만)"
        if len(doc) > MAX_DOC_CHARS:
            return f"{name}가 {len(doc)}자로 김"
    lines = check_lines(problem.hidden_tests)
    if not MIN_CHECKS <= len(lines) <= MAX_CHECKS:
        return f"검사문이 {len(lines)}줄 (check {MIN_CHECKS}~{MAX_CHECKS}줄)"
    for line in lines:
        if not line.startswith("check("):
            return f"check( 로 시작하지 않는 줄: {line[:60]}"
        if FORBIDDEN.search(line):
            return f"검사문에 쓸 수 없는 말: {line[:60]}"
    return ""


def jobs_for(key: str, problem: PracticeProblem, timeout_ms: int) -> list[Job]:
    return [
        Job(f"{key}:starter", [problem.starter_code, problem.hidden_tests], timeout_ms, kind="web"),
        Job(f"{key}:reference", [problem.reference_solution, problem.hidden_tests], timeout_ms, kind="web"),
    ]


def checks_of(result: RunResult) -> list[dict]:
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [{"message": str(c.get("message", "")), "ok": bool(c.get("ok"))} for c in data if isinstance(c, dict)]


def judge(problem: PracticeProblem, starter: RunResult, reference: RunResult) -> tuple[bool, str]:
    """(통과, 이유)"""
    ref = checks_of(reference)
    if reference.timed_out:
        return False, "모범 문서 검사가 시간 제한 초과"
    if not reference.ok:
        failed = [c["message"] for c in ref if not c["ok"]] or [reference.describe()]
        return False, f"모범 문서가 검사를 통과하지 못함 — {', '.join(failed)[:200]}"
    if starter.ok:
        return False, "시작 문서도 모든 검사를 통과함 (고칠 것이 없음)"
    problem.verified = True
    return True, ""


def grade_result(result: RunResult) -> dict:
    """학생 채점 응답 — {passed, checks, error}"""
    checks = checks_of(result)
    error = ""
    if result.timed_out:
        error = "검사가 시간 제한에 걸렸어요."
    elif not checks:
        error = "채점하지 못했어요. 잠시 후 다시 해 보세요."
    return {"passed": result.ok and bool(checks), "checks": checks, "error": error}
