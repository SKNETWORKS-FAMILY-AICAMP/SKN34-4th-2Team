"""사람이 치는 표기와 사람인이 붙인 태그 표기가 다르다.

`Spring Boot`라고 치면 태그에 걸린 공고가 0건이었다. 사람인은 `SpringBoot`로 붙인다.
띄어쓰기 하나에 354건이 사라졌고, 챗봇은 "200건 중 직무가 맞는 건 8건"이라고 답했다.
숫자도 틀렸고 "직무"라는 말도 틀렸다 — Spring Boot는 기술이다. (지금 답은 직무·기술을
가르는 말 없이 제목·태그에 맞은 건수만 말한다.)
"""

from __future__ import annotations

import unittest

from job_matching_bot.retrieval.store_search import spellings_of


class SpellingTest(unittest.TestCase):
    def test_a_spaced_name_finds_the_joined_tag(self):
        self.assertIn("SpringBoot", spellings_of("Spring Boot"))

    def test_an_abbreviation_finds_the_full_name(self):
        self.assertIn("Kubernetes", spellings_of("K8s"))

    def test_the_typed_word_comes_first(self):
        # 사용자가 친 말을 빼면 태그에 없는 말(제목·본문에만 있는 말)을 못 찾는다.
        self.assertEqual(spellings_of("REST API")[0], "REST API")

    def test_an_unknown_word_is_left_alone(self):
        self.assertEqual(spellings_of("우주비행"), ["우주비행"])

    def test_the_same_spelling_is_not_repeated(self):
        found = spellings_of("SpringBoot")
        self.assertEqual(len(found), len(set(s.lower() for s in found)))


if __name__ == "__main__":
    unittest.main()
