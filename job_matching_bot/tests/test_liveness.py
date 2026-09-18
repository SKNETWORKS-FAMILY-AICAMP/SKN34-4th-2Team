"""낮 링크 확인 — 네트워크 없이 검증하는 약속.

1. 내려간 공고만 뺀다. 살아 있거나 모르는 것은 순서 그대로 남긴다.
2. 한 번 본 공고는 하루 안에 다시 열지 않는다. 내려간 것으로 본 기록도 그대로 쓴다.
3. 내려간 공고는 저장소 CLOSED + Pinecone 메타 CLOSED. OPEN이 아니던 것은 건드리지 않는다.
4. 차단 신호가 오면 아무것도 빼지 않고 한동안 요청도 보내지 않는다.
5. 확인 대상 소스가 아닌 공고는 열어 보지 않는다.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from job_matching_bot.crawling.http_session import BlockedByTargetSiteError
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.retrieval.liveness import Liveness
from job_matching_bot.schemas.job_record import STATUS_CLOSED, STATUS_EXPIRED, STATUS_OPEN

T0 = datetime(2026, 9, 9, 14, 0)


class FakeIndex:
    def __init__(self) -> None:
        self.updates: list[tuple[str, dict]] = []

    def update(self, *, id: str, set_metadata: dict, namespace: str) -> None:  # noqa: A002 — Pinecone 시그니처
        self.updates.append((id, set_metadata, namespace))


class LivenessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        store = SqliteJobStore(self.path)
        store.upsert(mock_jobs(), source="MOCK")
        self.ids = sorted(r.job.job_id for r in store.all_records())[:3]
        assert len(self.ids) == 3
        store.close()
        self.calls: list[str] = []
        self.states: dict[str, bool | None] = {}
        self.index = FakeIndex()
        self.now = T0

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def checker(self, session, rec_idx):
        self.calls.append(rec_idx)
        return self.states.get(rec_idx, True)

    def liveness(self, **kwargs) -> Liveness:
        return Liveness(
            self.path,
            source=kwargs.pop("source", "MOCK"),
            checker=kwargs.pop("checker", self.checker),
            session_factory=kwargs.pop("session_factory", lambda: object()),
            index_factory=lambda: self.index,
            namespace_factory=lambda: "jobs",
            clock=lambda: self.now,
            **kwargs,
        )

    @staticmethod
    def rec(job_id: str) -> str:
        return job_id.partition("-")[2]

    def status_of(self, job_id: str) -> str:
        store = SqliteJobStore(self.path)
        row = store.conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        store.close()
        return row["status"]

    # 1
    def test_drops_only_closed_and_keeps_order(self) -> None:
        a, b, c = self.ids
        self.states[self.rec(b)] = False   # 내려감
        self.states[self.rec(c)] = None    # 모름
        self.assertEqual(self.liveness().alive([a, b, c]), [a, c])
        self.assertEqual(sorted(self.calls), sorted(self.rec(i) for i in (a, b, c)))

    # 2
    def test_recent_check_is_not_repeated(self) -> None:
        a, b, *_ = self.ids
        self.states[self.rec(b)] = False
        live = self.liveness()
        self.assertEqual(live.alive([a, b]), [a])
        self.calls.clear()
        self.states.clear()  # 지금 다시 열면 살아 있다고 답할 것이다 — 하지만 열지 않아야 한다
        self.now = T0 + timedelta(minutes=59)
        self.assertEqual(live.alive([a, b]), [a], "한 시간 안이면 기록을 믿는다")
        self.assertEqual(self.calls, [])
        # 하루였을 때는 어제 열려 있던 공고가 오늘 조기 마감돼도 그대로 나갔다.
        self.now = T0 + timedelta(minutes=61)
        self.assertEqual(live.alive([a, b]), [a, b], "한 시간이 지나면 다시 열어 본다")
        self.assertEqual(sorted(self.calls), sorted([self.rec(a), self.rec(b)]))

    # 3
    def test_closed_is_recorded_in_store_and_index(self) -> None:
        a, b, c = self.ids
        store = SqliteJobStore(self.path)
        store.conn.execute("UPDATE jobs SET status = ? WHERE job_id = ?", (STATUS_EXPIRED, c))
        store.conn.commit()
        store.close()
        self.states[self.rec(b)] = False
        self.states[self.rec(c)] = False
        self.liveness().alive([a, b, c])
        self.assertEqual(self.status_of(a), STATUS_OPEN)
        self.assertEqual(self.status_of(b), STATUS_CLOSED)
        self.assertEqual(self.status_of(c), STATUS_EXPIRED, "OPEN이 아니던 것은 그대로")
        self.assertEqual(self.index.updates, [(b, {"status": STATUS_CLOSED}, "jobs")])

    # 4
    def test_block_signal_keeps_everything_and_rests(self) -> None:
        a, b, *_ = self.ids

        def blocked_checker(session, rec_idx):
            self.calls.append(rec_idx)
            raise BlockedByTargetSiteError("429")

        live = self.liveness(checker=blocked_checker, pause_minutes=30)
        self.assertEqual(live.alive([a, b]), [a, b])
        self.assertTrue(self.calls)
        self.calls.clear()
        self.now = T0 + timedelta(minutes=10)
        self.assertEqual(live.alive([a, b]), [a, b])
        self.assertEqual(self.calls, [], "쉬는 동안은 요청을 보내지 않는다")
        self.now = T0 + timedelta(minutes=31)
        live.alive([a, b])
        self.assertTrue(self.calls, "쉬는 시간이 끝나면 다시 연다")

    def test_session_failure_keeps_everything(self) -> None:
        a, b, *_ = self.ids

        def broken_session():
            raise BlockedByTargetSiteError("warm-up 403")

        live = self.liveness(session_factory=broken_session)
        self.assertEqual(live.alive([a, b]), [a, b])
        self.assertEqual(self.calls, [])

    # 5
    def test_other_sources_are_not_opened(self) -> None:
        a, *_ = self.ids
        self.states[self.rec(a)] = False
        live = self.liveness(source="saramin")
        self.assertEqual(live.alive([a, "other-9"]), [a, "other-9"])
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()


class ListingOnlyLivenessTest(unittest.TestCase):
    """목록에서만 본 공고에도 마감 확인이 돈다.

    목록에 `~09.30` 이라고 적혀 있어도 회사가 채용을 마치면 그 전에 닫는다. 날짜
    거르기로는 조기마감을 못 잡는다. 열어 봐야 안다.

    `alive()`는 `job_id`에서 번호만 떼어 페이지를 연다. 저장소를 뒤지지 않으므로
    `jobs`에 없는 목록 공고도 똑같이 확인된다. 이게 깨지면 마감된 공고가 검색에
    계속 나온다.
    """

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "store.sqlite"
        self.now = T0
        store = SqliteJobStore(self.path)
        store.record_list_jobs([
            {"source_job_id": "777", "company": "가", "title": "영업관리",
             "job_sectors": ["영업관리"], "source_url": "https://x/777",
             "condition_text": "서울 마포구 신입 · 정규직 고졸↑",
             "support_text": "입사지원 ~12.31"},
        ], self.now)
        store.close()
        self.opened: list[str] = []

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def live(self, closed: set[str]) -> Liveness:
        def checker(session, rec_idx):
            self.opened.append(rec_idx)
            return rec_idx not in closed

        return Liveness(
            self.path, source="SARAMIN", checker=checker,
            session_factory=lambda: object(), index_factory=lambda: FakeIndex(),
            namespace_factory=lambda: "jobs", clock=lambda: self.now,
        )

    def test_a_listing_only_posting_is_opened(self):
        self.live(set()).alive(["SARAMIN-777"])
        self.assertEqual(["777"], self.opened)

    def test_an_early_closed_listing_is_dropped(self):
        """마감일이 남았는데 회사가 먼저 닫은 경우. 날짜로는 못 잡는다."""
        alive = self.live({"777"}).alive(["SARAMIN-777"])
        self.assertEqual([], alive)

    def test_a_live_listing_stays(self):
        self.assertEqual(["SARAMIN-777"], self.live(set()).alive(["SARAMIN-777"]))
