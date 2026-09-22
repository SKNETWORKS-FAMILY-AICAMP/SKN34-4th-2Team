"""생성 → 검증 → (떨어진 것만) 한 번 고쳐서 재검증.

입력은 수업 자료, 출력은 검증된 문제와 통계다. 저장은 부르는 쪽이 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from study_notes.pipeline import Material
from study_notes.practice.generate import Usage, generate_drafts, repair_drafts
from study_notes.practice.models import KINDS, PracticeProblem
from study_notes.practice.runner import Runner
from study_notes.practice.verify import Verdict, verify_problems


@dataclass
class KindStats:
    drafted: int = 0
    passed_first: int = 0
    passed_after_repair: int = 0
    converted: int = 0  # 고치다가 다른 종류(대개 concept)로 바뀌어 통과
    dropped: int = 0


@dataclass
class BuildResult:
    problems: list[PracticeProblem]
    stats: dict[str, KindStats]
    dropped: list[dict[str, str]] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    llm_output_guesses: dict[str, int] = field(default_factory=lambda: {"right": 0, "wrong": 0})
    usage: Usage = field(default_factory=Usage)

    def to_json(self) -> dict[str, Any]:
        return {
            "problems": [p.to_json() for p in self.problems],
            "stats": {k: vars(v) for k, v in self.stats.items() if v.drafted},
            "dropped": self.dropped,
            "malformed": self.malformed,
            "llmOutputGuesses": self.llm_output_guesses,
            "usage": vars(self.usage),
        }


def _norm(text: str) -> str:
    return " ".join(text.split()).lower()


def _count_guess(result: BuildResult, verdict: Verdict) -> None:
    """LLM이 예상한 출력이 실제 실행 결과와 같았는지 — 실행 검증이 왜 필요한지 보여 주는 숫자."""
    problem = verdict.problem
    if problem.kind != "code_output" or not verdict.passed:
        return
    key = "right" if _norm(problem.llm_guessed_stdout) == _norm(problem.expected_stdout) else "wrong"
    result.llm_output_guesses[key] += 1


def build_practice_set(
    *, scope_label: str, materials: list[Material], runner: Runner, repair: bool = True, focus_note: str = "",
) -> BuildResult:
    usage = Usage()
    drafts = generate_drafts(scope_label=scope_label, materials=materials, usage=usage, focus_note=focus_note)
    result = BuildResult(problems=[], stats={k: KindStats() for k in KINDS}, usage=usage)
    result.malformed.extend(drafts.rejected)

    failures: list[tuple[PracticeProblem, str]] = []
    for verdict in verify_problems(drafts.problems, runner):
        stats = result.stats[verdict.problem.kind]
        stats.drafted += 1
        if verdict.passed:
            stats.passed_first += 1
            result.problems.append(verdict.problem)
            _count_guess(result, verdict)
        else:
            failures.append((verdict.problem, verdict.reason))

    retry: list[Verdict] = []
    if repair and failures:
        repaired = repair_drafts(failures, usage=usage)
        result.malformed.extend(repaired.rejected)
        retry = verify_problems(repaired.problems, runner)
        for verdict in retry:
            if verdict.passed:
                result.problems.append(verdict.problem)
                _count_guess(result, verdict)

    # 고친 문제가 같은 순서·개수로 왔을 때만 짝을 지어 원래 종류 기준으로 센다.
    aligned = len(retry) == len(failures)
    for i, (problem, reason) in enumerate(failures):
        entry = {"kind": problem.kind, "topic": problem.topic, "firstFailure": reason}
        if aligned:
            after = retry[i]
            stats = result.stats[problem.kind]
            if not after.passed:
                entry["afterRepair"] = after.reason
            elif after.problem.kind == problem.kind:
                stats.passed_after_repair += 1
                entry["afterRepair"] = "통과"
            else:
                stats.converted += 1
                entry["afterRepair"] = f"{after.problem.kind}로 바뀌어 통과"
        result.dropped.append(entry)
    if not aligned:
        for verdict in retry:
            if verdict.passed:
                result.stats[verdict.problem.kind].passed_after_repair += 1

    for stats in result.stats.values():
        stats.dropped = max(
            0, stats.drafted - stats.passed_first - stats.passed_after_repair - stats.converted,
        )
    return result
