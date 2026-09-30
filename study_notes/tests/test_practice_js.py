"""JS 문제 — 초안의 language, 실행 전 규칙, Node 검증(진짜 검증기), 하루 구성 · 파일별 지시, 스크립트 있는 웹 실습.

뒤쪽은 진짜 검증기(practice_verifier/js.mjs · web.mjs)를 부른다(node · jsdom 이 없으면 건너뛴다).
"""

from __future__ import annotations

import shutil
import unittest

from study_notes.practice.increments import kind_mix, plan_day
from study_notes.practice.js_problem import static_check
from study_notes.practice.models import parse_draft
from study_notes.practice.runner import VERIFIER_DIR, PyodideRunner
from study_notes.practice.verify import verify_problems


def js_draft(kind: str = "code_write", **over: object):
    raw = {
        "kind": kind, "language": "javascript", "prompt": "두 수를 더하는 `add(a, b)` 를 작성하세요. 예: add(1, 2) → 3",
        "starterCode": "function add(a, b) {\n  // 여기에\n}",
        "referenceSolution": "function add(a, b) {\n  return a + b;\n}",
        "hiddenTests": "assert(add(1, 2) === 3, '1 + 2');\nassert(add(-1, 1) === 0, '-1 + 1');",
        **over,
    }
    problem, reason = parse_draft(raw)
    assert problem, reason
    return problem


class DraftTests(unittest.TestCase):
    def test_language_marks_js(self) -> None:
        self.assertEqual(js_draft().packages, ["js"])
        python, _ = parse_draft({"kind": "code_write", "prompt": "p", "starterCode": "def f():\n    pass",
                                 "referenceSolution": "def f():\n    return 1", "hiddenTests": "assert f() == 1\nassert f()"})
        self.assertEqual(python.packages, [])

    def test_browser_and_node_only_names_are_refused(self) -> None:
        self.assertIn("document", static_check(js_draft(referenceSolution="function add(a, b) { document.title = a; return a + b; }")))
        self.assertIn("Math.random", static_check(js_draft(referenceSolution="function add(a, b) { return Math.random(); }")))
        self.assertIn("assert(", static_check(js_draft(hiddenTests="assert(add(1, 2) === 3, '하나');")))
        self.assertEqual(static_check(js_draft()), "")


class PlanTests(unittest.TestCase):
    def test_js_day_is_a_third_concepts(self) -> None:
        self.assertEqual(kind_mix(12, js=True),
                         {"concept": 4, "code_output": 2, "code_blank": 2, "code_fix": 2, "code_write": 1, "code_scratch": 1})

    def test_js_files_ask_for_javascript_and_html_with_script_for_web_js(self) -> None:
        lesson = "\n\n".join(f"let a{i} = {i};\nconsole.log(a{i} + '1');" for i in range(40))
        page = "<button id='b'>눌러</button>\n\n<script>\ndocument.getElementById('b').onclick = () => {};\n</script>\n\n" * 20
        plan = plan_day("d", [("01_core/02_types.js", "c", lesson), ("02_web/05_dom.html", "c", page)], {})
        counts = plan.kind_counts()
        self.assertIn('JavaScript 코드 문제("language": "javascript")', counts)
        self.assertIn("web_task", counts)
        note = plan.focus_note()
        self.assertIn('02_types.js: ', note)
        self.assertIn("(JavaScript", note)
        self.assertIn("(HTML + JavaScript", note)


@unittest.skipUnless(
    shutil.which("node") and (VERIFIER_DIR / "node_modules" / "jsdom").exists(),
    "node 또는 practice_verifier/node_modules 없음",
)
class NodeTests(unittest.TestCase):
    def test_js_write_passes_when_stub_fails_and_reference_passes(self) -> None:
        [verdict] = verify_problems([js_draft()], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual(verdict.problem.packages, ["js"])

    def test_js_output_takes_expected_from_execution(self) -> None:
        problem = js_draft("code_output", starterCode='console.log(3 + "3");\nconsole.log(3 - "3");', expectedStdout="틀린 추측")
        [verdict] = verify_problems([problem], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual(verdict.problem.expected_stdout, "33\n0")

    def test_js_blank_rejects_tests_that_null_passes(self) -> None:
        weak = js_draft("code_blank", starterCode="const double = (x) => x * __1__;", blankAnswers=["2"],
                        hiddenTests="assert(typeof double === 'function', '함수');\nassert(true, '항상');")
        [verdict] = verify_problems([weak], PyodideRunner())
        self.assertFalse(verdict.passed)

    def test_web_task_with_script_runs_in_jsdom(self) -> None:
        starter = "<input id='item'><button id='add'>추가</button><ul id='list'></ul>\n<script>\n// 여기에\n</script>"
        reference = starter.replace("// 여기에", "document.getElementById('add').addEventListener('click', () => {\n"
                                    "  const li = document.createElement('li');\n  li.textContent = document.getElementById('item').value;\n"
                                    "  document.getElementById('list').appendChild(li);\n});")
        problem, reason = parse_draft({
            "kind": "web_task", "prompt": "추가 버튼을 누르면 입력칸 글자로 #list 에 li 를 더하세요", "starterCode": starter,
            "referenceSolution": reference,
            "hiddenTests": "check(type('#item', '사과') && click('#add') && count('#list li') === 1, '항목이 하나 생겨요');\n"
                           "check(text('#list li') === '사과', '입력한 글자가 들어가요');",
        })
        assert problem, reason
        [verdict] = verify_problems([problem], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual(verdict.problem.packages, ["web-js"])


if __name__ == "__main__":
    unittest.main()
