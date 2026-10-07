"""SQL 조회 문제(sql_query) — 출제 초안 · 검증 규칙 · 하루 구성.

검증 하네스는 파이썬 sqlite3 만 쓰므로 여기서는 CPython 으로 직접 돌린다(LocalRunner). 진짜 Pyodide 검증기는
맨 끝 클래스가 부른다(node 와 practice_verifier/node_modules 가 없으면 건너뛴다).
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import unittest

from study_notes.practice import sql_problem
from study_notes.practice.increments import _sql_tag, kind_mix
from study_notes.practice.models import PracticeProblem, parse_draft
from study_notes.practice.runner import VERIFIER_DIR, Job, PyodideRunner, RunResult
from study_notes.practice.verify import verify_problems

SETUP = """CREATE TABLE tbl_category (category_code INTEGER PRIMARY KEY, category_name VARCHAR(30) NOT NULL);
CREATE TABLE tbl_menu (menu_code INTEGER PRIMARY KEY, menu_name VARCHAR(30), menu_price INT, category_code INT);
INSERT INTO tbl_category VALUES (1, '한식'), (2, '일식');
INSERT INTO tbl_menu VALUES (1, '김치찌개', 9000, 1), (2, '붕어빵초밥', 35000, 2), (3, '민트미역국', 15000, 1);
"""
REFERENCE = """SELECT a.menu_name, b.category_name
FROM tbl_menu a JOIN tbl_category b USING (category_code)
WHERE a.menu_price >= 10000
ORDER BY a.menu_price DESC;"""


class LocalRunner:
    """작업을 이 파이썬에서 바로 돌린다 — 하네스가 sqlite3 만 쓰므로 검증기와 같은 결과가 나온다."""

    def run(self, jobs: list[Job]) -> dict[str, RunResult]:
        out = {}
        for job in jobs:
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    for step in job.steps:
                        exec(step, {"__name__": "__main__"})
                out[job.id] = RunResult(id=job.id, ok=True, stdout=buf.getvalue(), timed_out=False)
            except Exception as exc:  # noqa: BLE001
                out[job.id] = RunResult(id=job.id, ok=False, stdout=buf.getvalue(), timed_out=False,
                                        error_type=type(exc).__name__, error_message=str(exc), error_step=0)
        return out


def sql_problem_(query: str = REFERENCE, setup: str = SETUP, starter: str = "-- 여기에 조회문을 쓰세요\n") -> PracticeProblem:
    return PracticeProblem(kind="sql_query", prompt="만 원 이상 메뉴의 이름과 분류를 비싼 순으로", setup_sql=setup,
                           reference_solution=query, starter_code=starter)


class DraftTests(unittest.TestCase):
    def test_sql_draft_needs_setup_and_reference(self) -> None:
        problem, reason = parse_draft({"kind": "sql_query", "prompt": "조회", "setupSql": SETUP, "referenceSolution": REFERENCE})
        self.assertEqual("", reason)
        self.assertTrue(problem.starter_code.startswith("--"), "시작 칸을 비우면 주석 한 줄")
        self.assertEqual("setupSql", next(k for k in problem.to_json() if k.startswith("setup")))
        self.assertIsNone(parse_draft({"kind": "sql_query", "prompt": "조회", "referenceSolution": REFERENCE})[0])

    def test_sql_day_is_concepts_plus_sql_queries(self) -> None:
        self.assertEqual({"concept": 2, "sql_query": 10}, kind_mix(12, sql=True))
        self.assertEqual({"concept": 1, "sql_query": 3}, kind_mix(4, sql=True))
        self.assertNotIn("sql_query", kind_mix(12))


class VerifyTests(unittest.TestCase):
    def test_reference_result_becomes_the_expected_table(self) -> None:
        [verdict] = verify_problems([sql_problem_()], LocalRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        expected = json.loads(verdict.problem.expected_stdout)
        self.assertEqual({"columns": ["menu_name", "category_name"], "rows": [["붕어빵초밥", "일식"], ["민트미역국", "한식"]],
                          "ordered": True}, expected)
        self.assertEqual(["sqlite3"], verdict.problem.packages)

    def test_values_are_written_like_the_browser_worker(self) -> None:
        [verdict] = verify_problems([sql_problem_("SELECT AVG(menu_price), NULL FROM tbl_menu")], LocalRunner())
        self.assertEqual([["19666.7", "NULL"]], json.loads(verdict.problem.expected_stdout)["rows"])
        self.assertFalse(json.loads(verdict.problem.expected_stdout)["ordered"])

    def test_rejects_empty_results_and_broken_setup(self) -> None:
        empty, broken = verify_problems(
            [sql_problem_("SELECT menu_name FROM tbl_menu WHERE menu_price > 99999"), sql_problem_(setup=SETUP + "INSERT INTO nope VALUES (1);")],
            LocalRunner(),
        )
        self.assertIn("0행", empty.reason)
        self.assertIn("실행 오류", broken.reason)

    def test_rejects_before_running(self) -> None:
        for query, setup, why in [
            ("UPDATE tbl_menu SET menu_price = 0", SETUP, "SELECT"),
            ("SELECT menu_name, NOW() FROM tbl_menu", SETUP, "NOW"),
            (REFERENCE, "SELECT 1", "CREATE TABLE"),
        ]:
            [verdict] = verify_problems([sql_problem_(query, setup)], LocalRunner())
            self.assertFalse(verdict.passed)
            self.assertIn(why, verdict.reason)

    def test_rejects_when_the_starter_already_gives_the_answer(self) -> None:
        [verdict] = verify_problems([sql_problem_(starter=REFERENCE)], LocalRunner())
        self.assertIn("시작 코드", verdict.reason)


MEMBER = """CREATE TABLE member (
  member_id INTEGER PRIMARY KEY,
  name VARCHAR(20) NOT NULL,
  age INT CHECK (age >= 0 AND (age < 200)),
  email VARCHAR(50) UNIQUE,
  status CHAR(1) DEFAULT 'Y'
);"""
MEMBER_CHECKS = """INSERT OR IGNORE INTO member (member_id, name, age, email) VALUES (1, '김', 20, 'a@x');
INSERT OR IGNORE INTO member (member_id, name, age, email) VALUES (2, NULL, 30, 'b@x');
INSERT OR IGNORE INTO member (member_id, name, age, email) VALUES (3, '이', -5, 'c@x');
INSERT OR IGNORE INTO member (member_id, name, age, email) VALUES (4, '박', 40, 'a@x');
SELECT member_id, name, status FROM member ORDER BY member_id;"""
GRADE = "PRAGMA foreign_keys = ON;\nCREATE TABLE grade (code INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO grade VALUES (10, '일반'), (20, '우수');"
CHILD = "CREATE TABLE child (id INTEGER PRIMARY KEY, grade INT REFERENCES grade(code) ON DELETE SET NULL);"
CHILD_CHECKS = """INSERT OR IGNORE INTO child VALUES (1, 10);
INSERT OR IGNORE INTO child VALUES (2, 20);
DELETE FROM grade WHERE code = 20;
SELECT id, grade FROM child ORDER BY id;"""


def ddl_problem(reference: str = MEMBER, checks: str = MEMBER_CHECKS, setup: str = "") -> PracticeProblem:
    return PracticeProblem(kind="sql_query", prompt="회원 테이블을 만드세요", setup_sql=setup, reference_solution=reference,
                           check_sql=checks, starter_code="-- 여기에 CREATE TABLE 문을 쓰세요\n")


class TableMakingTests(unittest.TestCase):
    """테이블 만들기 — 학생 CREATE TABLE 뒤 확인 문장(INSERT OR IGNORE …)의 표로 제약을 본다"""

    def test_draft_without_setup_is_fine_and_starter_asks_for_create_table(self) -> None:
        problem, reason = parse_draft({"kind": "sql_query", "prompt": "만들기", "referenceSolution": MEMBER, "checkSql": MEMBER_CHECKS})
        self.assertEqual("", reason)
        self.assertIn("CREATE TABLE", problem.starter_code)

    def test_constraints_show_in_the_expected_table_and_checks_go_with_it(self) -> None:
        [verdict] = verify_problems([ddl_problem()], LocalRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        expected = json.loads(verdict.problem.expected_stdout)
        # NULL 이름 · 음수 나이 · 겹친 이메일 행은 빠지고, 안 넣은 상태는 기본값
        self.assertEqual([["1", "김", "Y"]], expected["rows"])
        self.assertTrue(expected["ordered"])
        self.assertEqual(MEMBER_CHECKS, expected["after"])

    def test_checks_that_do_not_test_any_constraint_are_rejected(self) -> None:
        plain = "INSERT OR IGNORE INTO member (member_id, name, age, email, status) VALUES (1, '김', 20, 'a@x', 'N');\nSELECT name FROM member;"
        [verdict] = verify_problems([ddl_problem(checks=plain)], LocalRunner())
        self.assertFalse(verdict.passed)
        self.assertIn("제약 조건을 모두 빼고", verdict.reason)

    def test_foreign_key_is_checked_through_on_delete(self) -> None:
        [verdict] = verify_problems([ddl_problem(CHILD, CHILD_CHECKS, GRADE)], LocalRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual([["1", "10"], ["2", "NULL"]], json.loads(verdict.problem.expected_stdout)["rows"])

    def test_rejects_before_running(self) -> None:
        for reference, checks, why in [
            ("SELECT 1", MEMBER_CHECKS, "CREATE TABLE 이 없음"),
            (MEMBER + "\nINSERT INTO member VALUES (1, 'a', 1, 'x', 'Y');", MEMBER_CHECKS, "다른 문장"),
            (MEMBER, "SELECT * FROM member;", "INSERT 가 없음"),
            (MEMBER, "INSERT OR IGNORE INTO member (member_id, name) VALUES (1, 'a');", "SELECT"),
        ]:
            [verdict] = verify_problems([ddl_problem(reference, checks)], LocalRunner())
            self.assertFalse(verdict.passed)
            self.assertIn(why, verdict.reason)

    def test_ddl_lesson_files_ask_for_table_making(self) -> None:
        # 제약 조건 수업 — 만든 테이블을 SELECT * FROM t; 로 들여다보기만 한다(database 3. Constraints.sql)
        constraints = (MEMBER + "\nINSERT INTO member VALUES (1, 'a', 1, 'x', 'Y');\nSELECT * FROM member;\n") * 3
        self.assertIn("모두 테이블 만들기", _sql_tag(constraints))
        self.assertEqual("", _sql_tag(SETUP + REFERENCE * 5), "조회 수업(CREATE TABLE 은 예제 준비뿐)")
        self.assertIn("나눠서", _sql_tag(MEMBER * 2 + REFERENCE * 3))

    def test_loosened_drops_constraints_but_keeps_keys(self) -> None:
        loose = sql_problem.loosened(
            "-- 회원\nCREATE TABLE m (id INTEGER PRIMARY KEY, name TEXT NOT NULL, age INT CHECK (age >= 0 AND (age < 9)),"
            " g INT REFERENCES grade(code) ON DELETE CASCADE, s CHAR(1) DEFAULT 'Y', CONSTRAINT uq UNIQUE (name));"
        )
        for gone in ("NOT NULL", "CHECK", "DEFAULT", "UNIQUE", "CASCADE", "회원"):
            self.assertNotIn(gone, loose)
        self.assertIn("PRIMARY KEY", loose)
        self.assertIn("REFERENCES grade(code)", loose)


@unittest.skipUnless(shutil.which("node") and (VERIFIER_DIR / "node_modules" / "pyodide").exists(), "Pyodide 검증기 없음")
class PyodideTests(unittest.TestCase):
    def test_the_real_verifier_gives_the_same_table(self) -> None:
        [verdict] = verify_problems([sql_problem_()], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual([["붕어빵초밥", "일식"], ["민트미역국", "한식"]], json.loads(verdict.problem.expected_stdout)["rows"])

    def test_the_real_verifier_runs_table_making(self) -> None:
        [verdict] = verify_problems([ddl_problem()], PyodideRunner())
        self.assertTrue(verdict.passed, verdict.reason)
        self.assertEqual([["1", "김", "Y"]], json.loads(verdict.problem.expected_stdout)["rows"])


if __name__ == "__main__":
    unittest.main()
