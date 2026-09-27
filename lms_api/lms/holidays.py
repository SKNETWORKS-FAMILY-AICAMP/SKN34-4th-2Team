"""공휴일 — 출석 달력이 일요일처럼 칠할 날.

공공데이터포털 「한국천문연구원 특일 정보」(`getRestDeInfo`)를 해마다 한 번 받아 서버 메모리에 둔다.
DB 에는 저장하지 않는다. 키는 `.env` 의 `DATA_GO_KR_API_KEY` 다(자격 시험 일정 키와 다른 키).

키가 없거나 포털이 응답하지 않으면 원본 앱(Flutter)이 쓰던 표(`FALLBACK`, 2026~2028)로 답한다.
그래서 키가 없는 팀원 PC 에서도 달력은 제대로 나온다. 표는 `scripts/fetch_holidays.py` 가 만든 것이다.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

URL = "https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo"

# 받은 해는 하루 두고 다시 묻는다. 임시공휴일은 며칠 앞서 지정되므로 하루면 충분하다.
# 실패한 해는 10분 뒤에 다시 묻는다. 요청마다 포털을 두드리지 않게.
_TTL_OK = 24 * 3600.0
_TTL_FAIL = 600.0
_cache: dict[int, tuple[float, dict[str, str]]] = {}
_lock = threading.Lock()

# 원본 lib/core/constants/korean_holidays.dart 그대로.
FALLBACK: dict[str, str] = {
    "2026-01-01": "1월1일",
    "2026-02-16": "설날",
    "2026-02-17": "설날",
    "2026-02-18": "설날",
    "2026-03-01": "삼일절",
    "2026-03-02": "대체공휴일(삼일절)",
    "2026-05-01": "노동절",
    "2026-05-05": "어린이날",
    "2026-05-24": "부처님오신날",
    "2026-05-25": "대체공휴일(부처님오신날)",
    "2026-06-03": "전국동시지방선거",
    "2026-06-06": "현충일",
    "2026-07-17": "제헌절",
    "2026-08-15": "광복절",
    "2026-08-17": "대체공휴일(광복절)",
    "2026-09-24": "추석",
    "2026-09-25": "추석",
    "2026-09-26": "추석",
    "2026-10-03": "개천절",
    "2026-10-05": "대체공휴일(개천절)",
    "2026-10-09": "한글날",
    "2026-12-25": "기독탄신일",
    "2027-01-01": "1월1일",
    "2027-02-06": "설날",
    "2027-02-07": "설날",
    "2027-02-08": "설날",
    "2027-02-09": "대체공휴일(설날)",
    "2027-03-01": "삼일절",
    "2027-05-01": "노동절",
    "2027-05-03": "대체공휴일(노동절)",
    "2027-05-05": "어린이날",
    "2027-05-13": "부처님오신날",
    "2027-06-06": "현충일",
    "2027-07-17": "제헌절",
    "2027-07-19": "대체공휴일(제헌절)",
    "2027-08-15": "광복절",
    "2027-08-16": "대체공휴일(광복절)",
    "2027-09-14": "추석",
    "2027-09-15": "추석",
    "2027-09-16": "추석",
    "2027-10-03": "개천절",
    "2027-10-04": "대체공휴일(개천절)",
    "2027-10-09": "한글날",
    "2027-10-11": "대체공휴일(한글날)",
    "2027-12-25": "기독탄신일",
    "2027-12-27": "대체공휴일(기독탄신일)",
    "2028-01-01": "1월1일",
    "2028-01-26": "설날",
    "2028-01-27": "설날",
    "2028-01-28": "설날",
    "2028-03-01": "삼일절",
    "2028-04-12": "국회의원선거일",
    "2028-05-01": "노동절",
    "2028-05-02": "부처님오신날",
    "2028-05-05": "어린이날",
    "2028-06-06": "현충일",
    "2028-07-17": "제헌절",
    "2028-08-15": "광복절",
    "2028-10-02": "추석",
    "2028-10-03": "개천절·추석",
    "2028-10-04": "추석",
    "2028-10-05": "대체공휴일(추석)",
    "2028-10-09": "한글날",
    "2028-12-25": "기독탄신일",
}


def _fallback(year: int) -> dict[str, str]:
    prefix = f"{year}-"
    return {day: name for day, name in FALLBACK.items() if day.startswith(prefix)}


def _service_key() -> str:
    key = (os.environ.get("DATA_GO_KR_API_KEY") or "").strip().strip('"').strip("'")
    # 포털은 인코딩 키와 디코딩 키를 둘 다 준다. 인코딩된 키를 다시 인코딩하면
    # `%2F`가 `%252F`가 되어 403 이 온다. 한 번 풀어 두고 보낼 때 한 번만 인코딩한다.
    return urllib.parse.unquote(key)


def _fetch(year: int, key: str) -> dict[str, str]:
    query = urllib.parse.urlencode(
        {"serviceKey": key, "solYear": year, "_type": "json", "numOfRows": 100}
    )
    with urllib.request.urlopen(f"{URL}?{query}", timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))["response"]["body"]
    if not body.get("totalCount"):
        return {}
    items = body["items"]["item"]
    # 한 건만 있으면 리스트가 아니라 객체로 온다.
    if isinstance(items, dict):
        items = [items]
    # 하루에 이름이 둘일 수 있다(2028-10-03 개천절 · 추석). 이름을 이어 적는다.
    days: dict[str, list[str]] = {}
    for item in items:
        # 기념일 · 절기도 같은 창구로 오므로 실제로 쉬는 날만 남긴다.
        if item.get("isHoliday") != "Y":
            continue
        date = str(item["locdate"])
        day = f"{date[:4]}-{date[4:6]}-{date[6:]}"
        name = str(item["dateName"])
        if name not in days.setdefault(day, []):
            days[day].append(name)
    return {day: "·".join(names) for day, names in sorted(days.items())}


def holidays_of(year: int) -> dict[str, str]:
    """그 해 쉬는 날 {"YYYY-MM-DD": 이름}."""
    now = time.monotonic()
    with _lock:
        hit = _cache.get(year)
        if hit is not None and hit[0] > now:
            return hit[1]
    key = _service_key()
    if not key:
        return _fallback(year)
    try:
        days, ttl = _fetch(year, key), _TTL_OK
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        # 응답 본문에는 키가 실려 오므로 로그에 남기지 않는다.
        days, ttl = _fallback(year), _TTL_FAIL
    with _lock:
        _cache[year] = (now + ttl, days)
    return days
