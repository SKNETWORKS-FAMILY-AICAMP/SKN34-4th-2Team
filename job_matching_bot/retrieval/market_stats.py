"""조건에 맞는 공고들이 실제로 무엇을 요구하는지 센다. 챗봇의 "채용 질문"이 쓴다.

## 왜 이게 있나

"요즘 백엔드 신입은 뭘 준비해야 해?"에 LLM 혼자 답하면 어디서나 들을 수 있는 말이 나온다.
우리는 공고 1만여 건을 갖고 있으므로 **실제로 세어서** 답할 수 있다. "지금 열려 있는
백엔드 신입 공고 412건 중 Spring을 적은 곳이 251건(61%)"은 우리 데이터가 있어야만
나오는 답이고, 사용자가 그 말을 믿을 근거도 된다.

## 어떻게 세나

조건은 `store_search.conditions()`를 그대로 쓴다. **검색과 같은 모수**여야 한다.
"412건 중 61%"라고 말해 놓고 목록에는 다른 공고가 나오면 답이 거짓말이 된다.

기술은 `tech_stack`, 직무는 `keywords`를 센다. 둘 다 수집할 때 사이트가 붙여 둔 태그라
본문에서 뽑은 값보다 깨끗하다. 상위 몇 개만 보여 준다 — 꼬리는 한두 건짜리라 비율이
의미가 없다.

## 세지 않는 것

연봉은 공고에 "회사 내규에 따름"이 대부분이라 세면 오히려 잘못된 인상을 준다.
합격률·경쟁률은 우리가 알 수 없다. 그런 걸 물으면 LLM이 모른다고 답한다.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from job_matching_bot.retrieval.store_search import KST, JobFilters, conditions, connect

# 집계에 훑을 최대 행. 저장소 전체가 이보다 작으므로 보통은 전수로 센다. 상한은
# 저장소가 훨씬 커졌을 때를 위한 안전장치다. 걸리면 "대략"이라고 밝히고 답한다.
SCAN_LIMIT = 20000
# 각 분포에서 보여 줄 상위 개수. 꼬리는 한두 건이라 비율이 의미 없다.
TOP_N = 8
# 이 안에 마감하는 것을 "임박"으로 센다.
CLOSING_DAYS = 14


@dataclass
class Share:
    """센 것 하나. `count`가 있어야 사용자가 비율을 의심할 수 있다."""

    name: str
    count: int
    percent: int

    def __str__(self) -> str:
        return f"{self.name} {self.count}건({self.percent}%)"


@dataclass
class MarketStats:
    """조건에 맞는 공고들의 생김새."""

    total: int
    scanned: int                                    # 실제로 센 행. total보다 작으면 표본이다
    scope: str = "지금 열려 있는 공고 전체"           # 무엇을 센 것인가. 표 첫 줄에 적는다
    skills: list[Share] = field(default_factory=list)
    roles: list[Share] = field(default_factory=list)
    regions: list[Share] = field(default_factory=list)
    careers: list[Share] = field(default_factory=list)
    employment_types: list[Share] = field(default_factory=list)
    educations: list[Share] = field(default_factory=list)
    closing_soon: int = 0
    sample_titles: list[str] = field(default_factory=list)

    @property
    def is_sample(self) -> bool:
        return self.scanned < self.total

    def to_prompt(self) -> str:
        """LLM에 넘길 표.

        첫 줄에 **무엇을 센 것인지** 적는다. 이게 없으면 모델이 모수를 믿지 못해
        표에 답이 있는데도 "전체 공고 기준이라 알 수 없다"고 물러선다. 실제로 그랬다.
        """
        lines = [
            f"센 것: {self.scope}",
            f"그 공고 수: {self.total}건",
        ]
        if self.is_sample:
            lines.append(f"(그중 최근 {self.scanned}건을 세어 낸 비율이다. 대략의 값)")
        lines.append("아래 분포는 모두 위 공고들만 센 것이다.")
        for label, shares in (
            ("자주 요구하는 기술", self.skills),
            ("직무 분류", self.roles),
            ("지역", self.regions),
            ("경력", self.careers),
            ("고용형태", self.employment_types),
            ("학력", self.educations),
        ):
            if shares:
                lines.append(f"- {label}: " + ", ".join(str(share) for share in shares))
        if self.closing_soon:
            lines.append(f"- {CLOSING_DAYS}일 안에 마감: {self.closing_soon}건")
        if self.sample_titles:
            lines.append("- 공고 제목 예: " + " / ".join(self.sample_titles))
        return "\n".join(lines)


_CAREER_LABELS = {"ENTRY": "신입", "EXPERIENCED": "경력", "ANY": "경력무관"}

# 시·도. 지역을 이 단위로 묶는다. 구·군까지 세면 "서울 강남구 17%"처럼 잘게 흩어져
# "서울이 절반"이라는 정작 쓸모 있는 사실이 보이지 않는다.
SIDO = (
    "서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
    "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주",
)
# 사이트의 분류 태그에는 직무와 지역이 섞여 있다. 지역은 직무 분포에서 뺀다.
_REGION_TAGS = {*SIDO, "전국", "해외", "충청북도", "충청남도", "전라북도", "전라남도",
                "경상북도", "경상남도", "강원도", "경기도", "제주도"}


def summarize(
    store_path: Path, filters: JobFilters, as_of: datetime | None = None
) -> MarketStats:
    """조건에 맞는 공고를 훑어 분포를 낸다."""
    as_of = as_of or datetime.now(KST)
    where, params = conditions(filters, as_of)
    clause = " AND ".join(where)
    scope = describe(filters)

    # 검색과 같은 연결 함수를 쓴다. 조건에 RE_HAS 가 들어갈 수 있어 등록이 필요하다.
    connection = connect(store_path)
    try:
        total = connection.execute(
            f"SELECT COUNT(*) FROM jobs WHERE {clause}", params
        ).fetchone()[0]
        if not total:
            return MarketStats(total=0, scanned=0, scope=scope)

        until = _plus_days(as_of, CLOSING_DAYS)
        closing = connection.execute(
            f"SELECT COUNT(*) FROM jobs WHERE {clause} "
            "AND deadline IS NOT NULL AND substr(deadline, 1, 10) <= ?",
            [*params, until],
        ).fetchone()[0]

        rows = connection.execute(
            f"SELECT title, tech_stack, keywords, region, career_type, employment_type, "
            f"education FROM jobs WHERE {clause} ORDER BY first_seen_at DESC LIMIT ?",
            [*params, SCAN_LIMIT],
        ).fetchall()
    finally:
        connection.close()

    scanned = len(rows)
    skills: Counter[str] = Counter()
    roles: Counter[str] = Counter()
    regions: Counter[str] = Counter()
    careers: Counter[str] = Counter()
    employment: Counter[str] = Counter()
    educations: Counter[str] = Counter()

    for row in rows:
        # 한 공고가 같은 기술을 두 번 적어도 한 건으로 센다.
        skills.update(set(_tags(row["tech_stack"])))
        roles.update({tag for tag in _tags(row["keywords"]) if not _is_region(tag)})
        # 한 공고가 여러 지역을 적기도 한다. 시·도로 묶어 중복을 없앤다.
        regions.update({_sido(part) for part in (row["region"] or "").split(",")} - {""})
        careers.update({_CAREER_LABELS.get(row["career_type"] or "", "미기재")})
        employment.update({_first(row["employment_type"])} - {""})
        educations.update({(row["education"] or "").strip()} - {""})

    return MarketStats(
        total=total,
        scanned=scanned,
        scope=scope,
        skills=_top(skills, scanned),
        roles=_top(roles, scanned),
        regions=_top(regions, scanned, limit=6),
        careers=_top(careers, scanned, limit=3),
        employment_types=_top(employment, scanned, limit=4),
        educations=_top(educations, scanned, limit=4),
        closing_soon=closing,
        sample_titles=[(row["title"] or "").strip() for row in rows[:3] if row["title"]],
    )


def describe(filters: JobFilters) -> str:
    """무엇을 세는지 사람 말로. 조건이 없으면 전체다.

    경력은 그대로 옮기면 안 된다. "신입"으로 거르면 신입 명시 공고와 경력무관 공고가
    함께 걸리는데, 표에 "신입 공고"라고만 적으면 모델이 경력무관 몫까지 신입이라고
    말하거나, 반대로 모수를 의심해 답을 접는다. 무엇이 들어갔는지 그대로 밝힌다.
    """
    parts = [*filters.roles, *filters.skills]
    if filters.regions:
        parts.append("·".join(filters.regions))
    parts.extend(filters.employment_types)
    parts.extend(filters.keywords)
    if filters.deadline_within_days:
        parts.append(f"{filters.deadline_within_days}일 안에 마감하는")

    note = ""
    if filters.career == "신입":
        parts.append("신입이 지원할 수 있는")
        note = " (신입 명시 공고와 경력무관 공고를 함께 센 것)"
    elif filters.career == "경력":
        parts.append("경력자를 뽑는")
        note = " (경력 명시 공고와 경력무관 공고를 함께 센 것)"

    if not parts:
        return "지금 열려 있는 공고 전체"
    return "지금 열려 있는 " + " ".join(parts) + " 공고" + note


def _top(counter: Counter[str], scanned: int, limit: int = TOP_N) -> list[Share]:
    return [
        Share(name=name, count=count, percent=round(count * 100 / scanned))
        for name, count in counter.most_common(limit)
        if count > 1  # 한 건짜리는 비율로 말할 것이 못 된다
    ]


def _tags(raw: str | None) -> list[str]:
    try:
        values = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _first(raw: str | None) -> str:
    return (raw or "").split(",")[0].strip()


def _is_region(tag: str) -> bool:
    """분류 태그가 지역인가. 사이트가 직무와 지역을 한 칸에 섞어 둔다."""
    if tag in _REGION_TAGS:
        return True
    # "강남구", "성남시", "달성군". 두 글자는 "연구"처럼 직무일 수 있어 건드리지 않는다.
    return len(tag) >= 3 and tag[-1] in "구시군"


def _sido(raw: str) -> str:
    """"서울특별시 강남구" → "서울". 시·도를 못 찾으면 빈 문자열."""
    text = raw.strip()
    for name in SIDO:
        if text.startswith(name):
            return name
    return ""


def _plus_days(as_of: datetime, days: int) -> str:
    from datetime import timedelta

    return (as_of + timedelta(days=days)).date().isoformat()
