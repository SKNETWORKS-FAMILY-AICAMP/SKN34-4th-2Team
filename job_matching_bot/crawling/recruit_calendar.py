"""공채 달력 수집 — 회사 로고 · 기업 형태 · 지원 방법을 모은다.

공고 자체는 밤 배치가 이미 받는다. 달력에서 새로 얻는 것은 공고 목록에 없는 세 가지다.

- 회사 로고 주소(사람인) — 공고 맞춤 지원 첫 화면의 공채 카드
- 기업 형태(대기업 · 공기업 · 외국계 …) — 달력을 형태별로 걸러 받아 붙인다
- 지원 방법(홈페이지 · 이메일 · 사람인) — 「회사 채용 사이트 열기」를 띄울지

받은 것은 파일로만 둔다(artifacts/recruit_calendar/날짜/). DB 에 넣는 일은 company_profiles ·
jobs.jobs.apply_method 가 생긴 뒤(lms 0014) 따로 붙인다.

## 출처와 robots.txt (2026-10-07 확인)

- 사람인: calendar.saramin.co.kr 화면이 부르는 api-enricher.saramin.co.kr/calendar/recruits/schedule.
  두 호스트 모두 robots.txt 가 없다. 달마다 · 기업 형태마다 한 번씩만 부른다.
- 잡코리아: /starter/calendar/YYYYMM (신입 공채 달력, 서버 렌더링). `User-agent: *` 블록의
  Disallow 에 걸리지 않는다. 회사 이름 · 공고 번호 · 시작/마감 날짜만 있고 로고는 없다.

요청 예절은 목록 크롤러와 같다 — UA 하나 고정, 요청 사이 3~5초, 403 · 429 · 차단 문구면 바로 멈춘다.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.crawling import http_session, jobkorea

KST = timezone(timedelta(hours=9))
OUT_DIR = ARTIFACTS_DIR / "recruit_calendar"

SARAMIN_API = "https://api-enricher.saramin.co.kr/calendar/recruits/schedule"
SARAMIN_PAGE = "https://calendar.saramin.co.kr"
# 달력 화면의 기업 형태 거르기 값 — 회사 형태는 이 순서로 앞의 것을 고른다. 중소(scale003)는 받지 않는다.
# scale002 는 「1000대기업」이다(우리 공고의 기업형태 칸과 맞대 99%) — 중견 · 중소에도 붙어 맨 뒤
SARAMIN_TYPES = {
    "scale001": "대기업",
    "public": "공기업",
    "foreign": "외국계",
    "kospi": "코스피",
    "kosdaq": "코스닥",
    "scale002": "1000대기업",
}
# 나머지 조건은 화면의 테마 기본값 그대로(경력 · 직무 · 업종 · 지역 전부)
SARAMIN_QUERY = {
    "dateType": "OPEN,CLOSE,ACCEPTANCE,APTITUDE",
    "expCd": "0,1,3",
    "indBcd": ",".join(str(n) for n in range(1, 11)),
    "locBcd": ",".join(str(n) for n in (
        101000, 102000, 104000, 105000, 106000, 107000, 108000, 109000, 110000,
        111000, 112000, 113000, 114000, 115000, 116000, 117000, 118000,
    )),
    "jobType": "1,2,4",
}
# 사람인 how_to_apply(쉼표로 여럿, 예: 'email,homepage') → jobs.jobs.apply_method(HOMEPAGE · SITE · EMAIL · OTHER).
# 앞의 것이 있으면 그것 — 홈페이지가 있으면 「회사 채용 사이트 열기」를 띄운다. profile 은 사람인 입사지원
APPLY_METHODS = (("homepage", "HOMEPAGE"), ("profile", "SITE"), ("email", "EMAIL"))


def apply_method(how_to_apply: str | None) -> str | None:
    if not how_to_apply:
        return None
    ways = {w.strip() for w in how_to_apply.split(",")}
    return next((method for way, method in APPLY_METHODS if way in ways), "OTHER")

JOBKOREA_PAGE = jobkorea.BASE_URL + "/starter/calendar/{month}"
JOBKOREA_KINDS = {"start": "OPEN", "end": "CLOSE"}


def months_from(today: date, count: int) -> list[str]:
    """이번 달부터 count 달 — 'YYYYMM'"""
    out, year, month = [], today.year, today.month
    for _ in range(count):
        out.append(f"{year}{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def _ymd(value: Any) -> str | None:
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if re.fullmatch(r"\d{8}", text) else None


def parse_saramin(payload: dict[str, Any], type_code: str) -> list[dict[str, Any]]:
    """달력 API 응답(날짜 → 공고 목록) 하나를 공고별 줄로. 같은 공고가 시작 · 마감 날에 두 번 나온다."""
    if payload.get("success") is not True:
        raise ValueError((payload.get("error") or {}).get("message") or "사람인 달력 응답 오류")
    rows: dict[str, dict[str, Any]] = {}
    for items in ((payload.get("data") or {}).get("list") or {}).values():
        for item in items or []:
            rec = str(item.get("rec_idx") or "")
            if not rec:
                continue
            row = rows.setdefault(rec, {
                "source": "SARAMIN_POC",
                "source_job_id": rec,
                "company_name": (item.get("company_nm") or "").strip(),
                "title": (item.get("title") or "").strip(),
                "logo_url": item.get("company_logo_url") or None,
                "how_to_apply": item.get("how_to_apply") or None,
                "apply_method": apply_method(item.get("how_to_apply")),
                "opening_date": _ymd(item.get("opening_date")),
                "closing_date": _ymd(item.get("closing_date")),
                "company_types": [type_code],
                "schedule_types": [],
            })
            kind = item.get("schedule_type")
            if kind and kind not in row["schedule_types"]:
                row["schedule_types"].append(kind)
    return list(rows.values())


def parse_jobkorea(html: str, month: str) -> list[dict[str, Any]]:
    """신입 공채 달력 한 달 — 날짜 칸마다 「시작」 · 「마감」 링크. 지난달 · 다음달 칸(disable)은 비어 있다."""
    soup = BeautifulSoup(html, "html.parser")
    rows: dict[str, dict[str, Any]] = {}
    for cell in soup.select("td"):
        if "disable" in (cell.get("class") or []):
            continue
        day = cell.select_one("strong.day")
        if not day or not day.get_text(strip=True).isdigit():
            continue
        when = f"{month[:4]}-{month[4:]}-{int(day.get_text(strip=True)):02d}"
        for link in cell.select("a.AgiLink[data-gno]"):
            gno = link["data-gno"]
            kinds = [JOBKOREA_KINDS[c] for c in (link.parent.get("class") or []) if c in JOBKOREA_KINDS]
            row = rows.setdefault(gno, {
                "source": "JOBKOREA_POC",
                "source_job_id": gno,
                "company_name": (link.get("title") or "").strip(),
                "opening_date": None,
                "closing_date": None,
                "schedule_types": [],
            })
            for kind in kinds:
                row["opening_date" if kind == "OPEN" else "closing_date"] = when
                if kind not in row["schedule_types"]:
                    row["schedule_types"].append(kind)
    return list(rows.values())


def merge_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """같은 공고가 여러 형태 · 여러 달에 나오면 하나로 — 형태와 일정 종류는 합치고, 날짜는 처음 본 값"""
    merged: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["source"], row["source_job_id"])
        if key not in merged:
            merged[key] = {**row, "company_types": list(row.get("company_types") or []),
                           "schedule_types": list(row.get("schedule_types") or [])}
            continue
        have = merged[key]
        for field in ("company_types", "schedule_types"):
            have[field] += [v for v in row.get(field) or [] if v not in have[field]]
        for field in ("opening_date", "closing_date", "logo_url", "how_to_apply", "apply_method"):
            if not have.get(field) and row.get(field):
                have[field] = row[field]
    return list(merged.values())


def company_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """회사별 — company_profiles 에 넣을 이름 · 기업 형태 · 로고(가장 많이 쓴 것)"""
    by_name: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = row["company_name"]
        if not name:
            continue
        item = by_name.setdefault(name, {"company_name": name, "company_types": [], "logos": Counter(), "postings": 0, "sources": []})
        item["postings"] += 1
        item["company_types"] += [t for t in row.get("company_types") or [] if t not in item["company_types"]]
        if row["source"] not in item["sources"]:
            item["sources"].append(row["source"])
        if row.get("logo_url"):
            item["logos"][row["logo_url"]] += 1
    out = []
    for item in by_name.values():
        logos = item.pop("logos")
        item["logo_url"] = logos.most_common(1)[0][0] if logos else None
        item["company_type"] = next((SARAMIN_TYPES[t] for t in SARAMIN_TYPES if t in item["company_types"]), None)
        out.append(item)
    return sorted(out, key=lambda r: (-r["postings"], r["company_name"]))


def fetch_saramin(session: requests.Session, months: list[str], *, timeout: int = 30,
                  min_delay: float = 3.0, max_delay: float = 5.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for month in months:
        referer = f"{SARAMIN_PAGE}/{month[:4]}/{int(month[4:])}"
        for code in SARAMIN_TYPES:
            response = session.get(
                SARAMIN_API,
                params={**SARAMIN_QUERY, "companyType": code, "month": month},
                headers={**http_session.xhr_headers(referer), "Origin": SARAMIN_PAGE, "Sec-Fetch-Site": "same-site"},
                timeout=timeout,
            )
            http_session.check_response(response)
            found = parse_saramin(response.json(), code)
            print(f"[사람인] {month} {SARAMIN_TYPES[code]} {len(found):,}건")
            rows += found
            http_session.polite_delay(min_delay, max_delay)
    return rows


def fetch_jobkorea(session: requests.Session, months: list[str], *, timeout: int = 30,
                   min_delay: float = 3.0, max_delay: float = 5.0) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for month in months:
        url = JOBKOREA_PAGE.format(month=month)
        response = session.get(url, headers=jobkorea.navigation_headers(), timeout=timeout)
        jobkorea.check_response(response)
        found = parse_jobkorea(response.text, month)
        print(f"[잡코리아] {month} {len(found):,}건")
        rows += found
        http_session.polite_delay(min_delay, max_delay)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="공채 달력 수집 — 로고 · 기업 형태 · 지원 방법(파일로만 저장)")
    parser.add_argument("--months", nargs="*", help="YYYYMM 목록. 생략하면 이번 달과 다음 달")
    parser.add_argument("--source", choices=["all", "saramin", "jobkorea"], default="all")
    parser.add_argument("--out", type=Path, default=None, help="저장 폴더(기본 artifacts/recruit_calendar/오늘)")
    args = parser.parse_args(argv)

    today = datetime.now(KST).date()
    months = args.months or months_from(today, 2)
    out = args.out or OUT_DIR / today.isoformat()
    out.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update(http_session.SESSION_HEADERS)
    saramin = fetch_saramin(session, months) if args.source in ("all", "saramin") else []
    jk = fetch_jobkorea(session, months) if args.source in ("all", "jobkorea") else []

    postings = merge_rows([*saramin, *jk])
    companies = company_summary(postings)
    write_jsonl(out / "postings.jsonl", postings)
    write_jsonl(out / "companies.jsonl", companies)
    summary = {
        "collected_at": datetime.now(KST).isoformat(timespec="seconds"),
        "months": months,
        "postings": dict(Counter(r["source"] for r in postings)),
        "companies": len(companies),
        "with_logo": sum(1 for c in companies if c["logo_url"]),
        "company_types": dict(Counter(c["company_type"] or "-" for c in companies)),
        "apply_methods": dict(Counter(r.get("apply_method") or "-" for r in postings if r["source"] == "SARAMIN_POC")),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[끝] {json.dumps(summary, ensure_ascii=False)}\n저장: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
