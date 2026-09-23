"""공부방 노트 범위 — 학생이 고른 날짜·폴더·파일을 검사하고 노트 키(scope_key)를 만든다.

AI 서버(study_notes/service.py 의 normalize_scope_value · build_scope_key)와 같은 규칙이어야 한다.
같은 범위를 두 번 누르면 새로 만들지 않고 있던 노트를 돌려주는데, 그 판단을 이 키로 하기 때문이다.
둘이 어긋나지 않는지는 study_notes/tests/test_study_notes_lms.py 가 본다.

Django 를 끌어오지 않는다 — 테스트가 DB 없이 부를 수 있게.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

MAX_FILES = 8
SCOPE_TYPES = ("date", "prefix", "files")


class ScopeError(ValueError):
    """학생에게 그대로 보여 줄 이유"""


def _path(raw: Any) -> str:
    value = str(raw).strip().replace("\\", "/").lstrip("/")
    if not value or ".." in value or "\0" in value:
        raise ScopeError("파일 경로가 올바르지 않습니다.")
    return value


def normalize_scope(scope_type: str, raw: Any) -> str | list[str]:
    if scope_type not in SCOPE_TYPES:
        raise ScopeError("scopeType은 date, prefix, files만 가능합니다.")
    if scope_type == "files":
        if not isinstance(raw, list) or not raw:
            raise ScopeError("파일을 1개 이상 선택하세요.")
        if len(raw) > MAX_FILES:
            raise ScopeError(f"한 번에 최대 {MAX_FILES}개 파일만 정리할 수 있습니다. 범위를 좁혀 주세요.")
        return sorted({_path(item) for item in raw})
    value = str(raw or "").strip()
    if not value:
        raise ScopeError("범위를 선택하세요.")
    if scope_type == "date":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ScopeError("날짜는 YYYY-MM-DD 형식이어야 합니다.")
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ScopeError("존재하지 않는 날짜입니다.") from exc
        return value
    return _path(value).rstrip("/")


def scope_key(scope_type: str, value: str | list[str]) -> str:
    if scope_type == "date":
        return str(value)
    if scope_type == "prefix":
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")[:80]
        return f"prefix_{safe or 'root'}"
    digest = hashlib.sha1("\n".join(value).encode("utf-8")).hexdigest()[:12]
    return f"files_{digest}"
