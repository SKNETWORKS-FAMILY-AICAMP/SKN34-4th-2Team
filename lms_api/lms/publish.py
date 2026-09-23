"""예약 공지를 notices 로 발행. Cloud Functions 없음."""

from __future__ import annotations

from datetime import datetime, timedelta

from django.db import connection, transaction
from django.utils import timezone

from lms.services import schedule_notice_vector


def _time_parts(value) -> tuple[int, int]:
    if value is None:
        return 9, 0
    if hasattr(value, "hour"):
        return int(value.hour), int(value.minute)
    parts = str(value).split(":")
    hour = int(parts[0]) if parts and parts[0].isdigit() else 9
    minute = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    return hour, minute


def compute_next_publish_at(
    repeat_type: str | None,
    publish_time,
    publish_at,
    weekday: int | None,
    now: datetime | None = None,
) -> datetime:
    """Flutter computeNextPublishAt 와 같은 규칙. weekday 1=월 … 7=일."""
    base = timezone.localtime(now or timezone.now())
    hour, minute = _time_parts(publish_time)
    kind = (repeat_type or "once").lower()
    if kind == "once":
        if publish_at:
            if timezone.is_naive(publish_at):
                return timezone.make_aware(publish_at, timezone.get_current_timezone())
            return publish_at
        return base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if kind == "daily":
        candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= base:
            candidate += timedelta(days=1)
        return candidate
    want = int(weekday or 1)
    if want < 1 or want > 7:
        want = 1
    candidate = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    while candidate.isoweekday() != want or candidate <= base:
        candidate += timedelta(days=1)
    return candidate


def _dicts(cur):
    cols = [c[0] for c in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def publish_scheduled_notices(*, ids: list | None = None, now: datetime | None = None) -> int:
    """기한이 된 예약(또는 지정 id)을 notices 에 넣고 다음 시각을 갱신한다."""
    when = now or timezone.now()
    published = 0
    with transaction.atomic():
        with connection.cursor() as cur:
            if ids:
                rows = []
                for raw in ids:
                    try:
                        pk = int(raw)
                    except (TypeError, ValueError):
                        cur.execute("SELECT * FROM scheduled_notices WHERE legacy_id = %s", [str(raw)])
                    else:
                        cur.execute("SELECT * FROM scheduled_notices WHERE id = %s OR legacy_id = %s", [pk, str(raw)])
                    found = _dicts(cur)
                    if found:
                        rows.append(found[0])
            else:
                cur.execute(
                    """SELECT * FROM scheduled_notices
                       WHERE is_active = true AND next_publish_at IS NOT NULL AND next_publish_at <= %s""",
                    [when],
                )
                rows = _dicts(cur)

            for row in rows:
                cur.execute("SELECT code FROM cohorts WHERE id = %s", [row["cohort_id"]])
                code_row = cur.fetchone()
                code = code_row[0] if code_row else None
                author_name = ""
                if row.get("author_id"):
                    cur.execute("SELECT display_name FROM users WHERE id = %s", [row["author_id"]])
                    name_row = cur.fetchone()
                    author_name = name_row[0] if name_row else ""

                cur.execute(
                    """INSERT INTO notices
                       (cohort_id, title, content, author_id, author_name, is_favorite,
                        priority, vector_chunk_count, source, scheduled_notice_id, created_at, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,0,0,'scheduled',%s, now(), now()) RETURNING id""",
                    [
                        row["cohort_id"],
                        row.get("title") or "",
                        row.get("content") or "",
                        row.get("author_id"),
                        author_name,
                        bool(row.get("is_favorite")),
                        row["id"],
                    ],
                )
                notice_id = cur.fetchone()[0]
                kind = (row.get("repeat_type") or "once").lower()
                if kind in ("daily", "weekly"):
                    nxt = compute_next_publish_at(
                        kind, row.get("publish_time"), row.get("publish_at"), row.get("weekday"), when,
                    )
                    cur.execute(
                        """UPDATE scheduled_notices
                           SET last_published_at = now(), next_publish_at = %s, updated_at = now()
                           WHERE id = %s""",
                        [nxt, row["id"]],
                    )
                else:
                    cur.execute(
                        """UPDATE scheduled_notices
                           SET is_active = false, last_published_at = now(), updated_at = now()
                           WHERE id = %s""",
                        [row["id"]],
                    )
                if code:
                    schedule_notice_vector(
                        cohort_code=code,
                        notice_id=notice_id,
                        data={
                            "title": row.get("title"),
                            "content": row.get("content"),
                            "author_id": row.get("author_id"),
                            "author_name": author_name,
                        },
                        previous_chunk_count=0,
                    )
                published += 1
    return published
