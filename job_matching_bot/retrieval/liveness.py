"""추천 직전 확인 — 이 공고가 지금도 사이트에 있나.

저장소 상태는 밤에 한 번 맞춘 것이라 낮에 조기 마감된 공고를 모른다. 목록에서 안 보이는
것도 마감 신호가 아니다 — 한 번 못 본 공고 12건을 열어 보니 8건이 살아 있었다. 페이지를
열어 보는 것만이 판정이다. 그래서 **사용자에게 나갈 후보만 그 자리에서 열어 본다.**

- 동시에 연다. 8건이면 1초 안팎이다(한 건 0.6초). 브라우저가 페이지 하나를 열 때 보내는
  요청보다 적다.
- 한 시간 안에 본 공고는 다시 열지 않는다(`link_checks` 표). 한 대화에서 같은 공고를
  여러 번 보여 줘도 요청은 한 번이다. 예전에는 하루였는데, 어제 열려 있던 공고가 오늘
  조기 마감돼도 그대로 나갔다. 보내기 직전의 확인이라면 하루는 너무 길다.
- 마감이면 저장소 status를 CLOSED로, Pinecone 메타도 CLOSED로 바꾼다. SQL 검색과 벡터
  검색 양쪽에서 바로 빠지고, 밤 배치가 벡터를 지운다.
- 모르면(일시 오류) 남긴다. 차단 신호가 오면 한동안 쉰다. 잘못 지우는 것보다 낫다.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import requests

from job_matching_bot.crawling.http_session import BlockedByTargetSiteError, new_session
from job_matching_bot.crawling.nightly import check_alive
from job_matching_bot.schemas.job_record import STATUS_CLOSED

log = logging.getLogger(__name__)

# 이 소스의 공고만 열어 본다. 나머지는 확인 없이 남긴다.
# 저장소의 job_id 는 "SARAMIN-54947118" 꼴이라 대소문자를 무시하고 견준다.
SOURCE = "saramin"
TTL_HOURS = 1.0
MAX_WORKERS = 8
PAUSE_MINUTES = 30.0


def _default_session() -> requests.Session:
    return new_session(warm_up=True)


def _default_index():
    from job_matching_bot.retrieval.pinecone_index import index

    return index()


def _default_namespace() -> str:
    from job_matching_bot.retrieval.pinecone_index import namespace

    return namespace()


class Liveness:
    """`alive(job_ids)` 가 전부다. 내려간 공고를 뺀 목록을 순서 그대로 돌려준다."""

    def __init__(
        self,
        store_path: Path,
        *,
        source: str = SOURCE,
        ttl_hours: float = TTL_HOURS,
        max_workers: int = MAX_WORKERS,
        pause_minutes: float = PAUSE_MINUTES,
        checker: Callable[[requests.Session, str], bool | None] = check_alive,
        session_factory: Callable[[], requests.Session] = _default_session,
        index_factory: Callable[[], Any] = _default_index,
        namespace_factory: Callable[[], str] = _default_namespace,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.store_path = Path(store_path)
        self.source = source
        self.ttl = timedelta(hours=ttl_hours)
        self.max_workers = max_workers
        self.pause = timedelta(minutes=pause_minutes)
        self._checker = checker
        self._session_factory = session_factory
        self._index_factory = index_factory
        self._namespace_factory = namespace_factory
        self._clock = clock
        self._session: requests.Session | None = None
        self._paused_until: datetime | None = None

    # ── 바깥에서 쓰는 것 ──────────────────────────────────────
    def alive(self, job_ids: list[str]) -> list[str]:
        now = self._clock()
        if self._paused_until is not None and now < self._paused_until:
            return list(job_ids)

        targets = [job_id for job_id in job_ids if self._rec_idx(job_id) is not None]
        if not targets:
            return list(job_ids)

        store = self._open_store()
        known = store.recent_link_checks(targets, since=now - self.ttl)
        fresh = [job_id for job_id in targets if job_id not in known]
        results: dict[str, bool] = {}
        if fresh:
            results = self._check_many(fresh, now)
            if results:
                moved = store.record_link_checks(results, at=now)
                self._mark_index_closed(moved)
        store.close()

        verdict = {**known, **results}
        return [job_id for job_id in job_ids if verdict.get(job_id, True)]

    # ── 안쪽 ─────────────────────────────────────────────────
    def _rec_idx(self, job_id: str) -> str | None:
        source, _, rec_idx = job_id.partition("-")
        return rec_idx if source.lower() == self.source.lower() and rec_idx else None

    def _open_store(self):
        from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

        return SqliteJobStore(self.store_path)

    def _check_many(self, job_ids: list[str], now: datetime) -> dict[str, bool]:
        """(job_id → 살아 있나). 모르는 것은 넣지 않는다. 차단이면 비우고 쉰다."""
        try:
            if self._session is None:
                self._session = self._session_factory()
        except (BlockedByTargetSiteError, requests.RequestException) as error:
            self._rest(now, f"세션을 열지 못함: {type(error).__name__}")
            return {}

        session = self._session
        blocked: list[BaseException] = []

        def one(job_id: str) -> tuple[str, bool | None]:
            try:
                return job_id, self._checker(session, self._rec_idx(job_id))
            except BlockedByTargetSiteError as error:
                blocked.append(error)
                return job_id, None

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(job_ids))) as pool:
            outcomes = list(pool.map(one, job_ids))

        if blocked:
            self._rest(now, f"차단 신호: {blocked[0]}")
            return {}
        return {job_id: state for job_id, state in outcomes if state is not None}

    def _rest(self, now: datetime, why: str) -> None:
        self._paused_until = now + self.pause
        self._session = None
        log.warning("낮 링크 확인을 %s 분 쉽니다 — %s", int(self.pause.total_seconds() // 60), why)

    def _mark_index_closed(self, job_ids: list[str]) -> None:
        """벡터 검색의 OPEN 필터에서 바로 빠지게 메타만 바꾼다. 삭제는 밤 배치가 한다."""
        if not job_ids:
            return
        try:
            index = self._index_factory()
            space = self._namespace_factory()
            for job_id in job_ids:
                index.update(id=job_id, set_metadata={"status": STATUS_CLOSED}, namespace=space)
        except Exception as error:  # noqa: BLE001 — 메타 갱신 실패는 추천을 막을 이유가 아니다
            log.warning("Pinecone 상태 갱신 실패 (%d건): %s", len(job_ids), type(error).__name__)
