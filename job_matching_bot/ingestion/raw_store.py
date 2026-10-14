"""수집 원본 보존.

정규화하기 전의 응답을 그대로 남긴다. 선택자가 바뀌거나 파서가 틀렸을 때,
다시 수집하지 않고 저장된 원본만으로 재처리할 수 있어야 하기 때문이다.

설계 문서 §7의 경로 규칙을 따른다.

    job_raw/{source}/{source_job_id}
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from job_matching_bot.config import now

PARSE_OK = "OK"
PARSE_FAILED = "FAILED"

# 파일명으로 쓸 수 없는 문자를 치환한다. source_job_id는 외부에서 오는 값이라
# 경로 조작(../ 등)이 들어오지 않게 화이트리스트로 거른다.
_UNSAFE = re.compile(r"[^A-Za-z0-9_.\-]")


def safe_name(value: str) -> str:
    cleaned = _UNSAFE.sub("_", value).strip("._")
    return cleaned or "unknown"


def raw_path(root: Path, source: str, source_job_id: str) -> Path:
    return Path(root) / safe_name(source) / f"{safe_name(source_job_id)}.json"


def save_raw(
    root: Path,
    source: str,
    source_job_id: str,
    record: dict[str, Any],
    *,
    parse_status: str = PARSE_OK,
    parse_error: str | None = None,
    parser_version: str = "",
    fetched_at: datetime | None = None,
) -> Path:
    """원본 한 건을 저장한다. 파싱 성공 여부도 함께 남긴다."""
    fetched_at = fetched_at or now()
    path = raw_path(root, source, source_job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": source,
        "source_job_id": source_job_id,
        "fetched_at": fetched_at.isoformat(),
        "parser_version": parser_version,
        "parse_status": parse_status,
        "parse_error": parse_error,
        "raw": record,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_raw(root: Path, source: str | None = None) -> list[dict[str, Any]]:
    """저장된 원본을 읽는다. `source`를 주면 그 소스만 읽는다."""
    base = Path(root) / safe_name(source) if source else Path(root)
    if not base.exists():
        return []
    payloads = []
    for path in sorted(base.rglob("*.json")):
        payloads.append(json.loads(path.read_text(encoding="utf-8")))
    return payloads


def failed_raw(root: Path, source: str | None = None) -> list[dict[str, Any]]:
    """재처리해야 할 원본만 골라낸다."""
    return [
        payload
        for payload in load_raw(root, source)
        if payload.get("parse_status") != PARSE_OK
    ]


def reparse(
    root: Path,
    parser: Callable[[dict[str, Any]], Any],
    source: str | None = None,
    only_failed: bool = False,
) -> tuple[list[Any], list[dict[str, Any]]]:
    """저장된 원본을 다시 파싱한다.

    파서를 고친 뒤 재수집 없이 결과가 나아졌는지 확인하는 용도다.
    (성공한 결과, 여전히 실패한 원본)을 돌려준다.
    """
    payloads = failed_raw(root, source) if only_failed else load_raw(root, source)
    parsed: list[Any] = []
    failures: list[dict[str, Any]] = []
    for payload in payloads:
        try:
            parsed.append(parser(payload["raw"]))
        except Exception as error:  # 원본 하나가 깨져도 나머지는 계속 처리한다.
            failures.append({**payload, "parse_error": f"{type(error).__name__}: {error}"})
    return parsed, failures
