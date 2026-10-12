"""Bounded background preparation of authenticated server-only contexts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from functools import lru_cache, partial
import hashlib
import json
from threading import BoundedSemaphore, Lock
from uuid import uuid4

from chatbot.context_cache import (
    KST, NAMESPACE, enabled, fill_context_cache, has_ready_context, mark_redis_failure,
    read_connection_options, read_revision, redis_backoff_active, redis_client,
)

MAX_WORKERS = 2
MAX_PENDING = 8
LOCK_SECONDS = 60
COOLDOWN_SECONDS = 5
_capacity = BoundedSemaphore(MAX_PENDING)
_guard = Lock()
_pending: set[str] = set()  # Bounded opaque IDs only; never contexts.
_RELEASE = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0"
_COOLDOWN = "if redis.call('GET',KEYS[1]) == ARGV[1] then return redis.call('EXPIRE',KEYS[1],ARGV[2]) end return 0"


@lru_cache(maxsize=1)
def _executor():
    return ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='chat-context-warmup')


def schedule_warmup(session: dict, *, today: date | None = None) -> str:
    if not enabled():
        return 'disabled'
    if redis_backoff_active():
        return 'unavailable'
    session = dict(session)
    day = today if today is not None else datetime.now(KST).date()
    uid_hash = hashlib.sha256(json.dumps([session['uid'], session.get('cohort'), day.isoformat()]).encode()).hexdigest()
    with _guard:
        if uid_hash in _pending:
            return 'pending'
        if not _capacity.acquire(blocking=False):
            return 'busy'
        _pending.add(uid_hash)
    def run():
        client, acquired = None, False
        lock_key, token = None, uuid4().hex
        completed = False
        try:
            # Revalidate queued jobs; never rely on endpoint-time permission.
            revision = read_revision(session, include_attendance=True)
            current = {'uid': session['uid'], 'cohort': revision.cohort_code}
            current_day = today if today is not None else datetime.now(KST).date()
            lock_hash = hashlib.sha256(json.dumps([session['uid'], revision.cohort_code,
                                                   current_day.isoformat()]).encode()).hexdigest()
            lock_key = NAMESPACE + 'warmup-lock:' + lock_hash
            try:
                client = redis_client()
                acquired = bool(client.set(lock_key, token, nx=True, ex=LOCK_SECONDS))
            except Exception:
                mark_redis_failure()
                return
            if not acquired:
                return
            # Call the uncached source loader directly. Foreground misses only
            # enqueue work and must never recurse into this fill path.
            from chatbot.firebase_student_context import _load_unit_period_context
            background_loader = partial(_load_unit_period_context,
                                        _connection_options=read_connection_options())
            shared_ready = has_ready_context(current, revision, current_day, include_attendance=False)
            personal_ready = has_ready_context(current, revision, current_day,
                                               include_attendance=True, include_record_details=True)
            shared_ready = shared_ready or fill_context_cache(current, loader=background_loader,
                today=today, include_attendance=False)
            personal_ready = personal_ready or fill_context_cache(current, loader=background_loader,
                today=today, include_attendance=True, include_record_details=True)
            completed = shared_ready and personal_ready
        except Exception:
            pass  # No personal payload/credentials/exception text in logs.
        finally:
            if acquired:
                try:
                    if completed:
                        client.eval(_COOLDOWN, 1, lock_key, token, COOLDOWN_SECONDS)
                    else:
                        client.eval(_RELEASE, 1, lock_key, token)
                except Exception:
                    mark_redis_failure()  # Redis TTL releases orphan locks.
            with _guard:
                _pending.discard(uid_hash)
                _capacity.release()
    try:
        _executor().submit(run)
    except Exception:
        with _guard:
            _pending.discard(uid_hash)
            _capacity.release()
        return 'unavailable'
    return 'accepted'
