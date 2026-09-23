"""실습 문제 검증 규칙.

앞쪽은 가짜 실행기로 규칙만 본다. 맨 끝 클래스는 진짜 Pyodide 검증기를 부른다
(node 와 practice_verifier/node_modules 가 없으면 건너뛴다).
"""

from __future__ import annotations

import shutil
import unittest

from study_notes.practice.models import PracticeProblem, parse_draft
from study_notes.practice.runner import VERIFIER_DIR, Job, PyodideRunner, RunResult
from study_notes.practice.verify import static_check, verify_problems


class FakeRunner:
    """job id 끝부분(run1, starter …)으로 미리 정한 결과를 돌려준다."""

    def __init__(self, **by_suffix: RunResult) -> None:
        self.by_suffix = by_suffix
        self.jobs: list[Job] = []

    def run(self, jobs: list[Job]) -> dict[str, RunResult]:
        self.jobs += jobs
        return {j.id: self.by_suffix[j.id.split(":")[1]] for j in jobs}


def ok(stdout: str = "") -> RunResult:
    return RunResult(id="", ok=True, stdout=stdout, timed_out=False)


def fail(kind: str = "AssertionError") -> RunResult:
    return RunResult(id="", ok=False, stdout="", timed_out=False, error_type=kind, error_step=1)


def output_problem(code: str = 'print("hi")', guess: str = "hi") -> PracticeProblem:
    return PracticeProblem(kind="code_output", prompt="출력은?", starter_code=code, llm_guessed_stdout=guess)


def write_problem() -> PracticeProblem:
    return PracticeProblem(
        kind="code_write",
        prompt="짝수만 더하는 함수",
        starter_code="def even_sum(xs):\n    pass",
        reference_solution="def even_sum(xs):\n    return sum(x for x in xs if x % 2 == 0)",
        hidden_tests="assert even_sum([1, 2, 4]) == 6\nassert even_sum([]) == 0",
    )


def scratch_problem(**over: str) -> PracticeProblem:
    fields = dict(
        kind="code_scratch",
        prompt="`count_words(text)` 를 처음부터 작성하세요. 예: count_words('a b a') → {'a': 2, 'b': 1}",
        starter_code='def count_words(text):\n    """단어별 횟수"""\n    pass',
        reference_solution=(
            "def count_words(text):\n    counts = {}\n    for w in text.split():\n"
            "        counts[w] = counts.get(w, 0) + 1\n    return counts"
        ),
        hidden_tests=(
            "assert count_words('a b a') == {'a': 2, 'b': 1}\nassert count_words('') == {}\n"
            "assert count_words('x') == {'x': 1}"
        ),
    )
    fields.update(over)
    return PracticeProblem(**fields)


class ParseDraftTests(unittest.TestCase):
    def test_concept_needs_valid_answer_index(self) -> None:
        raw = {"kind": "concept", "prompt": "q", "choices": ["a", "b", "c", "d"], "answerIndex": 4}
        problem, reason = parse_draft(raw)
        self.assertIsNone(problem)
        self.assertIn("범위", reason)

    def test_code_output_keeps_llm_guess_apart_from_expected(self) -> None:
        problem, _ = parse_draft({
            "kind": "code_output", "prompt": "q", "starterCode": "print(1)", "expectedStdout": "1",
        })
        self.assertEqual(problem.llm_guessed_stdout, "1")
        self.assertEqual(problem.expected_stdout, "")

    def test_code_write_needs_tests(self) -> None:
        problem, reason = parse_draft({
            "kind": "code_write", "prompt": "q", "starterCode": "def f(): pass", "referenceSolution": "def f(): return 1",
        })
        self.assertIsNone(problem)
        self.assertIn("테스트", reason)

    def test_code_blank_builds_reference_by_filling_blanks(self) -> None:
        problem, reason = parse_draft({
            "kind": "code_blank", "prompt": "q",
            "starterCode": "import re\nm = re.search(__1__, 'a_frame007.jpg')\nn = int(m.group(__2__))",
            "blankAnswers": ["r'_frame(\\d+)'", "1"],
            "hiddenTests": "assert n == 7\nassert m is not None",
        })
        self.assertEqual(reason, "")
        self.assertEqual(problem.reference_solution,
                         "import re\nm = re.search(r'_frame(\\d+)', 'a_frame007.jpg')\nn = int(m.group(1))")

    def test_code_blank_rejects_mismatched_blanks(self) -> None:
        _problem, reason = parse_draft({
            "kind": "code_blank", "prompt": "q", "starterCode": "x = __1__ + __3__",
            "blankAnswers": ["1", "2"], "hiddenTests": "assert x == 3\nassert x",
        })
        self.assertIn("빈칸 번호", reason)

    def test_to_json_uses_camel_case(self) -> None:
        data = output_problem().to_json()
        self.assertIn("starterCode", data)
        self.assertIn("expectedStdout", data)


class StaticCheckTests(unittest.TestCase):
    def test_allows_stdlib_and_numpy(self) -> None:
        packages, reason = static_check("import numpy as np\nfrom collections import Counter\nprint(1)")
        self.assertEqual(reason, "")
        self.assertEqual(packages, ["numpy"])

    def test_blocks_file_network_and_clock(self) -> None:
        for code, needle in [
            ("import os", "os"),
            ("open('a.txt')", "open"),
            ("import requests", "requests"),
            ("import pandas as pd\npd.read_csv('data.csv')", "read_csv"),
            ("from datetime import datetime\ndatetime.now()", "now"),
            ("x = input()", "input"),
            ("import torch", "torch"),
        ]:
            _packages, reason = static_check(code)
            self.assertIn(needle, reason, code)

    def test_reports_syntax_error(self) -> None:
        _packages, reason = static_check("def f(:\n  pass")
        self.assertIn("문법 오류", reason)


class VerifyRuleTests(unittest.TestCase):
    def test_code_output_takes_expected_from_execution_not_llm(self) -> None:
        problem = output_problem(guess="틀린 예상")
        [verdict] = verify_problems([problem], FakeRunner(run1=ok("hi\n"), run2=ok("hi\n")))
        self.assertTrue(verdict.passed)
        self.assertEqual(problem.expected_stdout, "hi")

    def test_code_output_rejects_nondeterministic_output(self) -> None:
        [verdict] = verify_problems([output_problem()], FakeRunner(run1=ok("1\n"), run2=ok("2\n")))
        self.assertFalse(verdict.passed)
        self.assertIn("두 번", verdict.reason)

    def test_code_output_rejects_long_output(self) -> None:
        long = "\n".join(str(i) for i in range(10))
        [verdict] = verify_problems([output_problem()], FakeRunner(run1=ok(long), run2=ok(long)))
        self.assertFalse(verdict.passed)

    def test_code_output_rejects_long_decimals(self) -> None:
        out = "[127.55555556 127.55555556]\n"
        [verdict] = verify_problems([output_problem()], FakeRunner(run1=ok(out), run2=ok(out)))
        self.assertFalse(verdict.passed)
        self.assertIn("소수점", verdict.reason)

    def test_code_write_passes_when_stub_fails_and_reference_passes(self) -> None:
        [verdict] = verify_problems([write_problem()], FakeRunner(starter=fail(), reference=ok()))
        self.assertTrue(verdict.passed)

    def test_code_write_rejects_tests_that_stub_passes(self) -> None:
        [verdict] = verify_problems([write_problem()], FakeRunner(starter=ok(), reference=ok()))
        self.assertFalse(verdict.passed)
        self.assertIn("테스트가 약함", verdict.reason)

    def test_code_write_rejects_broken_reference(self) -> None:
        [verdict] = verify_problems([write_problem()], FakeRunner(starter=fail(), reference=fail()))
        self.assertFalse(verdict.passed)
        self.assertIn("모범답안", verdict.reason)

    def test_code_scratch_runs_like_code_write(self) -> None:
        runner = FakeRunner(starter=fail("NameError"), reference=ok())
        [verdict] = verify_problems([scratch_problem()], runner)
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual([j.id for j in runner.jobs], ["p0:starter", "p0:reference"])

    def test_code_scratch_needs_function_name_in_prompt(self) -> None:
        runner = FakeRunner()
        [verdict] = verify_problems([scratch_problem(prompt="단어 수를 세는 함수를 만드세요")], runner)
        self.assertFalse(verdict.passed)
        self.assertIn("count_words", verdict.reason)
        self.assertEqual(runner.jobs, [])

    def test_code_scratch_rejects_one_liner_and_few_tests(self) -> None:
        short = scratch_problem(reference_solution="def count_words(text):\n    return {}")
        few = scratch_problem(hidden_tests="assert count_words('') == {}\nassert count_words('a') == {'a': 1}")
        verdicts = verify_problems([short, few], FakeRunner())
        self.assertIn("짧음", verdicts[0].reason)
        self.assertIn("3개 미만", verdicts[1].reason)

    def test_code_scratch_parses_like_code_write(self) -> None:
        problem, reason = parse_draft({
            "kind": "code_scratch", "prompt": "`f()`", "starterCode": "def f():\n    pass",
            "referenceSolution": "def f():\n    return 1", "hiddenTests": "assert f() == 1\nassert f()",
        })
        self.assertEqual(reason, "")
        self.assertEqual(problem.kind, "code_scratch")

    def test_static_failure_skips_execution(self) -> None:
        runner = FakeRunner()
        [verdict] = verify_problems([output_problem(code="import os\nprint(os.getcwd())")], runner)
        self.assertFalse(verdict.passed)
        self.assertEqual(runner.jobs, [])

    def test_concept_is_not_executed(self) -> None:
        concept = PracticeProblem(kind="concept", prompt="q", choices=["a", "b", "c"], answer_index=0)
        runner = FakeRunner()
        [verdict] = verify_problems([concept], runner)
        self.assertTrue(verdict.passed)
        self.assertEqual(runner.jobs, [])


class BuildStatsTests(unittest.TestCase):
    def test_repair_that_switches_kind_counts_as_converted(self) -> None:
        from unittest import mock

        from study_notes.practice import build
        from study_notes.practice.generate import DraftBatch

        torch_problem = output_problem(code="import torch\nprint(torch.zeros(2).shape)")
        concept = PracticeProblem(kind="concept", prompt="q", choices=["a", "b", "c"], answer_index=0)
        with mock.patch.object(build, "generate_drafts", return_value=DraftBatch([torch_problem])), \
                mock.patch.object(build, "repair_drafts", return_value=DraftBatch([concept])):
            result = build.build_practice_set(scope_label="s", materials=[], runner=FakeRunner())

        stats = result.stats["code_output"]
        self.assertEqual((stats.drafted, stats.passed_after_repair, stats.converted, stats.dropped), (1, 0, 1, 0))
        self.assertEqual(result.dropped[0]["afterRepair"], "concept로 바뀌어 통과")
        self.assertEqual([p.kind for p in result.problems], ["concept"])


@unittest.skipUnless(
    shutil.which("node") and (VERIFIER_DIR / "node_modules" / "pyodide").exists(),
    "node 또는 practice_verifier/node_modules 없음",
)
class PyodideIntegrationTests(unittest.TestCase):
    def test_end_to_end_with_real_pyodide(self) -> None:
        fix = PracticeProblem(
            kind="code_fix",
            prompt="무한 루프를 고치세요",
            starter_code="def count_up(n):\n    out = []\n    i = 0\n    while i < n:\n        out.append(i)\n    return out",
            reference_solution="def count_up(n):\n    out = []\n    i = 0\n    while i < n:\n        out.append(i)\n        i += 1\n    return out",
            hidden_tests="assert count_up(3) == [0, 1, 2]\nassert count_up(0) == []",
        )
        seeded = output_problem(code="import random\nrandom.seed(1)\nprint(random.randint(1, 100))")
        unseeded = output_problem(code="import random\nprint(random.random())")
        blank, _ = parse_draft({
            "kind": "code_blank", "prompt": "q",
            "starterCode": "def keep_every(frames, step):\n    return [f for i, f in enumerate(frames) if i __1__ step == 0]",
            "blankAnswers": ["%"],
            "hiddenTests": "assert keep_every(list('abcdef'), 2) == ['a', 'c', 'e']\nassert keep_every([], 3) == []",
        })
        # 빈칸이 None이면 `i None step` 이 문법 오류 → 실패. 모범 답 `%` 이면 통과.
        verdicts = verify_problems(
            [output_problem(code='d = {"a": 1, "b": 2}\nprint(sum(d.values()))'), write_problem(), fix, seeded, unseeded, blank],
            PyodideRunner(),
        )
        self.assertEqual([v.passed for v in verdicts], [True, True, True, True, False, True], [v.reason for v in verdicts])
        self.assertEqual(verdicts[0].problem.expected_stdout, "3")


if __name__ == "__main__":
    unittest.main()
