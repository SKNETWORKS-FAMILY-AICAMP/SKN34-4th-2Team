"""Read a selected matching job from the authoritative store, never a client excerpt."""
from datetime import datetime, time, timezone, timedelta
from pathlib import Path

from job_matching_bot.ingestion.detail_quality import is_image_only_detail
from job_matching_bot.ingestion.company_name import clean_company_name
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore

from app.review_workflow import ReviewConflict, ReviewInputError, digest, job_role_title


class JobStoreUnavailable(RuntimeError):
    pass


def load_selected_job(path: Path, job_id: str) -> dict:
    """공고 한 건을 저장소에서 읽는다.

    예전에는 sqlite 파일을 직접 열었다. 공고 저장소가 Postgres `jobs` 스키마로 옮겨 간 뒤로는
    추천(job_matching_bot)과 **같은 저장소**를 봐야 한다. 안 그러면 추천 목록에 뜬 공고를
    첨삭이 "찾을 수 없다"고 한다. `path` 는 이제 어느 스키마를 쓸지 고르는 이름으로만 쓰인다.
    """
    try:
        store = SqliteJobStore(Path(path))
        row = store.conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
    except Exception as exc:
        raise JobStoreUnavailable('matching_job_store_unavailable') from exc
    if row is None:
        raise ReviewInputError('selected_job_not_found')
    record = dict(row)
    record['company'] = clean_company_name(record.get('company'))
    if record.get('status') != 'OPEN':
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
            if end < datetime.now(korea):
                raise ReviewConflict('selected_job_expired')
        except ValueError as exc:
            raise ReviewInputError('selected_job_deadline_unverified') from exc
    body = record.get('description') or ''
    if not body.strip() or is_image_only_detail(body, record.get('body_is_image')):
        raise ReviewInputError('selected_job_full_text_unavailable')
    text = f"회사: {record.get('company', '')}\n공고: {record.get('title', '')}\n\n{body}"
    if len(text) > 50000:
        raise ReviewInputError('selected_job_text_too_long')
    source = {key: record.get(key) or '' for key in ('job_id', 'company', 'title', 'source_url', 'content_hash', 'deadline')}
    source['role_title'] = job_role_title(source['company'], source['title'])
    source['snapshot_hash'] = digest([source, text, record['status']])
    # 크롤러가 뽑아 둔 지원 조건. 요건 표에서 지원 자격의 근거로만 쓴다. source에 넣으면 snapshot_hash가 바뀌어
    # 이미 만든 맞춤 이력서가 모두 "공고가 바뀌었다"로 막히므로 따로 둔다.
    conditions = {key: record.get(key) for key in (
        'career_type', 'min_career_years', 'education', 'employment_type', 'region', 'military_required',
    ) if key in record}
    return {'text': text, 'source': source, 'conditions': conditions}
