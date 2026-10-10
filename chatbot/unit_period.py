"""교육일정과 출석 기록을 LLM 입력용 단위기간 컨텍스트로 계산한다."""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable

from chatbot.calculation_rules import CalculationRules, load_calculation_rules

ATTENDANCE_STATUSES = {"present", "late", "absent", "officialLeave", "earlyLeave", "outing"}


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year, month = value.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _periods(start: date, end: date) -> list[dict[str, Any]]:
    if end < start:
        raise ValueError("종강일은 개강일보다 빠를 수 없습니다")
    result = []
    number = 1
    while True:
        period_start = _add_months(start, number - 1)
        if period_start > end:
            break
        period_end = min(_add_months(start, number) - timedelta(days=1), end)
        result.append({
            "number": number,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
        })
        number += 1
    return result


def calculate_unit_period_context(
    start: date,
    end: date,
    *,
    today: date,
    scheduled_dates: Iterable[date] = (),
    attendance_records: dict[date, str] | None = None,
    rules: CalculationRules | None = None,
) -> dict[str, Any]:
    """검토 전 설정으로 기간·출석 예상치를 계산한다. 확정 판정이 아니다."""
    rules = rules if rules is not None else load_calculation_rules()
    periods = _periods(start, end)
    schedule = {day for day in scheduled_dates if start <= day <= end}
    attendance = attendance_records or {}
    current = None

    for period in periods:
        period_start = date.fromisoformat(period["start_date"])
        period_end = date.fromisoformat(period["end_date"])
        if period_start <= today <= period_end:
            current = period["number"]

        days = {day for day in schedule if period_start <= day <= period_end}
        statuses = Counter(
            status for day, status in attendance.items()
            if day in days and status in ATTENDANCE_STATUSES
        )
        recorded_days = sum(statuses.values())
        scheduled_days = len(days)
        complete = scheduled_days > 0 and recorded_days >= scheduled_days
        exception_count = statuses["late"] + statuses["earlyLeave"] + statuses["outing"]
        absence_equivalent = statuses["absent"] + exception_count // rules.exceptions_per_absence
        recognized_days = max(scheduled_days - absence_equivalent, 0) if complete else None
        attendance_rate = round(recognized_days / scheduled_days * 100, 1) if complete else None
        period.update({
            "scheduled_days": scheduled_days or None,
            "recorded_days": recorded_days,
            "status_counts": dict(statuses),
            "absence_equivalent_days": absence_equivalent if complete else None,
            "recognized_attendance_days": recognized_days,
            "attendance_rate": attendance_rate,
            "requirement_met": rules.requirement_met(recognized_days, scheduled_days) if complete else None,
            "attendance_data_complete": complete,
        })

    state = "in_progress" if current else ("upcoming" if today < start else "completed")
    return {
        "calculation_rules": rules.metadata(),
        "schedule_status": "generated_unconfirmed",
        "is_provisional": True,
        "timezone": "Asia/Seoul",
        "as_of": today.isoformat(),
        "course_start_date": start.isoformat(),
        "course_end_date": end.isoformat(),
        "course_state": state,
        "current_unit_period": current,
        "periods": periods,
        "calculation_notes": [
            "확정 일정이 아닌 검토 전 계산 일정이다. 기존 월별 산정 방식으로 생성하고 마지막 기간을 종강일에서 자른다.",
            "출석률은 실제 수업일과 모든 출석 상태가 확인된 기간에만 계산한다.",
            f"검토 전 계산 가정: 지각·조퇴·외출 합계 {rules.exceptions_per_absence}회당 결석 1일로 환산한다.",
            f"requirement_met은 검토 전 {rules.attendance_threshold_percent:g}% 기준의 예상값이다. 확정 출결 검증·수료·지급 판정이 아니다.",
        ],
    }
