"""잡코리아 채용공고 수집기 (requests + BeautifulSoup).

사람인 수집기(`crawl_list` / `crawl_detail`)와 같은 자리를 잡코리아에 대해 맡는다.
저장 형태도 사람인과 맞춰 두어 뒤쪽(적재·추천)이 출처를 가리지 않게 한다.

## robots.txt에서 확인한 것 (2026-09-19 확인, 파일에 적힌 갱신일 2026-04-01)

잡코리아 robots.txt는 머리말에 정책을 밝힌다.

    # Policy: Restrict AI/LLM crawlers while allowing search engine indexing of public pages.

그리고 `GPTBot` `ClaudeBot` `Claude-Web` `anthropic-ai` `PerplexityBot` 등 **AI 크롤러를
이름으로 지목해** 홈·공개정보 몇 경로만 남기고 `Disallow: /` 한다.

이 수집기는 그 UA들이 아니며 사람인 수집기와 같은 Chrome UA를 쓴다. 따라서 적용되는
규칙은 맨 아래 `User-agent: *` 블록이고, 거기서 우리가 쓰는 경로는 **명시적 Allow**다.

    Allow: /recruit/joblist      ← 목록
    Allow: /Recruit/GI_Read      ← 상세. `/Recruit/GI_Read_Comt_Ifrm`(본문)도 이 접두사에 걸린다.

Disallow인 `/login/` `/user/` `/my/` `/account/` `/RecrtMng/` `/corp/` `/text_co/`
`/Search?TS_Search=` `/Search/?stext=` `/recruit/ai-jobs/search` 는 요청하지 않는다.
`ALLOWED_PREFIXES` / `DENIED_PREFIXES` 로 코드에서 강제한다.

**경로 규칙은 지키지만 정책 머리말의 의도와는 어긋난다는 점을 적어 둔다.** 이 저장소는
공고를 임베딩해 LLM 추천에 쓴다. 팀이 그 점을 알고 진행하기로 정했다(2026-09-19).
발표·보고 자료에 수집 출처를 밝힐 때 이 문단을 근거로 쓴다.

## 사이트 구조에서 확인한 것

1. 목록 첫 쪽은 서버 렌더링이라 그냥 읽힌다. 그런데 **페이지 넘김은 안 된다.**
   `joblist?...&Page_No=2` `&Page=2` 는 둘 다 무시되고 1쪽이 그대로 온다.
   화면의 페이지 버튼 `href="/recruit/_GI_List?Page=2"` 는 **404**다(동작하지 않는 흔적).

   실제 넘김은 `Scripts/Recruit/jobList.js` 의 `_getGIList`가 하는 POST다.

       POST /Recruit/Home/_GI_List/
       condition[menucode]=duty&condition[dutyCtgr]=10031
       &page=N&pagesize=50&order=2&direct=0&tabindex=0&onePick=0&confirm=0&profile=0

   검증: page=1과 page=2의 공고번호가 **0건 겹침**. pagesize는 화면 선택지 기준 최대 50.

2. 직무 분류는 `dutyCtgr`다. `duty=`가 아니다(`duty=`는 조용히 무시되어 전체 206,857건이
   그대로 온다 — 필터가 걸린 줄 알기 쉬우니 주의).

3. 상세는 React(Next.js) 화면이라 껍데기 HTML에 본문이 없다. 대신 두 곳에서 얻는다.
   - `script[type="application/ld+json"]` 의 schema.org JobPosting: 제목·회사·마감일·
     고용형태·경력·학력·근무지가 구조화되어 있다.
   - 본문은 iframe: `/Recruit/GI_Read_Comt_Ifrm?Gno={공고번호}`. 여기에 담당업무·자격요건·
     우대사항·스킬이 섹션으로 들어 있다.

4. 목록 행에 조건이 이미 다 있다. 사람인과 같아서 `listing_conditions` 쪽 규칙을 그대로
   태울 수 있다.

## 수집 규칙

사람인 쪽과 같다. UA 고정(돌리지 않음), 프록시 없음, 3~5초 간격, 차단 문구·403·429면
**즉시 중단**하고 우회하지 않는다.

## 이어받기

상세는 공고 하나에 요청이 두 번이라 사람인보다 느리다(건당 약 6초). IT 8,504건이면
한 번에 14시간쯤이라 **한 번에 끝나는 것을 전제하지 않는다.** 받는 족족
`artifacts/job_raw/JOBKOREA_POC/details.jsonl`에 한 줄씩 붙이고, 다시 돌리면 그 파일에
있는 공고번호를 건너뛴다. 중간에 PC가 꺼져도 받아 둔 만큼은 남는다.

사용:
    python -m job_matching_bot.crawling.jobkorea                      # 오늘 몫 (일=전체, 평일=IT)
    python -m job_matching_bot.crawling.jobkorea --all --details      # IT 목록 전체 + 상세
    python -m job_matching_bot.crawling.jobkorea --all --details --max-minutes 300
    python -m job_matching_bot.crawling.jobkorea --full --all         # 전 대분류 목록만 (약 5.2시간)
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.crawling.http_session import (
    BlockedByTargetSiteError,
    polite_delay,
)
from job_matching_bot.ingestion.jobkorea import PARSER_VERSION, is_closed_page

KST = timezone(timedelta(hours=9))

BASE_URL = "https://www.jobkorea.co.kr"
LIST_PAGE_URL = f"{BASE_URL}/recruit/joblist"
LIST_AJAX_URL = f"{BASE_URL}/Recruit/Home/_GI_List/"
DETAIL_URL = f"{BASE_URL}/Recruit/GI_Read"
BODY_URL = f"{BASE_URL}/Recruit/GI_Read_Comt_Ifrm"

SOURCE = "JOBKOREA_POC"

# robots.txt `User-agent: *` 가 Allow 한 경로만 연다.
ALLOWED_PREFIXES = ("/recruit/joblist", "/Recruit/Home/_GI_List", "/Recruit/GI_Read")
# 같은 블록의 Disallow. 접두사 하나라도 걸리면 요청하지 않는다.
DENIED_PREFIXES = (
    "/login/",
    "/user/",
    "/my/",
    "/account/",
    "/RecrtMng/",
    "/corp/",
    "/text_co/",
    "/Salary/mylist",
    "/Recruit/JobList/SpaceClick",
    "/recruit/ai-jobs/search",
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CLIENT_HINTS = {
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}
SESSION_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    **CLIENT_HINTS,
}

BLOCK_MARKERS = (
    "비정상적인 접근",
    "자동입력 방지",
    "일시적으로 차단",
    "접근이 제한",
)

# 잡코리아 직무 대분류(`dutyCtgr`). 목록 화면의 input[name=duty] 에서 읽었다.
DUTY_CATEGORIES: dict[str, str] = {
    "10026": "기획·전략",
    "10027": "법무·사무·총무",
    "10028": "인사·HR",
    "10029": "회계·세무",
    "10030": "마케팅·광고·MD",
    "10031": "AI·개발·데이터",
    "10032": "디자인",
    "10033": "물류·무역",
    "10034": "운전·운송·배송",
    "10035": "영업",
    "10036": "고객상담·TM",
    "10037": "금융·보험",
    "10038": "식·음료",
    "10039": "고객서비스·리테일",
    "10040": "엔지니어링·설계",
    "10041": "제조·생산",
    "10042": "교육",
    "10043": "건축·시설",
    "10044": "의료·바이오",
    "10045": "미디어·문화·스포츠",
    "10046": "공공·복지",
}

# 지금 받는 대분류. 사람인 `2`(IT개발·데이터)에 대응한다.
IT_CATEGORY = "10031"

# 추천 대상이 아니라 훑지 않는 대분류. 사람인 `7`(운전·운송·배송)과 같은 이유다.
SKIPPED_CATEGORIES: tuple[str, ...] = ("10034",)

# **목록을 훑는 대분류.** 챗봇이 "서울 영업직 있어?"에 답하려면 상세가 없어도 목록은
# 있어야 한다. 사람인 쪽 `list_jobs`와 같은 쓰임이다.
LIST_CATEGORIES: tuple[str, ...] = tuple(
    code for code in DUTY_CATEGORIES if code not in SKIPPED_CATEGORIES
)

# 매일 훑는 대분류. 이력서와 겹치는 직군만 둔다.
# 사람인이 상세를 받는 넷(IT개발·데이터·연구R&D·디자인·기획전략)에 맞춘다.
# 겹침을 재려면 양쪽에 같은 직군의 상세가 있어야 한다. 잡코리아에는 연구·R&D에
# 해당하는 대분류가 없다 — 엔지니어링·설계와 의료·바이오로 흩어져 있다.
DAILY_CATEGORIES: tuple[str, ...] = (IT_CATEGORY, "10032", "10026")  # AI·개발·데이터, 디자인, 기획·전략

# **상세를 받는 대분류.** 목록은 주 1회 전부 훑지만 상세는 여기 있는 것만 받는다.
# 사람인과 같이 매일 훑는 것과 같은 값으로 둔다.
DETAIL_CATEGORIES: tuple[str, ...] = DAILY_CATEGORIES

# 상세를 처음 채울 때 앞에 두는 대분류. 겹침 분석을 IT부터 깊게 하려고 IT를 먼저 받는다.
PRIORITY_CATEGORIES: tuple[str, ...] = (IT_CATEGORY,)

# 2026-09-19에 대분류별 총 건수를 한 번씩 재서 나온 값이다(쪽당 50건 기준).
#
#     전 대분류 합계 242,761건 · 4,866쪽 · 4초 간격이면 약 5.4시간
#     운전·운송·배송을 뺀 20개   235,006건 · 4,710쪽 · 약 5.2시간
#     AI·개발·데이터 하나          8,504건 ·   171쪽 · 약 11분
#
# 사람인은 쪽당 100건이라 전 대분류가 약 1,760쪽인데 잡코리아는 50건이 최대라 같은
# 건수에 쪽수가 두 배다. **그래서 매일 전 대분류를 훑을 수 없다.** 사람인과 같이
# 주 1회만 전부 훑고 평일은 `DAILY_CATEGORIES`만 본다.
WEEKLY_DAY = 6  # 일요일

# 화면 선택지 기준 최대. 더 키워도 서버가 늘려 주지 않는다.
PAGE_SIZE = 50
# 정렬 2=등록일순. 훑는 동안 순서가 덜 흔들린다(추천순 20은 매 요청 바뀐다).
ORDER_REGISTERED = 2

GNO_RE = re.compile(r"GI_Read/(\d+)")
TOTAL_RE = re.compile(r"\(([\d,]+)건\)")
WS_RE = re.compile(r"\s+")

# JSON-LD의 `employmentType`은 schema.org 열거값(영어)이다. 사람인 쪽 `conditions["근무형태"]`는
# 한국어라 그대로 두면 `parse_employment`가 하나도 못 읽는다. 목록 행은 한국어로 주므로
# 그쪽이 있으면 그쪽을 쓰고, 없을 때 이 표로 옮긴다.
EMPLOYMENT_KO: dict[str, str] = {
    "FULL_TIME": "정규직",
    "PART_TIME": "파트타임",
    "CONTRACTOR": "계약직",
    "TEMPORARY": "임시직",
    "INTERN": "인턴",
    "VOLUNTEER": "자원봉사",
    "PER_DIEM": "일용직",
    "OTHER": "기타",
}


def _guard(url: str) -> None:
    """robots.txt에서 허용된 경로인지 확인한다. 아니면 요청하지 않는다."""
    path = urlparse(url).path
    if any(path.startswith(prefix) for prefix in DENIED_PREFIXES):
        raise ValueError(f"robots.txt가 막는 경로입니다: {url}")
    if not any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        raise ValueError(f"허용 목록에 없는 경로입니다: {url}")


def check_response(response: requests.Response) -> None:
    """차단·속도 제한이면 예외. 그 밖의 HTTP 오류는 raise_for_status에 맡긴다."""
    if response.status_code in (403, 429):
        raise BlockedByTargetSiteError(
            f"잡코리아가 요청을 거부했습니다(HTTP {response.status_code}). 자동화를 중단합니다. "
            "우회하지 말고 잠시 후 사람이 직접 확인하세요."
        )
    response.raise_for_status()
    if any(marker in response.text for marker in BLOCK_MARKERS):
        raise BlockedByTargetSiteError(
            "잡코리아가 이 요청을 차단했습니다. 자동화를 중단합니다. 우회하지 마세요."
        )


def navigation_headers(referer: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8"
        ),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin" if referer else "none",
        "Sec-Fetch-User": "?1",
    }
    if referer:
        headers["Referer"] = referer
    return headers


def ajax_headers(referer: str) -> dict[str, str]:
    """목록 POST용. 화면의 jQuery가 보내는 것과 같은 모양으로 맞춘다."""
    return {
        "Accept": "*/*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": BASE_URL,
        "Referer": referer,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }


def category_url(duty: str) -> str:
    return f"{LIST_PAGE_URL}?menucode=duty&dutyCtgr={duty}"


def new_session(
    duty: str = IT_CATEGORY,
    *,
    warm_up: bool = True,
    timeout: int = 30,
    min_delay: float = 3.0,
    max_delay: float = 5.0,
) -> requests.Session:
    """브라우저처럼 동작하는 세션.

    목록 POST는 앞서 목록 화면을 연 세션에서만 제대로 답한다(검색 조건이 세션에
    남는다). 그래서 워밍업이 선택이 아니라 사실상 필수다.
    """
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    if warm_up:
        url = category_url(duty)
        _guard(url)
        response = session.get(url, headers=navigation_headers(), timeout=timeout)
        check_response(response)
        polite_delay(min_delay, max_delay)
    return session


def _text(node: Any) -> str:
    """텍스트를 꺼내고 공백을 한 칸으로 접는다.

    목록의 고용형태 칸은 `정규직<공백 17개>외` 처럼 온다. 접지 않으면 그대로
    저장소에 들어가 뒤에서 비교가 어긋난다.
    """
    if not node:
        return ""
    return WS_RE.sub(" ", node.get_text(" ", strip=True)).strip()


def parse_row(tr: Any) -> dict[str, Any] | None:
    """목록 행 하나를 딕셔너리로. 사람인 목록 항목과 열 이름을 맞춘다."""
    link = tr.select_one("td.tplTit a[href*='GI_Read']")
    if not link:
        return None
    match = GNO_RE.search(link.get("href", ""))
    if not match:
        return None
    gno = match.group(1)
    # 빈 span.cell이 끝에 하나 붙어 온다. 조건 개수를 세는 쪽이 헷갈리니 여기서 턴다.
    cells = [text for cell in tr.select("td.tplTit p.etc span.cell") if (text := _text(cell))]
    sectors = _text(tr.select_one("td.tplTit p.dsc"))
    return {
        "source": SOURCE,
        "source_job_id": gno,
        "source_url": f"{DETAIL_URL}/{gno}",
        "company": _text(tr.select_one("td.tplCo a.link")),
        "title": (link.get("title") or _text(link)).strip(),
        # 목록이 주는 조건. 순서가 바뀔 수 있어 원문도 함께 남긴다.
        "condition_cells": cells,
        "condition_text": " ".join(cells),
        "job_sectors": [s.strip() for s in sectors.split(",") if s.strip()],
        "support_text": _text(tr.select_one("td.odd span.date")),
        "posted_text": _text(tr.select_one("td.odd span.time")),
    }


def fetch_page(
    session: requests.Session,
    duty: str,
    page: int,
    *,
    page_size: int = PAGE_SIZE,
    order: int = ORDER_REGISTERED,
    timeout: int = 30,
) -> tuple[list[dict[str, Any]], int | None]:
    """목록 한 쪽. `(행 목록, 사이트가 말하는 총 건수)`를 준다."""
    _guard(LIST_AJAX_URL)
    referer = category_url(duty)
    payload = {
        "condition[menucode]": "duty",
        "condition[dutyCtgr]": duty,
        "page": page,
        "direct": 0,
        "order": order,
        "pagesize": page_size,
        "tabindex": 0,
        "onePick": 0,
        "confirm": 0,
        "profile": 0,
    }
    response = session.post(
        LIST_AJAX_URL, data=payload, headers=ajax_headers(referer), timeout=timeout
    )
    check_response(response)
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    for tr in soup.select("tr.devloopArea"):
        row = parse_row(tr)
        if row:
            rows.append(row)
    total = None
    for text in soup.find_all(string=TOTAL_RE):
        total = int(TOTAL_RE.search(text).group(1).replace(",", ""))
        break
    return rows, total


def sweep_category(
    session: requests.Session,
    duty: str,
    *,
    max_pages: int | None = None,
    page_size: int = PAGE_SIZE,
    min_delay: float = 3.0,
    max_delay: float = 5.0,
) -> Iterator[dict[str, Any]]:
    """대분류 하나를 앞쪽부터 훑는다. 같은 쪽이 되풀이되면 끝으로 본다."""
    page = 1
    seen: set[str] = set()
    while max_pages is None or page <= max_pages:
        rows, total = fetch_page(session, duty, page, page_size=page_size)
        if not rows:
            break
        fresh = [row for row in rows if row["source_job_id"] not in seen]
        if not fresh:
            break
        for row in fresh:
            seen.add(row["source_job_id"])
            yield row
        if total is not None and len(seen) >= total:
            break
        page += 1
        polite_delay(min_delay, max_delay)


def read_done_ids(path: Path) -> set[str]:
    """이미 받아 둔 상세의 공고번호. 이어받기의 근거다.

    잡코리아 상세는 공고 하나에 요청이 두 번이라 사람인보다 느리다(건당 약 6초,
    IT 8,504건이면 14시간쯤). 한 번에 끝나지 않는 것을 전제로 두고, 받는 족족
    `.jsonl`에 붙여 두었다가 다음 실행에서 건너뛴다.
    """
    if not path.exists():
        return set()
    done: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(str(json.loads(line)["source_job_id"]))
            except (ValueError, KeyError):
                continue
    return done


def categories_for(today: date, *, full: bool = False) -> list[str]:
    """오늘 훑을 대분류. 일요일이나 `--full`이면 전부, 아니면 매일 보는 것만."""
    if full or today.weekday() == WEEKLY_DAY:
        return list(LIST_CATEGORIES)
    return list(DAILY_CATEGORIES)


def sweep_categories(
    session: requests.Session,
    duties: list[str],
    *,
    max_pages: int | None = None,
    min_delay: float = 3.0,
    max_delay: float = 5.0,
    on_category: Any = None,
) -> dict[str, dict[str, Any]]:
    """여러 대분류를 훑어 공고번호로 합친다.

    한 공고가 여러 대분류에 걸쳐 있다. 사람인 `list_seen`이 (공고, 대분류) 쌍을
    남기는 것과 같은 이유로 여기서도 **본 대분류를 전부 모아** `categories`에 둔다.
    상세를 받을지 고를 때 이 목록을 본다.
    """
    merged: dict[str, dict[str, Any]] = {}
    for duty in duties:
        count = 0
        # 사람이 하듯 대분류 화면을 먼저 연다. 세션에 조건이 남는다.
        url = category_url(duty)
        _guard(url)
        response = session.get(url, headers=navigation_headers(BASE_URL), timeout=30)
        check_response(response)
        polite_delay(min_delay, max_delay)

        for row in sweep_category(
            session, duty, max_pages=max_pages, min_delay=min_delay, max_delay=max_delay
        ):
            count += 1
            gno = row["source_job_id"]
            if gno in merged:
                merged[gno]["categories"].append(duty)
            else:
                row["categories"] = [duty]
                merged[gno] = row
        if on_category:
            on_category(duty, count, merged)
    return merged


def parse_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    """상세 껍데기의 schema.org JobPosting. 화면이 React라 여기가 제일 확실하다."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (TypeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("@type") == "JobPosting":
            return data
    return {}


def fetch_detail(
    session: requests.Session,
    gno: str,
    *,
    timeout: int = 30,
    min_delay: float = 3.0,
    max_delay: float = 5.0,
) -> dict[str, Any]:
    """상세 한 건. 껍데기(JSON-LD)와 본문 iframe을 합쳐 준다."""
    shell_url = f"{DETAIL_URL}/{gno}"
    _guard(shell_url)
    shell = session.get(shell_url, headers=navigation_headers(BASE_URL), timeout=timeout)
    check_response(shell)
    soup = BeautifulSoup(shell.text, "html.parser")
    ld = parse_json_ld(soup)
    # 마감 판정은 껍데기 글에서 본다. 판정 문구와 그 근거는 ingestion/jobkorea.py에 있다.
    shell_text = soup.get_text(" ", strip=True)

    # 본문 iframe은 브라우저가 상세 화면을 그리면서 곧바로 같이 받는다. 사람이 그 사이에
    # 쉬지 않으므로 여기서도 쉬지 않는다. 쉬는 것은 공고와 공고 사이다(호출한 쪽에서 한다).
    # 이 한 줄이 8,504건 기준 약 9시간을 가른다.
    body_url = f"{BODY_URL}?Gno={gno}&isHiringCenter=false&hideMapView=false"
    _guard(body_url)
    body_response = session.get(
        body_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Referer": shell_url,
            "Sec-Fetch-Dest": "iframe",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        },
        timeout=timeout,
    )
    check_response(body_response)
    body_soup = BeautifulSoup(body_response.text, "html.parser")
    for tag in body_soup(["script", "style", "noscript"]):
        tag.decompose()
    description = body_soup.get_text("\n", strip=True)
    image_count = len(body_soup.find_all("img"))

    org = ld.get("hiringOrganization") or {}
    place = (ld.get("jobLocation") or {}).get("address") or {}
    employment_raw = ld.get("employmentType") or ""
    codes = employment_raw if isinstance(employment_raw, list) else [employment_raw]
    employment = ", ".join(EMPLOYMENT_KO.get(code, code) for code in codes if code)

    return {
        "source": SOURCE,
        "source_job_id": gno,
        "source_url": shell_url,
        "title": ld.get("title") or "",
        "company": (org.get("name") if isinstance(org, dict) else "") or "",
        "description": description,
        # 사람인 쪽 `conditions`와 같은 자리. 열 이름을 맞춰 뒤쪽 규칙을 재사용한다.
        "conditions": {
            "경력": ld.get("experienceRequirements") or "",
            "학력": ld.get("educationRequirements") or "",
            "근무형태": employment,
            "근무지역": (place.get("streetAddress") if isinstance(place, dict) else "") or "",
        },
        # 옮기기 전 값. 표에 없는 코드가 나오면 여기를 보고 EMPLOYMENT_KO에 더한다.
        "employment_type_raw": employment_raw,
        "posted_at": ld.get("datePosted") or "",
        "deadline_raw": ld.get("validThrough") or "",
        # 본문이 이미지뿐이면 추천 근거로 쓸 글이 없다. 사람인과 같은 기준으로 센다.
        "image_body": len(description) < 50 and image_count > 0,
        "image_count": image_count,
        # 소스가 마감이라고 말하는지. 마감일이 남아 있어도 조기 마감될 수 있다.
        "closed": is_closed_page(shell_text),
        # 헤드헌팅 공고는 JSON-LD가 없어 제목·회사가 비어 온다. 적재 쪽에서 거른다.
        "has_json_ld": bool(ld),
        "parser_version": PARSER_VERSION,
        "fetched_at": datetime.now(KST).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="잡코리아 공고 수집. 목록은 여러 대분류, 상세는 IT만 받는다."
    )
    parser.add_argument(
        "--duty", action="append", default=None,
        help="훑을 대분류 코드. 여러 번 줄 수 있다. 안 주면 오늘 몫(일요일=전체, 평일=IT)",
    )
    parser.add_argument("--full", action="store_true", help="목록을 전 대분류로 훑는다")
    parser.add_argument("--pages", type=int, default=2, help="대분류당 받을 목록 쪽수")
    parser.add_argument("--all", action="store_true", help="목록을 끝까지 훑는다")
    parser.add_argument("--details", action="store_true", help="상세까지 받는다")
    parser.add_argument(
        "--detail-duty", action="append", default=None,
        help=f"상세를 받을 대분류. 기본 {DETAIL_CATEGORIES}",
    )
    parser.add_argument("--limit", type=int, default=0, help="상세를 받을 최대 건수 (0=전부)")
    parser.add_argument(
        "--max-minutes", type=float, default=0.0,
        help="상세에 쓸 시간 한도(분). 넘으면 멈추고 남은 건 다음 실행에서 이어받는다",
    )
    parser.add_argument(
        "--detail-file", type=Path, default=None,
        help="상세를 붙여 쓰는 jsonl. 기본값은 출처별 한 파일이라 이어받기가 된다",
    )
    parser.add_argument("--min-delay", type=float, default=3.0)
    parser.add_argument("--max-delay", type=float, default=5.0)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    # 시간 한도는 **실행 전체**를 덮는다. 상세만 재면 일요일에 목록 전체(약 5.2시간)를
    # 훑고 나서 상세가 한도를 새로 받아, 예약 작업의 제한시간을 넘겨 낮까지 돈다.
    run_started = time.monotonic()
    duties = args.duty or categories_for(datetime.now(KST).date(), full=args.full)
    detail_duties = set(args.detail_duty or DETAIL_CATEGORIES)

    out_dir = ARTIFACTS_DIR / "job_raw" / SOURCE
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y-%m-%d-%H%M")
    output = args.output or out_dir / f"jobkorea_{stamp}.json"
    # 실행마다 이름이 바뀌면 이어받기가 안 된다. 상세는 출처별로 한 파일에 쌓는다.
    if args.detail_file is None:
        args.detail_file = out_dir / "details.jsonl"

    try:
        session = new_session(duties[0], min_delay=args.min_delay, max_delay=args.max_delay)
    except (BlockedByTargetSiteError, requests.RequestException) as error:
        print(f"[중단] 목록 화면을 열지 못했습니다: {error}")
        return 1

    labels = ", ".join(DUTY_CATEGORIES.get(d, d) for d in duties)
    print(f"[목록] 대분류 {len(duties)}개: {labels}")

    def write_list(rows: list[dict[str, Any]], saved: int = 0, failed: int = 0) -> None:
        payload = {
            "source": SOURCE,
            "duties": duties,
            "duty_labels": {d: DUTY_CATEGORIES.get(d, d) for d in duties},
            "detail_duties": sorted(detail_duties),
            "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
            "list_count": len(rows),
            "detail_saved": saved,
            "detail_failed": failed,
            "detail_file": str(args.detail_file),
            "list": rows,
        }
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def report(duty: str, count: int, merged: dict[str, dict[str, Any]]) -> None:
        name = DUTY_CATEGORIES.get(duty, duty)
        print(f"  {name} {count:,}건 (누적 고유 {len(merged):,}건)", flush=True)
        # 대분류 하나 끝날 때마다 떨군다. 전 대분류 훑기가 다섯 시간이 넘어서,
        # 끝나고 한 번만 쓰면 도중에 연결이 끊길 때 그 다섯 시간이 통째로 날아간다.
        write_list(list(merged.values()))

    try:
        merged = sweep_categories(
            session,
            duties,
            max_pages=None if args.all else args.pages,
            min_delay=args.min_delay,
            max_delay=args.max_delay,
            on_category=report,
        )
    except BlockedByTargetSiteError as error:
        print(f"[중단] {error}")
        return 2

    rows = list(merged.values())
    print(f"[목록] 고유 {len(rows):,}건")

    # 상세로 넘어가기 전에 한 번 더. 상세가 끝나면 건수를 채워 같은 파일에 다시 쓴다.
    write_list(rows)
    print(f"[저장] 목록 {output}", flush=True)

    saved = 0
    failed = 0
    if args.details:
        # 상세는 `detail_duties`에 걸린 공고만. 목록에만 있는 나머지는 챗봇 검색용이다.
        targets = [r for r in rows if detail_duties.intersection(r["categories"])]
        list_only = len(rows) - len(targets)
        done = read_done_ids(args.detail_file)
        targets = [r for r in targets if r["source_job_id"] not in done]
        # 첫 채우기가 여러 밤에 걸친다. 어느 밤에 끊기든 IT부터 차 있도록 앞에 세운다.
        priority = set(PRIORITY_CATEGORIES)
        targets.sort(key=lambda r: 0 if priority.intersection(r["categories"]) else 1)
        if args.limit:
            targets = targets[: args.limit]
        print(
            f"[상세] {len(targets):,}건 (목록만 두는 공고 {list_only:,}건 · "
            f"이미 받은 것 {len(done):,}건은 건너뜀)"
        )
        started = time.monotonic()
        deadline = run_started + args.max_minutes * 60 if args.max_minutes else None
        if deadline is not None and time.monotonic() >= deadline:
            print(f"[상세] 목록에 한도 {args.max_minutes:.0f}분을 다 썼습니다. 상세는 다음 실행에서.")
            targets = []
        args.detail_file.parent.mkdir(parents=True, exist_ok=True)
        with args.detail_file.open("a", encoding="utf-8") as handle:
            for index, row in enumerate(targets, start=1):
                if deadline is not None and time.monotonic() >= deadline:
                    left = len(targets) - index + 1
                    print(f"[시간 종료] {args.max_minutes:.0f}분이 지나 멈춥니다. 남은 {left:,}건은 다음에.")
                    break
                try:
                    detail = fetch_detail(
                        session,
                        row["source_job_id"],
                        min_delay=args.min_delay,
                        max_delay=args.max_delay,
                    )
                except BlockedByTargetSiteError as error:
                    print(f"[중단] {error}")
                    break
                except requests.RequestException as error:
                    failed += 1
                    print(f"  [{index}/{len(targets)}] 실패 {row['source_job_id']}: {error}")
                    continue
                detail["list_item"] = row
                # 한 건씩 바로 붙인다. 중간에 꺼져도 여기까지는 남는다.
                handle.write(json.dumps(detail, ensure_ascii=False) + "\n")
                handle.flush()
                saved += 1
                flag = " [본문 이미지]" if detail["image_body"] else ""
                body_len = len(detail["description"])
                elapsed = (time.monotonic() - started) / 60
                left_min = elapsed / index * (len(targets) - index)
                print(
                    f"  [{index}/{len(targets)}] {detail['source_job_id']} "
                    f"본문 {body_len:,}자{flag}  (경과 {elapsed:.0f}분, 남은 예상 {left_min:.0f}분)"
                )
                polite_delay(args.min_delay, args.max_delay)

    write_list(rows, saved, failed)
    print(f"[저장] {output}  (상세 {saved:,}건 · 실패 {failed:,}건)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
