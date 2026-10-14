"""마감·삭제된 공고가 추천 후보로 나오지 않는지.

두 군데서 새고 있었다.

1. 조건이 좁아 0건이면 **필터를 통째로 버리고** 다시 찾았다. 좁히는 조건(지역·경력)만
   풀 생각이었는데 `status: OPEN` 까지 같이 풀렸다.
2. 마감 지난 공고를 인덱스에서 빼는 일은 야간 배치가 한다. 하루에 한 번이라 오늘
   마감인 공고가 내일 낮까지 남는다. 챗봇 조건 검색은 SQL 에서 매번 거르는데 추천만
   그러지 못했다.
"""

from __future__ import annotations

import unittest

from job_matching_bot.retrieval.search import OPEN_ONLY, drop_closed

TODAY = "2026-09-08"


def match(status="OPEN", deadline=None, job_id="SARAMIN-1"):
    meta = {"status": status}
    if deadline is not None:
        meta["deadline"] = deadline
    return {"id": job_id, "score": 0.5, "metadata": meta}


class DropClosedTest(unittest.TestCase):
    def kept(self, *matches):
        return [m["id"] for m in drop_closed(list(matches), TODAY)]

    def test_a_future_deadline_stays(self):
        self.assertEqual(["SARAMIN-1"], self.kept(match(deadline="2026-09-30")))

    def test_todays_deadline_stays(self):
        """오늘 마감이면 오늘까지는 지원할 수 있다."""
        self.assertEqual(["SARAMIN-1"], self.kept(match(deadline=TODAY)))

    def test_yesterdays_deadline_is_dropped(self):
        self.assertEqual([], self.kept(match(deadline="2026-09-07")))

    def test_no_deadline_stays(self):
        """"채용 시 마감" 같은 공고. 날짜로는 판단할 수 없으니 남긴다."""
        self.assertEqual(["SARAMIN-1"], self.kept(match()))

    def test_a_closed_posting_is_dropped(self):
        self.assertEqual([], self.kept(match(status="CLOSED", deadline="2026-12-31")))

    def test_a_removed_posting_is_dropped(self):
        self.assertEqual([], self.kept(match(status="REMOVED")))

    def test_metadata_without_status_is_treated_as_open(self):
        """옛 벡터에 status 가 없을 수 있다. 없다고 버리면 멀쩡한 공고를 잃는다."""
        self.assertEqual(["SARAMIN-1"], self.kept({"id": "SARAMIN-1", "metadata": {}}))

    def test_only_the_bad_ones_are_dropped(self):
        kept = self.kept(
            match(deadline="2026-09-30", job_id="A"),
            match(deadline="2026-09-01", job_id="B"),
            match(status="CLOSED", job_id="C"),
            match(job_id="D"),
        )
        self.assertEqual(["A", "D"], kept)


class OpenOnlyFilterTest(unittest.TestCase):
    """넓히는 재검색에서도 열려 있는 공고만 본다."""

    def test_the_fallback_filter_still_pins_open(self):
        self.assertEqual({"status": {"$eq": "OPEN"}}, OPEN_ONLY)


if __name__ == "__main__":
    unittest.main()
