"""진행 중 단위기간의 출석 판단 정보를 보강한다."""

from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


def enrich_unit_period_context(context: dict[str, Any]) -> dict[str, Any]:
    """완료 전 단위기간에도 확인된 기록 기준의 예상치와 주의값을 추가한다."""
    result = deepcopy(context)
    current_number = result.get("current_unit_period")
    for period in result.get("periods", []):
        if period.get("number") != current_number:
            continue

        scheduled = int(period.get("scheduled_days") or 0)
        recorded = int(period.get("recorded_days") or 0)
        counts = period.get("status_counts") or {}
        exceptions = sum(int(counts.get(key, 0)) for key in ("late", "earlyLeave", "outing"))
        absence_equivalent = int(counts.get("absent", 0)) + exceptions // 3
        recognized = max(recorded - absence_equivalent, 0)
        remaining = max(scheduled - recorded, 0)
        required = math.ceil(scheduled * 0.8) if scheduled else 0
        allowance = max(recognized + remaining - required, 0)

        period["in_progress_estimate"] = {
            "basis": "현재까지 출결 기록이 확인된 수업일",
            "recorded_scheduled_days": recorded,
            "recognized_attendance_days": recognized,
            "attendance_rate": round(recognized / recorded * 100, 1) if recorded else None,
            "requirement_met_so_far": recognized / recorded >= 0.8 if recorded else None,
            "full_period_required_recognized_days": required,
            "remaining_scheduled_days": remaining,
            "max_additional_absent_days_within_remaining": min(remaining, allowance),
            "exception_count": exceptions,
            "exception_count_until_next_absence_equivalent": 3 - (exceptions % 3),
            "absence_equivalent_days": absence_equivalent,
            "final_rate_if_all_remaining_present": (
                round((recognized + remaining) / scheduled * 100, 1) if scheduled else None
            ),
            "final_rate_if_all_remaining_absent": (
                round(recognized / scheduled * 100, 1) if scheduled else None
            ),
            "is_provisional": True,
        }
    return result


def enrich_student_context(context: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(context)
    private = result.get("data", {}).get("student_private")
    if isinstance(private, dict) and isinstance(private.get("unit_period_context"), dict):
        private["unit_period_context"] = enrich_unit_period_context(private["unit_period_context"])
    return result
