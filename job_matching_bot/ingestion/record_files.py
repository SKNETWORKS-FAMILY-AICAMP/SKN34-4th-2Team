"""수집 레코드 파일 입출력.

POC 초기에는 JSON 배열 하나에 전부 담았지만, 수천 건을 몇 시간에 걸쳐 긁을
때는 **한 건 끝날 때마다 바로 써야** 중간에 끊겨도 잃지 않는다. 그래서
JSON Lines(`.jsonl`, 한 줄에 한 건)를 쓴다. 읽는 쪽은 둘 다 받는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def read_records(path: Path) -> list[dict[str, Any]]:
    """`.json`(배열) 또는 `.jsonl`(줄 단위)을 읽는다. 없으면 빈 목록."""
    path = Path(path)
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        records = []
        # str.splitlines()는 U+2028 같은 유니코드 줄바꿈에서도 끊는다. 공고 본문에
        # 그런 문자가 들어 있으면 한 건이 둘로 쪼개지므로 반드시 개행(\n)으로만 자른다.
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                # 크롤러가 쓰는 도중 꺼지면 마지막 줄이 잘린 채 남는다. 그 한 건은
                # 버리고 나머지를 살린다. 재개 시 그 공고는 "안 받은 것"으로 다시 받는다.
                continue
        return records
    payload = json.loads(text) if text.strip() else []
    return payload if isinstance(payload, list) else []


def append_record(path: Path, record: dict[str, Any]) -> None:
    """한 건을 `.jsonl` 끝에 붙인다. 파일이 없으면 만든다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _record_id(record: dict[str, Any], key: str = "source_job_id") -> str | None:
    value = record.get(key) or (record.get("list_item") or {}).get(key)
    return str(value) if value else None


def latest_by_id(records: Iterable[dict[str, Any]], key: str = "source_job_id") -> dict[str, dict[str, Any]]:
    """같은 공고를 여러 번 받았으면 마지막 것만 남긴다. `.jsonl`은 덧붙이기만 하므로
    다시 받은 공고가 뒤에 한 번 더 들어 있다."""
    latest: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = _record_id(record, key)
        if record_id:
            latest[record_id] = record
    return latest


def record_ids(records: Iterable[dict[str, Any]], key: str = "source_job_id") -> set[str]:
    """레코드 목록에서 식별자만 모은다. 목록 항목 안에 있는 경우도 본다."""
    ids: set[str] = set()
    for record in records:
        value = record.get(key) or (record.get("list_item") or {}).get(key)
        if value:
            ids.add(str(value))
    return ids
