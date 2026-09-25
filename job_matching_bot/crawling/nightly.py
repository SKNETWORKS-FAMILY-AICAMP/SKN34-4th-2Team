"""밤마다 도는 수집 배치. 목록을 훑어 신규를 찾고, 상세를 받고, 저장소·인덱스를 맞춘다.

    python -m job_matching_bot.crawling.nightly                 # 오늘 몫 (월~토: IT 인접 4개 / 일: 전 대분류)
    python -m job_matching_bot.crawling.nightly --full          # 전 대분류 강제
    python -m job_matching_bot.crawling.nightly --dry-run       # 목록만 훑고 상세·기록·적재는 안 함
    python -m job_matching_bot.crawling.nightly --max-minutes 300

## 순서

1. 목록 sweep    대분류를 끝까지 훑는다(100건/쪽). 읽은 쪽수가 사이트 total_count 기준
                 쪽수에 못 미치면 '불완전'이다. 차단 신호가 오면 그 자리에서 모든 요청을 멈춘다.
2. 관측 기록     본 (공고, 대분류)를 저장소 `list_seen`에 남긴다. 사라짐 판정의 근거다.
3. 신규 상세     목록에는 있는데 저장소에 없는 공고를 인기 배지 → 목록 순위 → 마감 순으로
                 받는다(3~5초 간격). 시간이 다 되면 멈추고 남은 건 다음 밤에.
4. 링크 확인     오늘 삭제로 넘어갈 공고는 상세 페이지를 열어 정말 없어졌는지 본다.
                 열려 있으면 지우지 않는다. 하룻밤 건수 상한이 있다.
5. 적재          `sync`를 부른다. 오늘 받은 상세만 넣고, 목록 관측(observed)으로 만료·삭제를
                 판정한다. sweep이 불완전하면 안 본 공고는 '모름'으로 두어 지우지 않는다.
6. 공유          PostgreSQL `jobs` 원본 사용으로 전환하는 초안이다.
                 옛 Firebase Storage 슬림 파일 업로드 생략은 크롤링 담당자 확인 전이다.

## 주기

- 월~토: IT개발·데이터, 연구·R&D, 디자인, 기획·전략 (하루 신규 약 1,000건, 목록 약 250쪽)
- 일: 운전·운송·배송을 뺀 대분류 14개 전부 (목록 약 1,760쪽, 2~3시간)
- 매일 훑는 대분류의 공고는 이틀 연속 안 보이면 삭제. 주 1회 대분류의 공고는 마지막
  관측 뒤 15일까지 살아 있는 것으로 본다.

수집 규칙(robots 허용 경로만, UA 고정, 3~5초 간격, 차단 시 즉시 중단)은 `http_session`과
`crawl_list` / `crawl_detail`에 있고 여기서는 그대로 쓴다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from bs4 import BeautifulSoup

from job_matching_bot.env import ensure_loaded
from job_matching_bot.config import ARTIFACTS_DIR, RAW_DIR, REPO_ROOT
from job_matching_bot.crawling.crawl_detail import DETAIL_URL, SOURCE, crawl_details
from job_matching_bot.crawling.crawl_list import ALL_CATEGORIES, fetch_page, pages_for
from job_matching_bot.crawling.crawl_detail import is_closed_page
from job_matching_bot.crawling import jobkorea
from job_matching_bot.crawling.detail_queue import build_queue
from job_matching_bot.crawling.http_session import (
    LIST_PAGE_URL,
    BlockedByTargetSiteError,
    check_response,
    navigation_headers,
    new_session,
    polite_delay,
)
from job_matching_bot.ingest import DEFAULT_STORE
from job_matching_bot.ingestion.job_store import open_store
from job_matching_bot.ingestion.record_files import latest_by_id, read_records

KST = timezone(timedelta(hours=9))

# 매일 훑는 대분류. IT와 이력서가 겹치는 직군이다.
DAILY_CATEGORIES: tuple[str, ...] = ("2", "9", "15", "16")  # IT개발·데이터, 연구·R&D, 디자인, 기획·전략
# 추천 대상이 아니라 훑지 않는 대분류.
SKIPPED_CATEGORIES: tuple[str, ...] = ("7",)  # 운전·운송·배송
WEEKLY_DAY = 6  # 일요일
# 신규 상세를 받는 순서에서 앞에 두는 대분류. 첫 채우기는 IT부터 하기로 했다.
PRIORITY_CATEGORIES: tuple[str, ...] = ("2",)
# **상세를 받는 대분류.** 목록은 일요일에 전부 훑지만 상세는 여기 있는 것만 받는다.
# 넓히려면 여기에 하나씩 더한다. 대분류 하나가 사이트 기준 8,000~14,000건이고
# 하룻밤 4,500건을 받으므로 이틀에서 사흘이면 채워진다.
DETAIL_CATEGORIES: tuple[str, ...] = DAILY_CATEGORIES

# 주 1회 훑는 대분류의 공고를 살아 있다고 볼 기간. 일요일 sweep을 한 번 놓쳐도 지우지 않는다.
OBSERVED_WINDOW_DAYS = 15
PAGE_COUNT = 100
DEFAULT_MAX_MINUTES = 420.0  # 23:00 → 06:00
SYNC_RESERVE_MINUTES = 30.0  # 적재에 남겨 두는 시간
# 삭제 후보를 실제로 열어 보는 상한. 200일 때는 후보 3,000건을 한 바퀴 도는 데
# 15일이 걸려, 마감된 공고가 인덱스에 오래 남았다(확인한 200건 중 65%가 마감이었다).
# 800이면 4일에 한 바퀴다. 그만큼 상세 수집 시간이 줄지만, 마감 공고가 추천에
# 섞이는 쪽이 더 눈에 띄는 문제라 이쪽에 시간을 준다.
LINK_CHECK_LIMIT = 800
SWEEP_KEEP_DAYS = 14

SWEEP_DIR = RAW_DIR / "sweeps"
DETAIL_DIR = RAW_DIR / "details"
NIGHTLY_DIR = ARTIFACTS_DIR / "nightly"

# ── 잡코리아 ────────────────────────────────────────────────
# **수집은 사람인과 동시에, 적재는 차례로.** 사이트가 다르니 동시에 훑어도 어느 쪽에도
# 부담이 겹치지 않고, 수집은 대부분 기다리는 시간이라 둘을 나란히 두면 긴 쪽에 맞춰 끝난다.
# 적재는 다르다. 목록 적재가 수십만 줄을 한 트랜잭션에 넣어 WAL 의 busy_timeout(5초)을
# 넘길 수 있어서, 두 프로세스가 같이 쓰면 `database is locked` 가 난다.
#
# 그래서 잡코리아 수집기는 저장소를 아예 안 건드리고 파일까지만 만든다. 그 파일을
# 여기서 읽어 사람인 적재가 끝난 뒤에 넣는다.
JOBKOREA_SOURCE = "JOBKOREA_POC"
JOBKOREA_LIST_DIR = ARTIFACTS_DIR / "job_raw" / JOBKOREA_SOURCE
JOBKOREA_DETAIL_FILE = JOBKOREA_LIST_DIR / "details.jsonl"
# 잡코리아 수집에 주는 시간. 적재할 시간을 남기려고 전체 한도에서 떼어 둔다.
JOBKOREA_RESERVE_MINUTES = 40.0
# 사이트가 대분류당 이 수에서 막는다. 거기 닿은 대분류는 끝까지 못 본 것이므로
# "완전히 훑었다"로 기록하면 안 된다 — 못 본 공고가 사라진 것으로 판정된다.
JOBKOREA_WALL = 10_000

# 상세 페이지가 이 문구를 담으면 공고가 내려간 것으로 본다.
#
# 2026-09-08 실제 페이지로 검증했다. 그전 문구("마감된 공고", "채용이 마감" 등)는
# **하나도 맞지 않았다** — 마감된 공고 10건을 열어 0건을 잡았다. 사이트는 이렇게 쓴다.
#
#     "본 채용정보는 마감 되었습니다"      ← 띄어쓰기가 있다
#     "접수기간 및 방법 마감되었습니다"
#     "공고가 마감되어 작성할 수 없습니다"
#
# 열린 공고에도 "마감"은 많이 나온다("마감일은 기업의 사정, 조기마감 등으로 변경될 수
# 있습니다", "채용시 마감", "마감일 2026-09-30"). 그래서 "마감"만 보면 안 되고 **끝났다고
# 말하는 문장**을 봐야 한다.
#
# 표본 20건(마감 9 / 열림 11)으로 양쪽을 다 쟀다. 아래 문구는 마감 페이지 9건을 모두
# 잡고 열린 페이지 11건에서 하나도 걸리지 않았다.
#
# "접수마감"도 같은 성적이었지만 넣지 않았다. 위 문구가 이미 다 잡는데 상태 배지까지
# 보면 표기가 바뀌었을 때 왜 지워졌는지 알기 어려워진다.
# "지원하기"는 열린 페이지의 신호처럼 보이지만 마감 페이지에도 11/11 나와 쓸 수 없다.
def categories_for(today: date, full: bool = False) -> list[str]:
    if full or today.weekday() == WEEKLY_DAY:
        return [cat for cat in ALL_CATEGORIES if cat not in SKIPPED_CATEGORIES]
    return list(DAILY_CATEGORIES)


# ── 1. 목록 sweep ──────────────────────────────────────────────
@dataclass
class SweepResult:
    records: list[dict[str, Any]] = field(default_factory=list)   # (공고, 대분류)마다 한 건
    seen: dict[str, set[str]] = field(default_factory=dict)        # 대분류 → 본 ID
    totals: dict[str, int] = field(default_factory=dict)           # 대분류 → 사이트 total_count
    pages: dict[str, tuple[int, int]] = field(default_factory=dict)  # 대분류 → (읽은 쪽, 전체 쪽)
    complete: set[str] = field(default_factory=set)
    blocked: bool = False

    @property
    def seen_today(self) -> set[str]:
        return set().union(*self.seen.values()) if self.seen else set()

    def authoritative(self, planned: list[str]) -> bool:
        """계획한 대분류를 전부 끝까지 훑었는가. 그래야 '기록 없음 = 사라짐'으로 볼 수 있다."""
        return set(planned) <= self.complete


Fetcher = Callable[[str, int], tuple[int, list[dict[str, Any]]]]


def prioritize(queue: list[dict[str, Any]], first: tuple[str, ...] = PRIORITY_CATEGORIES) -> list[dict[str, Any]]:
    """우선 대분류의 공고를 앞으로. 그 안의 순서(인기 배지 → 순위 → 마감)는 그대로 둔다."""
    return sorted(queue, key=lambda r: 0 if str(r.get("cat_mcls") or "") in first else 1)


def sweep_category(
    fetch: Fetcher, cat: str, *, min_delay: float, max_delay: float, page_count: int = PAGE_COUNT
) -> tuple[list[dict[str, Any]], int, int, int, bool]:
    """대분류 하나를 끝까지 훑는다. (레코드, total_count, 읽은 쪽, 전체 쪽, 차단 여부).

    `fetch(cat, page)`는 (total_count, 레코드들)을 돌려준다. 네트워크는 거기에만 있다.
    """
    records: list[dict[str, Any]] = []
    total, last_page, page, retried, blocked = 0, 1, 1, False, False
    while page <= last_page:
        try:
            total, rows = fetch(cat, page)
        except BlockedByTargetSiteError as error:
            print(f"  [중단] {error}")
            blocked = True
            break
        except requests.RequestException as error:
            if retried:
                print(f"  [중단] 요청이 연속으로 실패했습니다: {error}")
                break
            retried = True
            print(f"  page {page}: 요청 실패({error}). 20~40초 쉬고 한 번 더 시도합니다.")
            polite_delay(20.0, 40.0)
            continue
        retried = False
        if page == 1:
            last_page = pages_for(total, page_count)
            print(f"  cat_mcls={cat} {ALL_CATEGORIES.get(cat, '')}: 사이트 {total:,}건 → {last_page}쪽")
        for row in rows:
            row["cat_mcls"] = cat
            row["list_rank"] = len(records) + 1
            row["list_sort"] = ""
            records.append(row)
        if not rows:
            # 사이트가 말한 쪽수보다 일찍 끝났다. 훑는 동안 공고가 줄어든 것이라 완전한 것으로 본다.
            page = last_page
            break
        page += 1
        if page <= last_page:
            polite_delay(min_delay, max_delay)
    pages_read = min(page, last_page) if not blocked and not retried else page - 1
    return records, total, pages_read, last_page, blocked


def sweep(
    categories: list[str], fetch: Fetcher, *, min_delay: float, max_delay: float, page_count: int = PAGE_COUNT
) -> SweepResult:
    result = SweepResult()
    for index, cat in enumerate(categories):
        print(f"[목록 {index + 1}/{len(categories)}] {ALL_CATEGORIES.get(cat, cat)}")
        records, total, pages_read, last_page, blocked = sweep_category(
            fetch, cat, min_delay=min_delay, max_delay=max_delay, page_count=page_count
        )
        result.records.extend(records)
        result.seen[cat] = {str(r["source_job_id"]) for r in records if r.get("source_job_id")}
        result.totals[cat] = total
        result.pages[cat] = (pages_read, last_page)
        if pages_read >= last_page and not blocked:
            result.complete.add(cat)
        print(f"  {len(records):,}건 / {pages_read}/{last_page}쪽 {'완전' if cat in result.complete else '불완전'}")
        if blocked:
            result.blocked = True
            break
        if index < len(categories) - 1:
            polite_delay(min_delay, max_delay)
    return result


def site_fetcher(session: requests.Session, page_count: int = PAGE_COUNT) -> Fetcher:
    def fetch(cat: str, page: int) -> tuple[int, list[dict[str, Any]]]:
        return fetch_page(session, page, None, cat, page_count=page_count)

    return fetch


# ── 4. 링크 확인 ───────────────────────────────────────────────
def check_alive(session: requests.Session, rec_idx: str, timeout: int = 30) -> bool | None:
    """True=아직 열려 있음, False=내려감, None=모름(일시 오류). 차단은 예외로 올린다."""
    url = f"{DETAIL_URL}?rec_idx={rec_idx}"
    try:
        response = session.get(url, headers=navigation_headers(LIST_PAGE_URL), timeout=timeout)
    except requests.RequestException:
        return None
    if response.status_code in (404, 410):
        return False
    try:
        check_response(response)
    except requests.HTTPError:
        return None
    return not is_closed_page(response.text)


def link_check_budget(minutes: float, max_delay: float, floor: int = 0) -> int:
    """남은 시간에 몇 건을 열어 볼 수 있나. 한 건에 응답 1초 + 쉬는 시간이 든다.

    목록에서 안 보이는 것은 마감 신호가 아니다(한 번 못 본 12건을 열어 보니 8건이 살아
    있었다). 그래서 링크 확인이 유일한 판정이고, 상세 수집이 끝나고 남은 시간은 전부
    여기에 쓴다. `floor`는 상세 수집 전에 미리 떼어 둔 몫이라 그 아래로는 내려가지 않는다.
    """
    fits = int(max(0.0, minutes) * 60 / (max_delay + 1))
    return max(floor, fits)


def link_check(
    session: requests.Session, candidates: list[str], *, limit: int, min_delay: float, max_delay: float
) -> tuple[set[str], Counter]:
    """삭제 직전 공고를 열어 본다. (살아 있어 남길 ID, 결과 집계)."""
    alive: set[str] = set()
    counts: Counter = Counter()
    for index, rec_idx in enumerate(candidates[:limit]):
        try:
            state = check_alive(session, rec_idx)
        except BlockedByTargetSiteError as error:
            print(f"  [중단] {error}")
            counts["blocked"] += 1
            # 못 본 나머지는 모르는 것이다. 지우지 않는다.
            alive.update(candidates[index:])
            break
        if state is None:
            counts["unknown"] += 1
            alive.add(rec_idx)
        elif state:
            counts["alive"] += 1
            alive.add(rec_idx)
        else:
            counts["closed"] += 1
        if index < min(limit, len(candidates)) - 1:
            polite_delay(min_delay, max_delay)
    # 상한 밖의 후보는 확인하지 못했다. 모르는 것은 지우지 않는다.
    alive.update(candidates[limit:])
    counts["unchecked"] += max(0, len(candidates) - limit)
    return alive, counts


# ── 5. 적재 ────────────────────────────────────────────────────
def run_sync(detail_file: Path, observed: set[str], store_path: Path, as_of: datetime, work_dir: Path) -> int:
    stamp = run_stamp(as_of)
    observed_file = work_dir / f"{stamp}_observed.json"
    observed_file.write_text(json.dumps([{"source_job_id": i} for i in sorted(observed)]), encoding="utf-8")
    # `--skip-index`: 인덱스는 두 출처가 다 들어오고 **묶은 뒤에** 한 번에 올린다.
    # 여기서 올리면 잡코리아가 들어오기 전 상태로 올라가, 나중에 대표가 바뀐 만큼
    # 지웠다 다시 올리게 된다.
    command = [
        sys.executable, "-m", "job_matching_bot.sync",
        "--input", str(detail_file), "--observed", str(observed_file),
        "--store", str(store_path), "--as-of", as_of.isoformat(),
        "--report", str(work_dir / f"{stamp}_sync.json"),
        "--skip-index",
    ]
    print("[적재] " + " ".join(command[2:]), flush=True)
    return subprocess.run(command, cwd=str(REPO_ROOT)).returncode


# 저장소를 못 열어 수집만 하고 끝난 밤의 종료 코드. 0 이 아니어서 예약 작업 기록에 드러난다.
FILES_ONLY_EXIT = 3


def known_from_files(store_path: Path) -> tuple[set[str], dict[str, str]]:
    """저장소를 못 열었을 때 "이미 상세를 받은 공고"를 파일에서 모은다.

    2026-09-22 밤에 저장소가 PostgreSQL 로 바뀌었는데 배치 환경에 드라이버가 없어 DB 를
    열다 죽었다. 목록은 다 훑었는데 상세 수집까지 같이 멈췄다. 수집은 DB 가 없어도 되는
    일이라, 무엇을 받았는지만 파일에서 알아내면 끝까지 갈 수 있다.

    - 옛 SQLite 저장소 파일(있으면 읽기 전용으로) — 마지막으로 적재된 상세
    - raw/details/*.jsonl — 그 뒤에 받아 파일로만 남은 상세

    판정(적재 때 중복 제거·재등록·묶기, 목록 기록으로 하는 사라짐)은 DB 가 있어야 한다.
    그건 빠지는 게 아니라 밀린다 — 파일이 남으므로 저장소가 열리는 날 적재하면 된다.
    """
    import sqlite3

    known: set[str] = set()
    waiting: dict[str, str] = {}
    if store_path.exists() and store_path.stat().st_size > 0:
        try:
            conn = sqlite3.connect(f"file:{store_path.as_posix()}?mode=ro", uri=True)
            try:
                known = {r[0] for r in conn.execute(
                    "SELECT source_job_id FROM jobs WHERE source = ?", (SOURCE,))}
                waiting = {r[0]: r[1] for r in conn.execute(
                    "SELECT source_job_id, MIN(first_seen_at) FROM list_seen "
                    "WHERE source = ? AND first_seen_at IS NOT NULL GROUP BY source_job_id", (SOURCE,))}
            finally:
                conn.close()
        except sqlite3.Error as error:
            print(f"  옛 SQLite 저장소를 읽지 못했습니다: {error}")
    for path in sorted(DETAIL_DIR.glob("*.jsonl")):
        for record in read_records(path):
            job_id = str(record.get("source_job_id") or (record.get("list_item") or {}).get("source_job_id") or "")
            if job_id:
                known.add(job_id)
    return known, waiting


def record_observations(store: Any, result: "SweepResult", now: datetime, authoritative: bool,
                        summary: dict[str, Any]) -> tuple[set[str], list[str]]:
    """목록에서 본 것을 저장소에 적고, 살아 있는 공고와 삭제 후보를 돌려준다."""
    store.record_list_seen(
        result.seen, {c: result.totals[c] for c in result.complete}, now, source=SOURCE
    )
    # 목록에서 본 공고를 챗봇 검색용 표에 담는다. **상세를 안 받는 대분류만** 담는다 —
    # 상세를 받는 쪽은 며칠 안에 `jobs`에 들어오므로 목록에 담아 봐야 중복이다.
    # 이것 덕에 "서울 영업직 있어?"에 답할 수 있다. `jobs`는 건드리지 않는다.
    listed = store.record_list_jobs(
        result.records, now, source=SOURCE, skip_categories=DETAIL_CATEGORIES
    )
    summary["list_jobs"] = listed
    print(f"[목록 적재] 챗봇 검색용 {listed:,}건")
    observed = store.list_observed(
        SOURCE, seen_today=result.seen_today, as_of=now, within_days=OBSERVED_WINDOW_DAYS, authoritative=authoritative
    )
    candidates = store.removal_candidates(SOURCE, observed)
    store.close()
    summary["observed"] = {"count": len(observed), "removal_candidates": len(candidates)}
    print(f"[관측] 살아 있는 것으로 볼 공고 {len(observed):,}건 · 삭제 후보 {len(candidates):,}건")
    return observed, candidates


def start_jobkorea(list_path: Path, log_path: Path, max_minutes: float) -> subprocess.Popen[bytes] | None:
    """잡코리아 수집기를 따로 띄운다. 저장소는 안 건드리고 파일까지만 만든다."""
    command = [
        sys.executable, "-u", "-m", "job_matching_bot.crawling.jobkorea",
        "--all", "--details", "--limit", "0",
        "--max-minutes", str(int(max(max_minutes, 1))),
        "--output", str(list_path),
    ]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print("[잡코리아] 수집 시작 (사람인과 동시) · 로그 " + str(log_path), flush=True)
    # 자식의 표준출력은 콘솔이 아니라 파일이라, 윈도우에서는 그대로 두면 cp949 로 쓴다.
    # 2026-09-21 첫 밤 로그가 그렇게 깨졌다. 사람인 로그와 같이 UTF-8 로 맞춘다.
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        handle = log_path.open("wb")
        return subprocess.Popen(
            command, cwd=str(REPO_ROOT), stdout=handle, stderr=subprocess.STDOUT, env=env
        )
    except OSError as error:
        # 잡코리아가 못 떠도 사람인 배치는 그대로 간다.
        print(f"[잡코리아] 띄우지 못했습니다: {error}")
        return None


def record_jobkorea_list(store: Any, list_path: Path, at: datetime) -> dict[str, Any]:
    """잡코리아 목록을 `list_seen`·`list_jobs`에 넣는다.

    사람인은 (공고, 대분류) 쌍마다 한 줄이라 `cat_mcls` 가 하나지만, 잡코리아는 한 공고에
    `categories` 목록으로 온다. 저장소 함수는 사람인 모양을 받으므로 여기서 펴 준다.
    """
    payload = json.loads(list_path.read_text(encoding="utf-8"))
    rows = payload.get("list") or []
    if not rows:
        return {"rows": 0}

    seen: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for cat in row.get("categories") or []:
            seen[cat].add(row["source_job_id"])
    capped = sorted(c for c, ids in seen.items() if len(ids) >= JOBKOREA_WALL)
    complete = {c: len(ids) for c, ids in seen.items() if len(ids) < JOBKOREA_WALL}

    # 상세를 받는 대분류의 공고는 `jobs` 로 들어오므로 목록 표에 담지 않는다. 저장소의
    # skip 판정은 `cat_mcls` 를 보므로 여기서 미리 거른다.
    skip = set(jobkorea.DETAIL_CATEGORIES)
    detailed = {r["source_job_id"] for r in rows if skip.intersection(r.get("categories") or [])}
    keep = [r for r in rows if r["source_job_id"] not in detailed]

    store.record_list_seen(dict(seen), complete, at, source=JOBKOREA_SOURCE)
    listed = store.record_list_jobs(keep, at, source=JOBKOREA_SOURCE, skip_categories=())
    if capped:
        print(f"  [잡코리아] 1만 벽에 닿은 대분류 {len(capped)}개 {capped} — 완전히 훑은 것으로 세지 않음")
    print(f"  [잡코리아] 목록 적재 {listed:,}건 (관측 {sum(len(v) for v in seen.values()):,}쌍)")
    return {"rows": len(rows), "listed": listed, "capped": capped}


def finish_jobkorea(
    proc: subprocess.Popen[bytes], list_path: Path, store_path: Path,
    as_of: datetime, work_dir: Path,
) -> dict[str, Any]:
    """잡코리아 수집이 끝나기를 기다렸다가 적재한다. 사람인 적재가 끝난 뒤에 부른다."""
    print("[잡코리아] 수집이 끝나기를 기다립니다", flush=True)
    code = proc.wait()
    if not list_path.exists():
        print(f"[잡코리아] 목록 파일이 없습니다(exit {code}). 적재를 건너뜁니다")
        return {"crawl_exit_code": code, "skipped": "목록 없음"}

    store = open_store(store_path)
    try:
        info = record_jobkorea_list(store, list_path, as_of)
    finally:
        store.close()

    # 사라짐 판정(`--observed`)은 아직 넘기지 않는다. 사이트가 대분류당 1만에서 막아
    # "안 보이면 사라진 것"을 아직 믿을 수 없다. 소분류로 쪼개 전량을 받게 된 뒤에 켠다.
    #
    # `--skip-index`: Pinecone 에는 아직 올리지 않는다. 같은 공고가 두 사이트에 다
    # 올라와 있는데(IT 상세에서만 1,100쌍) 묶는 코드가 아직 없다. 그대로 올리면 한
    # 공고가 벡터 둘이 되어 추천 목록에 두 번 뜬다. `find_reposts` 는 못 막는다 —
    # `(회사, 요건본문해시)` 로 묶는데 두 사이트의 본문 추출이 달라 해시가 안 맞는다.
    # 묶기를 붙이면 이 옵션을 빼면 된다. 그날 밤 한꺼번에 올라간다.
    command = [
        sys.executable, "-m", "job_matching_bot.sync",
        "--source", JOBKOREA_SOURCE, "--input", str(JOBKOREA_DETAIL_FILE),
        "--store", str(store_path), "--as-of", as_of.isoformat(),
        "--report", str(work_dir / f"{run_stamp(as_of)}_sync_jobkorea.json"),
        "--skip-index",
    ]
    print("[잡코리아 적재] " + " ".join(command[2:]), flush=True)
    info["crawl_exit_code"] = code
    info["sync_exit_code"] = subprocess.run(command, cwd=str(REPO_ROOT)).returncode
    return info


def run_regroup(store_path: Path, work_dir: Path, as_of: datetime) -> dict[str, Any]:
    """같은 공고를 묶어 `group_key` 에 적는다. 새 짝이 급증하면 스스로 멈춘다."""
    report = work_dir / f"{run_stamp(as_of)}_regroup.json"
    command = [
        sys.executable, "-m", "job_matching_bot.regroup",
        "--store", str(store_path), "--report", str(report), "--apply",
    ]
    print("[묶기] " + " ".join(command[2:]), flush=True)
    code = subprocess.run(command, cwd=str(REPO_ROOT)).returncode
    try:
        return {"exit_code": code, **json.loads(report.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return {"exit_code": code}


def run_index(store_path: Path, as_of: datetime, work_dir: Path) -> int:
    """묶기까지 끝난 상태로 Pinecone 을 맞춘다. 대표만 올라간다."""
    command = [
        sys.executable, "-m", "job_matching_bot.sync", "--index-only",
        "--store", str(store_path), "--as-of", as_of.isoformat(),
        "--report", str(work_dir / f"{run_stamp(as_of)}_index.json"),
    ]
    print("[인덱스] " + " ".join(command[2:]), flush=True)
    return subprocess.run(command, cwd=str(REPO_ROOT)).returncode


def share_store_file(store_path: Path) -> dict[str, Any]:
    """공유 파일 업로드 생략 초안. 크롤링 담당자 확인 후 운영 방식을 확정한다."""
    # TODO(크롤링 담당자 확인): 모든 소비자가 jobs 스키마를 직접 읽는지 검증하고
    # 정기 공유 파일이 불필요한지 합의한다. 확인 전에는 배포하지 않는다.
    del store_path
    print("[공유] PostgreSQL jobs 원본 사용; Firebase Storage 업로드 생략")
    return {"skipped": True, "reason": "shared_postgresql_jobs"}


def run_stamp(now: datetime) -> str:
    """이번 실행의 파일 이름. **날짜에 시작 시각을 붙인다.**

    날짜만 쓰던 때, 00:55에 시작한 배치(새벽에 다시 돌린 것)와 같은 날 23:00에 시작한
    정기 배치가 둘 다 `2026-09-13`이라 뒤엣것이 요약·적재 리포트·관측 목록·목록 원본을
    덮어썼다. 이름 앞 10자는 그대로 날짜라 `prune`이 보관 기간을 그대로 센다.

    상세 원본(`raw/details/<날짜>.jsonl`)은 날짜로 둔다. 같은 날 다시 돌리면 이미 받은
    상세를 건너뛰고 이어 받게 일부러 한 파일에 덧붙인다.
    """
    return f"{now:%Y-%m-%d-%H%M}"


def prune(directory: Path, keep_days: int, today: date) -> int:
    removed = 0
    cutoff = (today - timedelta(days=keep_days)).isoformat()
    for path in directory.glob("*.json"):
        if path.stem[:10] < cutoff:
            path.unlink()
            removed += 1
    return removed


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="야간 수집 배치")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--full", action="store_true", help="요일과 무관하게 전 대분류를 훑는다")
    parser.add_argument("--categories", default=None, help="훑을 대분류 코드. 쉼표 구분(예: 2,15)")
    parser.add_argument("--max-minutes", type=float, default=DEFAULT_MAX_MINUTES, help="전체 시간 한도")
    parser.add_argument("--link-check-limit", type=int, default=LINK_CHECK_LIMIT)
    # 평균 3초. 예전에는 3~5초(평균 4초)였고 건당 4.65초가 들었다. 폭을 좁히되
    # 고정값으로는 두지 않는다 — 간격이 자로 잰 듯 일정하면 오히려 눈에 띈다.
    parser.add_argument("--min-delay", type=float, default=2.5)
    parser.add_argument("--max-delay", type=float, default=3.5)
    parser.add_argument("--dry-run", action="store_true", help="목록만 훑고 상세·기록·적재는 하지 않는다")
    parser.add_argument("--no-share", action="store_true", help="공유 파일을 만들지 않는다")
    parser.add_argument("--no-jobkorea", action="store_true", help="잡코리아는 건드리지 않는다")
    args = parser.parse_args()
    # 저장소가 PostgreSQL 이라 DATABASE_URL 이 있어야 연다. 그 값은 저장소 루트 .env 에만 있고,
    # 예약 작업은 .env 를 모른다. SQLite 시절엔 파일 경로만 알면 돼서 안 읽어도 됐다.
    ensure_loaded()

    started = time.monotonic()
    now = datetime.now(KST)
    today = now.date()
    stamp = run_stamp(now)
    planned = [c.strip() for c in args.categories.split(",")] if args.categories else categories_for(today, args.full)
    summary: dict[str, Any] = {
        "date": today.isoformat(), "run": stamp,
        "started_at": now.isoformat(timespec="seconds"), "categories": planned,
    }
    print(f"야간 배치 {now:%Y-%m-%d %H:%M} · 대분류 {len(planned)}개 · 한도 {args.max_minutes:.0f}분")

    def minutes_left() -> float:
        return args.max_minutes - (time.monotonic() - started) / 60

    # 0. 잡코리아 수집을 먼저 띄운다. 사람인 목록을 훑는 동안 나란히 돈다.
    jobkorea_list = JOBKOREA_LIST_DIR / f"{stamp}.json"
    jobkorea_proc = None
    if not (args.dry_run or args.no_jobkorea):
        jobkorea_proc = start_jobkorea(
            jobkorea_list,
            NIGHTLY_DIR / "log" / f"jobkorea_{today.isoformat()}.log",
            args.max_minutes - JOBKOREA_RESERVE_MINUTES,
        )

    # 1. 목록 sweep
    try:
        session = new_session(min_delay=args.min_delay, max_delay=args.max_delay)
    except (BlockedByTargetSiteError, requests.RequestException) as error:
        print(f"[중단] 첫 페이지를 열지 못했습니다: {error}")
        return 1
    result = sweep(planned, site_fetcher(session), min_delay=args.min_delay, max_delay=args.max_delay)
    authoritative = result.authoritative(planned)
    summary["sweep"] = {
        "records": len(result.records), "unique": len(result.seen_today), "totals": result.totals,
        "pages": {c: list(p) for c, p in result.pages.items()}, "complete": sorted(result.complete),
        "authoritative": authoritative, "blocked": result.blocked,
    }
    print(
        f"[목록] {len(result.seen_today):,}건 · 완전 {len(result.complete)}/{len(planned)} · "
        f"{'전 대분류 확정' if authoritative else '불완전 — 안 본 공고는 지우지 않음'}"
    )

    SWEEP_DIR.mkdir(parents=True, exist_ok=True)
    (SWEEP_DIR / f"{stamp}.json").write_text(json.dumps(result.records, ensure_ascii=False), encoding="utf-8")
    prune(SWEEP_DIR, SWEEP_KEEP_DAYS, today)

    # 2. 관측 기록 · 신규 선별
    # 저장소를 못 열어도 수집은 끝까지 간다. 적재할 곳이 없을 뿐, 받는 일은 파일이면 된다.
    store = None
    files_only = None
    try:
        store = open_store(args.store)
    except Exception as error:  # 드라이버 없음 · DB 꺼짐 · 주소 없음
        files_only = f"{type(error).__name__}: {error}"
        summary["files_only"] = files_only
        print(f"[저장소] 열지 못했습니다 — {files_only}")
        print("  수집은 끝까지 하고 파일로만 남깁니다. 적재·묶기·인덱스·공유는 건너뜁니다.")
    if store is not None and not hasattr(store, "list_observed"):
        print(f"SQLite 저장소만 지원합니다: {args.store}")
        return 1
    if store is not None:
        known_ids, waiting = store.source_job_ids(SOURCE), store.waiting_since()
    else:
        known_ids, waiting = known_from_files(Path(args.store))
    detail_file = DETAIL_DIR / f"{today.isoformat()}.jsonl"
    already_today = set(latest_by_id(read_records(detail_file)))
    # 목록에서 처음 본 시각을 함께 넘긴다. 인기순 줄에 오래 기다린 공고를
    # 끼워 넣어, 순위가 밀린 공고도 매일 조금씩 차례가 오게 한다.
    # 상세는 **매일 훑는 대분류만** 받는다. 일요일 전체 훑기가 14개를 훑는데 IT 밖
    # 대분류의 상세까지 다 받으려면 13만 건에 38일이 걸려, 다음 일요일 전에 못 끝낸다.
    # 목록은 전부 훑으므로 사라짐 판정은 그대로다. 상세를 넓히려면 DAILY_CATEGORIES에
    # 대분류를 하나 추가한다 — 연구·R&D 8,707건이면 이틀치다.
    queue, queue_stats = build_queue(
        result.records, known_ids | already_today, now, waiting,
        detail_categories=DETAIL_CATEGORIES,
    )
    queue = prioritize(queue)
    summary["new"] = {"queued": len(queue), **{k: v for k, v in queue_stats.items()}}
    print(f"[신규] 저장소에 없는 공고 {len(queue):,}건 (제외 직종 {queue_stats.get('제외 직종(배달·배송·운전)', 0):,})")

    if args.dry_run:
        if store is not None:
            store.close()
        print("(--dry-run: 기록·상세·적재를 하지 않았습니다)")
        return 0

    observed: set[str] = set()
    candidates: list[str] = []
    if store is not None:
        observed, candidates = record_observations(store, result, now, authoritative, summary)

    # 3. 신규 상세 (차단됐으면 더 요청하지 않는다)
    crawl_counts: dict[str, int] = {}
    if result.blocked:
        print("[상세] 차단 신호가 있어 오늘은 더 요청하지 않습니다")
    elif queue:
        budget = minutes_left() - SYNC_RESERVE_MINUTES - min(len(candidates), args.link_check_limit) * (args.max_delay + 1) / 60
        if budget < 5:
            print(f"[상세] 남은 시간이 {budget:.0f}분이라 건너뜁니다")
        else:
            DETAIL_DIR.mkdir(parents=True, exist_ok=True)
            print(f"[상세] {len(queue):,}건 중 {budget:.0f}분 동안 받습니다")
            crawl_counts = crawl_details(queue, detail_file, args.min_delay, args.max_delay, max_minutes=budget)
    summary["detail"] = crawl_counts

    # 4. 링크 확인 — 상세 수집이 끝나고 남은 시간을 전부 쓴다. 못 본 건 다음 밤으로.
    if candidates and not result.blocked:
        reserved = min(len(candidates), args.link_check_limit)
        limit = min(len(candidates), link_check_budget(minutes_left() - SYNC_RESERVE_MINUTES, args.max_delay, floor=reserved))
        print(f"[링크 확인] 삭제 후보 {len(candidates):,}건 중 {limit:,}건 (남은 시간 기준)")
        alive, check_counts = link_check(
            session, candidates, limit=limit, min_delay=args.min_delay, max_delay=args.max_delay
        )
        observed |= alive
        summary["link_check"] = dict(check_counts)
        print("  " + " · ".join(f"{k} {v}" for k, v in check_counts.items()))
    elif candidates:
        observed |= set(candidates)  # 확인 못 했으니 지우지 않는다
        summary["link_check"] = {"skipped": len(candidates)}

    NIGHTLY_DIR.mkdir(parents=True, exist_ok=True)
    detail_file.parent.mkdir(parents=True, exist_ok=True)
    detail_file.touch(exist_ok=True)

    if files_only:
        # 잡코리아도 파일은 끝까지 받게 기다린다. 적재만 안 한다.
        if jobkorea_proc is not None:
            print("[잡코리아] 수집이 끝나기를 기다립니다 (적재는 건너뜀)", flush=True)
            summary["jobkorea"] = {"crawl_exit_code": jobkorea_proc.wait(), "skipped": "저장소 없음"}
        print("[적재] 건너뜀 — 저장소를 열 수 있게 되면 아래로 넣는다")
        print(f"  python -m job_matching_bot.sync --input {detail_file}")
        print(f"  python -m job_matching_bot.sync --source {JOBKOREA_SOURCE}")
        code = FILES_ONLY_EXIT
    else:
        # 5. 적재
        code = run_sync(detail_file, observed, args.store, now, NIGHTLY_DIR)
        summary["sync_exit_code"] = code

        # 5b. 잡코리아. 수집은 병렬로 이미 돌았고 적재만 차례로 한다 — 같이 쓰면 잠긴다.
        if jobkorea_proc is not None:
            summary["jobkorea"] = finish_jobkorea(
                jobkorea_proc, jobkorea_list, args.store, now, NIGHTLY_DIR
            )

        # 5c. 같은 공고 묶기 → 대표만 인덱스. 두 출처가 다 들어온 뒤라야 짝을 찾는다.
        summary["regroup"] = run_regroup(args.store, NIGHTLY_DIR, now)
        summary["index_exit_code"] = run_index(args.store, now, NIGHTLY_DIR)

        # 6. PostgreSQL 직접 공유 초안. 담당자 검토 전에는 이 배치 변경을 배포하지 않는다.
        if not args.no_share:
            summary["share"] = share_store_file(args.store)

    summary["elapsed_minutes"] = round((time.monotonic() - started) / 60, 1)
    (NIGHTLY_DIR / f"{stamp}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"완료 ({summary['elapsed_minutes']}분) · 요약 {NIGHTLY_DIR / f'{stamp}.json'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
