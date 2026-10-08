"""한 세트 안의 겹치는 문제 — 찾기(dedupe.py), 빼고 그만큼 다시 채우기(build.py · auto.build_day). LLM · 실행기는 가짜."""

from __future__ import annotations

import unittest
from unittest import mock

from study_notes.practice import auto, build
from study_notes.practice.build import BuildResult, KindStats
from study_notes.practice.dedupe import overlap_reason, split_overlaps
from study_notes.practice.generate import DraftBatch, Usage
from study_notes.practice.models import KINDS, PracticeProblem
from study_notes.tests.test_practice_blind import ScriptedRunner, write_problem


def odd_sum() -> PracticeProblem:
    other = write_problem("odd_sum")
    other.reference_solution = "def odd_sum(xs):\n    total = 0\n    for x in xs:\n        if x % 2:\n            total += x\n    return total"
    return other


def problem(kind: str, topic: str, code: str, **over) -> PracticeProblem:
    field = {"code_output": "starter_code", "code_blank": "starter_code"}.get(kind, "reference_solution")
    return PracticeProblem(kind=kind, prompt=over.pop("prompt", "p"), topic=topic, **{field: code}, **over)


MISCLASSIFIED = "import numpy as np\ndef wrong_idx(y, p):\n    return np.where(y != p)[0]"


class OverlapTests(unittest.TestCase):
    def test_same_function_in_blank_and_fix_overlaps(self) -> None:
        # dl 07-31 「오분류 인덱스」를 빈칸 · 버그 고치기로 두 번
        blank = problem("code_blank", "오분류 인덱스 찾기", MISCLASSIFIED.replace("!=", "__1__"), blank_answers=["!="])
        fix = problem("code_fix", "오분류 조건 디버깅", MISCLASSIFIED)
        self.assertEqual("같은 함수를 짜게 함", overlap_reason(fix, blank))

    def test_answer_shown_in_another_problem_overlaps(self) -> None:
        # dl 07-31 다시 출제: 출력 문제가 np.where(…)[0] 를 보여 주고, 빈칸 문제가 그걸 채우라 했다
        output = problem("code_output", "오분류 개수 확인", "import numpy as np\ny = np.array([1, 0])\np = np.array([1, 1])\nprint(len(np.where(y != p)[0]))")
        blank = problem("code_blank", "오분류 인덱스 추출", "def wrong(y, p):\n    return __1__", blank_answers=["np.where(y != p)[0]"])
        self.assertEqual("답이 다른 문제 코드에 그대로 나옴", overlap_reason(blank, output))
        short = problem("code_blank", "짝수", "def even(x):\n    return __1__", blank_answers=["x % 2 == 0"])
        self.assertEqual("", overlap_reason(short, problem("code_output", "짝수 세기", "print([x for x in range(4) if x % 2 == 0])")))

    def test_same_template_with_other_values_overlaps(self) -> None:
        # database 06-25 「tb○에서 ○가 N인 행 조회」
        a = problem("code_write", "AUTO_INCREMENT 컬럼 조회", "SELECT pk, col1 FROM tb2 WHERE fk = 20;")
        b = problem("code_write", "테이블의 특정 행 조회", "SELECT pk, col1 FROM tb6 WHERE fk = 30;")
        self.assertEqual("정답 코드가 거의 같음", overlap_reason(b, a))

    def test_sql_with_same_skeleton_overlaps_even_with_other_names(self) -> None:
        # database 06-25 다시 출제 — 테이블 · 열 · 값이 다 다른 「X에서 Y가 N인 행 조회」 일곱 개
        a = PracticeProblem(kind="sql_query", prompt="p", topic="NOT NULL 테이블 조회", reference_solution="SELECT user_name, phone FROM user_notnull WHERE user_id = 'user03';")
        b = PracticeProblem(kind="sql_query", prompt="p", topic="회원 등급 조회", reference_solution="SELECT grade_name FROM user_grade WHERE grade_code = 20")
        c = PracticeProblem(kind="sql_query", prompt="p", topic="분류별 개수", reference_solution="SELECT category, COUNT(*) FROM menu GROUP BY category")
        self.assertEqual("SQL 뼈대가 같음(테이블 · 값만 바뀜)", overlap_reason(b, a))
        self.assertEqual("", overlap_reason(c, a))

    def test_table_making_overlaps_only_with_the_same_constraints(self) -> None:
        # database 06-25 다시 출제 — DEFAULT · UNIQUE 를 묻는 두 문제를 「주제 + 코드 닮음」으로 잘못 뺐다
        def ddl(topic: str, body: str) -> PracticeProblem:
            return PracticeProblem(kind="sql_query", prompt="p", topic=f"{topic} 제약 조건", check_sql="SELECT 1;",
                                   reference_solution=f"CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT {body});")
        unique, default = ddl("UNIQUE", "UNIQUE"), ddl("DEFAULT", "DEFAULT 'Y'")
        check_a, check_b = ddl("CHECK", "CHECK (v <> '')"), ddl("기본 키와 CHECK", "CHECK (length(v) > 1)")
        self.assertEqual("", overlap_reason(default, unique))
        self.assertEqual("같은 제약 조건을 다시 물음", overlap_reason(check_b, check_a))

    def test_same_instruction_but_different_code_is_not_overlap(self) -> None:
        ask = "다음 코드의 출력 결과를 순서대로 적으세요."
        a = problem("code_output", "다차원 배열 인덱싱", "import numpy as np\na = np.arange(6).reshape(2, 3)\nprint(a[1, 2])", prompt=ask)
        b = problem("code_output", "argsort로 정렬 순서 확인", "import numpy as np\nprint(np.argsort([3, 1, 2]))", prompt=ask)
        self.assertEqual("", overlap_reason(a, b))

    def test_methods_and_html_skeleton_are_not_overlap(self) -> None:
        a = problem("code_fix", "인스턴스별 리스트", "class Hero:\n    def __init__(self):\n        self.skills = []\n\n\nh = Hero()\nh.skills.append('a')\nprint(h.skills)")
        b = problem("code_blank", "다중 상속 생성자", "class Mentor:\n    def __init__(self, field):\n        self.field = field\nclass Lecturer(Mentor):\n    pass")
        self.assertEqual("", overlap_reason(b, a))
        page = "<!DOCTYPE html><html><head><style>#box {{ {} }}</style></head><body><div id='box'>x</div></body></html>"
        css_a = problem("code_write", "fixed 위치", page.format("position: fixed; top: 0;"))
        css_b = problem("code_write", "display 속성", page.format("display: block;"))
        self.assertEqual("", overlap_reason(css_b, css_a))

    def test_split_keeps_the_first_and_checks_against_kept(self) -> None:
        first, second, other = write_problem(), write_problem(), odd_sum()
        keep, dropped = split_overlaps([first, other, second])
        self.assertEqual([first, other], keep)
        self.assertEqual([(second, first, "같은 함수를 짜게 함")], dropped)
        keep, dropped = split_overlaps([second], kept=[first])
        self.assertEqual([], keep)


class BuildRefillTests(unittest.TestCase):
    def build(self, first: list[PracticeProblem], refill: list[PracticeProblem]):
        gen = mock.MagicMock(side_effect=[DraftBatch(first), DraftBatch(refill)])
        with mock.patch.object(build, "generate_drafts", gen):
            out = build.build_practice_set(scope_label="s", materials=[{"path": "a.py"}], runner=ScriptedRunner([]), blind=False)
        return out, gen

    def test_overlap_is_dropped_and_refilled_once_from_the_same_materials(self) -> None:
        out, gen = self.build([write_problem(), write_problem()], [odd_sum()])
        self.assertEqual(["even_sum", "odd_sum"], [p.prompt.split("`")[1].split("(")[0] for p in out.problems])
        refill = gen.call_args_list[1].kwargs
        self.assertEqual("code_write 1개", refill["kind_counts"])
        self.assertEqual([{"path": "a.py"}], refill["materials"])
        self.assertIn("이미 낸 문제", refill["focus_note"])
        stats = out.stats["code_write"]
        self.assertEqual((stats.passed_first, stats.overlapped, stats.refilled), (2, 1, 1))
        self.assertIn("겹침: 같은 함수를 짜게 함", out.dropped[0]["firstFailure"])

    def test_refill_that_overlaps_again_is_dropped(self) -> None:
        out, gen = self.build([write_problem(), write_problem()], [write_problem()])
        self.assertEqual(1, len(out.problems))
        self.assertEqual(2, gen.call_count, "채우기는 한 번만")
        self.assertIn("채운 문제도 겹침", out.dropped[-1]["firstFailure"])

    def test_no_overlap_means_no_extra_call(self) -> None:
        other = write_problem("odd_sum")
        other.reference_solution = "def odd_sum(xs):\n    return len([x for x in xs if x % 2])"
        out, gen = self.build([write_problem(), other], [])
        self.assertEqual(2, len(out.problems))
        self.assertEqual(1, gen.call_count)


class BuildDayAcrossBatchesTests(unittest.TestCase):
    def test_overlap_between_batches_is_refilled_from_the_later_batch(self) -> None:
        # 같은 주제의 exercise · question 이 다른 묶음에 들어간 날
        parts = [mock.MagicMock(), mock.MagicMock()]
        for i, part in enumerate(parts):
            part.materials.return_value = [{"path": f"{i}.py"}]
            part.focus_note.return_value = f"note {i}"
        plan = mock.MagicMock()
        plan.batches.return_value = parts
        a, b = write_problem(), write_problem()
        results = iter([
            BuildResult(problems=[a], stats={k: KindStats() for k in KINDS}, usage=Usage()),
            BuildResult(problems=[b], stats={k: KindStats() for k in KINDS}, usage=Usage()),
        ])
        refilled: list = []

        def refill(result, **kw):
            refilled.append((list(result.overlapped), kw["materials"]))
            result.problems.append(odd_sum())

        with mock.patch.object(auto, "build_practice_set", side_effect=lambda **kw: next(results)), \
                mock.patch.object(auto, "refill_overlaps", side_effect=refill):
            out = auto.build_day("2026-10-05", plan, ScriptedRunner([]))
        self.assertEqual([([b], [{"path": "1.py"}])], refilled)
        self.assertEqual([a], out.problems[:1])
        self.assertEqual(2, len(out.problems))
        self.assertEqual(1, out.stats["code_write"].overlapped)


if __name__ == "__main__":
    unittest.main()
