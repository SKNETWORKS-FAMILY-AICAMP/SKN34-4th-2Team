"""공부방 노트 범위 — 학생이 고른 날짜·폴더·파일을 검사하고 노트 키(scope_key)를 만든다.

AI 서버(study_notes/service.py 의 normalize_scope_value · build_scope_key)와 같은 규칙이어야 한다.
같은 범위를 두 번 누르면 새로 만들지 않고 있던 노트를 돌려주는데, 그 판단을 이 키로 하기 때문이다.
둘이 어긋나지 않는지는 study_notes/tests/test_study_notes_lms.py 가 본다.

Django 를 끌어오지 않는다 — 테스트가 DB 없이 부를 수 있게.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

MAX_FILES = 8
SCOPE_TYPES = ("date", "prefix", "files", "subject")
# 과목 전체 요약 — 저장소(과목) 하나에 하나. 날짜별 노트를 모아 만든다(study_note_service.start_subject_note).
SUBJECT_KEY = "subject"


class ScopeError(ValueError):
    """학생에게 그대로 보여 줄 이유"""


def _path(raw: Any) -> str:
    value = str(raw).strip().replace("\\", "/").lstrip("/")
    if not value or ".." in value or "\0" in value:
        raise ScopeError("파일 경로가 올바르지 않습니다.")
    return value


def normalize_scope(scope_type: str, raw: Any) -> str | list[str]:
    if scope_type not in SCOPE_TYPES:
        raise ScopeError("scopeType은 date, prefix, files, subject만 가능합니다.")
    if scope_type == "subject":
        return "all"
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
    if scope_type == "subject":
        return SUBJECT_KEY
    if scope_type == "date":
        return str(value)
    if scope_type == "prefix":
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("_")[:80]
        return f"prefix_{safe or 'root'}"
    digest = hashlib.sha1("\n".join(value).encode("utf-8")).hexdigest()[:12]
    return f"files_{digest}"


def _file_list(raw: Any) -> list[dict]:
    """노트 행의 files(jsonb). Django 드라이버는 JSON 글자로 주기도 한다."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    return [item for item in (raw or []) if isinstance(item, dict) and item.get("path")]


def same_material(stored: Any, current: Any) -> bool:
    """두 노트가 같은 수업 자료로 만든 것인가 — 파일이 같고, 파일마다 내용이 같은가.

    내용은 내용 해시(blob)로 견준다. 폴더 · 파일 범위는 커밋이 저장소 HEAD 라서 다른 파일이
    바뀌어도 커밋이 달라지기 때문이다. 해시가 없는 예전 노트는 커밋으로 견준다(다르면 한 번 다시 만든다).
    """
    old, new = _file_list(stored), _file_list(current)
    if not old or not new:
        return False
    now = {item["path"]: item for item in new}
    if {item["path"] for item in old} != set(now):
        return False
    for item in old:
        other = now[item["path"]]
        if item.get("blob") and other.get("blob"):
            if item["blob"] != other["blob"]:
                return False
        elif item.get("commit") != other.get("commit"):
            return False
    return True
