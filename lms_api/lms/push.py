"""앱 푸시 알림 — Expo Push API 로 보낸다.

쓰기 트랜잭션이 커밋된 뒤 별도 스레드에서 보내므로 요청이 느려지지 않고, 롤백된 내용은 알리지 않는다.
LMS_PUSH_ENABLED=0 이면 끈다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request

from django.db import connection, transaction

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_BATCH = 100


def is_expo_token(token: str) -> bool:
    return token.startswith(("ExponentPushToken[", "ExpoPushToken[")) and token.endswith("]")


def _enabled() -> bool:
    return os.environ.get("LMS_PUSH_ENABLED", "1").strip().lower() not in ("0", "false", "off", "no")


def register_token(cur, user_id: int, token: str, platform: str) -> None:
    """같은 기기로 다른 계정에 로그인하면 토큰 주인을 옮긴다"""
    cur.execute(
        """INSERT INTO push_tokens (user_id, token, platform, created_at, updated_at)
           VALUES (%s, %s, %s, now(), now())
           ON CONFLICT (token) DO UPDATE SET user_id = EXCLUDED.user_id, platform = EXCLUDED.platform,
                                             updated_at = now()""",
        [user_id, token, platform[:20]],
    )


def remove_token(cur, user_id: int, token: str) -> None:
    cur.execute("DELETE FROM push_tokens WHERE token = %s AND user_id = %s", [token, user_id])


def _tokens_for(user_ids: list[int]) -> list[str]:
    if not user_ids:
        return []
    with connection.cursor() as cur:
        cur.execute(
            """SELECT t.token FROM push_tokens t JOIN users u ON u.id = t.user_id
               WHERE t.user_id = ANY(%s) AND u.is_active = true""",
            [list(user_ids)],
        )
        return [row[0] for row in cur.fetchall()]


def _post(messages: list[dict]) -> list[dict]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    access = os.environ.get("EXPO_ACCESS_TOKEN", "").strip()
    if access:
        headers["Authorization"] = f"Bearer {access}"
    req = urllib.request.Request(EXPO_PUSH_URL, data=json.dumps(messages).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8")).get("data") or []


def _send(user_ids: list[int], title: str, body: str, url: str) -> None:
    try:
        tokens = _tokens_for(user_ids)
        dead: list[str] = []
        for start in range(0, len(tokens), _BATCH):
            chunk = tokens[start:start + _BATCH]
            messages = [
                {"to": token, "title": title, "body": body, "sound": "default", "data": {"url": url} if url else {}}
                for token in chunk
            ]
            try:
                tickets = _post(messages)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                logger.warning("push send failed: %s", type(exc).__name__)
                continue
            for token, ticket in zip(chunk, tickets):
                if ticket.get("status") == "error" and (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    dead.append(token)
        if dead:
            with connection.cursor() as cur:
                cur.execute("DELETE FROM push_tokens WHERE token = ANY(%s)", [dead])
    except Exception:
        logger.exception("push send crashed")
    finally:
        connection.close()


def notify_users(user_ids, title: str, body: str, url: str = "") -> None:
    """커밋 뒤에 보낸다. url 은 앱 안 경로(예: /(student)/notice/12)"""
    ids = sorted({int(uid) for uid in user_ids if uid})
    if not ids or not _enabled():
        return
    title = (title or "").strip()[:80] or "PLAYDATA LXP"
    body = " ".join((body or "").split())[:150]

    def start() -> None:
        threading.Thread(target=_send, args=(ids, title, body, url), name="lms-push", daemon=True).start()

    if connection.in_atomic_block:
        transaction.on_commit(start)
    else:
        start()


def cohort_student_ids(cur, cohort_id: int, exclude_user_id: int | None = None) -> list[int]:
    cur.execute(
        "SELECT id FROM users WHERE cohort_id = %s AND role = 'student' AND is_active = true",
        [cohort_id],
    )
    return [row[0] for row in cur.fetchall() if row[0] != exclude_user_id]


def notify_new_notice(cur, cohort_id: int, notice_id: int, title: str, content: str, author_id: int | None) -> None:
    notify_users(
        cohort_student_ids(cur, cohort_id, author_id),
        f"[공지] {title}" if title else "새 공지가 올라왔습니다",
        content,
        f"/(student)/notice/{notice_id}",
    )


def notify_alert_popup(cur, popup_id: int, cohort_id: int, title: str, content: str) -> None:
    """지정 대상이 있으면 그 학생들만, 없으면 기수 학생 전체"""
    cur.execute("SELECT user_id FROM alert_popup_targets WHERE popup_id = %s", [popup_id])
    targets = [row[0] for row in cur.fetchall()]
    notify_users(targets or cohort_student_ids(cur, cohort_id), title or "새 알림", content, "/(student)/(tabs)")
