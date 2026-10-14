"""구형 Redis(HELLO 미지원)에서도 Celery가 붙도록 RESP2를 강제한다."""

from __future__ import annotations


def force_redis_resp2() -> None:
    try:
        import redis
    except ImportError:
        return
    if getattr(redis.Redis.__init__, "_lms_resp2", False):
        return

    original = redis.Redis.__init__

    def __init__(self, *args, **kwargs):  # noqa: N807
        kwargs.setdefault("protocol", 2)
        return original(self, *args, **kwargs)

    __init__._lms_resp2 = True  # type: ignore[attr-defined]
    redis.Redis.__init__ = __init__  # type: ignore[method-assign]

    try:
        from redis.connection import Connection

        if not getattr(Connection.__init__, "_lms_resp2", False):
            conn_original = Connection.__init__

            def conn_init(self, *args, **kwargs):
                kwargs.setdefault("protocol", 2)
                return conn_original(self, *args, **kwargs)

            conn_init._lms_resp2 = True  # type: ignore[attr-defined]
            Connection.__init__ = conn_init  # type: ignore[method-assign]
    except Exception:
        pass
