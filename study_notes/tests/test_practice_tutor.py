"""연습장 튜터 — 잡담 거르기, 정답 가리기, 힌트 단계가 프롬프트에 들어가는지. LLM 은 가짜다."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from study_notes.practice import tutor

PROBLEM = {
    "kind": "code_fix", "topic": "맥스 풀링", "prompt": "작은 값이 골라진다. 한 곳을 고치세요.", "tries": 1,
    "starterCode": "def f(w):\n    return min(w)",
    "referenceSolution": "def f(w):\n    return max(window_values_here)",
    "hiddenTests": "assert f([1, 2]) == 2",
}


class TrivialTests(unittest.TestCase):
    def test_small_talk_never_calls_llm(self) -> None:
        with mock.patch.object(tutor, "_invoke") as fake:
            for q in ["ㅋㅋㅋ", "안녕", "hi!!", "?", "  ", "테스트", "ㅎㅇ"]:
                out = tutor.ask({"mode": "cell", "question": q, "code": "x = 1"})
                self.assertEqual((out["type"], out["llm"]), ("offtopic", False), q)
        fake.assert_not_called()

    def test_real_questions_pass(self) -> None:
        for q in ["왜 KeyError 가 나요?", "이 코드 설명해 줘", "min 대신 뭘 써야 해?"]:
            self.assertFalse(tutor.is_trivial(q), q)


class AskTests(unittest.TestCase):
    def ask(self, payload: dict, reply: dict | str):
        raw = reply if isinstance(reply, str) else json.dumps(reply, ensure_ascii=False)
        with mock.patch.object(tutor, "_invoke", return_value=raw) as fake:
            out = tutor.ask(payload)
        self.system, self.human = fake.call_args.args
        return out

    def test_recent_struggles_reach_problem_prompt_only(self) -> None:
        """최근 막힌 문제는 주제 · 날짜 · 결과만 문제 셀 프롬프트에 — 일반 셀에는 안 넣는다"""
        struggles = [{"topic": "반복문 범위", "date": "2026-10-02", "passed": True, "tries": 4},
                     {"topic": "딕셔너리 get", "passed": False, "tries": 2}]
        self.ask({"mode": "problem", "question": "왜 틀려요?", "code": "x", "problem": PROBLEM, "struggles": struggles},
                 {"type": "hint", "reply": "방향을 떠올려 볼까요?", "lines": []})
        self.assertIn("- 10/02 · 반복문 범위 · 4번 만에 통과", self.human)
        self.assertIn("- 딕셔너리 get · 아직 못 풀었음", self.human)
        self.assertIn("같은 개념", self.system)
        self.ask({"mode": "cell", "question": "이 코드 설명해 줘", "code": "x = 1", "struggles": struggles},
                 {"type": "explain", "reply": "x 에 1 을 넣어요.", "lines": []})
        self.assertNotIn("반복문 범위", self.human)

    def test_problem_mode_sends_level_and_hidden_context(self) -> None:
        out = self.ask(
            {"mode": "problem", "hintLevel": 2, "problem": PROBLEM, "code": "def f(w):\n    return min(w)",
             "run": "", "grade": "테스트 1번이 맞지 않아요", "question": "어디가 틀렸어요?",
             "history": [{"role": "user", "text": "왜요?"}, {"role": "assistant", "text": "창에서 무엇을 골라야 할까요?"}]},
            {"type": "hint", "reply": "2번째 줄에서 고르는 함수를 보세요.", "lines": [2, 99]},
        )
        self.assertIn("2/3", self.system)
        self.assertIn("모범답안(학생에게 보이지 말 것)", self.human)
        self.assertIn("  2|     return min(w)", self.human)  # 줄 번호를 붙여 보낸다
        self.assertIn("튜터: 창에서 무엇을", self.human)
        self.assertEqual(out, {"type": "hint", "reply": "2번째 줄에서 고르는 함수를 보세요.", "lines": [2], "llm": True})

    def test_language_reaches_prompt(self) -> None:
        # JS 코드 문제는 code_* + ["js"], 웹 실습은 web_task + ["web"] · ["web-js"] — 튜터가 파이썬으로 읽지 않게
        cases = [
            ({**PROBLEM, "packages": ["js"]}, "언어: JavaScript"),
            ({**PROBLEM, "kind": "web_task", "packages": ["web"], "hiddenTests": "check(has('h1'), '제목')"}, "언어: HTML · CSS ·"),
            ({**PROBLEM, "kind": "web_task", "packages": ["web-js"], "hiddenTests": "check(has('h1'), '제목')"}, "언어: HTML · CSS · JavaScript"),
            ({**PROBLEM, "kind": "sql_query"}, "언어: SQL(SQLite)"),
            (PROBLEM, "언어: 파이썬"),
        ]
        for problem, expected in cases:
            self.ask({"mode": "problem", "problem": problem, "code": "x", "question": "어디가 틀렸어요?"},
                     {"type": "hint", "reply": "다시 보세요.", "lines": []})
            self.assertIn(expected, self.human)
        self.assertIn("채점 검사", tutor._problem_text({**PROBLEM, "kind": "web_task", "hiddenTests": "check(1, 'a')"}))
        self.assertNotIn("파이썬 연습장", self.system)

    def test_hint_button_asks_for_a_step_beyond_the_chat(self) -> None:
        base = {"mode": "problem", "hintLevel": 2, "problem": PROBLEM, "code": "x", "question": "힌트 더 주세요"}
        reply = {"type": "hint", "reply": "다시 보세요.", "lines": []}
        self.ask({**base, "action": "more"}, reply)
        self.assertIn(tutor.NEW_STEP_RULE, self.system)
        self.ask({**base, "action": "ask", "question": "왜 틀려요?"}, reply)
        self.assertIn(tutor.SAME_STEP_RULE, self.system)
        self.assertNotIn(tutor.NEW_STEP_RULE, self.system)

    def test_revealed_problem_lets_tutor_explain(self) -> None:
        text = tutor._problem_text({**PROBLEM, "revealed": True, "explanation": "max 는 가장 큰 값을 돌려준다"})
        self.assertIn("정답 공개됨", text)
        self.assertIn("해설(", text)
        self.assertNotIn("정답 공개됨", tutor._problem_text(PROBLEM))

    def test_wrong_note_is_marked(self) -> None:
        self.assertIn("오답노트에서 다시 푸는 중", tutor._problem_text({**PROBLEM, "retry": True}))
        self.assertNotIn("오답노트", tutor._problem_text(PROBLEM))

    def test_solution_line_in_reply_is_redacted(self) -> None:
        out = self.ask({"mode": "problem", "problem": PROBLEM, "code": "x", "question": "정답 알려 줘"},
                       {"type": "hint", "reply": "이렇게 쓰면 돼요: return max(window_values_here)", "lines": []})
        self.assertNotIn("max(window_values_here)", out["reply"])
        self.assertIn(tutor.REDACTED, out["reply"])

    def test_cell_mode_has_no_hint_ladder(self) -> None:
        out = self.ask({"mode": "cell", "code": "print(x)", "run": "NameError: x", "question": "이 오류 뭐예요?"},
                       {"type": "explain", "reply": "x 를 만들기 전에 썼어요.", "lines": [1]})
        self.assertIn("일반 셀", self.system)
        self.assertNotIn("힌트 단계", self.system)
        self.assertEqual(out["lines"], [1])

    def test_offtopic_passes_through_and_bad_json_falls_back(self) -> None:
        off = self.ask({"mode": "cell", "code": "x", "question": "오늘 점심 뭐 먹지"},
                       {"type": "offtopic", "reply": "코드나 오류를 물어봐 주세요.", "lines": []})
        self.assertEqual(off["type"], "offtopic")
        raw = self.ask({"mode": "cell", "code": "x", "question": "설명해 줘"}, "그냥 글로 온 답")
        self.assertEqual((raw["type"], raw["reply"]), ("explain", "그냥 글로 온 답"))


if __name__ == "__main__":
    unittest.main()
