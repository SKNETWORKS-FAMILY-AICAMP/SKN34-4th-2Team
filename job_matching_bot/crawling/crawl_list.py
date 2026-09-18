"""사람인 채용공고 목록 POC 크롤러 (requests + BeautifulSoup).

API 키가 나오기 전까지 쓸 테스트 데이터를 만드는 용도다. 비로그인 상태에서
공개된 목록 페이지만 읽고, 상세 페이지는 열지 않는다.

## 확인한 제약

1. robots.txt (saramin.co.kr) — `User-agent: *` 아래 Disallow 목록에
   `/zf_user/jobs/list/`는 없다. 이 스크립트는 이 경로만 요청한다
   (`ALLOWED_PATH` 로 코드에서 강제).
   참고로 사람인은 `GPTBot`과 `Bytespider`를 이름으로 지목해 전체 차단한다.
   이 스크립트는 그 봇이 아니며 모델 학습용 수집도 아니다.

2. 목록 본문은 HTML에 없다. 브라우저가 XHR로 다시 받아온다.
   `isAjaxRequest=y`를 붙이면 아래 JSON이 오고, 여기에 광고가 섞이지 않은
   실제 공고만 들어 있다. Selenium 없이 requests로 충분한 이유다.

       {"total_count": 1824, "contents": "<section class=...>...</section>"}

   `isAjaxRequest` 없이 같은 URL을 부르면 `li.item`이 전부 `rel="sponsored"`
   광고 배너다. 그래서 그쪽은 쓰지 않는다.

3. 차단/캡차는 우회하지 않는다. 차단 문구가 감지되면 즉시 멈춘다.

4. 요청 간격을 둔다(기본 3~6초). 한 번 실행의 페이지 수도 제한한다.

사용:
    pip install requests beautifulsoup4
    python crawl_saramin.py --pages 3
    python crawl_saramin.py --cat-kewd 84 --pages 5 --output output/saramin_raw.json
    python crawl_saramin.py --it --all        # IT개발·데이터 전체 목록 (약 11,880건, 238페이지)
    python crawl_saramin.py --all-categories --all --sort AD --page-count 100 \
        --output output/saramin_all_raw.json  # 대분류 15개 전체, 지원순(인기), 100건/쪽
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from job_matching_bot.ingestion.company_name import clean_company_name, clean_listing_text
from job_matching_bot.crawling.http_session import (
    LIST_PAGE_URL,
    BlockedByTargetSiteError,
    check_response,
    new_session,
    polite_delay,
    xhr_headers,
)

BASE_URL = "https://www.saramin.co.kr"
LIST_URL = f"{BASE_URL}/zf_user/jobs/list/job-category"

# robots.txt에서 허용된 경로만 요청한다. 이 목록 밖은 요청하지 않는다.
ALLOWED_PATH = "/zf_user/jobs/list/"

# 정상적인 브라우저 요청으로 보이도록 일반 헤더를 넣는다. 설계 문서 §10.3이
# 허용하는 범위이며, 헤더를 돌려가며 차단을 피하는 식의 회피는 하지 않는다.


REC_IDX_RE = re.compile(r"rec_idx=(\d+)")




def _guard_allowed(url: str) -> None:
    if not urlparse(url).path.startswith(ALLOWED_PATH):
        raise ValueError(f"허용 경로가 아닙니다: {url} (허용: {ALLOWED_PATH})")




def _text(node: Any, selector: str) -> str:
    found = node.select_one(selector)
    return found.get_text(" ", strip=True) if found else ""


def _company_name(item: Any) -> str:
    """회사명만 뽑는다. 링크(a.str_tit)가 정답이고, 없을 때만 칸 글자를 손질한다.

    링크가 없는 카드가 아직 있다(2026-09-13 밤 21만 6천 줄 중 2,203줄). 예전에는 "관심기업 등록"
    버튼 글자만 지워서 "현대카드(주) 현대자동차그룹 대기업"처럼 그룹·기업형태 뱃지가 남았다.
    """
    link = item.select_one("div.company_nm a.str_tit")
    if link:
        return clean_company_name(link.get_text(" ", strip=True))
    return clean_company_name(_text(item, "div.company_nm"))


def parse_item(item: Any) -> dict[str, Any]:
    """목록 카드 하나를 레코드로 만든다.

    상세 페이지를 열지 않으므로 목록에 보이는 값만 담는다. 원문 텍스트를
    그대로 남겨서, 해석이 틀렸을 때 원본으로 되돌아갈 수 있게 한다.
    """
    link = item.select_one("div.job_tit a.str_tit")
    href = link.get("href", "") if link else ""
    match = REC_IDX_RE.search(href)

    # "서울 마포구  신입 · 경력 · 정규직  대학교(4년)↑" 처럼 조건이 한 덩어리로 온다.
    # 규칙으로 쪼개면 사이트가 표기를 바꿀 때 조용히 틀리므로, 조각만 나눠 두고
    # 의미 해석은 정규화 단계에 맡긴다.
    condition_node = item.select_one("div.job_condition") or item.select_one(".col.recruit_info")
    conditions = (
        [part.get_text(" ", strip=True) for part in condition_node.select("span, div") if part.get_text(strip=True)]
        if condition_node
        else []
    )

    return {
        "source": "SARAMIN_POC",
        "source_job_id": match.group(1) if match else "",
        "source_url": f"{BASE_URL}{href}" if href.startswith("/") else href,
        # 회사명은 링크 텍스트만 쓴다. div.company_nm 전체를 읽으면 "관심기업 등록"
        # 버튼과 그룹명·기업형태 뱃지가 딸려 온다(목록 11,882건 중 672건에서 확인).
        "company": _company_name(item),
        "title": clean_listing_text(link.get("title", "")) if link else "",
        # 사람인이 붙여 둔 직무 분류. 기술 키워드 추출의 좋은 입력이다.
        "job_sectors": [
            span.get_text(strip=True)
            for span in item.select("span.job_sector span")
            if span.get_text(strip=True)
        ],
        "conditions": conditions,
        "condition_text": _text(item, ".col.recruit_info"),
        "support_text": _text(item, ".col.support_info"),
        # "지원 TOP100" 같은 인기 배지. 상세 크롤 우선순위의 근거가 된다.
        "badge": _text(item, ".job_badge"),
        "collected_from": "job-category",
    }


# 사람인 직무 대분류. 2 = IT개발·데이터 (세부 키워드 84·92·80 등을 전부 포함).
IT_CATEGORY_MCLS = "2"

# 대분류 전체. 1은 비어 있어 뺐다. 이름은 fixtures/saramin_job_codes.json 과 같다.
ALL_CATEGORIES: dict[str, str] = {
    "2": "IT개발·데이터", "3": "회계·세무·재무", "4": "총무·법무·사무", "5": "인사·노무·HRD",
    "6": "의료", "7": "운전·운송·배송", "8": "영업·판매·무역", "9": "연구·R&D",
    "10": "서비스", "11": "생산", "12": "상품기획·MD", "13": "미디어·문화·스포츠",
    "14": "마케팅·홍보·조사", "15": "디자인", "16": "기획·전략",
}

# 목록 정렬. 사이트 UI의 값 그대로다. AD(지원순)를 인기순으로 쓴다.
SORT_OPTIONS = {"RL": "추천순", "RD": "최신순", "MD": "수정순", "EA": "마감순", "AD": "지원순"}


def fetch_page(
    session: requests.Session,
    page: int,
    cat_kewd: str | None,
    cat_mcls: str | None = None,
    timeout: int = 30,
    sort: str | None = None,
    page_count: int = 50,
) -> tuple[int, list[dict[str, Any]]]:
    """목록 한 페이지를 가져와 (전체 건수, 레코드들)로 돌려준다.

    `cat_mcls`(대분류)를 주면 세부 키워드 없이 그 분류 전체를 훑는다.
    """
    _guard_allowed(LIST_URL)
    params: dict[str, Any] = {"page": page, "isAjaxRequest": "y"}
    if cat_mcls:
        params["cat_mcls"] = cat_mcls
    if cat_kewd:
        params["cat_kewd"] = cat_kewd
    # 사이트 UI가 제공하는 값만 쓴다(정렬 5종, 페이지 크기 최대 100).
    if sort:
        params["sort"] = sort
    if page_count != 50:
        params["page_count"] = page_count

    # 목록은 페이지 안의 스크립트가 XHR로 불러온다. 브라우저가 보내는 대로 보낸다.
    response = session.get(
        LIST_URL, params=params, headers=xhr_headers(LIST_PAGE_URL), timeout=timeout
    )
    check_response(response)

    payload = response.json()
    soup = BeautifulSoup(payload.get("contents", ""), "html.parser")
    records = [parse_item(item) for item in soup.select("div.list_item")]
    return int(payload.get("total_count", 0)), records


# 목록 한 페이지에 실리는 공고 수. 전체 페이지 수 계산에 쓴다.
PAGE_SIZE = 50


def pages_for(total_count: int, page_size: int = PAGE_SIZE) -> int:
    """total_count 를 다 보려면 몇 페이지가 필요한가."""
    return max(1, -(-total_count // page_size))


def crawl(
    pages: int | None,
    cat_kewd: str | None,
    min_delay: float,
    max_delay: float,
    seen: set[str] | None = None,
    cat_mcls: str | None = None,
    sort: str | None = None,
    page_count: int = 50,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """목록을 훑는다. `pages=None`이면 첫 페이지의 total_count 로 끝까지 간다.

    `seen`을 넘기면 키워드 여러 개를 이어 돌릴 때 같은 공고를 한 번만 담는다.
    `sort`를 주면 그 순서로 받고, 각 레코드에 대분류와 그 안에서의 순위(`list_rank`)를
    남겨 나중에 상세 크롤 우선순위로 쓴다. `session`을 주면 대분류를 이어 돌 때
    쿠키를 유지한다.
    """
    # 사람처럼 목록 페이지를 먼저 열어 쿠키를 받은 세션으로 시작한다.
    if session is None:
        try:
            session = new_session(min_delay=min_delay, max_delay=max_delay)
        except (BlockedByTargetSiteError, requests.RequestException) as error:
            print(f"[중단] 첫 페이지를 열지 못했습니다: {error}")
            return []
    rank = 0
    collected: list[dict[str, Any]] = []
    seen = seen if seen is not None else set()
    last_page = pages or 1
    page = 1

    retried = False
    while page <= last_page:
        try:
            total, records = fetch_page(
                session, page, cat_kewd, cat_mcls, sort=sort, page_count=page_count
            )
        except BlockedByTargetSiteError as error:
            print(f"[중단] {error}")
            break
        except requests.RequestException as error:
            # 연결이 끊기거나 5xx가 오면 한 번은 길게 쉬고 다시 시도한다.
            # 두 번 연속이면 서버가 원하지 않는 것으로 보고 멈춘다.
            if retried:
                print(f"[중단] 요청이 연속으로 실패했습니다: {error}")
                break
            retried = True
            print(f"  page {page}: 요청 실패({error}). 20~40초 쉬고 한 번 더 시도합니다.")
            polite_delay(20.0, 40.0)
            continue
        retried = False

        if pages is None and page == 1:
            last_page = pages_for(total, page_count)
            label = f"cat_mcls={cat_mcls}" if cat_mcls else f"cat_kewd={cat_kewd}"
            print(f"  {label}: 사이트 전체 {total:,}건 → {last_page}페이지")

        for record in records:
            rank += 1
            record["cat_mcls"] = cat_mcls or ""
            record["list_rank"] = rank
            record["list_sort"] = sort or ""
        new = [r for r in records if r["source_job_id"] and r["source_job_id"] not in seen]
        seen.update(r["source_job_id"] for r in new)
        collected.extend(new)
        print(f"  page {page}/{last_page}: {len(records)}건 파싱 / 신규 {len(new)}건")

        if not records:
            print("  더 이상 결과가 없어 중단합니다.")
            break
        page += 1
        if page <= last_page:
            polite_delay(min_delay, max_delay)

    return collected


def main() -> int:
    parser = argparse.ArgumentParser(description="사람인 목록 POC 크롤러 (requests + bs4)")
    parser.add_argument(
        "--pages", type=int, default=3, help="키워드당 수집할 페이지 수 (한 페이지 50건)"
    )
    parser.add_argument(
        "--all", action="store_true", help="--pages 대신 total_count 기준으로 끝까지 훑는다"
    )
    parser.add_argument(
        "--cat-kewd",
        default=None,
        help="세부 직무 코드. 쉼표로 여러 개 (84=백엔드/서버개발, 92=프론트엔드, 83=데이터엔지니어, 80=게임개발). "
        "--it 와 같이 쓰면 안 된다",
    )
    parser.add_argument(
        "--it",
        action="store_true",
        help="IT개발·데이터 대분류 전체(cat_mcls=2, 약 11,880건)를 훑는다",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="대분류 15개(IT부터 기획·전략까지)를 순서대로 전부 훑는다. --it, --cat-kewd 와 같이 쓰면 안 된다",
    )
    parser.add_argument(
        "--sort",
        choices=sorted(SORT_OPTIONS),
        default=None,
        help="목록 정렬. AD=지원순(인기), RL=추천순, RD=최신순, MD=수정순, EA=마감순. 없으면 사이트 기본값",
    )
    parser.add_argument(
        "--page-count",
        type=int,
        choices=(20, 30, 50, 100),
        default=50,
        help="한 페이지에 받을 건수. 사이트 UI가 허용하는 값만. 100이면 요청 수가 절반",
    )
    parser.add_argument("--min-delay", type=float, default=3.0)
    parser.add_argument("--max-delay", type=float, default=6.0)
    parser.add_argument("--output", type=Path, default=Path("output/saramin_raw.json"))
    args = parser.parse_args()

    if sum(bool(x) for x in (args.it, args.cat_kewd, args.all_categories)) > 1:
        print("--it, --cat-kewd, --all-categories 는 하나만 고르세요.")
        return 2
    if not args.it and not args.cat_kewd and not args.all_categories:
        # 아무것도 안 주면 예전 기본값(백엔드)으로 작은 표본만 받는다.
        args.cat_kewd = "84"
    pages = None if args.all else args.pages
    scope = "전체" if pages is None else f"{pages}페이지"
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    sort_label = f", 정렬={SORT_OPTIONS[args.sort]}" if args.sort else ""
    if args.all_categories:
        print(f"사람인 목록 수집: 대분류 {len(ALL_CATEGORIES)}개 전체, {scope}{sort_label}, {args.page_count}건/쪽")
        # 세션 하나로 이어 돌린다. 사람이 카테고리를 바꿔 가며 보는 흐름과 같다.
        try:
            session = new_session(min_delay=args.min_delay, max_delay=args.max_delay)
        except (BlockedByTargetSiteError, requests.RequestException) as error:
            print(f"[중단] 첫 페이지를 열지 못했습니다: {error}")
            return 1
        for index, (mcls, name) in enumerate(ALL_CATEGORIES.items()):
            print(f"[{index + 1}/{len(ALL_CATEGORIES)}] {name} (cat_mcls={mcls})")
            records.extend(
                crawl(
                    pages, None, args.min_delay, args.max_delay, seen=seen, cat_mcls=mcls,
                    sort=args.sort, page_count=args.page_count, session=session,
                )
            )
            # 중간 저장: 끊겨도 받은 만큼은 남긴다.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  누적 {len(records):,}건 저장")
            if index < len(ALL_CATEGORIES) - 1:
                polite_delay(args.min_delay, args.max_delay)
    elif args.it:
        print(f"사람인 목록 수집: IT개발·데이터 전체(cat_mcls={IT_CATEGORY_MCLS}), {scope}{sort_label}")
        records = crawl(
            pages, None, args.min_delay, args.max_delay, seen=seen, cat_mcls=IT_CATEGORY_MCLS,
            sort=args.sort, page_count=args.page_count,
        )
    else:
        keywords = [k.strip() for k in args.cat_kewd.split(",") if k.strip()]
        print(f"사람인 목록 수집: cat_kewd={keywords}, {scope}")
        for index, keyword in enumerate(keywords):
            records.extend(
                crawl(
                    pages, keyword, args.min_delay, args.max_delay, seen=seen,
                    sort=args.sort, page_count=args.page_count,
                )
            )
            if index < len(keywords) - 1:
                polite_delay(args.min_delay, args.max_delay)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"{len(records)}건 저장: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
