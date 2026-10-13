"""Shared, fail-closed login limits and refresh-session state.

Production uses Redis so gunicorn workers observe the same rotation/revocation.
The in-process backend is limited to DEBUG/local tests and is never used in production.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import threading
import time
from functools import lru_cache
from uuid import uuid4

from django.conf import settings


class SessionUnavailable(Exception):
    """Authentication state cannot be checked; callers must fail closed."""


_lock = threading.Lock()
_local: dict[str, tuple[str, float]] = {}
_ROTATE = """
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local state = cjson.decode(current)
if state[1] ~= ARGV[1] then return 0 end
if state[2] == ARGV[2] then
  redis.call('SET', KEYS[1], cjson.encode({state[1], ARGV[3], state[2], tonumber(ARGV[5])}), 'EX', ARGV[4])
  return 1
end
-- A simultaneous second refresh is rejected without destroying the winner.
if state[3] == ARGV[2] and tonumber(ARGV[5]) - state[4] <= 3 then return 0 end
redis.call('DEL', KEYS[1])
return -1
"""
_REVOKE = """
local current = redis.call('GET', KEYS[1])
if not current then return 0 end
local state = cjson.decode(current)
if state[1] ~= ARGV[1] then return 0 end
return redis.call('DEL', KEYS[1])
"""
_LIMIT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return count
"""


def _dev_memory() -> bool:
    return settings.DEBUG and os.environ.get("AUTH_SESSION_BACKEND", "memory") == "memory"


@lru_cache(maxsize=1)
def _redis():
    import redis

    return redis.Redis.from_url(
        os.environ.get("AUTH_REDIS_URL") or os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
        protocol=2,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def _key(sid: str) -> str:
    return f"lms:auth:session:{sid}"


def _ttl() -> int:
    return max(1, int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()))


def _call(fn):
    try:
        return fn()
    except Exception as exc:
        raise SessionUnavailable("authentication state unavailable") from exc


def create_session(uid: str, jti: str, sid: str | None = None) -> str:
    sid = sid or uuid4().hex
    value = json.dumps([uid, jti, "", 0], separators=(",", ":"))
    if _dev_memory():
        with _lock:
            _local[_key(sid)] = (value, time.monotonic() + _ttl())
    else:
        if not _call(lambda: _redis().set(_key(sid), value, ex=_ttl(), nx=True)):
            raise SessionUnavailable("session identity collision")
    return sid


def session_active(sid: str, uid: str) -> bool:
    if not sid or not uid:
        return False
    if _dev_memory():
        with _lock:
            value, deadline = _local.get(_key(sid), ("", 0))
            return deadline > time.monotonic() and bool(value) and json.loads(value)[0] == uid
    value = _call(lambda: _redis().get(_key(sid)))
    return bool(value and json.loads(value)[0] == uid)


def rotate_session(sid: str, uid: str, old_jti: str, new_jti: str) -> bool:
    if not all((sid, uid, old_jti, new_jti)):
        return False
    if _dev_memory():
        with _lock:
            current, deadline = _local.get(_key(sid), ("", 0))
            if not current or deadline <= time.monotonic():
                return False
            owner, current_jti, previous_jti, changed_at = json.loads(current)
            if owner != uid:
                return False
            if current_jti != old_jti:
                if previous_jti != old_jti or time.time() - changed_at > 3:
                    del _local[_key(sid)]
                return False
            value = json.dumps([uid, new_jti, old_jti, time.time()], separators=(",", ":"))
            _local[_key(sid)] = (value, time.monotonic() + _ttl())
            return True
    return _call(lambda: _redis().eval(_ROTATE, 1, _key(sid), uid, old_jti, new_jti, _ttl(), time.time())) == 1


def revoke_session(sid: str, uid: str) -> bool:
    # A refresh may rotate while logout is in flight. A signed token from this
    # session can revoke that session regardless of its now-stale JTI.
    if _dev_memory():
        with _lock:
            current, deadline = _local.get(_key(sid), ("", 0))
            if not current or deadline <= time.monotonic():
                return False
            owner, _, _, _ = json.loads(current)
            if owner != uid:
                return False
            del _local[_key(sid)]
            return True
    return bool(_call(lambda: _redis().eval(_REVOKE, 1, _key(sid), uid)))


def client_ip(request) -> str:
    """Never trust arbitrary X-Forwarded-For; opt-in header requires a known proxy hop."""
    peer = str(request.META.get("REMOTE_ADDR") or "")
    try:
        peer_ip = ipaddress.ip_address(peer)
    except ValueError:
        return "unknown"
    if os.environ.get("AUTH_TRUST_CLOUDFRONT_CLIENT_IP") == "1":
        cidrs = os.environ.get("AUTH_TRUSTED_PROXY_CIDRS", "").split(",")
        try:
            trusted = any(peer_ip in ipaddress.ip_network(c.strip(), strict=False) for c in cidrs if c.strip())
            if trusted:
                raw = str(request.META.get("HTTP_X_LMS_CLIENT_IP") or "")
                return str(ipaddress.ip_address(raw))
        except ValueError:
            pass
    return str(peer_ip)


def login_attempt_allowed(email: str, ip: str) -> bool:
    # HMAC hides email/IP values from Redis keys and prevents user-controlled key content.
    def key(kind: str, value: str) -> str:
        digest = hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
        return f"lms:auth:limit:{kind}:{digest}"

    account_key, ip_key = key("account", email), key("ip", ip)
    if _dev_memory():
        with _lock:
            now = time.monotonic()
            counts = []
            for item in (account_key, ip_key):
                count, deadline = _local.get(item, ("0", 0))
                count = int(count) + 1 if deadline > now else 1
                _local[item] = (str(count), deadline if deadline > now else now + 900)
                counts.append(count)
    else:
        def increment():
            pipeline = _redis().pipeline(transaction=False)
            pipeline.eval(_LIMIT, 1, account_key, 900)
            pipeline.eval(_LIMIT, 1, ip_key, 900)
            return pipeline.execute()
        counts = _call(increment)
    return int(counts[0]) <= 8 and int(counts[1]) <= 300
