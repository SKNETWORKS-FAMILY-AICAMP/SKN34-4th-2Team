"""Exact date-only requests using validated authenticated cohort context."""
from dataclasses import dataclass
from datetime import date
import re

from chatbot.active_policy_rules import validated_calendar_basis


@dataclass(frozen=True)
class ScheduleRequest:
    current_period: bool
    start: bool
    end: bool


_SUFFIX = r'(?:은|는|이|가|을|를)?(?:알려줘|알려주세요|알려줘요|언제|언제야|언제인가요|언제예요|언제인지알려줘|어떻게돼|어떻게되나요|말해줘)?'
_COURSE_DATE = r'개강일|개강날짜|개강|종강일|종강날짜|종강'
_PERIOD_DATE = r'시작일|시작날짜|시작|종료일|종료날짜|종료|끝나는날|끝날짜'
_COURSE = re.compile(r'^(?:(?:우리|저희|내|이번|현재)(?:의)?)?(?:(?:기수|과정|훈련과정|교육과정|캠프)(?:의)?)?'
    rf'(?P<first>{_COURSE_DATE})(?:(?:과|와|랑|및|하고|/|,)?(?P<second>{_COURSE_DATE}))?{_SUFFIX}$')
_PERIOD = re.compile(r'^(?:(?:이번|현재|지금|내|우리))?단위기간(?:의)?'
    rf'(?P<first>{_PERIOD_DATE})(?:(?:과|와|랑|및|하고|/|,)?(?P<second>{_PERIOD_DATE}))?{_SUFFIX}$')
_PERIOD_RANGE = re.compile(r'^(?:(?:이번|현재|지금|내|우리))?단위기간(?:은|는|이)?'
                          r'언제부터언제까지(?:야|예요|인가요|인지알려줘|알려줘)?$')


def parse_simple_schedule_request(question: str) -> ScheduleRequest | None:
    # Removing whitespace does not remove words/conditions/mixed intent. Whole
    # string matching excludes after/before rules, changed notices and class topics.
    text = re.sub(r'\s+', '', question).rstrip('?!。.!')
    if _PERIOD_RANGE.fullmatch(text):
        return ScheduleRequest(True, True, True)
    for period, pattern in ((False, _COURSE), (True, _PERIOD)):
        match = pattern.fullmatch(text)
        if match:
            terms = [match['first'], match['second'] or '']
            return ScheduleRequest(period,
                any(term.startswith('시작' if period else '개강') for term in terms),
                any(term.startswith(('종료', '끝') if period else '종강') for term in terms))
    return None


def validated_schedule_dates(context: dict, cohort: str, request: ScheduleRequest):
    if (not isinstance(context, dict) or context.get('schedule_status') != 'generated_unconfirmed'
            or context.get('unavailable_reason') or context.get('calendar_unavailable_reason')):
        return None
    try:
        snapshot = context['policy_calculation']
        if snapshot.get('status') != 'unverified' or snapshot.get('cohort') != cohort:
            return None
        basis = validated_calendar_basis(snapshot)
        if basis != context.get('calendar_basis'):
            return None
        start, end = date.fromisoformat(context['course_start_date']), date.fromisoformat(context['course_end_date'])
        if end < start:
            return None
        if request.current_period:
            current = context.get('current_unit_period')
            rows = [row for row in context.get('periods', []) if row.get('number') == current]
            if type(current) is not int or len(rows) != 1:
                return None
            period_start, period_end = date.fromisoformat(rows[0]['start_date']), date.fromisoformat(rows[0]['end_date'])
            as_of = date.fromisoformat(context['as_of'])
            if not start <= period_start <= as_of <= period_end <= end:
                return None
            start, end = period_start, period_end
        return start, end
    except (KeyError, TypeError, ValueError):
        return None


def schedule_answer(request: ScheduleRequest, dates) -> str:
    def formatted(value):
        return f'{value.year}년 {value.month}월 {value.day}일'
    start, end = dates
    if request.current_period:
        labels = ('현재 단위기간 시작일', '종료일')
        note = '등록 일정과 현재 정책 산정 규칙에 따른 잠정 일정이에요.'
    else:
        labels = ('등록된 개강일', '종강일')
        note = '현재 등록 일정 기준이며, 별도의 변경 공지를 확인한 답변은 아니에요.'
    parts = []
    if request.start:
        parts.append(f'{labels[0]}은 **{formatted(start)}**')
    if request.end:
        parts.append(f'{labels[1]}은 **{formatted(end)}**')
    return ', '.join(parts) + '이에요.\n\n' + note
