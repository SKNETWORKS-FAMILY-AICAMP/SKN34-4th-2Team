"""추천 목록에서 같은 적합도끼리 세울 때 쓰는 기업 등급.

적합도가 먼저다. 등급은 「높음」끼리 · 「보통」끼리 안에서만 순서를 가른다 — 맞지 않는
대기업 공고가 맞는 중소기업 공고 위에 서지 않는다.

근거는 기업형태 칸(`company_type`) 하나다. 연봉 · 직원 수 · 평점 칸은 저장소에 없다.
- 사람인: 상세 기업정보의 「기업형태」. "코스피, 대기업, 1000대기업, 외부감사법인" 처럼 여럿이 쉼표로 붙는다.
- 잡코리아: 목록의 기업형태 거르기 이름. 거르기에 안 걸린 공고는 "미기재"(대부분 중소기업).
"1000대기업" 은 매출 1000대라 중견 · 중소에도 붙는다 — 등급에 쓰지 않는다.
"""

from __future__ import annotations

import re

# (등급, 정규식). 위에서부터 처음 맞는 것. 숫자가 작을수록 앞에 선다.
_TIERS: tuple[tuple[int, re.Pattern[str]], ...] = (
    (0, re.compile(r"(?:^|,)\s*대기업\s*(?:,|$)")),
    (0, re.compile(r"공사/공|공공기관")),
    (1, re.compile(r"외국인 투|외국 법인|외국계")),
    (1, re.compile(r"(?:^|,)\s*중견기업\s*(?:,|$)")),
    (1, re.compile(r"코스피|코스닥")),
)
OTHER = 2


def company_tier(company_type: str | None) -> int:
    """0 대기업 · 공기업 / 1 외국계 · 중견 · 상장 / 2 그 밖(중소 · 미기재)."""
    text = company_type or ""
    for tier, pattern in _TIERS:
        if pattern.search(text):
            return tier
    return OTHER
