"""공고 저장소의 판정 규칙: content_hash 기반 upsert와 상태 전이.

저장은 `sqlite_store.SqliteJobStore`가 하고, 이 모듈은 그 저장소가 따르는 규칙
(`reconcile`, `resolve_status`)과 여는 곳(`open_store`)만 둔다.

매 수집마다 전량을 새로 만들면 두 번째 수집부터 무엇이 새 공고이고 무엇이
사라진 공고인지 알 수 없다. 이 모듈은 `source + source_job_id`를 키로
기존 레코드와 대조해 다음을 판정한다.

    처음 본 공고            → 신규 등록, first_seen_at 기록
    content_hash 같음       → 내용 그대로, last_seen_at만 갱신
    content_hash 다름       → 내용 갱신, revisions 증가
    이번에 안 보임           → 즉시 삭제하지 않고 상태로 남김

마감일이 지나면 EXPIRED, 마감 전인데 소스에서 계속 사라져 있으면 REMOVED다.
수집이 한 번 실패했다고 전체가 REMOVED가 되면 안 되므로, 연속으로 관측되지
않은 횟수가 기준을 넘을 때만 REMOVED로 넘긴다.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from job_matching_bot.config import now
from job_matching_bot.schemas.job_posting import Job
from job_matching_bot.schemas.job_record import (
    DEFAULT_MISSING_RUN_LIMIT,
    STATUS_CLOSED,
    STATUS_EXPIRED,
    STATUS_OPEN,
    STATUS_REMOVED,
    CollectionReport,
    JobRecord,
)

# 이 필드가 비어 있으면 선택자 오류나 파싱 실패를 의심해야 한다.
REQUIRED_FIELDS = ("company", "title", "source_url")


def _deadline_passed(deadline: str | None, as_of: datetime) -> bool:
    if not deadline:
        return False
    try:
        parsed = datetime.fromisoformat(deadline)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=as_of.tzinfo)
    return parsed < as_of


def _is_expired(job: Job, as_of: datetime) -> bool:
    return _deadline_passed(job.deadline, as_of)


def resolve_status(job: Job, as_of: datetime) -> str:
    """관측된 공고의 상태. 소스가 마감이라고 하면 그 말을 따른다."""
    if job.status == STATUS_CLOSED:
        return STATUS_CLOSED
    return STATUS_EXPIRED if _is_expired(job, as_of) else STATUS_OPEN


def listing_deadline_change(
    stored: str | None, status: str, listed: str | None, open_ended: bool, as_of: datetime
) -> tuple[str | None, str] | None:
    """오늘 목록에 보인 공고의 마감일을 목록 값으로 고칠지. 고치면 (새 마감, 새 상태), 아니면 None.

    상세는 한 번 받으면 다시 받지 않는다. 그래서 회사가 마감일을 늘려도 저장소는 처음 마감일로
    공고를 마감(EXPIRED)했고, 되살릴 길은 학생이 그 링크를 가져올 때뿐이었다. 목록에는 늘린
    마감일(`~10.31`, `D-7`, `상시채용`)이 그대로 보인다. 2026-10-06 최근 사흘 목록에 보인 마감 공고
    2,010건 — 페이지로 표본을 열어 보니 목록에 계속 보인 것은 다 살아 있었다.

    - OPEN · EXPIRED만 고친다. CLOSED는 페이지가 내려갔다고 본 것이고, REMOVED는 목록 관측이 되살린다.
    - 목록 마감을 못 읽었으면(`listed` None, 상시도 아님) 두지 않는다. 모르는 것을 지우지 않는다.
    - 하루 안쪽 차이면 저장된 값을 지킨다. `D-2` · `내일마감`은 목록을 받은 시각에 대한 말인데 밤 수집이
      자정을 넘기므로 같은 마감이 하루씩 어긋나 보인다(10/5 목록으로 대 보니 열린 공고 5,594건이 하루 차이).
      상세 페이지에서 읽은 시각(18:00 마감 등)도 지킨다.
    - 상시채용으로 바뀌었으면 마감일을 비운다 — 끝이 정해지지 않은 것이지 지난 것이 아니다.
    - 상태는 새 마감일로 다시 정한다. 줄인 마감이 이미 지났으면 EXPIRED가 된다.
    """
    if status not in (STATUS_OPEN, STATUS_EXPIRED):
        return None
    if listed is None and not open_ended:
        return None
    if open_ended:
        new = None
        if not stored:
            return None
    else:
        new = listed
        if stored and _days_apart(stored, listed) <= 1:
            return None
    new_status = STATUS_EXPIRED if _deadline_passed(new, as_of) else STATUS_OPEN
    return new, new_status


def _days_apart(a: str, b: str) -> int:
    """두 마감일의 날짜 차이. 못 읽으면 크게 — 다른 값으로 본다."""
    try:
        return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)
    except ValueError:
        return 9999


def keep_listing_fields(job: Job, company: str | None, title: str | None, deadline: str | None) -> Job:
    """다시 받은 상세에 **목록 값이 없으면** 저장돼 있던 목록 값을 이어받는다.

    제목·회사명·마감일은 상세 페이지가 아니라 목록에서 온다(`list_item`). 수집기는 목록에서
    본 줄을 상세에 붙여 저장하는데, 공고 번호만 들고 상세를 다시 받으면 붙일 목록 줄이 없다.
    2026-09-11에 파서를 고치고 328건을 번호로 다시 받았을 때 그렇게 들어온 레코드가 저장된
    제목·회사명·마감일을 빈 값으로 덮어써 313건이 이름 없는 공고가 됐다. 마감일이 비어
    마감이 지나도 만료로 넘어가지 않았다.

    제목과 회사명이 **둘 다** 비었을 때만 목록이 없던 것으로 본다. 정상 공고는 둘 다 있다.
    이때 마감일도 이어받는다 — 목록이 없어서 비었지 상시채용이라서 빈 것이 아니다.
    """
    if job.title or job.company or not (title or company):
        return job
    return replace(
        job,
        company=company or "",
        title=title or "",
        deadline=job.deadline or deadline,
    )


def _missing_field_names(job: Job) -> list[str]:
    return [name for name in REQUIRED_FIELDS if not getattr(job, name, None)]


def reconcile(
    existing: dict[tuple[str, str], JobRecord],
    collected: Iterable[Job],
    *,
    source: str,
    as_of: datetime | None = None,
    missing_run_limit: int = DEFAULT_MISSING_RUN_LIMIT,
    observed_ids: set[str] | None = None,
) -> tuple[dict[tuple[str, str], JobRecord], CollectionReport]:
    """수집 결과를 기존 저장 내용과 대조해 새 저장 상태와 리포트를 만든다.

    `source`는 이번 수집이 책임지는 범위다. 다른 소스의 공고는 이번에 안 보였다고
    사라진 것으로 보지 않는다. 백엔드 공고만 수집한 날 프론트엔드 공고가 안
    보이는 것은 삭제가 아니기 때문이다.

    `observed_ids`는 **목록 페이지에서 본** source_job_id 집합이다. 증분 수집은
    새 공고의 상세만 받으므로 `collected`에는 기존 공고가 없다. 이때 목록에서
    보인 공고를 "안 보였다"고 세면 두 번 만에 전부 REMOVED가 된다. 목록에 있었으면
    살아 있는 것이고, 내용은 마지막으로 받은 것을 유지한다. None이면 전량 수집으로
    보고 `collected`만으로 판단한다.
    """
    as_of = as_of or now()
    merged = dict(existing)
    report = CollectionReport(source=source, collected_at=as_of.isoformat())
    seen: set[tuple[str, str]] = set()
    timestamp = as_of.isoformat()

    for job in collected:
        key = (job.source, job.source_job_id)
        seen.add(key)
        previous = merged.get(key)
        if previous is not None:
            job = keep_listing_fields(
                job, previous.job.company, previous.job.title, previous.job.deadline
            )
        status = resolve_status(job, as_of)
        job_id = job.job_id

        missing = _missing_field_names(job)
        if missing:
            report.missing_fields[job_id] = missing
        report.parser_versions[job.parser_version] = (
            report.parser_versions.get(job.parser_version, 0) + 1
        )

        if previous is None:
            merged[key] = JobRecord(
                job=job,
                first_seen_at=timestamp,
                last_seen_at=timestamp,
                status=status,
            )
            report.new.append(job_id)
            continue

        changed = previous.job.content_hash != job.content_hash
        merged[key] = JobRecord(
            job=job,
            first_seen_at=previous.first_seen_at,
            last_seen_at=timestamp,
            status=status,
            # 다시 보였으므로 미관측 카운터를 되돌린다. 삭제 처리됐던 공고가
            # 재게시되면 그대로 다시 열린 상태가 된다.
            missing_runs=0,
            revisions=previous.revisions + (1 if changed else 0),
        )
        (report.updated if changed else report.unchanged).append(job_id)

    for key, record in merged.items():
        if key in seen or record.job.source != source:
            continue
        # 마감일은 관측 여부와 무관하게 확정적으로 판정할 수 있다.
        if _is_expired(record.job, as_of):
            record.status = STATUS_EXPIRED
            report.expired.append(record.job.job_id)
            continue
        if observed_ids is not None and record.job.source_job_id in observed_ids:
            # 목록에서 봤다. 상세를 다시 받지 않았을 뿐 사라진 게 아니다.
            record.last_seen_at = timestamp
            record.missing_runs = 0
            if record.status == STATUS_REMOVED:
                # 삭제 처리했던 공고가 목록에 다시 보이면 되살린다.
                record.status = STATUS_OPEN
            report.observed.append(record.job.job_id)
            continue
        record.missing_runs += 1
        if record.missing_runs >= missing_run_limit:
            record.status = STATUS_REMOVED
            report.removed.append(record.job.job_id)
        else:
            report.still_missing.append(record.job.job_id)

    return merged, report


def open_store(path: Path):
    """저장소를 연다. **SQLite만 쓴다.**

    예전에는 확장자가 `.json`이면 JSON 파일 저장소를 골랐다. 전량을 메모리에 올렸다 통째로
    쓰는 방식이라 수만 건에서 못 쓰게 됐고, 운영은 처음부터 SQLite였다. 테스트만 JSON을
    쓰고 있어 두 구현을 같이 지고 가던 것을 걷어냈다. 판정 규칙(`reconcile`)은 남긴다 —
    SQLite 저장소가 따라야 할 기준이고 `test_sqlite_store`가 둘을 대조한다.
    """
    from job_matching_bot.ingestion.sqlite_store import SqliteJobStore, is_sqlite_path

    path = Path(path)
    if not is_sqlite_path(path):
        raise ValueError(f"SQLite 저장소 경로(.sqlite/.db)여야 합니다: {path}")
    return SqliteJobStore(path)
