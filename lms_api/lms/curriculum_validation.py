"""Pure validation for curriculum replacement; no database or network access."""
from __future__ import annotations

from datetime import date, datetime
import re


_WEEKDAY = r'[월화수목금토일](?:요일)?'
_WEEKDAY_SUFFIX = re.compile(
    rf'(?:\((?P<paren>{_WEEKDAY})\)|\[(?P<bracket>{_WEEKDAY})\]|(?P<plain>{_WEEKDAY}))?'
)
_DATE_PATTERNS = (
    re.compile(r'(?P<year>\d{4})\s*년\s*(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일'),
    re.compile(r'(?P<year>\d{4})\s*(?P<sep>[-./])\s*(?P<month>\d{1,2})\s*(?P=sep)\s*(?P<day>\d{1,2})'),
    re.compile(r'(?P<month>\d{1,2})\s*월\s*(?P<day>\d{1,2})\s*일'),
    re.compile(r'(?P<month>\d{1,2})\s*[/.]\s*(?P<day>\d{1,2})'),
)


def _error(row_number, day_index, message):
    day_label = f'{day_index}일차' if day_index is not None else '교육일차 미확인'
    raise ValueError(f'커리큘럼 {row_number}행 ({day_label}): {message}')


def _integer(value, *, minimum, row_number, day_index, field):
    # Accept JSON integers and digit strings; do not truncate floats or bools.
    if type(value) is int:
        normalized = value
    elif isinstance(value, str) and re.fullmatch(r'[0-9]+', value.strip()):
        try:
            normalized = int(value.strip())
        except ValueError:
            _error(row_number, day_index, f'{field} 값이 너무 큽니다.')
    else:
        _error(row_number, day_index, f'{field}는 {"양의" if minimum else "0 이상의"} 정수여야 합니다.')
    if not minimum <= normalized <= 2_147_483_647:
        _error(row_number, day_index, f'{field}는 {minimum} 이상인 저장 가능한 정수여야 합니다.')
    return normalized


def _course_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _parse_date(label, *, start, end, row_number, day_index):
    text = label.strip()
    if not text or re.fullmatch(r'[1-9][0-9]*\s*일차', text):
        return None
    match = next((m for pattern in _DATE_PATTERNS if (m := pattern.match(text))), None)
    if match is None:
        _error(row_number, day_index, '날짜 형식을 확인해 주세요. 실제 날짜 또는 일차 표시를 사용해 주세요.')
    suffix = _WEEKDAY_SUFFIX.fullmatch(text[match.end():].strip())
    if suffix is None:
        _error(row_number, day_index, '날짜 뒤에는 올바른 요일 표시만 사용할 수 있습니다.')
    month, day = int(match['month']), int(match['day'])
    year_text = match.groupdict().get('year')
    if year_text:
        try:
            parsed = date(int(year_text), month, day)
        except ValueError:
            _error(row_number, day_index, '존재하지 않는 날짜입니다.')
        if start is None or end is None:
            _error(row_number, day_index, '날짜 범위를 검증할 기수 시작일·종료일이 없습니다.')
        if not start <= parsed <= end:
            _error(row_number, day_index, '날짜가 해당 기수의 시작일·종료일 범위를 벗어납니다.')
    else:
        if start is None or end is None:
            _error(row_number, day_index, '연도 없는 날짜는 기수 시작일·종료일이 있어야 확인할 수 있습니다.')
        candidates = []
        for year in range(start.year, end.year + 1):
            try:
                candidate = date(year, month, day)
            except ValueError:
                continue
            if start <= candidate <= end:
                candidates.append(candidate)
        if not candidates:
            _error(row_number, day_index, '존재하지 않거나 기수 기간 밖의 날짜입니다. 연도를 포함해 주세요.')
        if len(candidates) != 1:
            _error(row_number, day_index, '기수 기간에서 연도를 하나로 확정할 수 없습니다. 연도를 포함해 주세요.')
        parsed = candidates[0]
    weekday = next((value for value in suffix.groupdict().values() if value), None)
    if weekday and weekday[0] != '월화수목금토일'[parsed.weekday()]:
        _error(row_number, day_index, '표시된 요일이 실제 날짜의 요일과 다릅니다.')
    return parsed


def validate_curriculum_rows(rows, *, course_start=None, course_end=None):
    """Return normalized copies in input order; retain original dateLabel text.

    Dated rows require both course bounds. Blank/N일차 learning-plan rows are
    allowed without inventing dates. A day may contain several subject rows.
    """
    if not isinstance(rows, list) or not rows:
        raise ValueError('커리큘럼 rows는 비어 있지 않은 행 목록이어야 합니다. 기존 시트는 교체하지 않았습니다.')
    start, end = _course_date(course_start), _course_date(course_end)
    if start and end and end < start:
        raise ValueError('기수 종료일이 시작일보다 앞입니다. 커리큘럼 날짜를 검증할 수 없습니다.')
    normalized, dates_by_day, days_by_date = [], {}, {}
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            _error(number, None, '각 행은 객체여야 합니다.')
        day_index = _integer(row.get('dayIndex'), minimum=1, row_number=number,
                             day_index=None, field='교육일차')
        item = dict(row)
        item['dayIndex'] = day_index
        for field in ('dateLabel', 'subject', 'topic', 'detail'):
            value = row.get(field)
            if value is None:
                value = ''
            if not isinstance(value, str):
                _error(number, day_index, f'{field}는 문자열이어야 합니다.')
            item[field] = value
        order = row.get('order')
        if order is None or order == '':
            order = number - 1
        item['order'] = _integer(order, minimum=0, row_number=number,
                                 day_index=day_index, field='표시 순서')
        parsed = _parse_date(item['dateLabel'], start=start, end=end,
                             row_number=number, day_index=day_index)
        if parsed is not None:
            previous = dates_by_day.get(day_index)
            if previous and previous[0] != parsed:
                _error(number, day_index, f'같은 교육일차의 날짜가 {previous[1]}행과 다릅니다.')
            other_day = days_by_date.get(parsed)
            if other_day is not None and other_day != day_index:
                _error(number, day_index, f'{parsed.isoformat()} 날짜가 {other_day}일차와 중복됩니다.')
            dates_by_day.setdefault(day_index, (parsed, number))
            days_by_date[parsed] = day_index
        normalized.append(item)
    previous = None
    for day_index, (parsed, number) in sorted(dates_by_day.items()):
        if previous and parsed < previous[1]:
            _error(number, day_index, f'교육일차 순으로 날짜가 역전됩니다. {previous[0]}일차보다 날짜가 앞입니다.')
        previous = (day_index, parsed)
    return normalized
