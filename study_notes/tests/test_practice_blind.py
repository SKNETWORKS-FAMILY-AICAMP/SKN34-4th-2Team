"""문제만 보고 다시 풀어 보기 — 테스트가 문제 문장에 없는 조건을 검사하는 문제를 고치기로 보내는지.

LLM · 검증기는 가짜다. 풀이(solver)와 실행 결과(runner)를 정해 두고 판정 흐름만 본다.
"""

from __future__ import annotations

import unittest
from unittest import mock

from study_notes.practice import build
from study_notes.practice.blind import blind_failures
from study_notes.practice.generate import DraftBatch, Usage
from study_notes.practice.models import PracticeProblem
from study_notes.practice.runner import Job, RunResult
from study_notes.practice.verify import check_test_imports, verify_problems


def write_problem(name: str = "even_sum") -> PracticeProblem:
    return PracticeProblem(
        kind="code_write",
        prompt=f"짝수만 더하는 `{name}(xs)` 함수",
        starter_code=f"def {name}(xs):\n    pass",
        reference_solution=f"def {name}(xs):\n    return sum(x for x in xs if x % 2 == 0)",
        hidden_tests=f"assert {name}([1, 2, 4]) == 6\nassert {name}([]) == 0",
    )


def result(ok: bool) -> RunResult:
    return RunResult(id="", ok=ok, stdout="", timed_out=False, error_type="" if ok else "AssertionError", error_step=-1 if ok else 1)


class ScriptedRunner:
    """verify 의 starter · reference 는 정해진 대로, 다시 풀어 보기(b…)는 blind_ok 에 따라"""

    def __init__(self, blind_ok: list[bool]) -> None:
        self.blind_ok = list(blind_ok)
        self.jobs: list[Job] = []

    def run(self, jobs: list[Job]) -> dict[str, RunResult]:
        self.jobs += jobs
        out = {}
        for job in jobs:
            if job.id.startswith("b"):
                out[job.id] = result(self.blind_ok.pop(0))
            else:
                out[job.id] = result(job.id.endswith(":reference"))
        return out


def solver_of(code: str = "def even_sum(xs):\n    return 0"):
    calls: list[list[PracticeProblem]] = []

    def solve(problems: list[PracticeProblem], usage: Usage) -> dict[int, str]:
        calls.append(problems)
        return {i: code for i in range(len(problems))}

    solve.calls = calls  # type: ignore[attr-defined]
    return solve


class BlindFailuresTests(unittest.TestCase):
    def test_failing_blind_solution_gives_reason_with_the_solution(self) -> None:
        concept = PracticeProblem(kind="concept", prompt="q", choices=["a", "b", "c"], answer_index=0)
        solve = solver_of("def even_sum(xs):\n    return -1")
        failed = blind_failures([concept, write_problem()], ScriptedRunner([False]), Usage(), solve)
        self.assertEqual(list(failed), [1], "개념 문제는 풀게 하지 않는다")
        self.assertIn("문제 문장과 시작 코드만 보고 푼 다른 풀이", failed[1])
        self.assertIn("return -1", failed[1])
        self.assertEqual(len(solve.calls[0]), 1)

    def test_passing_blind_solution_is_fine(self) -> None:
        self.assertEqual(blind_failures([write_problem()], ScriptedRunner([True]), Usage(), solver_of()), {})

    def test_missing_solution_is_not_judged(self) -> None:
        runner = ScriptedRunner([])
        failed = blind_failures([write_problem()], runner, Usage(), lambda problems, usage: {})
        self.assertEqual(failed, {})
        self.assertEqual(runner.jobs, [])

    def test_scratch_solver_does_not_see_skeleton(self) -> None:
        from study_notes.practice import blind

        seen: dict = {}
        fake_llm = mock.MagicMock()
        scratch = write_problem()
        scratch.kind = "code_scratch"
        with mock.patch.object(blind, "_llm", return_value=fake_llm), \
                mock.patch.object(blind, "BLIND_PROMPT") as prompt:
            prompt.__or__.return_value.invoke.side_effect = lambda args: seen.update(args) or mock.MagicMock(
                content='{"solutions": []}', usage_metadata={})
            blind.solve_blind([scratch, write_problem()], Usage())
        self.assertNotIn('"starterCode"', seen["problems"].split('"index": 1')[0])
        self.assertIn('"starterCode"', seen["problems"].split('"index": 1')[1])
        self.assertNotIn("reference", seen["problems"])
        self.assertNotIn("assert", seen["problems"])


class BuildWithBlindTests(unittest.TestCase):
    def build(self, blind_ok: list[bool], repaired: list[PracticeProblem]):
        runner = ScriptedRunner(blind_ok)
        with mock.patch.object(build, "generate_drafts", return_value=DraftBatch([write_problem()])), \
                mock.patch.object(build, "repair_drafts", return_value=DraftBatch(repaired)) as repair:
            out = build.build_practice_set(scope_label="s", materials=[], runner=runner, solver=solver_of())
        return out, repair

    def test_blind_failure_goes_to_repair_and_repaired_problem_is_kept(self) -> None:
        out, repair = self.build([False, True], [write_problem("even_total")])
        [(problem, reason)] = repair.call_args.args[0]
        self.assertIn("다른 풀이가 숨긴 테스트에서 떨어짐", reason)
        self.assertEqual([p.prompt for p in out.problems], ["짝수만 더하는 `even_total(xs)` 함수"])
        stats = out.stats["code_write"]
        self.assertEqual((stats.drafted, stats.passed_first, stats.passed_after_repair, stats.dropped), (1, 0, 1, 0))

    def test_repaired_problem_that_still_fails_blind_is_dropped(self) -> None:
        out, _ = self.build([False, False], [write_problem("even_total")])
        self.assertEqual(out.problems, [])
        self.assertIn("다른 풀이", out.dropped[0]["afterRepair"])
        self.assertEqual(out.stats["code_write"].dropped, 1)

    def test_blind_off_keeps_old_flow(self) -> None:
        runner = ScriptedRunner([])
        with mock.patch.object(build, "generate_drafts", return_value=DraftBatch([write_problem()])):
            out = build.build_practice_set(scope_label="s", materials=[], runner=runner, blind=False)
        self.assertEqual(len(out.problems), 1)
        self.assertFalse(any(j.id.startswith("b") for j in runner.jobs))


class ParseBatchTests(unittest.TestCase):
    def test_model_refusal_reason_is_kept(self) -> None:
        from study_notes.practice.generate import _parse_batch

        batch = _parse_batch('{"problems": [], "error": "SQL 자료는 파일 하나뿐이라 SQL 10문제는 못 냅니다"}')
        self.assertEqual(batch.problems, [])
        self.assertIn("SQL 10문제는 못 냅니다", batch.rejected[0])


class TestsImportTests(unittest.TestCase):
    def test_module_used_without_import_is_rejected(self) -> None:
        self.assertIn("math", check_test_imports("assert abs(f(1) - math.cos(1)) < 1e-9\nassert f(0) == 1"))
        self.assertIn("np", check_test_imports("assert np.allclose(f([1]), [2])"))

    def test_imported_modules_and_plain_names_pass(self) -> None:
        self.assertEqual(check_test_imports("import math\nassert abs(f(1) - math.cos(1)) < 1e-9"), "")
        self.assertEqual(check_test_imports("import numpy as np\nassert np.allclose(f([1]), [2])"), "")
        self.assertEqual(check_test_imports("from math import cos\nassert f(1) == cos(1)"), "")
        self.assertEqual(check_test_imports("result = f()\nassert result == 3"), "", "학생 함수 · 변수는 모듈이 아니다")

    def test_verify_rejects_before_running(self) -> None:
        problem = write_problem()
        problem.hidden_tests = "assert even_sum([2]) == 2\nassert math.isclose(even_sum([4]), 4)"
        runner = ScriptedRunner([])
        [verdict] = verify_problems([problem], runner)
        self.assertFalse(verdict.passed)
        self.assertIn("import", verdict.reason)
        self.assertEqual(runner.jobs, [])


if __name__ == "__main__":
    unittest.main()
