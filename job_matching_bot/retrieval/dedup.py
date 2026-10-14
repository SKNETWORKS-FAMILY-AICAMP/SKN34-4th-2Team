"""인덱스에 올릴 공고를 고를 때 거르는 두 규칙.

## 1. 마감 지난 공고

저장소의 `status`는 수집 시각 기준이라, 수집 이후에 마감된 공고가 `OPEN`으로 남는다.
적재할 때 **오늘 날짜로 다시 판정**해서 지난 것은 올리지 않고 인덱스에서도 지운다.
마감이 미기재인 공고는 상시 채용으로 보고 남긴다.

## 2. 재등록 공고

기업이 같은 공고를 여러 번 올리는 경우가 있다. 사람인이 각각 다른 `rec_idx`를 주므로
ID로는 걸러지지 않는다. 요건 구간 본문이 완전히 같은 것을 한 그룹으로 묶고, 그중
**지역과 경력 조건까지 같은 그룹**만 재등록으로 본다.

같은 본문이라도 이런 것은 서로 다른 공고이므로 남긴다:

- 지점 분리 — 같은 직무를 은평·죽전·전주 지점별로 올린 경우. 지원자에게 다른 선택지다
- 연차 분리 — 같은 직무를 3~5년 / 6~8년 / 9년~ 으로 나눈 경우. 지원 대상이 다르다

재등록 그룹에서는 **마감이 늦은 것**을 남긴다. 마감이 같거나 둘 다 미기재이면
`source_job_id`가 큰 쪽(나중에 등록된 쪽)을 남긴다.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from job_matching_bot.retrieval import documents as doc
from job_matching_bot.schemas.job_posting import Job

KST = timezone(timedelta(hours=9))
FAR_FUTURE = "9999-12-31"


def today_kst() -> str:
    return datetime.now(KST).date().isoformat()


def is_expired(job: Job, today: str | None = None) -> bool:
    """마감일이 오늘보다 이전이면 만료. 미기재는 상시 채용으로 보고 만료가 아니다."""
    if not job.deadline:
        return False
    return job.deadline[:10] < (today or today_kst())


def _body_hash(job: Job) -> str:
    return hashlib.sha256(doc.index_body(job).encode("utf-8")).hexdigest()


def _keep_order(job: Job) -> tuple[str, str]:
    """남길 우선순위. 마감이 늦은 것, 그다음 나중에 등록된 것."""
    return (job.deadline[:10] if job.deadline else FAR_FUTURE, job.source_job_id)


def find_reposts(jobs: list[Job]) -> dict[str, str]:
    """재등록으로 판정된 공고. {지울 job_id: 남길 job_id}."""
    groups: dict[tuple[str, str], list[Job]] = defaultdict(list)
    for job in jobs:
        groups[(job.company, _body_hash(job))].append(job)

    dropped: dict[str, str] = {}
    for rows in groups.values():
        if len(rows) < 2:
            continue
        if len({j.region for j in rows}) > 1:
            continue  # 지점 분리
        if len({(j.career_type, j.min_career_years) for j in rows}) > 1:
            continue  # 연차 분리
        ordered = sorted(rows, key=_keep_order, reverse=True)
        for job in ordered[1:]:
            dropped[job.job_id] = ordered[0].job_id
    return dropped


def select(jobs: list[Job], today: str | None = None) -> tuple[list[Job], dict[str, int]]:
    """인덱스에 올릴 공고를 고른다. (올릴 목록, 단계별 제외 건수)."""
    today = today or today_kst()
    stats: dict[str, int] = {}

    open_jobs = [j for j in jobs if j.status == "OPEN"]
    stats["수집 시점 마감·삭제"] = len(jobs) - len(open_jobs)

    live = [j for j in open_jobs if not is_expired(j, today)]
    stats[f"마감 지남({today} 기준)"] = len(open_jobs) - len(live)

    indexable = [j for j in live if doc.is_indexable(j)]
    stats["요건 문장 없음"] = len(live) - len(indexable)

    reposts = find_reposts(indexable)
    selected = [j for j in indexable if j.job_id not in reposts]
    stats["재등록"] = len(reposts)

    return selected, stats
