"""후보를 LLM에 넘기기 전에 다시 세우는 규칙.

벡터 유사도는 후보 안에서 거의 평평하다(실측 폭 0.042~0.140). 기술 겹침은 넓게
흩어지고 LLM 판정과도 이어진다(높음 30% · 보통 19% · 낮음 10%). 그래서 둘을 섞는다.

여기서 지키는 약속 셋.

1. **기술 정보가 없는 공고를 벌주지 않는다.** 인덱스 공고의 53%가 그런 상태다.
   겹침을 0으로 치면 그 절반이 통째로 뒤로 밀린다.
2. **근거가 없으면 순서를 만들어내지 않는다.** 아무도 정보가 없으면 벡터 순서 그대로.
3. **같은 점수면 들어온 순서를 지킨다.** 매번 다른 결과가 나오면 안 된다.
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.matching.pre_ranker import (
    PreferredMatch,
    SkillMatch,
    pre_rank,
    preferred_match,
    skill_match,
)

MINE = ["React", "TypeScript", "Next.js"]


def _job(
    job_id: str,
    *,
    required: list[str] | None = None,
    stack: list[str] | None = None,
    description: str = "",
):
    return replace(
        mock_jobs()[0],
        job_id=job_id,
        source_job_id=job_id,
        required_skills=required or [],
        preferred_skills=[],
        tech_stack=stack or [],
        description=description,
    )


class SkillMatchTest(unittest.TestCase):
    def test_required_and_stack_are_pooled(self):
        """둘 중 하나만 보면 볼 수 있는 공고가 절반으로 준다. 저장소에서 각각 26%·35%다."""
        match = skill_match(_job("j1", required=["React"], stack=["TypeScript", "Java"]), MINE)
        self.assertEqual(("react", "typescript"), match.matched)
        self.assertEqual(3, match.pool_size)
        self.assertAlmostEqual(2 / 3, match.coverage)

    def test_aliases_are_folded(self):
        """`ReactJS`와 `React`가 다른 기술로 잡히면 점수가 새 나간다."""
        match = skill_match(_job("j2", stack=["ReactJS", "Node.js"]), ["react", "nodejs"])
        self.assertEqual(2, len(match.matched))

    def test_no_skill_data_is_unknown_not_zero(self):
        match = skill_match(_job("j3"), MINE)
        self.assertEqual(0, match.pool_size)
        self.assertIsNone(match.coverage, "정보 없음은 0%가 아니다")

    def test_untagged_job_is_read_from_its_requirement_sections(self):
        """태그가 없는 공고가 70%다. 요건 구간에 글로 적은 기술을 태그 대신 쓴다."""
        body = "회사 소개\nReact를 쓰는 회사입니다\n자격요건\n- TypeScript, Spring Boot 경험\n- AWS 클라우드를 운영해 본 분\n복리후생\n- Python 교육비 지원"
        match = skill_match(_job("j4", description=body), MINE)
        self.assertTrue(match.from_body)
        self.assertEqual(("typescript",), match.matched)
        self.assertEqual(4, match.pool_size, "TypeScript·Spring Boot·AWS·클라우드. 구간 밖의 React·Python은 안 센다")

    def test_tags_win_over_body_text(self):
        """기업이 고른 태그가 있으면 글은 보지 않는다."""
        match = skill_match(_job("j5", stack=["Java"], description="자격요건\n- React 경험"), MINE)
        self.assertFalse(match.from_body)
        self.assertEqual((), match.matched)

    def test_body_without_tech_is_still_unknown(self):
        match = skill_match(_job("j6", description="자격요건\n- 성실하고 책임감 있는 분"), MINE)
        self.assertIsNone(match.coverage)
        self.assertFalse(match.from_body)


class PreRankTest(unittest.TestCase):
    def test_skill_overlap_lifts_a_lower_ranked_job(self):
        """벡터가 앞선 공고보다, 기술이 확실히 겹치는 공고를 앞에 세운다."""
        ranked = pre_rank(
            ["벡터 1위", "기술 맞음", "벡터 꼴찌"],
            [0.50, 0.49, 0.48],
            [
                SkillMatch((), 5),
                SkillMatch(("react", "typescript", "nextjs"), 3),
                SkillMatch((), 4),
            ],
        )
        self.assertEqual(["기술 맞음", "벡터 1위", "벡터 꼴찌"], ranked)

    def test_the_vector_gap_is_read_relatively_not_absolutely(self):
        """후보 안에서 0~1로 편다. 코사인 값의 절대 폭이 아니라 서로의 위치가 기준이다.

        후보가 둘뿐이면 벡터 차이가 0.001이든 0.1이든 최대 폭으로 펴진다. 그래서 한쪽이
        벡터 1위, 다른 쪽이 겹침 1위면 반씩 섞은 점수가 같아지고 들어온 순서가 남는다.
        놀랄 일이 아니라 정한 동작이다.
        """
        args = (["벡터 1위", "겹침 1위"], [0.50, 0.48],
                [SkillMatch((), 3), SkillMatch(("react",), 1)])
        self.assertEqual(["벡터 1위", "겹침 1위"], pre_rank(*args))
        self.assertEqual(["겹침 1위", "벡터 1위"], pre_rank(*args, weight=0.6))

    def test_a_job_without_skill_data_keeps_its_place(self):
        """정보가 없다고 뒤로 밀지 않는다. 평균만큼 가진 것으로 본다."""
        ranked = pre_rank(
            ["겹침 높음", "정보 없음", "겹침 낮음"],
            [0.50, 0.49, 0.48],
            [SkillMatch(("react", "typescript"), 2), SkillMatch((), 0), SkillMatch((), 4)],
        )
        self.assertEqual(["겹침 높음", "정보 없음", "겹침 낮음"], ranked)
        self.assertLess(ranked.index("정보 없음"), ranked.index("겹침 낮음"))

    def test_nobody_has_data_keeps_vector_order(self):
        ranked = pre_rank(
            ["a", "b", "c"], [0.9, 0.5, 0.1], [SkillMatch((), 0)] * 3
        )
        self.assertEqual(["a", "b", "c"], ranked)

    def test_equal_scores_keep_input_order(self):
        ranked = pre_rank(["a", "b", "c"], [0.4, 0.4, 0.4], [SkillMatch((), 2)] * 3)
        self.assertEqual(["a", "b", "c"], ranked)

    def test_single_candidate_and_length_mismatch(self):
        self.assertEqual(["only"], pre_rank(["only"], [0.3], [SkillMatch((), 0)]))
        with self.assertRaises(ValueError):
            pre_rank(["a", "b"], [0.1], [SkillMatch((), 0)])

    def test_weight_zero_is_the_old_behaviour(self):
        """가중치를 0으로 두면 예전처럼 벡터 순서만 본다. 되돌릴 길을 남겨 둔다."""
        args = (["a", "b"], [0.40, 0.45], [SkillMatch(("react",), 1), SkillMatch((), 3)])
        self.assertEqual(["b", "a"], pre_rank(*args, weight=0.0))
        self.assertEqual(["a", "b"], pre_rank(*args, weight=1.0))


if __name__ == "__main__":
    unittest.main()


def _pref(job_id: str, *, certs: list[str] | None = None, majors: list[str] | None = None,
          terms: list[str] | None = None):
    return replace(
        mock_jobs()[0],
        job_id=job_id,
        source_job_id=job_id,
        preferred_certifications=certs or [],
        preferred_majors=majors or [],
        preferred_major_terms=terms or [],
    )


class PreferredMatchTest(unittest.TestCase):
    """우대 자격증·전공은 조건이 아니라 가점이다. 대조 규칙은 하드 필터와 같다."""

    def test_a_certification_matches_by_normalized_containment(self):
        match = preferred_match(_pref("j1", certs=["정보처리기사"]), ["정보처리기사 1급"], [])
        self.assertEqual(("정보처리기사",), match.certifications)
        self.assertTrue(match.hit)

    def test_an_unrelated_certification_does_not_match(self):
        self.assertFalse(preferred_match(_pref("j2", certs=["정보보안기사"]), ["SQLD"], []).hit)

    def test_a_major_matches_by_group_term_not_by_name(self):
        """`빅데이터과`는 `컴퓨터·소프트웨어`와 이름이 다르지만 `데이터`로 걸린다."""
        job = _pref("j3", majors=["컴퓨터·소프트웨어"], terms=["컴퓨터", "데이터"])
        self.assertTrue(preferred_match(job, [], ["빅데이터과(3년제)"]).hit)
        self.assertFalse(preferred_match(job, [], ["시각디자인학과"]).hit)

    def test_a_job_with_no_preferred_terms_matches_nothing(self):
        self.assertFalse(preferred_match(_pref("j4"), ["정보처리기사"], ["컴퓨터공학과"]).hit)


class BonusTest(unittest.TestCase):
    def test_matching_a_preferred_qualification_breaks_a_tie(self):
        """가점은 접전을 가르는 몫이다. 벌어진 순위를 뒤집지 않는다.

        후보 열둘 사이에서 벡터·기술 겹침이 같아지는 일은 흔하다. 그때 우대 자격증을
        가진 쪽이 앞에 선다.
        """
        ranked = pre_rank(
            ["앞에 있던 것", "우대 맞춤"],
            [0.50, 0.50],
            [SkillMatch((), 2)] * 2,
            [PreferredMatch(), PreferredMatch(certifications=("정보처리기사",))],
        )
        self.assertEqual(["우대 맞춤", "앞에 있던 것"], ranked)

    def test_the_bonus_is_too_small_to_overturn_a_clear_vector_gap(self):
        """0.05는 기술 겹침(0.5)의 십분의 일이다. 확실히 앞선 것을 못 이긴다."""
        ranked = pre_rank(
            ["벡터 1위", "가운데", "우대 맞춤 꼴찌"],
            [0.60, 0.50, 0.40],
            [SkillMatch((), 2)] * 3,
            [PreferredMatch(), PreferredMatch(), PreferredMatch(certifications=("SQLD",))],
        )
        self.assertEqual(["벡터 1위", "가운데", "우대 맞춤 꼴찌"], ranked)

    def test_a_job_without_preferred_terms_is_not_pushed_down(self):
        """우대 요건이 아예 없는 공고(표본의 89%)를 벌주면 안 된다.

        못 맞춘 것과 우대 요건이 없는 것은 둘 다 0이다. 빼지 않으니 서로의 순서는
        벡터·기술 겹침이 정한 그대로 남는다.
        """
        args = (["우대 없음", "우대 있는데 못 맞춤"], [0.50, 0.48], [SkillMatch((), 2)] * 2)
        without = pre_rank(*args)
        with_bonus = pre_rank(*args, [PreferredMatch(), PreferredMatch()])
        self.assertEqual(without, with_bonus)

    def test_the_bonus_does_not_overturn_a_real_gap(self):
        """가점은 비슷할 때 앞에 세우는 정도다. 기술이 확실히 겹치는 쪽을 못 이긴다."""
        ranked = pre_rank(
            ["기술 겹침 큼", "우대만 맞춤"],
            [0.50, 0.50],
            [SkillMatch(("react", "typescript"), 2), SkillMatch((), 4)],
            [PreferredMatch(), PreferredMatch(certifications=("SQLD",))],
        )
        self.assertEqual(["기술 겹침 큼", "우대만 맞춤"], ranked)

    def test_the_count_must_line_up(self):
        with self.assertRaises(ValueError):
            pre_rank(["a", "b"], [0.1, 0.2], [SkillMatch((), 0)] * 2, [PreferredMatch()])

    def test_passing_none_is_the_old_behaviour(self):
        args = (["a", "b", "c"], [0.9, 0.5, 0.1], [SkillMatch((), 0)] * 3)
        self.assertEqual(pre_rank(*args), pre_rank(*args, None))
