"""Nonblocking, bounded login hook; transmit only a trusted server UID."""
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import hashlib
import json
import os
from threading import BoundedSemaphore, Lock
import time
import urllib.request

MAX_WORKERS = 2
MAX_PENDING = 8
DISPATCH_TIMEOUT_SECONDS = 0.75
COOLDOWN_SECONDS = 15
MAX_COOLDOWN_IDS = 256
_capacity = BoundedSemaphore(MAX_PENDING)
_guard = Lock()
_pending: set[str] = set()
_recent: dict[str, float] = {}  # Bounded opaque IDs; never student data.


@lru_cache(maxsize=1)
def _executor():
    return ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix='chat-warmup-dispatch')


def dispatch_login_warmup(user: dict) -> bool:
    """Reserve a bounded job only; login never waits for upstream DB/network."""
    if (os.getenv('LMS_CHATBOT_WARMUP', '').strip() != '1'
            or user.get('role') != 'student' or user.get('is_active') is not True
            or user.get('must_change_password') is not False):
        return False
    uid = user.get('firebase_uid')
    base = (os.getenv('CHATBOT_URL') or '').rstrip('/')
    token = os.getenv('LMS_AI_SHARED_TOKEN')
    if not isinstance(uid, str) or not uid or not base or not token:
        return False
    identity = hashlib.sha256(uid.encode()).hexdigest()
    with _guard:
        now = time.monotonic()
        for key in list(_recent):
            if now - _recent[key] >= COOLDOWN_SECONDS:
                del _recent[key]
        if (identity in _pending or identity in _recent
                or not _capacity.acquire(blocking=False)):
            return False
        _pending.add(identity)
        if len(_recent) >= MAX_COOLDOWN_IDS:
            del _recent[min(_recent, key=_recent.get)]
        _recent[identity] = now
    def dispatch():
        try:
            request = urllib.request.Request(base + '/api/v1/student-chatbot/warmup',
                data=json.dumps({'uid': uid}).encode(), method='POST',
                headers={'Content-Type': 'application/json', 'X-LMS-AI-Token': token})
            with urllib.request.urlopen(request, timeout=DISPATCH_TIMEOUT_SECONDS):
                pass
        except Exception:
            pass  # Never let preparation failures affect login or print UID.
        finally:
            with _guard:
                _pending.discard(identity)
                _capacity.release()
    try:
        _executor().submit(dispatch)
    except Exception:
        with _guard:
            _pending.discard(identity)
            _recent.pop(identity, None)
            _capacity.release()
        return False
    return True
