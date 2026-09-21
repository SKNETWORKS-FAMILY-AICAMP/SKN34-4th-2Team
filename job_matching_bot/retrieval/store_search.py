"""저장소에서 조건으로 공고를 찾는다. 챗봇 "공고 찾아보기"가 쓴다.

추천(`api/service.py`)과 목적이 다르다. 추천은 이력서를 읽고 **뜻이 가까운** 공고를
벡터로 찾지만, 여기는 사용자가 말한 **조건에 맞는** 공고를 고른다. "서울 백엔드 신입"은
해석이 갈릴 여지가 없으니 벡터가 필요 없고, 조건 조회가 정확하고 빠르다.

그래서 Pinecone이 아니라 저장소(SQLite)를 본다. 인덱스에는 요건 문장이 있는 IT 인접
공고만 올라가지만, 저장소에는 **모든 카테고리**가 있다. "생산관리 신입 있어?"에도
답하려면 저장소여야 한다.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Collection

from job_matching_bot.matching.hard_filter import ENTRY_ONLY_MAX_YEARS
from job_matching_bot.matching.skill_normalize import canonical_skill

KST = timezone(timedelta(hours=9))

# 한 번에 훑을 최대 행. 조건이 헐거우면 수만 건이 걸리므로 상한을 둔다.
SCAN_LIMIT = 3000

# 사용자가 말하는 경력 표현 → 저장소의 career_type
CAREER_TYPES = {"신입": ("ENTRY", "ANY"), "경력": ("EXPERIENCED", "ANY"), "무관": None}

# 접두사인데 **뜻이 다른** 말. 이것만 막는다.
#
# `LIKE '%Java%'` 는 JavaScript 도 걸린다. 실측으로 "Java" 검색 2,004건 중 198건(15%)이
# Java 태그 없이 Javascript 만 있는 공고였다. 그렇다고 단어 경계로 일괄 차단하면 안 된다.
# 기술 태그 220종에서 접두사 쌍 11개 중 10개는 같은 계열이라(Spring⊂SpringBoot,
# React⊂ReactJS, HTML⊂HTML5, 임베디드⊂임베디드리눅스 …) 막으면 열 곳이 나빠지고 한 곳만
# 고쳐진다. 뜻이 갈리는 것만 여기 적는다.
#
# 값은 그 말을 찾을 정규식이다. 형태가 제각각이라 규칙 하나로 못 묶는다.
#
# 후보는 `python -m job_matching_bot.evaluation.scan_terms` 로 뽑는다. 태그가 늘면
# 다시 돌려 새로 생긴 겹침만 보면 된다. 판단은 사람이 한다 — "같은 계열인가"는
# 글자로 알 수 없다.
CONFUSABLE = {
    # 뒤를 본다. JavaScript 는 Java 가 아니다.
    "java": r"java(?!script)",
    "자바": r"자바(?!스크립트)",
    # 앞뒤를 다 본다. MongoDB·Django·Google 의 "go" 는 Go 가 아니다. GoLang 은 맞다.
    # 두 글자짜리라 어쩔 수 없이 "Go-to-market" 같은 말은 남는다.
    "go": r"(?<![a-z])go(?:lang)?(?![a-z])",
}


@lru_cache(maxsize=1)
def _tag_spellings() -> dict[str, list[str]]:
    """표준키 → 사람인이 실제로 붙인 태그 표기.

    사람인은 `SpringBoot`, `Node.js`, `RestAPI`로 붙이는데 사람은 `Spring Boot`,
    `Node JS`, `REST API`라고 친다. 친 글자를 그대로 찾으면 하나도 안 걸린다.

        Spring Boot   태그에 걸린 공고 0건 → SpringBoot 로 찾으면 354건
        REST API      0건 → RestAPI 301건
        K8s           5건 → Kubernetes 221건

    표기를 접는 `canonical_skill`은 이미 있고 적재할 때 쓴다. 검색이 안 썼다.

    저장소를 고치지 않는다. 태그는 보여 줄 글이기도 해서 원문이 남아야 하고, 칸을
    더 만들면 29,000건을 다시 써야 한다. 찾을 때만 접는다.
    """
    from job_matching_bot.ingestion.saramin_tech_vocab import load_codes

    spellings: dict[str, list[str]] = {}
    for row in load_codes():
        name = str(row["kewd_name"]).strip()
        if not name:
            continue
        spellings.setdefault(canonical_skill(name), [])
        if name not in spellings[canonical_skill(name)]:
            spellings[canonical_skill(name)].append(name)
    return spellings


def spellings_of(term: str) -> list[str]:
    """이 말을 찾을 때 함께 걸 표기. 사용자가 친 말이 늘 맨 앞이다."""
    found = [term]
    for name in _tag_spellings().get(canonical_skill(term), []):
        if name.lower() != term.strip().lower():
            found.append(name)
    return found


def _like_or_regex(column: str, term: str) -> tuple[str, list[object]]:
    """한 컬럼에서 한 말을 찾는 조건. 헷갈리는 말이면 뒤에 오는 글자를 본다.

    돌려주는 것은 (SQL 조각, 값 목록)이다. 값 개수가 조건마다 다르므로 함께 돌려준다.
    """
    pattern = CONFUSABLE.get(term.strip().lower())
    if not pattern:
        return f"{column} LIKE ?", [f"%{term}%"]
    # 한 공고에 Java 와 Javascript 가 둘 다 있으면 Java 쪽이 걸린다. 빼면 진짜 Java
    # 공고를 잃는다.
    return f"RE_HAS(?, {column})", [pattern]


def _match(column: str, term: str) -> tuple[str, list[object]]:
    """한 컬럼에서 이 말을 찾는 조건. 표기 변형을 전부 건다."""
    parts: list[str] = []
    values: list[object] = []
    for spelling in spellings_of(term):
        sql, vals = _like_or_regex(column, spelling)
        parts.append(sql)
        values.extend(vals)
    return "(" + " OR ".join(parts) + ")", values


# 직무 말 끝에 붙는 일반 명사와, 공고에 같은 뜻으로 적히는 말.
#
# "AI 엔지니어"를 한 덩어리로 찾으면 판교 신입이 1건이었다. 공고 제목은 "AI Engineer",
# "AI 모델 개발", "인공지능 엔지니어"로 적힌다. "LLM 개발자"는 2건, "LLM"은 994건이었다.
# 라우터는 사람이 말한 대로 "OO 개발자"를 넘기므로 찾는 쪽에서 푼다.
_ROLE_SUFFIX_ALTERNATIVES: dict[str, tuple[str, ...]] = {
    "개발자": ("개발", "developer", "엔지니어", "engineer", "프로그래머"),
    "엔지니어": ("엔지니어", "engineer"),
    "프로그래머": ("프로그래머", "programmer", "개발"),
    "디자이너": ("디자이너", "designer", "디자인"),
    "기획자": ("기획",),
    "담당자": ("담당",),
}

# 같은 뜻의 다른 표기. 뜻이 넓어지는 것은 넣지 않는다.
_ROLE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "ai": ("AI", "인공지능"),
    "인공지능": ("인공지능", "AI"),
    "프론트": ("프론트엔드", "frontend", "front-end"),
    "프론트엔드": ("프론트엔드", "frontend", "front-end"),
    "백엔드": ("백엔드", "backend", "back-end"),
    # 한글로 말하고 공고는 영문으로 적는 기술·도구 이름.
    "유니티": ("유니티", "Unity"),
    "언리얼": ("언리얼", "Unreal"),
    "파이썬": ("파이썬", "Python"),
    "자바": ("자바", "Java"),
    "리액트": ("리액트", "React"),
    "플러터": ("플러터", "Flutter"),
    "안드로이드": ("안드로이드", "Android"),
}

# "개발"은 "사업개발·상품개발"의 개발이 아니다. "데이터 분석 인턴"에 "B2B 사업개발 매니저(인턴)"가
# 나갔다. 제목 기준으로 이런 게시 중 공고가 272건이다.
_DEVELOP = r"(?<!사업)(?<!상품)(?<!교육)(?<!영업)(?<!조직)(?<!인재)개발"

# 세 글자 이하 영문은 단어로만 찾는다. `LIKE '%AI%'`는 Mail·Detail·Maintenance에도 걸린다.
_SHORT_LATIN = re.compile(r"^[A-Za-z]{1,3}$")


def _alternative_sql(column: str, word: str) -> tuple[str, list[object]]:
    """직무 말 한 낱말(또는 그 대체어)을 한 컬럼에서 찾는 조건."""
    if word == "개발":
        return f"RE_HAS(?, {column})", [_DEVELOP]
    if _SHORT_LATIN.match(word):
        return f"RE_HAS(?, {column})", [rf"(?<![a-z]){re.escape(word)}(?![a-z])"]
    return _match(column, word)


def role_word_groups(term: str) -> list[list[str]]:
    """직무 말을 '모두 있어야 하는 낱말 묶음'으로. 묶음 안의 말은 하나만 있어도 된다.

        "AI 엔지니어"     → [[AI, 인공지능], [엔지니어, engineer, 개발]]
        "게임 클라이언트"  → [[게임], [클라이언트]]
        "백엔드"          → [[백엔드, backend, back-end]]
    """
    words = term.split()
    groups: list[list[str]] = []
    for index, word in enumerate(words):
        last = index == len(words) - 1
        if last and word in _ROLE_SUFFIX_ALTERNATIVES:
            groups.append(list(_ROLE_SUFFIX_ALTERNATIVES[word]))
        elif word.lower() in _ROLE_SYNONYMS:
            groups.append(list(_ROLE_SYNONYMS[word.lower()]))
        elif word == "개발":
            groups.append(["개발"])
        else:
            groups.append([word])
    return groups


def _role_match(column: str, term: str) -> tuple[str, list[object]]:
    """한 컬럼에서 직무 말을 찾는 조건. 낱말 묶음이 모두 그 컬럼에 있어야 한다.

    **나눠 찾는 것은 제목뿐이다.** 제목은 한 줄이라 "데이터"와 "엔지니어"가 함께 있으면 그 일이다.
    본문은 길어서 둘이 따로따로 스친다 — 본문까지 나눠 찾자 "데이터 엔지니어"가 772건에서
    2,956건이 됐다. 태그·본문에서는 말한 그대로(띄어쓰기만 무시)만 본다.
    """
    words = term.split()
    if column != "title" and len(words) > 1:
        # 태그 칸은 태그 여러 개가 한 글자열에 들어 있어, 나눠 찾으면 "데이터분석가"의 데이터와
        # "네트워크엔지니어"의 엔지니어가 합쳐 걸린다. 태그·본문은 말 그대로만 찾는다.
        spellings = [term, "".join(words)]
        # "LLM 개발자"처럼 앞이 짧은 영문이면 그 말만 달린 태그("LLM")도 같은 일이다.
        core = " ".join(words[:-1])
        if column != "description" and words[-1] in _ROLE_SUFFIX_ALTERNATIVES and _SHORT_LATIN.match(core):
            spellings.append(core)
        parts, values = [], []
        for spelling in dict.fromkeys(spellings):
            sql, vals = _alternative_sql(column, spelling)
            parts.append(sql)
            values.extend(vals)
        return "(" + " OR ".join(parts) + ")", values
    clauses: list[str] = []
    values: list[object] = []
    for group in role_word_groups(term):
        parts = []
        for word in group:
            sql, vals = _alternative_sql(column, word)
            parts.append(sql)
            values.extend(vals)
        clauses.append("(" + " OR ".join(parts) + ")")
    return "(" + " AND ".join(clauses) + ")", values


# 기업형태로 걸러야 하는 말. 공고 글에서 찾으면 안 된다.
#
# "대기업 IT 신입"을 글에서 찾자 "(대기업 상주)" 파견 공고와 "[공기업/부산]"을 제목에 단
# 헤드헌팅 공고가 나갔다. 기업형태는 상세 페이지의 기업 정보 칸(`company_type`)에 있다.
# "1000대기업"은 대기업이 아니다(중견기업도 들어간다) — 쉼표로 나뉜 한 칸 전체가 맞아야 한다.
COMPANY_TYPES: dict[str, str] = {
    "대기업": r"(?:^|,)\s*대기업\s*(?:,|$)",
    "중견기업": r"(?:^|,)\s*중견기업\s*(?:,|$)",
    "중견": r"(?:^|,)\s*중견기업\s*(?:,|$)",
    "중소기업": r"(?:^|,)\s*중소기업\s*(?:,|$)",
    "공기업": r"공사/공",
    "공공기관": r"공사/공",
    "외국계": r"외국인 투|외국 법인",
    "외국계기업": r"외국인 투|외국 법인",
    "코스닥": r"코스닥",
    "코스피": r"코스피",
    "상장사": r"코스닥|코스피",
    "스타트업": r"스타트업",
}


# 빼 달라는 말 중 고용형태 칸으로 거를 것. 값은 그 칸에서 찾을 글자다.
EMPLOYMENT_WORDS: dict[str, str] = {
    "계약직": "계약", "인턴": "인턴", "파견": "파견", "파견직": "파견",
    "프리랜서": "프리랜서", "아르바이트": "아르바이트", "알바": "아르바이트",
}


def _company_type_keywords(filters: "JobFilters") -> list[str]:
    return [word for word in _dedupe(filters.keywords) if word.replace(" ", "") in COMPANY_TYPES]


def _text_keywords(filters: "JobFilters") -> list[str]:
    return [word for word in _dedupe(filters.keywords) if word.replace(" ", "") not in COMPANY_TYPES]


def _re_has(pattern: str, text: str | None) -> int:
    """SQLite에 등록해 쓰는 함수. 대소문자를 가리지 않는다."""
    if not text:
        return 0
    return 1 if re.search(pattern, text, re.IGNORECASE) else 0


def connect(store_path: Path) -> sqlite3.Connection:
    """읽기 전용으로 열고 `RE_HAS` 를 등록한다. 검색과 집계가 같이 쓴다."""
    connection = sqlite3.connect(
        f"{Path(store_path).resolve().as_uri()}?mode=ro", uri=True
    )
    connection.row_factory = sqlite3.Row
    connection.create_function("RE_HAS", 2, _re_has, deterministic=True)
    return connection


@dataclass
class JobFilters:
    """대화에서 뽑아낸 검색 조건. 다음 turn에 그대로 돌려주어 이어서 좁힌다."""

    roles: list[str] = field(default_factory=list)          # 직무 (백엔드, 데이터분석)
    skills: list[str] = field(default_factory=list)         # 기술 (Python, React)
    regions: list[str] = field(default_factory=list)        # 시·도 (서울, 경기)
    career: str = "무관"                                     # 신입 / 경력 / 무관
    career_years: int | None = None                         # 몇 년차인지 말했으면
    employment_types: list[str] = field(default_factory=list)
    deadline_within_days: int | None = None                 # 마감 임박만 보기
    keywords: list[str] = field(default_factory=list)       # 그 밖의 말
    exclude_keywords: list[str] = field(default_factory=list)  # 빼 달라는 말(스타트업, 파견)
    posted_within_days: int | None = None                   # 최근 올라온 것만. 0이면 오늘

    @property
    def is_empty(self) -> bool:
        return not any(
            [self.roles, self.skills, self.regions, self.employment_types,
             self.keywords, self.deadline_within_days, self.career != "무관",
             self.career_years is not None, self.exclude_keywords,
             self.posted_within_days is not None]
        )

    def summary(self) -> str:
        """무엇으로 걸렀는지 사람 말로. 해석이 틀렸을 때 사용자가 알아채야 한다."""
        parts = [
            *self.roles, *self.skills,
            *(f"{region}" for region in self.regions),
            *self.employment_types,
        ]
        if self.career_years is not None:
            # 무엇으로 걸렀는지 그대로 보인다. 해석이 틀렸으면 사용자가 알아채야 한다.
            parts.append(f"{self.career_years}년차")
        elif self.career != "무관":
            parts.append(self.career)
        if self.deadline_within_days:
            parts.append(f"{self.deadline_within_days}일 내 마감")
        if self.posted_within_days is not None:
            # "오늘"이라고 쓰지 않는다. 마지막 수집일에서 센다(`conditions`).
            parts.append("새로 올라온" if self.posted_within_days == 0 else f"최근 {self.posted_within_days}일 새로 올라온")
        parts.extend(self.keywords)
        parts.extend(f"{word} 제외" for word in self.exclude_keywords)
        return " · ".join(parts) if parts else "조건 없음"


@dataclass
class JobHit:
    """찾은 공고 한 건. `relevance`는 사용자가 말한 말이 **어디에** 있었는지다."""

    job_id: str
    company: str
    title: str
    source_url: str
    region: str
    career_label: str
    employment_type: str
    deadline: str | None
    tech_stack: list[str]
    relevance: int = 0   # 4 제목에 말 그대로 · 3 제목 · 2 직무·기술 태그 · 1 본문에만
    # 상세를 받아 본문까지 있는가. False면 목록에서만 본 공고다. 조건 검색에는
    # 온전히 쓰이지만 "자격요건 알려줘"에는 답할 수 없어 원문 링크로 안내한다.
    has_detail: bool = True


@dataclass
class SearchResult:
    jobs: list[JobHit]
    total: int          # 조건에 맞는 전체 건수 (보여 준 것보다 많을 수 있다)
    scanned_cap: bool   # 상한에 걸려 세다 만 경우
    strong: int         # 그중 제목·태그에 직접 맞은 건수
    skipped: int = 0    # 이미 보여 줘서 뺀 건수. "이거 말고"로 넘겨 보는 중이면 0보다 크다


# 공고 한 건을 만드는 데 필요한 컬럼. 조건 검색과 의미 검색이 같은 것을 읽는다.
_HIT_COLUMNS = (
    "job_id, company, title, source_url, region, career_type, min_career_years, "
    "employment_type, deadline, tech_stack"
)


def _to_hit(row, relevance: int, has_detail: bool = True) -> JobHit:
    from job_matching_bot.ingestion.company_name import clean_company_name

    return JobHit(
        job_id=row["job_id"],
        company=clean_company_name(row["company"]),
        title=row["title"] or "",
        source_url=row["source_url"] or "",
        region=row["region"] or "미기재",
        career_label=_career_label(row["career_type"] or "", row["min_career_years"]),
        employment_type=row["employment_type"] or "미기재",
        deadline=(row["deadline"] or None),
        tech_stack=json.loads(row["tech_stack"] or "[]"),
        relevance=relevance,
        has_detail=has_detail,
    )


def deadline_passed(deadline: str | None, now: datetime | None = None) -> bool:
    """마감 시각이 지났나. **보내기 직전에** 본다.

    조회 조건은 날짜만 견준다(`substr(deadline, 1, 10) >= 오늘`). 그래서 밤 11시에 받은
    "오늘 23:59 마감" 공고를 자정이 지나 눌러 보면 이미 닫혀 있었다. 시각이 적힌 마감은
    시각까지 보고, 날짜만 적힌 마감은 그날 끝까지 열린 것으로 본다. 못 읽으면 지나지
    않은 것으로 둔다 — 잘못 빼는 것보다 낫다.
    """
    if not deadline:
        return False
    now = now or datetime.now(KST)
    try:
        when = datetime.fromisoformat(deadline)
    except ValueError:
        return False
    if when.tzinfo is None:
        if len(deadline) <= 10:
            return when.date() < now.date()
        when = when.replace(tzinfo=KST)
    return when <= now


def _career_label(career_type: str, min_years: int | None) -> str:
    if career_type == "ENTRY":
        return "신입"
    if career_type == "EXPERIENCED":
        return "경력" if min_years is None else f"경력 {min_years}년 이상"
    if career_type == "ANY":
        return "경력무관"
    return "미기재"


def _dedupe(terms: list[str]) -> list[str]:
    seen: list[str] = []
    for term in terms:
        term = term.strip()
        if term and term not in seen:
            seen.append(term)
    return seen


# 말을 찾는 칸. 직무를 기술과 함께 말했을 때는 본문을 보지 않는다(아래 `conditions`).
_ALL_COLUMNS = ("title", "keywords", "tech_stack", "description")
_ROLE_COLUMNS = ("title", "keywords", "tech_stack")


def conditions(filters: JobFilters, as_of: datetime, *, listing: bool = False) -> tuple[list[str], list[object]]:
    """조건을 WHERE 절과 값으로. 검색(`search`)과 집계(`market_stats`)가 같이 쓴다.

    조건이 여럿이면 **모두 만족**해야 한다. 같은 갈래의 말끼리는 하나만 맞아도 된다
    ("백엔드나 프론트엔드", "Python이나 Go").

    **직무와 기술을 함께 말하면 둘 다 맞아야 한다.** 예전에는 직무·기술을 한 묶음 OR로 걸었다.
    "파이썬 쓰는 서울 신입 프론트엔드"가 Python만 적힌 백엔드·AI 공고까지 480건 걸려서
    "프론트엔드 공고"라며 프론트엔드가 아닌 공고를 보여 줬다. 둘 다 맞게 하면 53건이다.
    이때 직무는 **제목·직무 태그·기술 태그**에서만 찾는다. 본문의 "프론트엔드와 협업"은 그 일을
    뽑는 공고라는 뜻이 아니라서, 본문까지 보면 Python 백엔드 공고가 다시 섞인다(53 → 41건).
    직무만 말했을 때는 예전처럼 본문도 본다 — 좁힐 다른 말이 없으니 놓치지 않는 쪽이 낫다.

    **키워드(재택·공기업·비전공자 …)는 직무·기술과 따로 묶어 함께 만족해야 한다.** 예전에는
    한 묶음으로 OR였다. "재택 가능한 QA"가 QA 공고 전부에 "재택"이 스친 공고까지 3,000건
    넘게 걸렸고, "공기업 IT"에 일반 기업 IT 공고가 나갔다. 키워드는 좁히는 말이다.
    키워드끼리는 하나만 맞아도 된다("공기업이나 공공기관").

    두 곳이 같은 함수를 쓰는 것이 중요하다. "412건 중 Spring 61%"라고 말해 놓고 목록에는
    다른 모수의 공고가 나오면 답이 거짓말이 된다.
    """
    today = as_of.date().isoformat()
    where = ["status = 'OPEN'", "(deadline IS NULL OR substr(deadline, 1, 10) >= ?)"]
    params: list[object] = [today]

    if filters.regions:
        where.append("(" + " OR ".join("region LIKE ?" for _ in filters.regions) + ")")
        params.extend(f"%{region}%" for region in filters.regions)

    types = CAREER_TYPES.get(filters.career)
    if types:
        where.append("career_type IN (" + ", ".join("?" for _ in types) + ")")
        params.extend(types)

    # 몇 년차인지 말했으면 **모자란 공고를 뺀다.** "3년차인데 갈 만한 데"에 경력 5년
    # 이상 공고가 나갔었다. 추천 쪽 하드 필터와 같은 규칙으로 본다.
    #
    # 연차 미기재(`min_career_years IS NULL`)는 빼지 않는다. 미기재인 것은 연차이지
    # "이 사람에게 안 맞는다"는 사실이 아니다. 여기는 검색이라 빠지면 사용자가 아예
    # 못 본다 — 판단할 거리를 남기는 쪽이 낫다.
    if filters.career_years is not None:
        where.append("(min_career_years IS NULL OR min_career_years <= ?)")
        params.append(filters.career_years)
        # 신입만 뽑는다고 적은 공고는 경력자에게 맞지 않는다. 경계는 하드 필터와 같다.
        if filters.career_years >= ENTRY_ONLY_MAX_YEARS:
            where.append("career_type != 'ENTRY'")

    if filters.employment_types:
        where.append("(" + " OR ".join("employment_type LIKE ?" for _ in filters.employment_types) + ")")
        params.extend(f"%{value}%" for value in filters.employment_types)

    if filters.deadline_within_days:
        until = (as_of + timedelta(days=filters.deadline_within_days)).date().isoformat()
        where.append("deadline IS NOT NULL AND substr(deadline, 1, 10) <= ?")
        params.append(until)

    # 직무 묶음·기술 묶음·키워드 묶음을 따로 걸어 모두 만족하게 한다(위 설명).
    roles, skills = _dedupe(filters.roles), _dedupe(filters.skills)
    groups = [
        (roles, _ROLE_COLUMNS if skills else _ALL_COLUMNS, _role_match),
        (skills, _ALL_COLUMNS, _match),
        (_text_keywords(filters), _ALL_COLUMNS, _match),
    ]
    for group, columns, matcher in groups:
        if not group:
            continue
        clauses = []
        for term in group:
            parts = []
            for column in columns:
                sql, values = matcher(column, term)
                parts.append(sql)
                params.extend(values)
            clauses.append("(" + " OR ".join(parts) + ")")
        where.append("(" + " OR ".join(clauses) + ")")

    # 기업형태는 기업 정보 칸에서만 본다. 같은 뜻끼리는 하나만 맞아도 된다.
    # 목록에서만 본 공고(`listing`)에는 기업 정보가 없다. 걸러 달라면 `search`가 그쪽을 통째로 빼고,
    # 빼 달라면 그쪽은 빼지 않는다 — 모르는 것을 스타트업이라고 단정하지 않는다.
    company_types = _company_type_keywords(filters)
    if company_types and not listing:
        where.append("(" + " OR ".join("RE_HAS(?, company_type)" for _ in company_types) + ")")
        params.extend(COMPANY_TYPES[word.replace(" ", "")] for word in company_types)

    # 빼 달라는 말. 기업형태는 기업 정보 칸, 고용형태는 고용형태 칸, 나머지는 제목·회사명에서 본다.
    # 본문은 보지 않는다 — "파견 근무 없음"처럼 빼 달라는 말이 본문에 부정으로 적힌 공고도 있다.
    for word in _dedupe(filters.exclude_keywords):
        key = word.replace(" ", "")
        if key in COMPANY_TYPES:
            if not listing:
                where.append("NOT RE_HAS(?, company_type)")
                params.append(COMPANY_TYPES[key])
            continue
        if key in EMPLOYMENT_WORDS:
            where.append("(employment_type IS NULL OR employment_type NOT LIKE ?)")
            params.append(f"%{EMPLOYMENT_WORDS[key]}%")
            continue
        where.append("NOT (title LIKE ? OR company LIKE ?)")
        params.extend([f"%{word}%", f"%{word}%"])

    # 최근에 올라온 것만. 우리가 그 공고를 처음 본 날로 세되, **오늘이 아니라 마지막 수집일에서**
    # 거꾸로 센다. 공고는 밤 23시 수집에서 처음 보므로, 낮에 "오늘 올라온"을 오늘 날짜로 세면
    # 늘 0건이었다. 0이면 마지막 수집에서 처음 본 공고다.
    if filters.posted_within_days is not None:
        where.append(
            "substr(first_seen_at, 1, 10) >= "
            "date((SELECT MAX(substr(first_seen_at, 1, 10)) FROM jobs), ?)"
        )
        params.append(f"-{filters.posted_within_days} days")

    return where, params


def search(
    store_path: Path,
    filters: JobFilters,
    limit: int = 5,
    as_of: datetime | None = None,
    exclude_ids: Collection[str] = (),
) -> SearchResult:
    """조건에 맞는 공고를 관련도 순으로. (보여 줄 것, 전체 건수).

    `exclude_ids`는 **이미 보여 준 공고**다. "이거 말고"를 거듭하면 앱이 본 것을 모아
    보내고, 여기서 빼고 다음 공고를 준다. 서버는 대화를 저장하지 않으므로 몇 쪽째인지
    대신 무엇을 봤는지를 받는다. 전체 건수(`total`)는 빼기 전 그대로다.
    """
    as_of = as_of or datetime.now(KST)
    where, params = conditions(filters, as_of)
    listing_where, listing_params = conditions(filters, as_of, listing=True)

    # 어디에서 맞았는지로 순서를 가른다. 본문만 훑으면 "신입/경력 공개채용" 같은 범용
    # 공고가 온갖 직무 말을 다 담고 있어서 무엇을 물어도 같은 공고가 올라온다.
    # 제목에 있으면 그 일을 뽑는 공고이고, 태그에 있으면 기업이 그렇게 분류한 것이다.
    # (말, 그 말을 찾는 함수). 직무 말은 낱말로 나눠 찾는다(`_role_match`).
    roles = _dedupe(filters.roles)
    terms = [(term, _role_match) for term in roles]
    # 직무와 기술을 함께 말했으면 **직무가 어디 있나**로 가른다. 둘 다 맞는 공고만 남았으니
    # 기술이 제목에 있는 "Python (Flask) 웹 개발자"보다 제목이 "프론트엔드 개발자"인 공고가
    # 물어본 일에 가깝다.
    if not (roles and filters.skills):
        terms += [(term, _match) for term in _dedupe(filters.skills) if term not in roles]
    terms += [(term, _match) for term in _text_keywords(filters)]
    relevance = "0"
    # CASE 식이 SELECT에 들어가므로 그 물음표 값을 따로 모은다. 제목 먼저, 그다음 태그 둘씩.
    case_params: list[object] = []
    if terms:
        title_parts, tag_parts = [], []
        for term, matcher in terms:
            sql, values = matcher("title", term)
            title_parts.append(sql)
            case_params.extend(values)
        for term, matcher in terms:
            pieces = []
            for column in ("keywords", "tech_stack"):
                sql, values = matcher(column, term)
                pieces.append(sql)
                case_params.extend(values)
            tag_parts.append("(" + " OR ".join(pieces) + ")")
        # 여러 낱말 직무는 낱말로 나눠 찾으므로 "서비스 사업기획"도 "서비스 기획"에 걸린다.
        # 제목에 말한 그대로("서비스 기획", "서비스기획") 있으면 그 공고를 맨 앞에 둔다.
        phrase_parts: list[str] = []
        phrase_params: list[object] = []
        for term in (term for term, matcher in terms if matcher is _role_match and len(term.split()) > 1):
            for spelling in dict.fromkeys((term, term.replace(" ", ""))):
                phrase_parts.append("title LIKE ?")
                phrase_params.append(f"%{spelling}%")
        phrase_case = f"WHEN {' OR '.join(phrase_parts)} THEN 4 " if phrase_parts else ""
        case_params = [*phrase_params, *case_params]
        relevance = (
            f"CASE {phrase_case}WHEN {' OR '.join(title_parts)} THEN 3 "
            f"WHEN {' OR '.join(tag_parts)} THEN 2 ELSE 1 END"
        )

    # 상세까지 있는 공고와, 목록에서만 본 공고를 함께 본다.
    #
    # 상세를 받아야 `jobs`에 들어가서 IT 밖 10개 대분류가 영영 0건이었다. "서울 영업직
    # 있어?"에 없어서가 아니라 안 갖고 있어서 답을 못 했다. 목록에는 회사·제목·직무·
    # 조건·링크가 다 있고, 조건 검색은 원래 그 값들로만 거른다.
    #
    # 조건 SQL은 두 표에 **그대로** 쓴다. `list_jobs_search` 뷰가 목록에 없는 칸을
    # 상수로 채우고, 해석은 상세와 같은 파서를 쓴다. 그래서 섞여도 결과가 안 어긋난다.
    #
    # `has_detail`이 0인 것은 늘 뒤에 세운다. 본문이 있는 쪽이 먼저 보여야 한다.
    detail_part = (
        f"SELECT {_HIT_COLUMNS}, {relevance} AS relevance, 1 AS has_detail, "
        "keywords, first_seen_at FROM jobs WHERE " + " AND ".join(where)
    )
    listing_part = (
        f"SELECT {_HIT_COLUMNS}, {relevance} AS relevance, 0 AS has_detail, "
        "keywords, first_seen_at FROM list_jobs_search WHERE " + " AND ".join(listing_where)
        # 상세를 받은 공고는 `jobs`에 있다. 같은 공고가 두 번 나오지 않게 뺀다.
        # 번호만으로 견주면 안 된다 — 사이트마다 따로 매긴 번호라, 사람인 상세가
        # 있다는 이유로 번호가 같은 잡코리아 목록이 통째로 사라진다.
        + " AND (source, source_job_id) NOT IN (SELECT source, source_job_id FROM jobs)"
    )
    # 목록에서만 본 공고를 뺄 때가 둘이다.
    # - 기업형태로 걸렀을 때. 기업 정보는 상세에만 있어 맞는지 알 수 없다.
    # - 새로 올라온 공고만 볼 때. 목록 표(`list_jobs`)는 2026-09-13에 처음 채워져 13만 5천 건의
    #   처음 본 날이 전부 그날이다. 넣으면 "새로 올라온"이 목록 전체가 된다.
    with_listing = not _company_type_keywords(filters) and filters.posted_within_days is None
    body = detail_part + (" UNION ALL " + listing_part if with_listing else "")
    sql = (
        f"SELECT * FROM ({body}) "
        # 제목·태그에 직접 맞은 공고(관련도 2 이상)를 먼저 전부 세운다. 답이 말하는 건수가
        # 이 묶음이라, 넘겨 보다 보면 그 건수만큼 본 뒤에 본문에만 스친 공고로 넘어가야
        # 말과 목록이 맞는다. 묶음 안에서는 본문이 있는 공고가 먼저다.
        # 관련도가 같으면 태그를 적게 단 공고를 먼저. 직무 태그를 열 개씩 달아 둔
        # "전 직군 공개채용"은 무엇을 물어도 걸리므로, 그 일에 특화된 공고에 자리를 내준다.
        " ORDER BY (relevance >= 2) DESC, has_detail DESC, relevance DESC,"
        " LENGTH(keywords) ASC, first_seen_at DESC LIMIT ?"
    )

    # 값 순서는 상세 쪽 SELECT → WHERE, 목록 쪽 SELECT → WHERE, 그다음 LIMIT. 목록 쪽 WHERE는
    # 기업형태 조건이 빠질 수 있어 값이 다르다(`conditions(listing=True)`).
    values = [*case_params, *params]
    if with_listing:
        values += [*case_params, *listing_params]
    connection = connect(store_path)
    try:
        rows = connection.execute(sql, [*values, SCAN_LIMIT]).fetchall()
    finally:
        connection.close()

    rows = _one_per_posting(rows)
    seen = set(exclude_ids)
    remaining = [row for row in rows if row["job_id"] not in seen]
    jobs = [_to_hit(row, int(row["relevance"] or 0), bool(row["has_detail"]))
            for row in remaining[:limit]]
    return SearchResult(
        jobs=jobs,
        total=len(rows),
        scanned_cap=len(rows) >= SCAN_LIMIT,
        strong=sum(1 for row in rows if int(row["relevance"] or 0) >= 2),
        skipped=len(rows) - len(remaining),
    )


_BRACKETS = re.compile(r"\[[^\]]*\]")


def posting_key(row) -> tuple:
    """같은 공고를 알아보는 열쇠. 회사, 대괄호 머리말을 뗀 제목, 경력·고용형태.

    파견·헤드헌팅 회사가 같은 공고를 지역만 바꿔 여러 번 올린다("[공기업/부산] …",
    "[공기업/강남] …"). 목록 다섯 칸이 한 공고로 차서 게시 중 329묶음 700건이 이렇다.
    지역은 열쇠에 넣지 않는다. 경력·고용형태는 넣는다 — 같은 제목으로 신입과 경력 3년을
    따로 올린 것은 사용자에게 다른 공고다. 소괄호도 남긴다("(신입)"과 "(3년 이상)").
    """
    title_key = " ".join(_BRACKETS.sub(" ", row["title"] or "").split()).lower()
    return (
        " ".join((row["company"] or "").split()),
        title_key,
        row["career_type"],
        row["min_career_years"],
        row["employment_type"],
    )


def _one_per_posting(rows: list) -> list:
    """같은 공고는 순서가 앞선 한 건만 남긴다. 순서가 늘 같아 "이거 말고"에도 같은 한 건이 남는다."""
    kept, keys = [], set()
    for row in rows:
        key = posting_key(row)
        if key in keys:
            continue
        keys.add(key)
        kept.append(row)
    return kept


def by_ids(
    store_path: Path, job_ids: list[str], as_of: datetime | None = None
) -> list[JobHit]:
    """job_id 목록을 **준 순서 그대로** 꺼낸다. 벡터 검색이 매긴 순서가 곧 관련도다.

    마감했거나 내려간 공고는 뺀다. 인덱스는 밤에 한 번 갱신되므로 낮 동안 마감된 것이
    남아 있을 수 있다. 저장소가 먼저 안다.
    """
    if not job_ids:
        return []
    as_of = as_of or datetime.now(KST)
    today = as_of.date().isoformat()

    placeholders = ", ".join("?" for _ in job_ids)
    sql = (
        f"SELECT {_HIT_COLUMNS} FROM jobs WHERE job_id IN ({placeholders}) "
        "AND status = 'OPEN' AND (deadline IS NULL OR substr(deadline, 1, 10) >= ?)"
    )
    connection = connect(store_path)
    try:
        rows = connection.execute(sql, [*job_ids, today]).fetchall()
    finally:
        connection.close()

    found = {row["job_id"]: row for row in rows}
    # relevance는 0으로 둔다. 이 목록의 순서는 글자가 어디에 있었는지가 아니라 뜻이
    # 얼마나 가까운지로 매겨졌으므로, 조건 검색의 점수와 섞어 쓸 수 없다.
    return [_to_hit(found[job_id], 0) for job_id in job_ids if job_id in found]
