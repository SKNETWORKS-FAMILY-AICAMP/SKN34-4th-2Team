"""테스트는 운영 저장소(RDS)를 열지 못한다.

저장소 이름이 `job_store.sqlite`면 운영 스키마로 붙고, `.env`의 DB_HOST(RDS)를 쓴다.
테스트가 그 이름을 쓰면 RDS에 가짜 공고(MOCK-1)를 넣고 공고 전체(437MB)를 읽었다.
여기서 막으면 그런 테스트는 조용히 RDS를 건드리는 대신 바로 실패한다.

연결 경로를 보려는 테스트는 `connect_postgres`를 직접 바꿔 끼우므로 이 막음보다 안쪽에서 돈다.
"""

from __future__ import annotations

import pytest

from job_matching_bot.ingestion import sqlite_store


@pytest.fixture(autouse=True)
def _no_managed_store(monkeypatch):
    real = sqlite_store.connect_postgres

    def guarded(*args, use_db_host: bool = True, **kwargs):
        if use_db_host:
            raise RuntimeError(
                "테스트에서 운영 저장소(RDS)를 열려고 했습니다. "
                "저장소 파일 이름을 job_store.sqlite 가 아닌 것으로 바꾸세요."
            )
        return real(*args, use_db_host=use_db_host, **kwargs)

    monkeypatch.setattr(sqlite_store, "connect_postgres", guarded)
    # 앞 테스트가 열어 둔 운영 연결을 다음 테스트가 꺼내 쓰지 않게 비운다.
    monkeypatch.setattr(sqlite_store, "_pool", [])
