"""기술명 표준화 검증. 사람인 태그 어휘와 이력서 표기가 같은 키로 모이는지 본다."""

import unittest

from job_matching_bot.matching.skill_normalize import canonical_set, canonical_skill


class CanonicalSkillTest(unittest.TestCase):
    def test_saramin_tag_variants_collapse(self):
        # 실제 사람인 기술스택 태그에 함께 나오는 표기들
        self.assertEqual(canonical_skill("React"), canonical_skill("ReactJS"))
        self.assertEqual(canonical_skill("Node.js"), canonical_skill("nodejs"))
        self.assertEqual(canonical_skill("Vue.js"), canonical_skill("Vue"))
        self.assertEqual(canonical_skill("CSS3"), canonical_skill("CSS"))

    def test_resume_spellings_match_tags(self):
        self.assertEqual(canonical_skill("Spring Boot"), canonical_skill("SpringBoot"))
        self.assertEqual(canonical_skill("REST API"), canonical_skill("RestAPI"))
        self.assertEqual(canonical_skill("Postgres"), canonical_skill("PostgreSQL"))
        self.assertEqual(canonical_skill("React Native"), canonical_skill("React-Native"))
        self.assertEqual(canonical_skill("Go"), canonical_skill("GoLang"))
        self.assertEqual(canonical_skill("k8s"), canonical_skill("Kubernetes"))

    def test_c_family_stays_distinct(self):
        # 기호를 다 지우면 C/C++/C#이 하나로 뭉개진다.
        keys = {canonical_skill(name) for name in ("C", "C++", "C#", "C언어")}
        self.assertEqual({"c", "c++", "c#"}, keys)

    def test_ambiguous_abbreviations_are_not_folded(self):
        # "ts"는 TypeScript일 수도, 다른 뜻일 수도 있어 접지 않는다.
        self.assertNotEqual(canonical_skill("ts"), canonical_skill("TypeScript"))

    def test_blank_entries_are_dropped_from_sets(self):
        self.assertEqual({"python"}, canonical_set(["Python", "", "  "]))


if __name__ == "__main__":
    unittest.main()
