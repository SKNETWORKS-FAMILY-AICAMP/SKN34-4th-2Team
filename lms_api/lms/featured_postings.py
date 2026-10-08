"""공고 맞춤 지원 첫 화면의 「주요 기업 채용」 카드 — 대기업 · 인기 기업 · 외국계 공고를 고른다.

수집 공고는 6만 건 가까이 되고 대부분 중소기업이다. 첫 화면에는 수강생이 먼저 찾는 회사만 둔다.

- 대기업: 상세 페이지 기업 정보 칸(`company_type`)이 대기업. 「1000대기업」은 중견도 들어가 치지 않는다
  (job_matching_bot/retrieval/store_search.COMPANY_TYPES 와 같은 규칙). 잡코리아 공고는 기업형태가 비어
  (미기재) 있어, 사람인에서 대기업으로 확인된 회사 이름(`big_names`)으로 알아본다
- 인기 기업: 토스 · 우아한형제들 · 당근처럼 대기업이 아닌데 수강생이 찾는 회사. 인기 자료가 없어 이름 목록으로 둔다
- 외국계: 외국인 투자 · 외국 법인 중 중견기업 이상이거나 상장사. 작은 외국인 투자기업과 파견사가 대부분이라 좁히고,
  공채를 다 넣으면 이름 모를 제조 · 바이오 회사가 판을 채워 개발 직군 공고만 둔다

공고는 신입이 낼 수 있고, 계약직 · 알바가 아니고, 개발 직군이거나 개발 아닌 부문을 적지 않은 공채여야 한다.
같은 공고가 사람인 · 잡코리아에 함께 올라오면 수집기가 group_key 로 묶어 둔다 — 한 공고로 센다.
회사마다 카드 한 장. 안 그러면 현대자동차(공고 42건) · 쿠팡이 판을 다 채운다.

- 진행 중(`pick_live`): 열린 공고, 마감 임박순. 날짜 없는 상시채용은 뒤로
- 지난 공채(`pick_past`): 최근 1년 안에 마감한 공채. 회사 · 시즌마다 한 장, 최근 마감순 — 지난 문항으로 미리 쓰는 입구
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from typing import Any, Iterable

TIERS = ("인기 기업", "대기업", "외국계")

# 법인 표기 · 띄어쓰기를 뗀 이름 — 「(주)카카오」 「카카오 (주)」 = 카카오. SQL 의 NORM_SQL 과 같다
_LEGAL = re.compile(r"\(주\)|\(유\)|㈜|주식회사|유한회사|\s")
NORM_SQL = r"regexp_replace(company, '\(주\)|\(유\)|㈜|주식회사|유한회사|\s', '', 'g')"
# company_profiles.company_key 와 같은 열쇠 — recruit_role_store.canonical_company_key(NFKC · 소문자 · 앞뒤 법인 표기만 뗌)를
# SQL 로 옮긴 것. 우리 NORM_SQL 과 규칙이 달라 따로 둔다(2026-10-08 공고 회사 이름 36,578개에서 둘이 모두 같음)
PROFILE_KEY_SQL = r"""regexp_replace(regexp_replace(lower(regexp_replace(normalize(j.company, NFKC), '^\s+|\s+$', '', 'g')),
    '^(주식회사|\(주\)|㈜)\s*|\s*(주식회사|\(주\)|㈜)$', '', 'g'), '\s+', '', 'g')"""
# 사이트마다 붙였다 뗐다 하는 영문 이름 — 「엠디엑스 주식회사(MDX Inc.)」 「(MDX lnc.)」
_ENGLISH_ALIAS = re.compile(r"\([A-Za-z0-9 .,&'-]+\)")

# 이 이름으로 시작하면 인기 기업. 짧아서 다른 회사에 걸리는 이름(쿠팡풀필먼트 · 넥슨화장품 · 컬리넌)은 _POPULAR_EXACT 에 둔다
_POPULAR_PREFIXES = (
    "네이버", "카카오", "라인플러스", "우아한형제들", "비바리퍼블리카", "토스뱅크", "토스페이먼츠", "토스증권",
    "토스인슈어런스", "당근마케팅", "당근페이", "무신사", "넷마블", "엔씨소프트", "크래프톤", "야놀자", "아마존웹서비시즈",
)
_POPULAR_EXACT = frozenset({"쿠팡", "넥슨", "넥슨코리아", "NC", "컬리"})

# 인력 파견 · 헤드헌팅사는 기업형태가 커도 다른 회사 공고를 대신 올린다
_AGENCY = re.compile(r"아데코|맨파워|헤드헌팅|에이치알그룹")

_BIG = re.compile(r"(?:^|,)\s*대기업\s*(?:,|$)")
_FOREIGN = re.compile(r"외국인 투|외국 법인|외국계")
_SIZED = re.compile(r"(?:^|,)\s*(?:대기업|중견기업|코스피|코스닥)\s*(?:,|$)")

_BAD_EMPLOYMENT = re.compile(r"계약|파견|아르바이트|프리랜서|파트타임")
_BAD_TITLE = re.compile(r"계약직|기간제|알바|아르바이트|파견|위촉|도급|체험형|장학생")
# 경력만 뽑는 공고. 경력 구분이 「경력무관」으로 적혀도 제목이 「경력직 채용」이면 신입은 못 낸다
_CAREER_ONLY = re.compile(r"경력\s*(?:직|사원)|경력\s*(?:채용|모집)")
_NEWCOMER = re.compile(r"신입")
# 교육 과정 모집 — 대기업 이름으로 올라와도 채용이 아니다(「[IBM] … AI agent 6기」).
# 강한 말(교육생 · 부트캠프)은 채용 말이 없으면 교육 과정, 약한 말(국비 · K-디지털 · 아카데미 · 「6기」)은
# 채용 말도 직무 말도 없을 때만 교육 과정이다 — 「K-디지털 수료 백엔드 개발」은 수료자를 뽑는 채용이다.
# job_matching_bot/retrieval/training.py 와 같은 규칙 — 한쪽을 바꾸면 같이 바꾼다
_TRAINING_STRONG = re.compile(r"교육생|수강생|훈련생|연수생|부트캠프")
_TRAINING_WEAK = re.compile(r"국비|K-?디지털|K-?뉴딜|KDT|교육\s*과정|과정|아카데미|academy|\d+\s*기(?![가-힣])", re.IGNORECASE)
_TRAINING_HIRE = re.compile(r"채용|공채|사원|직원|담당자|강사|교사|초빙|정규직|인력|코치|박사후|연구원")
_TRAINING_ROLE = re.compile(
    r"개발|엔지니어|디자이너|수료|출신|우대|이수|모십니다|매니저|기획|운영|멘토|컨설턴트|담당|PM|신입|경력|총괄|팀장|부장|임원|engineer|developer",
    re.IGNORECASE,
)


def _is_training(title: str) -> bool:
    if _TRAINING_HIRE.search(title):
        return False
    if _TRAINING_STRONG.search(title):
        return True
    return bool(_TRAINING_WEAK.search(title)) and not _TRAINING_ROLE.search(title)

# 개발 직군. 영문 두 글자(AI · IT)는 낱말일 때만 — mail · with 에 걸리지 않게
_DEV_TITLE = re.compile(
    r"개발|프로그래머|데이터(?!\s*센터)|인공지능|머신러닝|딥러닝|백엔드|프론트|풀스택|서버|클라우드|인프라|보안|소프트웨어|"
    r"정보시스템|전산|앱|developer|engineer|software|backend|frontend|full[- ]?stack|devops|cloud|data|"
    r"security|analyst|platform|(?<![a-z])(?:ai|ml|it|sw|s/w|qa|ios|android|llm)(?![a-z])",
    re.IGNORECASE,
)
# 공채 · 수시 · 채용형 인턴 — 전 부문을 한 공고로 뽑아 개발 직군 말이 제목에 없다
_OPEN_HIRING = re.compile(
    r"공채|공개\s*채용|신입\s*사원|신입\s*행원|신입\s*(?:채용|모집)|대졸\s*신입|수시\s*채용|채용형\s*인턴|채용연계형"
)
# 공채 제목에 부문을 적었는데 개발이 아닌 것 — 「신입사원 채용(건축-플랜트건축)」 「공개채용 (지점영업)」
_NON_DEV_FIELD = re.compile(
    r"건축|토목|플랜트|원자력|시공|설계|생산|제조|품질|영업|사업|법무|HR|재무|재경|회계|인사|총무|경영지원|경영기획|환경|안전|보건|"
    r"병리|간호|약사|물류|구매|마케팅|디자인|지점|창구|현장|정비|조리|판매"
)

_DATE = re.compile(r"^(\d{4})[-.](\d{2})[-.](\d{2})")
_SEASON_IN_TITLE = re.compile(r"(20\d\d|\d\d)\s*년?\s*(?:도\s*)?(상반기|하반기)")
_ROLLING = re.compile(r"수시|상시")

# DB 에서 먼저 줄이는 조건 — 기업형태나 이름에 이 말이 있는 공고만 가져와 아래 함수로 다시 고른다
COARSE_TYPE = r"대기업|외국인 투|외국 법인|외국계"
COARSE_NAME = "|".join((*_POPULAR_PREFIXES, *sorted(_POPULAR_EXACT)))
BIG_TYPE = _BIG.pattern
SMALLER_TYPE = r"(?:^|,)\s*(?:중견기업|중소기업)\s*(?:,|$)"

PAST_DAYS = 365


def company_key(company: str) -> str:
    """법인 표기 · 띄어쓰기만 뗀 이름. SQL(NORM_SQL)과 같아 `big_names` 를 이것으로 견준다."""
    return _LEGAL.sub("", company or "")


def card_key(company: str) -> str:
    """카드를 묶는 이름 — 영문 별칭까지 뗀다. 사이트마다 달리 적은 같은 회사를 한 장으로."""
    return company_key(_ENGLISH_ALIAS.sub("", company or "")) or company_key(company)


def display_name(company: str) -> str:
    return re.sub(r"\(주\)|\(유\)|㈜|주식회사|유한회사", "", company or "").strip()


def tier_of(
    company: str, company_type: str, big_names: frozenset[str] = frozenset(), small_names: frozenset[str] = frozenset()
) -> str | None:
    """인기 기업 · 대기업 · 외국계 중 하나, 셋 다 아니면 None.

    `big_names` 는 다른 공고에서 대기업으로 확인된 회사 이름(company_key). `small_names` 는 사람인이
    중견 · 중소로만 적은 회사 — 잡코리아의 「대기업」 분류는 넓어(비상교육) 사람인 쪽을 따른다.
    코치 검색(job_matching_bot/retrieval/store_search._NOT_SMALLER_ON_SARAMIN)과 같은 규칙이다.
    """
    key = company_key(company)
    if _AGENCY.search(key):
        return None
    if key in _POPULAR_EXACT or key.startswith(_POPULAR_PREFIXES):
        return "인기 기업"
    kind = company_type or ""
    if (_BIG.search(kind) or key in big_names) and key not in small_names:
        return "대기업"
    if _FOREIGN.search(kind) and _SIZED.search(kind):
        return "외국계"
    return None


def date_of(value: str | None) -> str | None:
    """「YYYY-MM-DD」. 상시채용 · 채용시 마감처럼 날짜가 없으면 None. 「2026.09.20」도 읽는다."""
    found = _DATE.match((value or "").strip())
    return "-".join(found.groups()) if found else None


def is_open_hiring(title: str) -> bool:
    return bool(_OPEN_HIRING.search(title or ""))


def wanted(row: dict[str, Any], tier: str = "") -> bool:
    """수강생이 낼 만한 공고인가 — 정규직(또는 채용형 인턴)이고, 개발 직군이거나 개발 아닌 부문을 적지 않은 공채다."""
    title = row.get("title") or ""
    if _BAD_EMPLOYMENT.search(row.get("employment_type") or "") or _BAD_TITLE.search(title):
        return False
    if _CAREER_ONLY.search(title) and not _NEWCOMER.search(title):
        return False
    if _is_training(title):
        return False
    if _DEV_TITLE.search(title):
        return True
    if tier == "외국계" or not _OPEN_HIRING.search(title):
        return False
    return not _NON_DEV_FIELD.search(title)


def season_of(title: str, posted_at: str | None, deadline: str | None) -> str:
    """「2026 하반기」 · 「수시」. 제목에 적힌 시즌이 먼저, 없으면 접수 시작일(모르면 마감일)의 달로 정한다."""
    found = _SEASON_IN_TITLE.search(title or "")
    if found:
        year = int(found.group(1))
        return f"{year + 2000 if year < 100 else year} {found.group(2)}"
    if _ROLLING.search(title or ""):
        return "수시"
    day = date_of(posted_at) or date_of(deadline)
    if day is None:
        return "수시"
    return f"{day[:4]} {'상반기' if int(day[5:7]) <= 6 else '하반기'}"


def _skills(value: Any) -> list[str]:
    if isinstance(value, str):
        try:
            value = json.loads(value or "[]")
        except json.JSONDecodeError:
            return []
    return [str(s) for s in value or []][:3]


def _homepage(rows: list[dict[str, Any]]) -> bool | None:
    """홈페이지 지원인가. 한 사본이라도 HOMEPAGE 면 True, 아는 값이 다른 것뿐이면 False, 모르면 None."""
    methods = {r.get("apply_method") for r in rows if r.get("apply_method")}
    if not methods:
        return None
    return "HOMEPAGE" in methods


def _groups(rows: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """같은 공고(group_key)끼리 묶는다. 대표 사본은 본문 · 기업 정보가 있는 사람인이 앞."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row.get("group_key") or row["job_id"], []).append(row)
    for copies in groups.values():
        copies.sort(key=lambda r: (not str(r.get("source") or "").startswith("SARAMIN"), r["job_id"]))
    return groups


def _card(copies: list[dict[str, Any]], tier: str, deadline: str | None, count: int, *, closed: bool) -> dict[str, Any]:
    head = copies[0]
    title = head.get("title") or ""
    return {
        "job_id": head["job_id"],
        "company": display_name(head.get("company") or ""),
        "title": title,
        "tier": tier,
        "deadline": deadline,
        "season": season_of(title, head.get("posted_at"), head.get("deadline")),
        "career_type": head.get("career_type") or "",
        "posting_count": count,
        "skills": _skills(head.get("tech_stack")),
        "open_hiring": is_open_hiring(title),
        "homepage": _homepage(copies),
        "logo_url": next((r["logo_url"] for r in copies if r.get("logo_url")), None),
        "closed": closed,
    }


def _qualified(rows: Iterable[dict[str, Any]], big_names: frozenset[str], small_names: frozenset[str]):
    """(공고 사본들, 기업 구분, 마감일) — 기업 · 공고 조건을 넘은 것만. 한 사본이라도 넘으면 그 공고는 넘은 것으로 본다."""
    for copies in _groups(rows).values():
        tiers = [(r, tier_of(r.get("company") or "", r.get("company_type") or "", big_names, small_names)) for r in copies]
        passed = [(r, t) for r, t in tiers if t is not None and wanted(r, t)]
        if not passed:
            continue
        tier = min((t for _, t in passed), key=TIERS.index)
        deadline = min((d for r in copies if (d := date_of(r.get("deadline")))), default=None)
        yield copies, tier, deadline


def pick_live(
    rows: Iterable[dict[str, Any]], today: date,
    big_names: frozenset[str] = frozenset(), small_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """진행 중 — 회사마다 카드 한 장. 마감이 가장 가까운 공고를 올리고 공고 수를 붙인다. 마감 임박순, 상시채용은 뒤로."""
    by_company: dict[str, list[tuple[list[dict[str, Any]], str, str | None]]] = {}
    for copies, tier, deadline in _qualified(rows, big_names, small_names):
        if deadline is not None and deadline < today.isoformat():
            continue  # 저장소 상태가 OPEN 이어도 마감일이 지난 공고가 있다
        by_company.setdefault(card_key(copies[0].get("company") or ""), []).append((copies, tier, deadline))

    cards = []
    for postings in by_company.values():
        postings.sort(key=lambda p: (p[2] is None, p[2] or "", p[0][0]["job_id"]))
        copies, tier, deadline = postings[0]
        cards.append(_card(copies, min((p[1] for p in postings), key=TIERS.index), deadline, len(postings), closed=False))
    cards.sort(key=lambda c: (c["deadline"] is None, c["deadline"] or "", TIERS.index(c["tier"]), c["company"]))
    return cards


def pick_past(
    rows: Iterable[dict[str, Any]], today: date,
    big_names: frozenset[str] = frozenset(), small_names: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """지난 공채 — 최근 1년 안에 마감한 신입 공채. 회사 · 시즌마다 한 장, 최근 마감순.

    카드 제목은 개발 직무 공고를 먼저 — 같은 공채의 「재경」 공고가 대표로 오르지 않게.
    """
    since = (today - timedelta(days=PAST_DAYS)).isoformat()
    by_season: dict[tuple[str, str], list[tuple[list[dict[str, Any]], str, str]]] = {}
    for copies, tier, deadline in _qualified(rows, big_names, small_names):
        head = copies[0]
        if deadline is None or not (since <= deadline < today.isoformat()):
            continue
        if not (is_open_hiring(head.get("title") or "") or head.get("career_type") == "ENTRY"):
            continue
        season = season_of(head.get("title") or "", head.get("posted_at"), head.get("deadline"))
        by_season.setdefault((card_key(head.get("company") or ""), season), []).append((copies, tier, deadline))

    cards = []
    for postings in by_season.values():
        postings.sort(key=lambda p: (bool(_DEV_TITLE.search(p[0][0].get("title") or "")), p[2]), reverse=True)
        copies, _, _ = postings[0]
        last = max(p[2] for p in postings)
        cards.append(_card(copies, min((p[1] for p in postings), key=TIERS.index), last, len(postings), closed=True))
    cards.sort(key=lambda c: (c["deadline"], c["company"]), reverse=True)
    return cards
