"""실습 문제 구조와 LLM 초안 정리.

LLM이 준 JSON은 모양이 제멋대로일 수 있다. 여기서 한 번 걸러 정해진 모양으로 맞춘다.
정답 출력(expectedStdout)은 LLM 값을 쓰지 않는다 — 검증기가 실제 실행 결과로 채운다.
LLM이 적어 낸 값은 llmGuessedStdout 으로 따로 남겨 얼마나 맞히는지만 잰다.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

# code_scratch — 뼈대 없이 빈 에디터에서 함수를 처음부터 짠다. starter_code 는 「뼈대 받기」를 눌렀을 때만 보이는 뼈대
# sql_query — 예제 테이블(setup_sql)에 조회문을 쓴다. 결과 표가 모범 조회문과 같으면 통과(sql_problem.py)
# web_task — HTML · CSS 를 요구대로 고친다. hidden_tests 는 check(…) 검사문, 채점은 jsdom(web_problem.py)
Kind = Literal["concept", "code_output", "code_blank", "code_fix", "code_write", "code_scratch", "sql_query", "web_task"]
KINDS: tuple[Kind, ...] = (
    "concept", "code_output", "code_blank", "code_fix", "code_write", "code_scratch", "sql_query", "web_task",
)
RUNNABLE: tuple[Kind, ...] = ("code_output", "code_blank", "code_fix", "code_write", "code_scratch", "sql_query", "web_task")

# 빈칸 표시. `__1__`은 올바른 파이썬 이름이라 빈칸이 남은 채로도 ast로 읽힌다.
BLANK_RE = re.compile(r"__(\d)__")
MAX_BLANKS = 3
MAX_BLANK_CHARS = 60


def fill_blanks(code: str, answers: list[str]) -> str:
    """`__1__` … 을 answers 순서대로 채운다. 번호가 answers 범위를 넘으면 그대로 둔다."""
    def swap(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        return answers[index] if 0 <= index < len(answers) else match.group(0)
    return BLANK_RE.sub(swap, code)


@dataclass
class PracticeProblem:
    kind: Kind
    prompt: str
    topic: str = ""
    source_files: list[str] = field(default_factory=list)
    explanation: str = ""
    # concept
    choices: list[str] = field(default_factory=list)
    answer_index: int | None = None
    # code_*
    starter_code: str = ""
    reference_solution: str = ""
    hidden_tests: str = ""
    # code_blank — starter_code 안의 `__1__` … 자리에 들어갈 모범 답
    blank_answers: list[str] = field(default_factory=list)
    # sql_query — 예제 테이블을 만드는 스크립트(CREATE TABLE · INSERT). 학생 조회문보다 먼저 돈다
    setup_sql: str = ""
    # sql_query 중 테이블 만들기 — 학생 CREATE TABLE 뒤에 돌리는 확인 문장(INSERT OR IGNORE … · 끝은 SELECT).
    # 검증을 통과하면 기대 결과 JSON 의 after 로 들어간다(sql_problem.py)
    check_sql: str = ""
    # 검증기가 채운다
    expected_stdout: str = ""
    llm_guessed_stdout: str = ""
    packages: list[str] = field(default_factory=list)
    verified: bool = False

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        return {_camel(k): v for k, v in data.items()}


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(part.title() for part in rest)


def _text(value: Any) -> str:
    return value.strip("\n") if isinstance(value, str) else ""


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def parse_draft(raw: Any) -> tuple[PracticeProblem | None, str]:
    """LLM 초안 하나를 문제로 바꾼다. 못 쓰면 (None, 이유)."""
    if not isinstance(raw, dict):
        return None, "객체가 아님"
    kind = raw.get("kind")
    if kind not in KINDS:
        return None, f"알 수 없는 kind: {kind!r}"
    prompt = _text(raw.get("prompt")).strip()
    if not prompt:
        return None, "문제 문장이 비어 있음"

    problem = PracticeProblem(
        kind=kind,
        prompt=prompt,
        topic=_text(raw.get("topic")).strip(),
        source_files=_str_list(raw.get("sourceFiles")),
        explanation=_text(raw.get("explanation")).strip(),
    )
    # JS 코드 문제 — 종류는 파이썬 코드 문제와 같고 언어만 다르다(js_problem.py). 검증 · 채점이 이 표시로 갈린다
    if kind.startswith("code_") and str(raw.get("language") or "").strip().lower() in ("javascript", "js"):
        problem.packages = ["js"]

    if kind == "concept":
        choices = _str_list(raw.get("choices"))
        index = raw.get("answerIndex")
        if len(choices) < 3:
            return None, "보기가 3개 미만"
        if not isinstance(index, int) or not 0 <= index < len(choices):
            return None, "정답 번호가 보기 범위 밖"
        problem.choices = choices
        problem.answer_index = index
        return problem, ""

    if kind == "sql_query":
        problem.setup_sql = _text(raw.get("setupSql"))
        problem.reference_solution = _text(raw.get("referenceSolution"))
        problem.check_sql = _text(raw.get("checkSql"))
        # 시작 칸은 비워 두어도 된다 — 주석 한 줄로 채운다
        problem.starter_code = _text(raw.get("starterCode")) or (
            "-- 여기에 CREATE TABLE 문을 쓰세요\n" if problem.check_sql.strip() else "-- 여기에 조회문을 쓰세요\n"
        )
        if not problem.setup_sql.strip() and not problem.check_sql.strip():
            return None, "준비 스크립트(setupSql)가 비어 있음"
        if not problem.reference_solution.strip():
            return None, "모범 조회문이 비어 있음"
        return problem, ""

    problem.starter_code = _text(raw.get("starterCode"))
    if not problem.starter_code.strip():
        return None, "시작 코드가 비어 있음"
    if kind == "code_output":
        problem.llm_guessed_stdout = _text(raw.get("expectedStdout"))
        return problem, ""

    problem.hidden_tests = _text(raw.get("hiddenTests"))
    if kind == "code_blank":
        answers = [str(a).strip() for a in raw.get("blankAnswers") or [] if str(a).strip()]
        numbers = sorted({int(n) for n in BLANK_RE.findall(problem.starter_code)})
        if not numbers:
            return None, "빈칸(__1__)이 없음"
        if numbers != list(range(1, len(numbers) + 1)) or len(numbers) != len(answers):
            return None, f"빈칸 번호 {numbers}와 답 {len(answers)}개가 맞지 않음"
        if len(answers) > MAX_BLANKS:
            return None, f"빈칸이 {MAX_BLANKS}개 초과"
        if any("\n" in a or len(a) > MAX_BLANK_CHARS for a in answers):
            return None, "빈칸 답이 한 줄·짧은 식이 아님"
        if not problem.hidden_tests.strip():
            return None, "테스트가 비어 있음"
        problem.blank_answers = answers
        problem.reference_solution = fill_blanks(problem.starter_code, answers)
        return problem, ""

    problem.reference_solution = _text(raw.get("referenceSolution"))
    if not problem.reference_solution.strip():
        return None, "모범답안이 비어 있음"
    if not problem.hidden_tests.strip():
        return None, "테스트가 비어 있음"
    return problem, ""
