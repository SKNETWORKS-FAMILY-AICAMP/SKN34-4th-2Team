"""사람인 요청을 실제 브라우저 세션처럼 보내기 위한 공통 부품.

목록·상세 크롤러가 같이 쓴다. 목표는 "사람이 Chrome으로 사람인을 보는 것과
같은 요청"이지, 차단을 피하는 것이 아니다. 그래서:

- UA는 **하나로 고정**한다(돌리지 않는다). 프록시도 쓰지 않는다.
- 사람이 하는 순서를 따른다: 목록 페이지를 먼저 열어 쿠키를 받고, 그 뒤에
  목록 ajax나 상세 페이지로 간다. 세션 하나가 이 흐름을 그대로 유지한다.
- 문서 요청과 XHR 요청의 헤더를 구분한다. Chrome은 둘을 다르게 보낸다.
- 429나 차단 문구가 오면 **즉시 멈춘다.** 간격을 줄이거나 재시도해서 뚫지 않는다.

Chrome 131 / Windows 기준이며, `CLIENT_HINTS`의 버전은 UA와 맞춰 둔다.
"""

from __future__ import annotations

import random
import time

import requests

BASE_URL = "https://www.saramin.co.kr"
LIST_PAGE_URL = f"{BASE_URL}/zf_user/jobs/list/job-category"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Chrome이 모든 요청에 붙이는 클라이언트 힌트. UA의 버전과 같아야 한다.
CLIENT_HINTS = {
    "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
}

# 세션 공통 헤더. requests가 기본으로 넣는 Accept-Encoding(gzip, deflate)과
# Connection(keep-alive)은 그대로 둔다.
SESSION_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    **CLIENT_HINTS,
}

BLOCK_MARKERS = ("보안정책에 의하여", "일시적으로 중지", "자동입력 방지", "비정상적인 접근")


class BlockedByTargetSiteError(RuntimeError):
    """차단/캡차/속도 제한이 감지되어 중단해야 할 때."""


def navigation_headers(referer: str | None = None) -> dict[str, str]:
    """주소창 이동·링크 클릭으로 문서를 여는 요청의 헤더."""
    headers = {
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7"
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


def xhr_headers(referer: str) -> dict[str, str]:
    """페이지 안의 스크립트가 보내는 XHR 요청의 헤더. 목록 ajax가 이것이다."""
    return {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Referer": referer,
    }


def check_response(response: requests.Response) -> None:
    """차단·속도 제한이면 예외. 그 밖의 HTTP 오류는 raise_for_status에 맡긴다."""
    if response.status_code in (403, 429):
        raise BlockedByTargetSiteError(
            f"사람인이 요청을 거부했습니다(HTTP {response.status_code}). 자동화를 중단합니다. "
            "우회하지 말고 잠시 후 사람이 직접 확인하세요."
        )
    response.raise_for_status()
    if any(marker in response.text for marker in BLOCK_MARKERS):
        raise BlockedByTargetSiteError(
            "사람인이 이 요청을 차단했습니다. 자동화를 중단합니다. 우회하지 마세요."
        )


def polite_delay(min_s: float, max_s: float) -> None:
    time.sleep(random.uniform(min_s, max_s))


def new_session(
    *, warm_up: bool = True, timeout: int = 30, min_delay: float = 3.0, max_delay: float = 5.0
) -> requests.Session:
    """브라우저처럼 동작하는 세션.

    `warm_up=True`면 사람이 하듯 목록 페이지를 먼저 한 번 연다. 서버가 주는
    쿠키가 세션에 남아 이후 요청이 같은 방문자의 흐름으로 이어진다.
    """
    session = requests.Session()
    session.headers.update(SESSION_HEADERS)
    if warm_up:
        response = session.get(LIST_PAGE_URL, headers=navigation_headers(), timeout=timeout)
        check_response(response)
        # 사람도 페이지가 뜬 뒤에 다음 행동을 한다.
        polite_delay(min_delay, max_delay)
    return session
