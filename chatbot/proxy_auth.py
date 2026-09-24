"""Fail-closed authentication for Django-to-AI server requests."""

from __future__ import annotations

import hmac
import os


def valid_proxy_token(provided: str | None) -> bool:
    expected = os.environ.get("LMS_AI_SHARED_TOKEN") or ""
    return bool(expected and provided and hmac.compare_digest(provided, expected))
