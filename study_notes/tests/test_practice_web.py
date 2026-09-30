"""웹 실습(web_task) — 실행 전 규칙, jsdom 검증(모범 통과 · 시작 실패), 학생 채점, 하루 구성.

앞쪽은 실행기 없이 규칙만 본다. 뒤쪽은 진짜 검증기(practice_verifier/web.mjs)를 부른다(node · jsdom 이 없으면 건너뛴다).
"""

from __future__ import annotations

import shutil
import unittest

from study_notes.practice.increments import kind_mix
from study_notes.practice.models import parse_draft
from study_notes.practice.runner import VERIFIER_DIR, PyodideRunner
from study_notes.practice.verify import verify_problems
from study_notes.practice.web_problem import static_check

STARTER = """<style>
  .menu { display: block; justify-content: left; }
</style>
<ul class="menu"><li>홈</li><li>소개</li><li>문의</li></ul>"""
REFERENCE = STARTER.replace("display: block; justify-content: left;", "display: flex; justify-content: center;")
CHECKS = "\n".join([
    "check(css('.menu', 'display') === 'flex', '메뉴가 가로 한 줄로 놓여요');",
    "check(css('.menu', 'justify-content') === 'center', '항목이 가운데 정렬돼요');",
    "check(count('.menu li') === 3, '항목이 세 개 있어요');",
])


def draft(**over: str):
    raw = {"kind": "web_task", "prompt": "메뉴를 가로 한 줄 · 가운데 정렬로", "starterCode": STARTER,
           "referenceSolution": REFERENCE, "hiddenTests": CHECKS, **over}
    problem, reason = parse_draft(raw)
    assert problem, reason
    return problem


class StaticRuleTests(unittest.TestCase):
    def test_good_problem_passes(self) -> None:
        self.assertEqual(static_check(draft()), "")

    def test_inline_script_marks_web_js_and_outside_script_is_refused(self) -> None:
        from study_notes.practice.web_problem import mark

        with_script = draft(referenceSolution=REFERENCE + "<script>document.title = 'x';</script>")
        self.assertEqual(static_check(with_script), "")
        self.assertEqual(mark(with_script), ["web-js"])
        self.assertEqual(mark(draft()), ["web"])
        self.assertIn("src", static_check(draft(referenceSolution=REFERENCE + '<script src="https://x/y.js"></script>')))

    def test_checks_are_one_line_calls_only(self) -> None:
        self.assertIn("check(", static_check(draft(hiddenTests=CHECKS + "\nconst x = 1;")))
        self.assertIn("쓸 수 없는", static_check(draft(hiddenTests=CHECKS + "\ncheck((() => true)(), '화살표');")))
        self.assertIn("쓸 수 없는", static_check(draft(hiddenTests=CHECKS + "\ncheck(this.constructor, '탈출');")))
        self.assertIn("검사문이 1줄", static_check(draft(hiddenTests="check(has('.menu'), '메뉴');")))


class GradeAuthTests(unittest.TestCase):
    """두 EC2 — 운영(토큰 있음)에서는 Django 의 토큰이 맞아야 검사문을 돌린다. 로컬(토큰 없음)은 그대로"""

    def check(self, env: str, sent: str | None) -> bool:
        from unittest import mock

        from fastapi import HTTPException

        from study_notes import api

        with mock.patch.dict("os.environ", {"LMS_AI_SHARED_TOKEN": env}):
            try:
                api._proxy_auth_if_configured(sent)
                return True
            except HTTPException:
                return False

    def test_token(self) -> None:
        self.assertTrue(self.check("", None), "로컬은 토큰 없이")
        self.assertTrue(self.check("secret-1", "secret-1"))
        self.assertFalse(self.check("secret-1", None))
        self.assertFalse(self.check("secret-1", "wrong"))


class DayMixTests(unittest.TestCase):
    def test_web_day_is_a_third_concepts(self) -> None:
        self.assertEqual(kind_mix(12, web=True), {"concept": 4, "web_task": 8})
        self.assertEqual(kind_mix(8, web=True), {"concept": 3, "web_task": 5})


@unittest.skipUnless(
    shutil.which("node") and (VERIFIER_DIR / "node_modules" / "jsdom").exists(),
    "node 또는 practice_verifier/node_modules/jsdom 없음",
)
class JsdomTests(unittest.TestCase):
    def test_reference_passes_and_starter_fails(self) -> None:
        [verdict] = verify_problems([draft()], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual(verdict.problem.packages, ["web"])

    def test_starter_that_already_passes_is_rejected(self) -> None:
        [verdict] = verify_problems([draft(starterCode=REFERENCE)], PyodideRunner())
        self.assertFalse(verdict.passed)
        self.assertIn("고칠 것이 없음", verdict.reason)

    def test_broken_reference_is_rejected_with_the_failing_check(self) -> None:
        [verdict] = verify_problems([draft(referenceSolution=STARTER.replace("block", "flex"))], PyodideRunner())
        self.assertFalse(verdict.passed)
        self.assertIn("항목이 가운데 정렬돼요", verdict.reason)

    def test_student_grading_lists_each_check(self) -> None:
        from study_notes import api

        half = STARTER.replace("display: block", "display: flex")
        out = api.proxy_practice_web_grade(api.ProxyWebGradeRequest(html=half, checks=CHECKS))
        self.assertFalse(out["passed"])
        self.assertEqual([c["ok"] for c in out["checks"]], [True, False, True])
        self.assertEqual(out["error"], "")
        self.assertTrue(api.proxy_practice_web_grade(api.ProxyWebGradeRequest(html=REFERENCE, checks=CHECKS))["passed"])


if __name__ == "__main__":
    unittest.main()
