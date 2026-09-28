"""잡코리아 목록 훑기 — 빈 쪽 · 1만 벽 · 쪼개 받기. 사이트는 부르지 않는다(가짜 목록).

2026-09-28 에 확인한 사이트 동작(jobkorea 모듈 설명 5 · 6):
- 목록 중간에 빈 쪽이 끼어 있다. 빈 쪽에서 멈추면 뒤의 공고를 통째로 놓친다
- 한 목록은 200쪽(1만 건)까지만 보여 주고, 그 뒤로는 200쪽이 되풀이된다
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from job_matching_bot.crawling import jobkorea


def _row(gno: str) -> dict:
    return {"source_job_id": gno}


class FakeSite:
    """`fetch_page` 대신. 거르기(filters)마다 쪽 목록과 총 건수를 준다."""

    def __init__(self, lists: dict[tuple, tuple[list[list[str]], int | None]]):
        self.lists = lists
        self.calls: list[tuple] = []

    def __call__(self, session, duty, page, *, page_size=50, filters=None, **_):
        key = tuple(sorted((filters or {}).items()))
        self.calls.append((key, page))
        pages, total = self.lists[key]
        if page <= len(pages):
            return [_row(g) for g in pages[page - 1]], total
        # 벽 흉내: 마지막 쪽이 되풀이된다
        return [_row(g) for g in pages[-1]], total


def _sweep(site: FakeSite, **kwargs) -> tuple[list[str], dict, dict]:
    totals: dict = {}
    swept: dict = {}
    with patch.object(jobkorea, "fetch_page", site), patch.object(jobkorea, "polite_delay", lambda *a: None):
        rows = list(jobkorea.sweep_category(None, "10028", page_size=2, totals=totals, swept=swept, **kwargs))
    return [r["source_job_id"] for r in rows], totals, swept


class HolesTest(unittest.TestCase):
    def test_empty_page_in_the_middle_does_not_end_the_sweep(self):
        # 총 8건 → 4쪽. 2쪽이 비어 있다(사이트가 숨긴 자리)
        site = FakeSite({(): ([["a", "b"], [], ["c", "d"], ["e", "f"]], 8)})
        ids, totals, swept = _sweep(site)
        self.assertEqual(["a", "b", "c", "d", "e", "f"], ids)
        self.assertEqual({"10028": 8}, totals)
        self.assertEqual({"10028": True}, swept, "끝 쪽까지 넘겼으면 받은 수가 총 건수보다 적어도 완전")

    def test_stops_at_the_last_page_from_the_total(self):
        site = FakeSite({(): ([["a", "b"], ["c"]], 3)})
        ids, _, swept = _sweep(site)
        self.assertEqual(["a", "b", "c"], ids)
        self.assertEqual([((), 1), ((), 2)], site.calls, "끝 쪽 뒤로는 묻지 않는다")
        self.assertTrue(swept["10028"])

    def test_without_a_total_it_stops_at_the_first_empty_page_as_before(self):
        site = FakeSite({(): ([["a", "b"], [], ["c", "d"]], None)})
        ids, _, _ = _sweep(site)
        self.assertEqual(["a", "b"], ids)

    def test_repeated_page_is_the_wall_and_not_complete(self):
        # 총 12건 → 6쪽이라는데 3쪽부터 2쪽이 되풀이된다
        site = FakeSite({(): ([["a", "b"], ["c", "d"]], 12)})
        ids, _, swept = _sweep(site)
        self.assertEqual(["a", "b", "c", "d"], ids)
        self.assertFalse(swept["10028"])

    def test_page_cap_for_trials_is_not_complete(self):
        site = FakeSite({(): ([["a", "b"], ["c", "d"], ["e"]], 5)})
        ids, _, swept = _sweep(site, max_pages=2)
        self.assertEqual(["a", "b", "c", "d"], ids)
        self.assertFalse(swept["10028"])


class SplitOverWallTest(unittest.TestCase):
    def setUp(self):
        self.wall = patch.object(jobkorea, "LIST_WALL", 4)
        self.regions = patch.object(jobkorea, "REGION_CODES", ("I000", "B000"))
        self.careers = patch.object(jobkorea, "CAREER_CODES", ("1", "2"))
        for p in (self.wall, self.regions, self.careers):
            p.start()
            self.addCleanup(p.stop)

    def test_over_the_wall_is_split_by_region_then_career_and_merged(self):
        site = FakeSite({
            (): ([["a", "b"]], 9),                                    # 대분류 전체 9건 > 벽 4
            (("local", "I000"),): ([["a", "b"], ["c"]], 3),           # 서울 3건 — 그대로
            (("local", "B000"),): ([["d", "e"]], 6),                  # 경기 6건 > 벽 — 경력으로
            (("career", "1"), ("local", "B000")): ([["d", "e"], ["c", "f"]], 4),  # c 는 서울에도 있다
            (("career", "2"), ("local", "B000")): ([["g", "h"], ["i"]], 3),
        })
        ids, totals, swept = _sweep(site)
        self.assertEqual(["a", "b", "c", "d", "e", "f", "g", "h", "i"], ids, "여러 조각에 걸친 공고는 한 번만")
        self.assertEqual({"10028": 9}, totals)
        self.assertTrue(swept["10028"])

    def test_a_slice_still_over_the_wall_is_not_complete(self):
        site = FakeSite({
            (): ([["a"]], 9),
            (("local", "I000"),): ([["a"]], 1),
            (("local", "B000"),): ([["b"]], 8),
            (("career", "1"), ("local", "B000")): ([["b", "c"], ["d", "e"]], 6),  # 경력으로 쪼개도 벽
            (("career", "2"), ("local", "B000")): ([["f"]], 1),
        })
        _, _, swept = _sweep(site)
        self.assertFalse(swept["10028"])


if __name__ == "__main__":
    unittest.main()
