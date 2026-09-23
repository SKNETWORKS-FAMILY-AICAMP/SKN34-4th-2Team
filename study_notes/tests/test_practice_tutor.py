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
