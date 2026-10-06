"""연습장 튜터 — 「정답 알려 줘」 안내가 문제 셀에 실제로 있는 길을 가리키는지, 잡담 차단 중에도 공부 질문은 받는지."""

from datetime import date
from unittest.mock import Mock

from django.test import SimpleTestCase

from lms.practice_tutor import ON_TOPIC, STRUGGLE_LIMIT, _problem_payload, _struggles, _thread_key, locked_reply


def row(kind: str, packages: str = "[]", tries: int = 0, passed: bool = False) -> dict:
    return {"kind": kind, "packages": packages, "tries": tries, "passed": passed, "topic": "", "prompt": "", "choices": "[]", "explanation": "",
            "answer_index": None, "expected_stdout": "", "starter_code": "", "reference_solution": "x", "hidden_tests": "t"}


class LockedReplyTests(SimpleTestCase):
    def test_concept_and_output_point_to_submit_not_solution_button(self):
        # 개념 · 출력 예상은 「모범답안 보기」 단추가 없다 — 한 번 내면 정답 · 해설이 나온다
        self.assertIn("정답 확인", locked_reply(row("concept"), 1))
        self.assertIn("제출", locked_reply(row("code_output", '["js"]'), 1))
        for kind in ("concept", "code_output"):
            self.assertNotIn("모범답안", locked_reply(row(kind), 1))

    def test_after_submit_answer_is_already_on_screen(self):
        # 개념 · 출력 예상은 한 번 내면 정답 · 해설이 보인다 — 튜터도 해설한다
        self.assertIn("이미 나와 있어요", locked_reply(row("concept", tries=1), 1))
        self.assertTrue(_problem_payload(row("concept", tries=1))["revealed"])
        self.assertFalse(_problem_payload(row("concept"))["revealed"])
        # 코드 문제는 통과해야 해설이 보인다(두 번 틀려 모범답안이 열려도 해설은 아직)
        self.assertFalse(_problem_payload(row("code_fix", tries=3))["revealed"])
        self.assertTrue(_problem_payload(row("code_fix", passed=True))["revealed"])

    def test_code_problems_follow_reveal_rule(self):
        self.assertIn("2번 채점해 본 뒤", locked_reply(row("code_fix"), 2))
        self.assertIn("「모범답안 보기」에서", locked_reply(row("code_fix", tries=2), 2))
        # 웹 실습(code_write + ["web"])도 코드 문제와 같은 규칙
        self.assertIn("「모범답안 보기」에서", locked_reply(row("code_write", '["web"]', passed=True), 1))


class RetryThreadTests(SimpleTestCase):
    def test_wrong_note_gets_its_own_thread_per_day(self):
        # 복습 때 대화(set:…)와 따로, 날마다 새로 — 복습 때 받은 3단계 힌트가 오답노트에 떠 있지 않게
        self.assertEqual(_thread_key("problem", "ps-a", 3), "set:ps-a:3")
        self.assertEqual(_thread_key("problem", "ps-a", 3, "retry:2026-09-30"), "retry:2026-09-30:set:ps-a:3")
        self.assertNotEqual(_thread_key("problem", "ps-a", 3, "retry:2026-10-01"), _thread_key("problem", "ps-a", 3, "retry:2026-09-30"))

    def test_unknown_thread_values_fall_back_to_the_lesson_thread(self):
        for bad in ("", "retry", "retry:all", "x:2026-09-30", "retry:2026-09-30:set:ps-b:0"):
            self.assertEqual(_thread_key("problem", "ps-a", 3, bad), "set:ps-a:3", bad)
        self.assertEqual(_thread_key("cell", None, None, "retry:2026-09-30"), "cell")


class TutorPayloadTests(SimpleTestCase):
    def test_language_mark_reaches_ai_server(self):
        self.assertEqual(_problem_payload(row("code_fix", '["js"]'))["packages"], ["js"])
        web = _problem_payload(row("code_write", '["web-js"]'))
        self.assertEqual((web["kind"], web["packages"]), ("web_task", ["web-js"]))

    def test_web_and_js_questions_count_as_study(self):
        for q in ["태그가 안 보여요", "querySelector 가 뭐예요", "이벤트가 안 걸려요", "const 랑 let 차이"]:
            self.assertTrue(ON_TOPIC.search(q), q)
        self.assertFalse(ON_TOPIC.search("오늘 점심 뭐 먹지"))


class StruggleTests(SimpleTestCase):
    """튜터가 이어 짚을 「최근 막힌 문제」 — 주제 · 날짜 · 결과만, 주제가 겹치면 한 번, 최대 STRUGGLE_LIMIT 개."""

    COLUMNS = ("topic", "kind", "packages", "passed", "tries", "lesson_date")

    def _rows(self, rows):
        cur = Mock()
        cur.description = [(c,) for c in self.COLUMNS]
        cur.fetchall.return_value = rows
        return cur

    def test_dedupes_topics_and_keeps_only_safe_fields(self):
        cur = self._rows([
            ("반복문 범위", "code_fix", "[]", True, 4, date(2026, 10, 2)),
            ("반복문 범위", "code_blank", "[]", False, 2, date(2026, 10, 1)),
            ("GROUP BY", "code_write", '["sqlite3"]', False, 3, date(2026, 9, 30)),
        ])
        got = _struggles(cur, 7, 99)
        self.assertEqual(["반복문 범위", "GROUP BY"], [s["topic"] for s in got], "같은 주제는 가장 최근 한 번만")
        self.assertEqual({"topic", "kind", "passed", "tries", "date"}, set(got[0]), "코드 · 답은 보내지 않는다")
        self.assertEqual("sql_query", got[1]["kind"], "code_write + sqlite3 는 SQL 조회 문제로 되돌린다")
        self.assertEqual("2026-10-02", got[0]["date"])
        sql, args = cur.execute.call_args.args
        self.assertIn("a.problem_id <> %s", sql, "지금 문제는 빼고")
        self.assertEqual([7, 99], args[:2])

    def test_limit(self):
        cur = self._rows([(f"주제 {i}", "code_fix", "[]", False, 1, None) for i in range(STRUGGLE_LIMIT + 3)])
        got = _struggles(cur, 7, 1)
        self.assertEqual(STRUGGLE_LIMIT, len(got))
        self.assertEqual("", got[0]["date"], "수업 날짜가 없으면 빈 칸")
