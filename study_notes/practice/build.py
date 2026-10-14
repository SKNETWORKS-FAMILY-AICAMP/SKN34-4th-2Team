"""생성 → 검증 → 문제만 보고 다시 풀어 보기(blind.py) → (떨어진 것만) 한 번 고쳐서 재검증 · 다시 풀어 보기.

입력은 수업 자료, 출력은 검증된 문제와 통계다. 저장은 부르는 쪽이 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from study_notes.pipeline import Material
from study_notes.practice.blind import Solver, blind_failures, solve_blind
from study_notes.practice.dedupe import split_overlaps
from study_notes.practice.generate import Usage, generate_drafts, repair_drafts
from study_notes.practice.increments import kind_counts_text
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
    overlapped: int = 0  # 통과했지만 앞 문제와 겹쳐 뺌(dedupe.py) — 그 자리는 채우기(refill)로
    refilled: int = 0


@dataclass
class BuildResult:
    problems: list[PracticeProblem]
    stats: dict[str, KindStats]
    dropped: list[dict[str, str]] = field(default_factory=list)
    malformed: list[str] = field(default_factory=list)
    llm_output_guesses: dict[str, int] = field(default_factory=lambda: {"right": 0, "wrong": 0})
    usage: Usage = field(default_factory=Usage)
    overlapped: list[PracticeProblem] = field(default_factory=list)  # 겹쳐서 뺀 문제(채우기 몫)

    def to_json(self) -> dict[str, Any]:
        return {
            "problems": [p.to_json() for p in self.problems],
            "stats": {k: vars(v) for k, v in self.stats.items() if v.drafted or v.refilled},
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


def _blind(verdicts: list[Verdict], runner: Runner, usage: Usage, solver: Solver) -> list[Verdict]:
    """검증을 통과한 문제를 문제만 보고 다시 풀어 본다. 떨어지면 그 판정을 실패로 바꾼다(이유는 고치기에 넘긴다)."""
    passed = [v for v in verdicts if v.passed]
    failed = blind_failures([v.problem for v in passed], runner, usage, solver)
    if not failed:
        return verdicts
    swap = {id(passed[i]): reason for i, reason in failed.items()}
    return [Verdict(v.problem, False, swap[id(v)]) if id(v) in swap else v for v in verdicts]


def build_practice_set(
    *, scope_label: str, materials: list[Material], runner: Runner, repair: bool = True, focus_note: str = "", kind_counts: str = "",
    blind: bool = True, solver: Solver = solve_blind, refill: bool = True,
) -> BuildResult:
    """refill — 앞 문제와 겹쳐서 뺀 만큼 한 번 더 만든다(dedupe.py)."""
    usage = Usage()
    drafts = generate_drafts(scope_label=scope_label, materials=materials, usage=usage, focus_note=focus_note, kind_counts=kind_counts)
    result = BuildResult(problems=[], stats={k: KindStats() for k in KINDS}, usage=usage)
    result.malformed.extend(drafts.rejected)

    failures: list[tuple[PracticeProblem, str]] = []
    first = verify_problems(drafts.problems, runner)
    first = _blind(first, runner, usage, solver) if blind else first
    for verdict in first:
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
        retry = _blind(retry, runner, usage, solver) if blind else retry
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
    drop_overlaps(result)
    if refill:
        refill_overlaps(result, scope_label=scope_label, materials=materials, runner=runner, focus_note=focus_note, blind=blind, solver=solver)
    return result


REFILL_NOTE = (
    "이번에는 위 파일별 개수 대신 아래 종류 · 개수만 더 냅니다.\n"
    "이미 낸 문제(아래)와 겹치지 않게 — 같은 함수 · 같은 코드를 종류만 바꿔 다시 내지 말고, 아직 묻지 않은 개념으로 냅니다.\n"
    "이미 낸 문제:\n{listing}"
)


def drop_overlaps(result: BuildResult) -> list[PracticeProblem]:
    """앞 문제와 겹치는 문제를 뺀다. 뺀 문제를 돌려준다(종류 · 개수만큼 채우기에 쓴다)."""
    result.problems, overlaps = split_overlaps(result.problems)
    for problem, other, why in overlaps:
        result.stats[problem.kind].overlapped += 1
        result.dropped.append({"kind": problem.kind, "topic": problem.topic, "firstFailure": f"겹침: {why} — 「{other.topic}」"})
    result.overlapped = [p for p, _, _ in overlaps]
    return result.overlapped


def refill_overlaps(
    result: BuildResult, *, scope_label: str, materials: list[Material], runner: Runner, focus_note: str, blind: bool, solver: Solver,
) -> None:
    """겹쳐서 뺀 만큼 한 번 더 만든다 — 같은 수업 자료로, 이미 낸 문제 목록을 보여 주고. 고치기는 안 한다(한 번만)."""
    if not result.overlapped or not materials:
        return
    mix: dict[str, int] = {}
    for p in result.overlapped:
        mix[p.kind] = mix.get(p.kind, 0) + 1
    listing = "\n".join(f"- {p.topic} ({p.kind})" for p in result.problems)
    note = "\n\n".join(x for x in (focus_note, REFILL_NOTE.format(listing=listing)) if x)
    try:
        drafts = generate_drafts(
            scope_label=scope_label, materials=materials, usage=result.usage, focus_note=note, kind_counts=kind_counts_text(mix),
        )
    except Exception as exc:  # noqa: BLE001 — 채우기가 안 돼도 이미 만든 문제는 낸다
        result.malformed.append(f"겹친 문제 채우기 실패: {type(exc).__name__}: {exc}")
        return
    result.malformed.extend(drafts.rejected)
    verdicts = verify_problems(drafts.problems, runner)
    verdicts = _blind(verdicts, runner, result.usage, solver) if blind else verdicts
    fresh = [v.problem for v in verdicts if v.passed]
    keep, again = split_overlaps(fresh, kept=result.problems)
    keep = keep[: len(result.overlapped)]
    for p in keep:
        result.stats[p.kind].refilled += 1
        _count_guess(result, Verdict(p, True, ""))
    result.problems.extend(keep)
    for problem, other, why in again:
        result.dropped.append({"kind": problem.kind, "topic": problem.topic, "firstFailure": f"채운 문제도 겹침: {why} — 「{other.topic}」"})
