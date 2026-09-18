"""프로젝트 기수 범위 검색과 결과 다양화 유틸리티."""

from __future__ import annotations

import re
from typing import Any, Iterable


COHORT_RANGE_RE = re.compile(
    r"(?<!\d)(?P<start>\d{1,3})\s*기?\s*"
    r"(?:~|〜|～|[-–—]|부터)\s*"
    r"(?P<end>\d{1,3})\s*기(?:까지)?",
    re.IGNORECASE,
)


def cohort_range(query: str) -> tuple[int, int] | None:
    match = COHORT_RANGE_RE.search(query)
    if not match:
        return None
    start, end = int(match.group("start")), int(match.group("end"))
    start, end = min(start, end), max(start, end)
    if start < 1 or end > 999 or end - start > 100:
        return None
    return start, end


def neutralize_cohort_ranges(query: str) -> str:
    """범위 끝 숫자가 임베딩 유사도를 지배하지 않도록 중립 표현으로 바꾼다."""
    return COHORT_RANGE_RE.sub("여러 이전 기수", query)


def cohort_buckets(start: int, end: int, size: int = 4) -> list[list[str]]:
    values = [str(value) for value in range(start, end + 1)]
    return [values[index:index + size] for index in range(0, len(values), size)]


def diversify_by_cohort(items: Iterable[Any], limit: int) -> list[Any]:
    """유사도 순서를 유지하면서 먼저 서로 다른 기수를 선택한다."""
    values = list(items)
    selected: list[Any] = []
    selected_ids: set[str] = set()
    seen_cohorts: set[str] = set()

    def identity(item: Any) -> str:
        return str(getattr(item, "id", "") or id(item))

    for item in values:
        cohort = str(getattr(item, "metadata", {}).get("cohort", ""))
        item_id = identity(item)
        if cohort and cohort not in seen_cohorts and item_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item_id)
            seen_cohorts.add(cohort)
            if len(selected) >= limit:
                return selected
    for item in values:
        item_id = identity(item)
        if item_id not in selected_ids:
            selected.append(item)
            selected_ids.add(item_id)
            if len(selected) >= limit:
                break
    return selected
