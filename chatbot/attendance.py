"""진행 중 단위기간의 출석 판단 정보를 보강한다."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chatbot.calculation_rules import CalculationRules


def enrich_unit_period_context(context: dict[str, Any]) -> dict[str, Any]:
    """완료 전 단위기간에도 확인된 기록 기준의 예상치와 주의값을 추가한다."""
    result = deepcopy(context)
    # Use exactly the same rule snapshot as the base calculation, never a new
    # config read or a fallback that could silently apply a different threshold.
    for period in result.get("periods", []):
        period.pop("in_progress_estimate", None)
    try:
        rules = CalculationRules(**result["calculation_rules"])
    except (KeyError, TypeError, ValueError):
        result["estimate_unavailable_reason"] = "계산 기준이 없거나 유효하지 않습니다."
        return result
    current_number = result.get("current_unit_period")
    for period in result.get("periods", []):
        if period.get("number") != current_number:
            continue

        scheduled = int(period.get("scheduled_days") or 0)
        recorded = int(period.get("recorded_days") or 0)
        counts = period.get("status_counts") or {}
        exceptions = sum(int(counts.get(key, 0)) for key in ("late", "earlyLeave", "outing"))
        absence_equivalent = int(counts.get("absent", 0)) + exceptions // rules.exceptions_per_absence
        recognized = max(recorded - absence_equivalent, 0)
        remaining = max(scheduled - recorded, 0)
        required = rules.required_days(scheduled)
        allowance = max(recognized + remaining - required, 0)
        partitions = [period.get(key) for key in (
            'unrecorded_past_days', 'unrecorded_today_days', 'unrecorded_future_days', 'future_recorded_days')]
        partition_valid = (all(type(value) is int and value >= 0 for value in partitions)
                           and sum(partitions[:3]) == remaining)
        reliable_projection = (scheduled > 0 and recorded > 0 and partition_valid
                               and partitions[0] == 0 and partitions[1] == 0 and partitions[3] == 0)
        needed = max(required - recognized, 0) if scheduled > 0 and recorded > 0 else None
        until_conversion = rules.exceptions_per_absence - (exceptions % rules.exceptions_per_absence)
        scenarios = {}
        if reliable_projection and partitions[2] > 0:
            # A new scheduled day adds a record as well as any absence conversion.
            # Never reuse this for correcting an already recorded day.
            for status in ('present', 'late', 'earlyLeave', 'outing', 'absent'):
                next_exceptions = exceptions + int(status in ('late', 'earlyLeave', 'outing'))
                next_absence = (int(counts.get('absent', 0)) + int(status == 'absent')
                                + next_exceptions // rules.exceptions_per_absence)
                next_recognized = max(recorded + 1 - next_absence, 0)
                next_needed = max(required - next_recognized, 0)
                scenarios[status] = {
                    'recorded_days': recorded + 1,
                    'exception_count': next_exceptions,
                    'absence_equivalent_days': next_absence,
                    'recognized_attendance_days': next_recognized,
                    'additional_normal_attendance_days_needed': next_needed,
                    'remaining_future_days': partitions[2] - 1,
                    'reachable_with_future_normal_attendance': next_needed <= partitions[2] - 1,
                }

        period["in_progress_estimate"] = {
            "basis": "현재까지 출결 기록이 확인된 수업일",
            "recorded_scheduled_days": recorded,
            "recognized_attendance_days": recognized,
            "attendance_rate": round(recognized / recorded * 100, 1) if recorded else None,
            "requirement_met_so_far": rules.requirement_met(recognized, recorded),
            "full_period_required_recognized_days": required,
            "remaining_scheduled_days": remaining,
            "unrecorded_past_days": period.get('unrecorded_past_days'),
            "unrecorded_today_days": period.get('unrecorded_today_days'),
            "unrecorded_future_days": period.get('unrecorded_future_days'),
            "future_recorded_days": period.get('future_recorded_days'),
            "additional_recognized_days_needed": needed,
            "additional_normal_attendance_days_needed": needed if reliable_projection else None,
            "reachable_with_future_normal_attendance": (
                needed <= partitions[2] if reliable_projection else None),
            "projection_status": 'conditional_estimate' if reliable_projection else 'records_need_review',
            "projection_assumption": '앞으로 정상 출석하며 추가 결석 환산이 발생하지 않는다는 가정',
            "next_scheduled_day_scenarios": scenarios,
            "scenario_scope": '현재 단위기간의 다음 미기록 미래 수업일에 한 가지 출결 상태를 신규 기록한 가정. '
                              '기존 기록 정정·하루 복수 예외·다음 단위기간에는 적용 불가. '
                              '그 이후에는 정상 출석하고 추가 결석 환산이 없다고 가정. 실제 기록 변경 아님.',
            "additional_absence_equivalent_if_one_more_exception": 1 if until_conversion == 1 else 0,
            "max_additional_absent_days_within_remaining": min(remaining, allowance),
            "exception_count": exceptions,
            "exception_count_until_next_absence_equivalent": until_conversion,
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
