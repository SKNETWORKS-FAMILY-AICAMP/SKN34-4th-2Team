"""Read a selected matching job from the authoritative store, never a client excerpt."""
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

from job_matching_bot.ingestion.detail_quality import is_image_only_detail
from job_matching_bot.ingestion.company_name import clean_company_name
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

from app.review_workflow import ReviewConflict, ReviewInputError, digest, job_role_title


class JobStoreUnavailable(RuntimeError):
    pass


def load_selected_job(path: Path, job_id: str, allow_closed: bool = False) -> dict:
    """공고 한 건을 저장소에서 읽는다.

    allow_closed: 이미 만든 자소서의 답을 쓸 때만 켠다. 마감 뒤에도 고치고 다듬을 수 있어야 한다
    (닫힌 공고도 자소서가 가리키면 밤 정리가 지우지 않는다 — prune REFERENCES). 새 사본 만들기와
    이력서 첨삭은 지금처럼 막는다. 마감된 공고는 마감 전과 같은 스냅샷을 내어, 저장된 요건을 그대로 쓴다.

    예전에는 sqlite 파일을 직접 열었다. 공고 저장소가 Postgres `jobs` 스키마로 옮겨 간 뒤로는
    추천(job_matching_bot)과 **같은 저장소**를 봐야 한다. 안 그러면 추천 목록에 뜬 공고를
    첨삭이 "찾을 수 없다"고 한다. `path` 는 이제 어느 스키마를 쓸지 고르는 이름으로만 쓰인다.
    """
    try:
        store = SqliteJobStore(Path(path))
        row = store.conn.execute('SELECT * FROM jobs WHERE job_id = %s', (job_id,)).fetchone()
    except Exception as exc:
        raise JobStoreUnavailable('matching_job_store_unavailable') from exc
    if row is None:
        raise ReviewInputError('selected_job_not_found')
    record = dict(row)
    record['company'] = clean_company_name(record.get('company'))
    closed = record.get('status') != 'OPEN'
    if closed and not allow_closed:
        raise ReviewConflict('selected_job_closed')
    deadline = record.get('deadline')
    if deadline:
        try:
            korea = timezone(timedelta(hours=9))
            end = datetime.fromisoformat(deadline)
            if len(deadline) == 10:
                end = datetime.combine(end.date(), time.max)
            if end.tzinfo is None:
                end = end.replace(tzinfo=korea)
            expired = end < datetime.now(korea)
        except ValueError as exc:
            if not allow_closed:
                raise ReviewInputError('selected_job_deadline_unverified') from exc
            expired = False
        if expired and not allow_closed:
            raise ReviewConflict('selected_job_expired')
        closed = closed or expired
    body = record.get('description') or ''
    if not body.strip() or is_image_only_detail(body, record.get('body_is_image')):
        raise ReviewInputError('selected_job_full_text_unavailable')
    text = f"회사: {record.get('company', '')}\n공고: {record.get('title', '')}\n\n{body}"
    if len(text) > 50000:
        raise ReviewInputError('selected_job_text_too_long')
    source = {key: record.get(key) or '' for key in ('job_id', 'company', 'title', 'source_url', 'content_hash', 'deadline')}
    source['role_title'] = job_role_title(source['company'], source['title'])
    source['snapshot_hash'] = digest([source, text, 'OPEN' if closed else record['status']])
    # 크롤러가 뽑아 둔 지원 조건. 요건 표에서 지원 자격의 근거로만 쓴다. source에 넣으면 snapshot_hash가 바뀌어
    # 이미 만든 맞춤 이력서가 모두 "공고가 바뀌었다"로 막히므로 따로 둔다.
    conditions = {key: record.get(key) for key in (
        'career_type', 'min_career_years', 'education', 'employment_type', 'region', 'military_required',
    ) if key in record}
    return {'text': text, 'source': source, 'conditions': conditions, 'closed': closed}
