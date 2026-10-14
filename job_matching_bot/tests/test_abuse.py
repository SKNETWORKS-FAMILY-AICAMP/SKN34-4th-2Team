"""모델을 부르기 전에 막는 한 겹.

여기서 지키는 약속 둘.

1. **적어 둔 말은 확실히 막힌다.** 모델이 그날 어떻게 보든 상관없다. 호출도 안 나간다.
2. **문장은 막지 않는다.** "미친 듯이 준비했는데 안 되네"는 하소연이지 시비가 아니다.
   잘못 막힌 사람은 다시 물을 길이 없으므로, 놓치는 쪽을 택한다. 놓친 말은 모델이
   한 번 더 거른다.
"""

from __future__ import annotations

import unittest

from job_matching_bot.api.abuse import is_abuse


class BlockedTest(unittest.TestCase):
    """통째로 욕인 말."""

    def test_a_bare_insult(self):
        self.assertTrue(is_abuse("바보"))
        self.assertTrue(is_abuse("멍청이"))
        self.assertTrue(is_abuse("호구"))

    def test_punctuation_and_spaces_do_not_hide_it(self):
        self.assertTrue(is_abuse(" 바보!! "))
        self.assertTrue(is_abuse("바 보"))
        self.assertTrue(is_abuse("바보..."))

    def test_laughter_at_the_end_does_not_hide_it(self):
        self.assertTrue(is_abuse("바보ㅋㅋㅋ"))
        self.assertTrue(is_abuse("호구ㅎㅎ"))

    def test_a_one_letter_suffix_does_not_hide_it(self):
        self.assertTrue(is_abuse("바보야"))
        self.assertTrue(is_abuse("멍청아"))
        self.assertTrue(is_abuse("호구냐"))

    def test_repeating_it_does_not_hide_it(self):
        self.assertTrue(is_abuse("바보바보"))
        self.assertTrue(is_abuse("바보 바보 바보"))

    def test_english_too(self):
        self.assertTrue(is_abuse("stupid"))
        self.assertTrue(is_abuse("Idiot!"))


class AllowedTest(unittest.TestCase):
    """말 속에 들어 있을 뿐인 것. 여기서 막으면 진짜 취업 이야기가 걸린다."""

    def test_a_sentence_that_happens_to_contain_one(self):
        self.assertFalse(is_abuse("미친 듯이 준비했는데 안 되네요"))
        self.assertFalse(is_abuse("제가 바보처럼 느껴져요"))

    def test_a_recruiting_question_with_a_rough_word(self):
        """거칠게 말해도 채용 이야기면 통과다. 막는 기준은 말투가 아니라 무엇을 시켰나다."""
        self.assertFalse(is_abuse("채용에서 호구 안 되려면 뭘 봐야 해?"))
        self.assertFalse(is_abuse("연봉 협상에서 호구 잡히지 않는 법"))

    def test_ordinary_messages(self):
        self.assertFalse(is_abuse("안녕"))
        self.assertFalse(is_abuse("서울 백엔드 신입 찾아줘"))
        self.assertFalse(is_abuse("취업 너무 막막해"))

    def test_an_empty_message(self):
        self.assertFalse(is_abuse(""))
        self.assertFalse(is_abuse("   "))
        self.assertFalse(is_abuse("!!!"))


if __name__ == "__main__":
    unittest.main()
