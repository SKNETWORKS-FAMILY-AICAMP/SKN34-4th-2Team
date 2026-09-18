"""상세 큐 순서 — 인기순만으로는 뒤쪽 공고가 영영 안 받힌다.

큐는 밤마다 처음부터 다시 만들어진다. 인기 순위로만 세우면 순위가 밀린 공고는
어제도 뒤였고 오늘도 뒤다. 밤에 받는 양은 한정돼 있어(실측 4,200건 남짓) 차례가
오지 않는다. 실제로 목록에서 본 4만 건 중 1만 5천 건이 제목만 있는 채로 남았다.

그래서 다섯 자리 중 한 자리를 가장 오래 기다린 공고에 준다.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from job_matching_bot.crawling.detail_queue import OLDEST_EVERY, build_queue

NOW = datetime(2026, 9, 10, tzinfo=timezone.utc)


def record(job_id: str, rank: int, *, top: bool = False) -> dict:
    return {
        "source_job_id": job_id,
        "list_rank": rank,
        "badge": "TOP100" if top else "",
        "support_text": "~12.31(수)",
        "cat_mcls": "2",
        "job_sectors": [],
    }


class DetailQueueOrderTest(unittest.TestCase):
    def test_popular_first_when_nothing_is_waiting(self):
        """기다린 기록을 안 주면 예전 그대로 인기순이다."""
        records = [record(f"j{i}", rank=i) for i in range(5)]
        queue, _ = build_queue(list(reversed(records)), set(), NOW)

        self.assertEqual([r["source_job_id"] for r in queue], ["j0", "j1", "j2", "j3", "j4"])

    def test_the_longest_waiting_gets_every_fifth_slot(self):
        records = [record(f"j{i}", rank=i) for i in range(10)]
        # j9는 순위가 꼴찌라 인기순으로는 맨 뒤다. 그런데 가장 오래 기다렸다.
        waiting = {f"j{i}": f"2026-09-{9 - i:02d}" for i in range(10)}

        queue, _ = build_queue(records, set(), NOW, waiting)
        ids = [r["source_job_id"] for r in queue]

        self.assertEqual(len(ids), 10, "빠지거나 겹치는 공고가 없어야 한다")
        self.assertEqual(len(set(ids)), 10)
        self.assertEqual(ids[OLDEST_EVERY - 1], "j9", "다섯 번째 자리는 가장 오래 기다린 것")
        self.assertLess(ids.index("j9"), 5, "꼴찌 순위여도 앞쪽으로 온다")

    def test_popular_postings_still_lead(self):
        """한 자리를 떼어 줘도 앞자리는 인기 공고가 지킨다."""
        records = [record(f"j{i}", rank=i) for i in range(10)]
        waiting = {f"j{i}": f"2026-09-{9 - i:02d}" for i in range(10)}

        queue, _ = build_queue(records, set(), NOW, waiting)
        ids = [r["source_job_id"] for r in queue]

        self.assertEqual(ids[0], "j0")
        self.assertEqual(ids[1], "j1")

    def test_postings_without_a_first_seen_count_as_oldest(self):
        """그 값이 생기기 전에 쌓인 공고. 기록이 없다는 것 자체가 오래됐다는 뜻이다."""
        records = [record(f"j{i}", rank=i) for i in range(10)]
        waiting = {f"j{i}": "2026-09-09" for i in range(9)}  # j9만 빠져 있다

        queue, _ = build_queue(records, set(), NOW, waiting)
        ids = [r["source_job_id"] for r in queue]

        self.assertLess(ids.index("j9"), 5)

    def test_nothing_is_lost_or_duplicated(self):
        records = [record(f"j{i}", rank=i, top=i % 3 == 0) for i in range(37)]
        waiting = {f"j{i}": f"2026-08-{(i % 28) + 1:02d}" for i in range(37)}

        queue, stats = build_queue(records, set(), NOW, waiting)
        ids = [r["source_job_id"] for r in queue]

        self.assertEqual(sorted(ids), sorted(r["source_job_id"] for r in records))
        self.assertEqual(stats["큐에 담김"], 37)


if __name__ == "__main__":
    unittest.main()


def in_category(job_id: str, cat: str, rank: int = 1) -> dict:
    return {**record(job_id, rank), "cat_mcls": cat}


class DetailCategoryTest(unittest.TestCase):
    """목록은 전부 훑되 상세는 고른 대분류만 받는다.

    일요일 전체 훑기가 14개 대분류를 훑는다. IT 밖 대분류의 상세까지 다 받으려면
    13만 건에 38일이 걸려, 하룻밤 4,500건으로는 다음 일요일 전에 못 끝낸다. 그러면
    큐 숫자가 "밀린 양"이라는 뜻을 잃는다.

    목록만 훑어도 **사라짐 판정은 그대로 된다.** 그게 일요일 훑기의 다른 역할이고
    거기에는 상세가 필요 없다.
    """

    def test_only_the_chosen_categories_enter_the_queue(self):
        records = [
            in_category("a", "2"),    # IT개발·데이터
            in_category("b", "9"),    # 연구·R&D
            in_category("c", "1"),    # 매일 훑지 않는 대분류
            in_category("d", "4"),
        ]
        queue, stats = build_queue(records, set(), NOW, detail_categories=("2", "9"))
        self.assertEqual(["a", "b"], [r["source_job_id"] for r in queue])
        self.assertEqual(2, stats["상세 대상 아닌 대분류"])

    def test_giving_no_list_keeps_everything(self):
        """예전과 같은 동작. 인자를 안 주면 전부 담는다."""
        records = [in_category("a", "2"), in_category("c", "1")]
        queue, _ = build_queue(records, set(), NOW)
        self.assertEqual(["a", "c"], [r["source_job_id"] for r in queue])

    def test_widening_is_one_more_category(self):
        """넓히는 방법이 대분류 하나를 더하는 것이어야 한다."""
        records = [in_category(str(i), "15") for i in range(3)]
        self.assertEqual(0, len(build_queue(records, set(), NOW, detail_categories=("2",))[0]))
        self.assertEqual(3, len(build_queue(records, set(), NOW, detail_categories=("2", "15"))[0]))

    def test_the_order_rules_still_apply_inside_the_kept_categories(self):
        records = [
            {**record("popular", 1, top=True), "cat_mcls": "2"},
            {**record("plain", 50), "cat_mcls": "2"},
            {**record("other", 1, top=True), "cat_mcls": "1"},
        ]
        queue, _ = build_queue(records, set(), NOW, detail_categories=("2",))
        self.assertEqual(["popular", "plain"], [r["source_job_id"] for r in queue])
