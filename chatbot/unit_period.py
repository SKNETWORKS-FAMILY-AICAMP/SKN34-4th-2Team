"""교육일정과 출석 기록을 LLM 입력용 단위기간 컨텍스트로 계산한다."""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import date, timedelta
from typing import Any, Iterable

from chatbot.calculation_rules import CalculationRules, calendar_method_from_basis, load_calculation_rules

ATTENDANCE_STATUSES = {"present", "late", "absent", "officialLeave", "earlyLeave", "outing"}


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year, month = value.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))


def _periods(start: date, end: date, calendar_method: str = 'anchored_month_clamped') -> list[dict[str, Any]]:
    if end < start:
        raise ValueError("종강일은 개강일보다 빠를 수 없습니다")
    if calendar_method not in {'anchored_month_clamped', 'anchored_month_strict'}:
        raise ValueError('지원하지 않는 단위기간 산정 방식')
    result = []
    number = 1
    period_start = start
    while True:
        if period_start > end:
            break
        if calendar_method == 'anchored_month_strict':
            month_index = start.month - 1 + number
            year, month = start.year + month_index // 12, month_index % 12 + 1
            # A boundary after course end is unnecessary, even if that month
            # does not contain the original anchor day (e.g. Jan 31–Feb 10).
            if (year, month, start.day) > (end.year, end.month, end.day):
                next_start = None
            else:
                try:
                    next_start = date(year, month, start.day)
                except ValueError as exc:
                    raise ValueError('월말 처리 기준 미확인') from exc
        else:
            next_start = _add_months(start, number)
        period_end = min(next_start - timedelta(days=1), end) if next_start else end
        result.append({
            "number": number,
            "start_date": period_start.isoformat(),
            "end_date": period_end.isoformat(),
        })
        if period_end == end:
            break
        period_start = next_start
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
    require_policy: bool = False,
    calendar_basis: dict[str, Any] | None = None,
    cohort: str | None = None,
) -> dict[str, Any]:
    """서버 정책 출처로 기간·출석 예상치를 계산한다. 확정 판정이 아니다."""
    rules = rules if rules is not None or require_policy else load_calculation_rules()
    schedule = {day for day in scheduled_dates if start <= day <= end}
    attendance = attendance_records or {}
    calendar_unavailable_reason = None
    try:
        if require_policy:
            method = calendar_method_from_basis(calendar_basis, cohort=cohort,
                document_hash=rules.version if rules else None)
            if rules and rules.calendar_method != method:
                raise ValueError('수치 계산 규칙과 단위기간 산정 방식 불일치')
        else:
            method = rules.calendar_method if rules else 'anchored_month_clamped'
        periods = _periods(start, end, calendar_method=method)
    except ValueError as exc:
        if not require_policy:
            raise
        periods = []
        calendar_unavailable_reason = str(exc)
        rules = None
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
        recorded_dates = {day for day, status in attendance.items()
                          if day in days and status in ATTENDANCE_STATUSES}
        unrecorded_dates = days - recorded_dates
        scheduled_days = len(days)
        complete = scheduled_days > 0 and recorded_days >= scheduled_days
        exception_count = statuses["late"] + statuses["earlyLeave"] + statuses["outing"]
        absence_equivalent = statuses["absent"] + exception_count // rules.exceptions_per_absence if rules else None
        recognized_days = max(scheduled_days - absence_equivalent, 0) if complete and rules else None
        attendance_rate = round(recognized_days / scheduled_days * 100, 1) if complete and rules else None
        period.update({
            "scheduled_days": scheduled_days or None,
            "recorded_days": recorded_days,
            "unrecorded_past_days": sum(day < today for day in unrecorded_dates),
            "unrecorded_today_days": sum(day == today for day in unrecorded_dates),
            "unrecorded_future_days": sum(day > today for day in unrecorded_dates),
            "future_recorded_days": sum(day > today for day in recorded_dates),
            "status_counts": dict(statuses),
            "absence_equivalent_days": absence_equivalent if complete else None,
            "recognized_attendance_days": recognized_days,
            "attendance_rate": attendance_rate,
            "requirement_met": rules.requirement_met(recognized_days, scheduled_days) if complete and rules else None,
            "attendance_data_complete": complete,
        })

    state = "upcoming" if today < start else ("completed" if today > end else "in_progress")
    raw_statuses = Counter(status for day, status in attendance.items()
                           if start <= day <= end and status in ATTENDANCE_STATUSES)
    return {
        "calculation_rules": rules.metadata() if rules else None,
        "calculation_unavailable_reason": None if rules else '활성 기수 정책에서 계산 기준을 확인하지 못했습니다.',
        "calendar_basis": dict(calendar_basis) if isinstance(calendar_basis, dict) else None,
        "calendar_unavailable_reason": calendar_unavailable_reason,
        "schedule_status": "unavailable" if calendar_unavailable_reason else "generated_unconfirmed",
        "scheduled_days": len(schedule),
        "raw_attendance": {
            "recorded_days": sum(raw_statuses.values()),
            "status_counts": dict(raw_statuses),
            "recorded_scheduled_days": sum(day in schedule and status in ATTENDANCE_STATUSES
                                           for day, status in attendance.items()),
        },
        "is_provisional": True,
        "timezone": "Asia/Seoul",
        "as_of": today.isoformat(),
        "course_start_date": start.isoformat(),
        "course_end_date": end.isoformat(),
        "course_state": state,
        "current_unit_period": current,
        "periods": periods,
        "calculation_notes": [
            (f"단위기간 산정 중단: {calendar_unavailable_reason}." if calendar_unavailable_reason else
             "활성 정책 원문에서 추출한 단위기간 규칙에 따른 잠정 일정이다. 시행 이력·확정 일정 판정은 아니다."
             if require_policy else "서버의 검토 전 계산 설정에 따른 잠정 일정이다. 확정 일정 판정은 아니다."),
            "출석률은 실제 수업일과 모든 출석 상태가 확인된 기간에만 계산한다.",
            (f"검토 전 계산 가정: 지각·조퇴·외출 합계 {rules.exceptions_per_absence}회당 결석 1일로 환산한다." if rules else '정책 계산 기준 미확인. 공통값으로 대신 계산하지 않는다.'),
            (f"requirement_met은 검토 전 {rules.attendance_threshold_percent:g}% 기준의 예상값이다. 확정 출결 검증·수료·지급 판정이 아니다." if rules else '출결 기록과 수업일수만 안내할 수 있다.'),
        ],
    }
