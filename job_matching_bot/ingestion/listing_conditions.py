"""목록 한 줄의 조건 글을 지역·경력·고용형태·학력으로 가른다.

## 왜 필요한가

상세를 받아야만 저장소에 들어간다. 그래서 목록에서 본 4만 8천 건 중 1만 8천 건이
회사·제목·조건을 다 갖고 있는데도 챗봇 검색에 안 잡힌다. 더 큰 것은 IT 밖 10개
대분류다. 상세를 안 받기로 했으므로 그쪽은 **영영 0건**이다. "서울 영업직 있어?"에
없어서가 아니라 우리가 안 갖고 있어서 답을 못 한다.

조건은 목록에 이미 있다. 한 줄에 붙어 있을 뿐이다.

    서울 강남구 3 ~ 11년 · 정규직 대학(2,3년)↑
    경기 평택시 외 신입 · 경력 · 정규직 외 고졸↑
    경북 김천시 경력 2년↑ · 정규직 학력무관

챗봇 검색은 `region LIKE '%서울%'` 처럼 이 값들로만 거른다. 안 가르면 전부 미기재가
되어 어떤 지역 검색에도 안 걸린다. 그래서 이 파싱이 되어야 나머지가 의미를 갖는다.

## 어떻게 가르나

양 끝에서 안으로 좁힌다. 가운데(경력)가 가장 변덕스러워 마지막에 남긴다.

1. **학력은 맨 뒤**다. `고졸↑` `대학(2,3년)↑` `학력무관` 중 하나로 끝난다.
2. **고용형태는 그 앞**이다. `정규직` `계약직` 같은 말이고 `외`가 붙기도 한다.
3. **지역은 맨 앞**이다. 시·도로 시작하고 `외`가 붙기도 한다.
4. **남는 가운데가 경력**이다. `신입 · 경력` 처럼 가운뎃점이 들어가기도 한다.

값을 뽑은 뒤 해석은 `saramin.py`의 파서를 그대로 쓴다. 상세로 만든 공고와 같은
규칙이어야 챗봇 검색에서 두 종류가 섞여도 결과가 어긋나지 않는다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from datetime import date, datetime, timedelta, timezone

from job_matching_bot.ingestion.saramin import (
    parse_career,
    parse_education,
    parse_employment,
)

# 시·도. 목록의 지역은 늘 이 중 하나로 시작한다.
PROVINCES: tuple[str, ...] = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
    "전국", "해외",
)

_EDUCATION_TAIL = re.compile(
    r"(?:학력무관|고졸|중졸|초대졸|대학\s*\(2,\s*3년\)|대학교\s*\(4년\)|대졸|석사|박사)"
    r"\s*(?:이상|↑)?\s*$"
)
_EMPLOYMENT = re.compile(
    r"(정규직|계약직|인턴|파견직|프리랜서|아르바이트|파트타임|비정규직|병역특례)"
    r"(?:\s*외)?"
)
_REGION_HEAD = re.compile(r"^(?:" + "|".join(PROVINCES) + r")\S*(?:\s+\S+)?(?:\s*외)?")


@dataclass(frozen=True)
class ListingConditions:
    """목록 글에서 가른 조건. 못 가른 칸은 빈 문자열로 둔다."""

    region: str = ""
    career: str = ""
    employment: str = ""
    education: str = ""

    @property
    def parsed_count(self) -> int:
        return sum(1 for v in (self.region, self.career, self.employment, self.education) if v)


def split_condition_text(text: str) -> ListingConditions:
    """조건 한 줄을 네 토막으로. 못 가르면 그 칸만 비운다.

    통째로 실패하지 않는다. 지역만 걸려도 지역 검색에는 쓸 수 있다.
    """
    line = re.sub(r"\s+", " ", (text or "").strip())
    if not line:
        return ListingConditions()

    education = ""
    tail = _EDUCATION_TAIL.search(line)
    if tail:
        education = tail.group(0).strip()
        line = line[: tail.start()].strip()

    employment = ""
    hit = _EMPLOYMENT.search(line)
    if hit:
        employment = hit.group(0).strip()
        line = (line[: hit.start()] + " " + line[hit.end():]).strip()

    region = ""
    head = _REGION_HEAD.match(line)
    if head:
        region = head.group(0).strip()
        line = line[head.end():].strip()

    # 남은 것이 경력이다. 토막을 가르던 가운뎃점은 지운다.
    career = re.sub(r"^[·\s]+|[·\s]+$", "", line)
    career = re.sub(r"\s*·\s*", "·", career)
    return ListingConditions(region, career, employment, education)


def conditions_from_listing(text: str) -> dict[str, object]:
    """목록 글 → `Job`에 넣을 값. 해석은 상세와 같은 파서를 쓴다."""
    parts = split_condition_text(text)
    career_type, min_years, _ = parse_career(parts.career)
    education, _ = parse_education(parts.education)
    employment, _ = parse_employment(parts.employment)
    return {
        "region": parts.region or "미기재",
        "career_type": career_type,
        "min_career_years": min_years,
        "education": education,
        "employment_type": employment,
    }


KST = timezone(timedelta(hours=9))

# 목록의 마감 표기. `~09.30` 처럼 날짜로, 또는 말로 적힌다.
_DEADLINE_DATE = re.compile(r"~\s*(\d{1,2})[./](\d{1,2})")
_TODAY = re.compile(r"오늘\s*마감")
_TOMORROW = re.compile(r"내일\s*마감")
# 끝이 정해지지 않은 것. 마감일로 거르면 안 된다.
_OPEN_ENDED = re.compile(r"상시\s*채용|채용\s*시\s*마감|수시\s*채용")


def deadline_from_listing(support_text: str, today: date | None = None) -> str | None:
    """목록의 마감 표기를 날짜로. 모르면 None.

    None은 "마감일 없음"으로 읽혀 검색에서 안 걸러진다. 그래서 **읽을 수 없을 때만**
    None을 준다. 상시채용도 None이다 — 끝이 정해지지 않은 것이지 지난 것이 아니다.

    `~09.30` 에는 연도가 없다. 연도를 고를 때 **오늘에서 가장 가까운 쪽**을 쓴다.

    처음에는 "과거면 내년"으로 두었는데, 그러면 어제 마감한 `~09.05` 가 내년 9월로
    읽혀 영영 안 걸러진다. 목록에 남아 있는 마감은 대개 **막 지난 것**이지 1년 뒤가
    아니다. 반대로 12월에 보는 `~01.15` 는 내년이 맞다. 두 경우를 다 맞추려면
    올해·작년·내년 중 오늘과 가장 가까운 날을 고르면 된다.
    """
    text = (support_text or "").strip()
    if not text or _OPEN_ENDED.search(text):
        return None
    now = today or datetime.now(KST).date()
    if _TODAY.search(text):
        return f"{now.isoformat()}T23:59:59+09:00"
    if _TOMORROW.search(text):
        return f"{(now + timedelta(days=1)).isoformat()}T23:59:59+09:00"
    hit = _DEADLINE_DATE.search(text)
    if not hit:
        return None
    month, day = int(hit.group(1)), int(hit.group(2))
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    candidates = []
    for year in (now.year - 1, now.year, now.year + 1):
        try:
            candidates.append(date(year, month, day))
        except ValueError:
            continue
    if not candidates:
        return None
    found = min(candidates, key=lambda d: abs((d - now).days))
    return f"{found.isoformat()}T23:59:59+09:00"
