"""Opt-in server-only unit-context cache, validated against current DB inputs.

No process-local context fallback. One fingerprint statement per hit validates
permission and insert/update/delete revisions; TTL is only a storage bound.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import os
from threading import Lock
import time
from typing import Any, Callable

from psycopg.rows import dict_row

from chatbot.database import connect

SCHEMA = 'unit-context-warmup-v1'  # Bump when calculation/interpretation changes.
NAMESPACE = f'lms:chat-context:{SCHEMA}:'
TTL_SECONDS = 300
MAX_ENTRY_BYTES = 128 * 1024
REDIS_TIMEOUT_SECONDS = 0.2
REDIS_BACKOFF_SECONDS = 5
KST = timezone(timedelta(hours=9))
_redis_guard = Lock()
_redis_retry_at = 0.0  # Failure backoff only; never context or permission state.

# Hash actual ordered inputs and row versions, not timestamp maxima. Empty
# sets also have identities, so deletions and later insertions invalidate hits.
# Shared revision contains no user identifiers or personal attendance data.
REVISION_SQL = """
WITH member AS (
    SELECT id, cohort_id, role, is_active, must_change_password
    FROM users WHERE firebase_uid = %s
), scope AS (
    SELECT m.id AS user_id, m.role, m.is_active AS user_active,
           m.must_change_password, c.id AS cohort_id, c.code AS cohort_code,
           c.is_active AS cohort_active, c.status, c.start_date, c.end_date,
           c.xmin::text AS cohort_version
    FROM member m JOIN cohorts c ON c.id = m.cohort_id
), sheet AS (
    SELECT s.id, s.uploaded_at, s.xmin::text AS row_version
    FROM curriculum_sheets s JOIN scope c ON s.cohort_id = c.cohort_id
    ORDER BY s.uploaded_at DESC NULLS LAST, s.id DESC LIMIT 1
)
SELECT c.user_id, c.cohort_id, c.cohort_code, c.role, c.user_active,
       c.must_change_password, c.cohort_active,
       EXISTS(SELECT 1 FROM cohort_deletion_jobs d
              WHERE d.cohort_id=c.cohort_id OR d.cohort_code=c.cohort_code) AS deleting,
       (SELECT count(*) FROM policy_documents p
        WHERE p.source_key='cohort:' || c.cohort_id::text || ':policy'
              AND p.source_type='cohort_policy' AND p.is_active=true) AS active_policy_count,
       md5(jsonb_build_array(c.cohort_id, c.cohort_code, c.cohort_active, c.status,
           c.start_date, c.end_date, c.cohort_version,
           (SELECT jsonb_build_array(id, uploaded_at, row_version) FROM sheet),
           (SELECT md5(COALESCE(string_agg(jsonb_build_array(r.id, r.day_index,
                   r.date_label, r."order", r.xmin::text)::text, ',' ORDER BY r.id), '[]'))
            FROM curriculum_rows r WHERE r.sheet_id=(SELECT id FROM sheet)),
           (SELECT COALESCE(jsonb_agg(jsonb_build_array(p.id, p.storage_key,
                   p.source_name, p.is_active, p.xmin::text) ORDER BY p.id), '[]'::jsonb)
            FROM policy_documents p WHERE p.source_key='cohort:' || c.cohort_id::text || ':policy'
                 AND p.source_type='cohort_policy'))::text) AS shared_revision,
       CASE WHEN %s THEN
           (SELECT md5(COALESCE(string_agg(jsonb_build_array(a.id, a.attendance_date,
                   a.status, a.xmin::text)::text, ',' ORDER BY a.id), '[]'))
            FROM attendances a WHERE a.user_id=c.user_id AND a.cohort_id=c.cohort_id)
       ELSE NULL END AS attendance_revision
FROM scope c
"""


class RevisionDenied(ValueError):
    """An authoritative permission/membership/deletion change, not a cache miss."""


@dataclass(frozen=True)
class ContextRevision:
    user_id: int
    cohort_id: int
    cohort_code: str
    shared_revision: str
    attendance_revision: str | None
    active_policy_count: int


def enabled() -> bool:
    return os.getenv('LMS_CHATBOT_WARMUP', '').strip() == '1'


def read_connection_options() -> dict:
    return {'connect_timeout': 1, 'options': '-c statement_timeout=1500 -c lock_timeout=300'}


def read_revision(session: dict, *, include_attendance: bool) -> ContextRevision:
    """One statement/snapshot; no returned names, emails or attendance rows."""
    with connect(row_factory=dict_row, autocommit=True, **read_connection_options()) as conn:
        row = conn.execute(REVISION_SQL, (session['uid'], include_attendance)).fetchone()
    if (not row or row['role'] != 'student' or row['user_active'] is not True
            or row['must_change_password'] is not False or row['cohort_active'] is not True
            or row['deleting']):
        raise RevisionDenied('현재 학생 권한 또는 기수 상태를 확인할 수 없습니다.')
    requested = session.get('cohort')
    if requested is not None and str(requested) not in (str(row['cohort_id']), row['cohort_code']):
        raise RevisionDenied('학생의 현재 기수가 요청 기수와 다릅니다.')
    return ContextRevision(int(row['user_id']), int(row['cohort_id']), row['cohort_code'],
                           row['shared_revision'], row['attendance_revision'], int(row['active_policy_count']))


def redis_backoff_active() -> bool:
    with _redis_guard:
        return time.monotonic() < _redis_retry_at


def mark_redis_failure() -> None:
    global _redis_retry_at
    with _redis_guard:
        _redis_retry_at = time.monotonic() + REDIS_BACKOFF_SECONDS


@lru_cache(maxsize=1)
def redis_client():
    import redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry
    url = ((os.getenv('CHATBOT_CONTEXT_REDIS_URL') or '').strip()
           or (os.getenv('REDIS_URL') or '').strip()
           or 'redis://127.0.0.1:6379/0')
    return redis.Redis.from_url(url,
        decode_responses=False, protocol=2, socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS, retry_on_timeout=False, retry=Retry(NoBackoff(), 0))


def cache_key(session: dict, revision: ContextRevision, day: date, *,
              include_attendance: bool, include_record_details: bool) -> str:
    parts = [SCHEMA, revision.cohort_id, revision.cohort_code, day.isoformat(),
             revision.shared_revision, include_attendance, include_record_details]
    if include_attendance:
        parts.extend([session['uid'], revision.user_id, revision.attendance_revision])
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    return NAMESPACE + ('personal:' if include_attendance else 'shared:') + digest


def ready_pointer_key(session: dict, day: date, *, include_attendance: bool,
                      include_record_details: bool) -> str:
    """Address candidates without a DB lookup; permission is checked on hits."""
    parts = [SCHEMA, str(session.get('cohort') or ''), day.isoformat(),
             include_attendance, include_record_details]
    if include_attendance:
        parts.append(session['uid'])
    digest = hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    return NAMESPACE + 'ready:' + digest


def _revision_payload(revision: ContextRevision, *, personal: bool) -> dict:
    result = {'cohort_id': revision.cohort_id, 'cohort_code': revision.cohort_code,
              'shared_revision': revision.shared_revision,
              'active_policy_count': revision.active_policy_count}
    if personal:
        result.update(user_id=revision.user_id, attendance_revision=revision.attendance_revision)
    return result


def _cacheable(context: Any, *, personal: bool) -> bool:
    if not isinstance(context, dict) or context.get('schedule_status') != 'generated_unconfirmed':
        return False
    if context.get('unavailable_reason') or context.get('calendar_unavailable_reason'):
        return False
    policy = context.get('policy_calculation')
    if not isinstance(policy, dict) or policy.get('status') != 'unverified':
        return False
    if personal:
        if context.get('calculation_unavailable_reason') or not context.get('calculation_rules'):
            return False
        if context.get('completion_progress', {}).get('unavailable_reason'):
            return False
    return True


def _store(client, session: dict, revision: ContextRevision, day: date, context: dict,
           *, include_attendance: bool, include_record_details: bool) -> bool:
    key = cache_key(session, revision, day, include_attendance=include_attendance,
                    include_record_details=include_record_details)
    data = json.dumps({'schema': SCHEMA, 'key_hash': key.rsplit(':', 1)[-1],
                       'context': context}, ensure_ascii=False).encode()
    if len(data) > MAX_ENTRY_BYTES:
        return False
    if not client.set(key, data, ex=TTL_SECONDS):
        return False
    pointer = json.dumps({'schema': SCHEMA, 'key': key,
                          'revision': _revision_payload(revision, personal=include_attendance)}).encode()
    # Store body first, then switch each alias with atomic SET. An expired or
    # missing body is a miss; a partial publication never authorizes a hit.
    for cohort in (revision.cohort_code, str(revision.cohort_id)):
        alias_session = {**session, 'cohort': cohort}
        client.set(ready_pointer_key(alias_session, day, include_attendance=include_attendance,
                                    include_record_details=include_record_details), pointer, ex=TTL_SECONDS)
    return True


def _read_ready_candidate(session: dict, day: date, *, include_attendance: bool,
                          include_record_details: bool):
    try:
        client = redis_client()
        raw = client.get(ready_pointer_key(session, day, include_attendance=include_attendance,
                                          include_record_details=include_record_details))
    except Exception:
        mark_redis_failure()
        return None
    try:
        pointer = json.loads(raw) if raw and len(raw) <= 4096 else None
        if not isinstance(pointer, dict) or pointer.get('schema') != SCHEMA:
            return None
        key = pointer.get('key')
        prefix = NAMESPACE + ('personal:' if include_attendance else 'shared:')
        if (not isinstance(key, str) or not key.startswith(prefix) or len(key) != len(prefix) + 64
                or any(ch not in '0123456789abcdef' for ch in key[len(prefix):])):
            return None
    except Exception:
        return None
    try:
        raw = client.get(key)
    except Exception:
        mark_redis_failure()
        return None
    try:
        entry = json.loads(raw) if raw and len(raw) <= MAX_ENTRY_BYTES else None
        if (not isinstance(entry, dict) or entry.get('schema') != SCHEMA
                or entry.get('key_hash') != key.rsplit(':', 1)[-1]
                or not _cacheable(entry.get('context'), personal=include_attendance)):
            return None
    except Exception:
        return None
    return pointer, entry


def _matches_revision(pointer: dict, session: dict, revision: ContextRevision, day: date,
                      *, include_attendance: bool, include_record_details: bool) -> bool:
    expected = cache_key(session, revision, day, include_attendance=include_attendance,
                         include_record_details=include_record_details)
    return (revision.active_policy_count == 1 and pointer.get('key') == expected
            and pointer.get('revision') == _revision_payload(revision, personal=include_attendance))


def has_ready_context(session: dict, revision: ContextRevision, day: date, *,
                      include_attendance: bool, include_record_details: bool = False) -> bool:
    """Background-only probe with an already server-validated revision."""
    candidate = _read_ready_candidate(session, day, include_attendance=include_attendance,
                                      include_record_details=include_record_details)
    return bool(candidate and _matches_revision(candidate[0], session, revision, day,
                  include_attendance=include_attendance, include_record_details=include_record_details))


def load_cached_context(session: dict, *, loader: Callable, today: date | None = None,
                        include_attendance: bool = True,
                        include_record_details: bool = False) -> dict:
    """Foreground read: no fingerprint/fill work when no candidate is ready."""
    day = today if today is not None else datetime.now(KST).date()
    def fresh():
        result = loader(dict(session), today=day, include_attendance=include_attendance,
                        include_record_details=include_record_details)
        try:
            from chatbot.warmup import schedule_warmup
            schedule_warmup(dict(session), today=today)
        except Exception:
            pass
        return result
    if redis_backoff_active():
        return fresh()  # Known outage: no cache lookup or extra fingerprint work.
    candidate = _read_ready_candidate(session, day, include_attendance=include_attendance,
                                      include_record_details=include_record_details)
    if candidate is None:
        return fresh()
    pointer, entry = candidate
    try:
        current = read_revision(session, include_attendance=include_attendance)
    except RevisionDenied:
        return {'unavailable_reason': '현재 학생 권한 또는 기수 상태를 확인할 수 없습니다.'}
    except Exception:
        return fresh()  # Never return old cached data after DB failure.
    if not _matches_revision(pointer, session, current, day, include_attendance=include_attendance,
                             include_record_details=include_record_details):
        return fresh()
    if today is None and datetime.now(KST).date() != day:
        return loader(dict(session), include_attendance=include_attendance,
                      include_record_details=include_record_details)
    return deepcopy(entry['context'])


def fill_context_cache(session: dict, *, loader: Callable, today: date | None = None,
                       include_attendance: bool = True,
                       include_record_details: bool = False) -> bool:
    """Background only: before/load/after validation, then body/alias publish."""
    if redis_backoff_active():
        return False
    day = today if today is not None else datetime.now(KST).date()
    try:
        before = read_revision(session, include_attendance=include_attendance)
        if before.active_policy_count != 1:
            return False
        current_session = {'uid': session['uid'], 'cohort': before.cohort_code}
        context = loader(current_session, today=day, include_attendance=include_attendance,
                         include_record_details=include_record_details)
        after = read_revision(current_session, include_attendance=include_attendance)
        if (before != after or not _cacheable(context, personal=include_attendance)
                or (today is None and datetime.now(KST).date() != day)):
            return False
    except Exception:
        return False  # No foreground result is replaced by a fill failure.
    try:
        client = redis_client()
        stored = _store(client, current_session, after, day, context,
                        include_attendance=include_attendance,
                        include_record_details=include_record_details)
        if include_attendance and include_record_details:
            # The uncached loader's only details=False difference is this field.
            # Do not cache any other student_private scope.
            minimal = deepcopy(context)
            minimal.pop('attendance_records', None)
            _store(client, current_session, after, day, minimal,
                   include_attendance=True, include_record_details=False)
        return stored
    except Exception:
        mark_redis_failure()
        return False
