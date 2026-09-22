"""Copy youtubeCurriculumCache documents into Redis. No Postgres table."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import firebase_admin
import redis
from firebase_admin import credentials, firestore

ROOT = Path(__file__).resolve().parents[2]
TTL_SECONDS = 12 * 60 * 60
REPORT = ROOT / "docs" / "cutover-report.md"


def _init():
    cred = os.environ.get(
        "GOOGLE_APPLICATION_CREDENTIALS",
        str(ROOT / "secrets" / "firebase-adminsdk.json"),
    )
    project = os.environ.get("FIREBASE_PROJECT_ID", "skn34-3rd-2team")
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(cred), {"projectId": project})
    return firestore.client()


def _dump(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    to_dt = getattr(value, "to_datetime", None)
    if callable(to_dt):
        return to_dt().isoformat()
    if isinstance(value, dict):
        return {str(k): _dump(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_dump(v) for v in value]
    return str(value)


def _remaining_ttl(fetched_at: datetime | None) -> int:
    if fetched_at is None:
        return TTL_SECONDS
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - fetched_at).total_seconds()
    left = int(TTL_SECONDS - elapsed)
    return max(left, 1)


def main() -> int:
    db = _init()
    client = redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"),
        decode_responses=True,
        protocol=2,
    )
    client.ping()
    moved = 0
    skipped = 0
    keys: list[str] = []
    for cohort in db.collection("cohorts").stream():
        code = str((cohort.to_dict() or {}).get("code") or cohort.id)
        for doc in cohort.reference.collection("youtubeCurriculumCache").stream():
            data = doc.to_dict() or {}
            fetched = data.get("fetchedAt")
            fetched_dt = fetched.to_datetime() if hasattr(fetched, "to_datetime") else None
            key = f"curriculum:yt:{code}:{doc.id}"
            payload = _dump(data)
            payload["weekKey"] = data.get("weekKey") or doc.id
            try:
                client.set(key, json.dumps(payload, ensure_ascii=False), ex=_remaining_ttl(fetched_dt))
                moved += 1
                keys.append(key)
            except Exception as exc:
                skipped += 1
                print(f"redis_fail {key} {type(exc).__name__}")
    print(f"youtube_cache_moved={moved}")
    print(f"youtube_cache_failed={skipped}")
    for key in keys:
        print(f"key={key}")
    extra = [
        "",
        "## Redis youtube curriculum cache",
        "",
        f"- Functions TTL 12h 와 동일 (`CACHE_TTL_MS`)",
        f"- 옮긴 키 {moved}건, 실패 {skipped}건",
        f"- 키: {', '.join(keys) if keys else '(없음)'}",
        "",
    ]
    if REPORT.exists():
        text = REPORT.read_text(encoding="utf-8")
        if "## Redis youtube curriculum cache" not in text:
            REPORT.write_text(text.rstrip() + "\n" + "\n".join(extra), encoding="utf-8")
    else:
        REPORT.write_text("# Cutover report\n" + "\n".join(extra), encoding="utf-8")
    return 0 if skipped == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
