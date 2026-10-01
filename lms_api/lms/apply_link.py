"""홈페이지 지원 공고의 회사 채용 사이트 주소 — 사람인 · 잡코리아 페이지에서 꺼낸다.

대기업 공채는 사람인 · 잡코리아 공고가 요약이고 「홈페이지 지원」으로 회사 채용 사이트에 간다. 직무 설명과
자기소개서 문항도 거기 있다. 학생이 공고 페이지를 거쳐 버튼을 한 번 더 누르지 않게 그 주소를 바로 준다.
수집기는 이 주소를 모으지 않고 넣을 칸도 없어 누를 때 찾는다.

- 잡코리아: 상세 페이지 데이터의 접수 방법 `"type":"HOMEPAGE","contents":["https://…"]`. 공고 페이지로 바로 간다
- 사람인: 「홈페이지 지원」 버튼이 여는 `/zf_user/track-apply-form/render-homepage?rec_idx=N` 이
  `document.location.replace("https://…")` 한 줄을 준다. 회사가 등록한 주소라 채용 사이트 첫 화면인 경우가 많다

그래서 같은 공고의 잡코리아 사본이 있으면 그쪽을 먼저 본다. 여는 곳은 사람인 · 잡코리아뿐이고(api 의 허용 목록),
꺼낸 회사 주소는 학생 브라우저가 연다 — 서버가 아무 주소나 대신 열지 않는다.
"""

from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urlparse

# 잡코리아 상세 페이지는 데이터를 문자열 속 JSON 으로 싣는다(따옴표가 \" 로 들어온다)
_JOBKOREA_HOMEPAGE = re.compile(
    r'\\?"type\\?"\s*:\s*\\?"HOMEPAGE\\?"\s*,\s*\\?"contents\\?"\s*:\s*\[\s*\\?"(https?://[^"\\\s]+)'
)
_SARAMIN_REDIRECT = re.compile(r"""location\.(?:replace\s*\(|href\s*=)\s*["'](https?://[^"'\s]+)["']""")
_ID = re.compile(r"^(SARAMIN|JOBKOREA)-(\d+)$")


def _safe(url: str | None) -> str | None:
    """학생 브라우저에 넘겨도 되는 주소인가 — http(s) 이고 호스트가 있어야 한다."""
    if not url:
        return None
    parsed = urlparse(url)
    return url if parsed.scheme in ("http", "https") and parsed.hostname else None


def homepage_from_jobkorea(html: str) -> str | None:
    found = _JOBKOREA_HOMEPAGE.search(html or "")
    return _safe(found.group(1)) if found else None


def homepage_from_saramin(html: str) -> str | None:
    found = _SARAMIN_REDIRECT.search(html or "")
    return _safe(found.group(1)) if found else None


def page_for(job_id: str) -> tuple[str, Callable[[str], str | None]] | None:
    """이 공고의 회사 주소가 적힌 사람인 · 잡코리아 페이지와 그 페이지를 읽는 함수. 모르는 번호면 None."""
    found = _ID.match(job_id or "")
    if found is None:
        return None
    site, number = found.groups()
    if site == "JOBKOREA":
        return f"https://www.jobkorea.co.kr/Recruit/GI_Read/{number}", homepage_from_jobkorea
    return f"https://www.saramin.co.kr/zf_user/track-apply-form/render-homepage?rec_idx={number}", homepage_from_saramin


def find_homepage(job_ids: list[str], fetch: Callable[[str], str | None]) -> tuple[str, str] | None:
    """(회사 채용 사이트 주소, 찾은 사본의 job_id). 잡코리아 사본을 먼저 본다. 못 찾으면 None."""
    for job_id in sorted(job_ids, key=lambda j: not j.startswith("JOBKOREA-")):
        target = page_for(job_id)
        if target is None:
            continue
        page_url, read = target
        html = fetch(page_url)
        url = read(html) if html else None
        if url:
            return url, job_id
    return None
