"""목록 화면의 회사명 칸에서 회사명만 남긴다.

목록 카드의 회사명은 보통 링크 글자로 깔끔하게 온다. 링크가 없는 카드는 칸 전체 글자를
읽는데, 그러면 버튼과 뱃지가 딸려 온다.

    현대카드(주) 현대자동차그룹 대기업
    (주)라이드플럭스 쏘카그룹
    NEZOT주식회사 관심기업 등록 외국계

2026-09-13 밤 목록 21만 6천 줄 중 2,203줄이 이랬고, 이 이름이 챗봇 카드와 추천 카드에
그대로 나갔다. **뒤에서부터만** 버튼 글자와 뱃지를 떼어 낸다. 이름 앞이나 가운데의 같은 말은
회사명의 일부일 수 있다("관심기업 등록 연구소").

**"~그룹"은 조심해서 뗀다.** 그룹 뱃지("쏘카그룹")와 진짜 회사명("주식회사 와이앤컨설팅그룹")이
같은 모양이다. 떼고 나서 법인 표기("주식회사", "(주)")만 남으면 회사명 자체였던 것이라 되돌린다.

두 갈래에서 같은 문제를 따로 고쳤다가 합쳤다. 첨삭 브랜치는 끝의 버튼 글자만 떼고(뒤에서만 뗀다는
원칙과 `object`를 받는 겉모습이 그쪽 것이다), 추천 브랜치는 그룹·기업형태 뱃지와 HTML 기호까지 뗐다.
"""

from __future__ import annotations

import html
import re

# 이름 끝에 붙어 오는 버튼 글자.
_TRAILING_UI_NOISE = re.compile(
    r"(?:\s*(?:관심기업\s*등록|관심기업|스크랩|즉시지원|지원하기))+\s*$"
)

# 기업형태·상장 뱃지. 이름 **끝**에 붙은 것만 뗀다.
BADGES = frozenset({
    "대기업", "중견기업", "중소기업", "외국계", "공사·공기업", "공기업",
    "코스피", "코스닥", "코넥스", "유가증권", "헤드헌팅", "파견·도급·대행",
    "벤처기업", "스타트업",
})

# 이것만 남으면 회사명이 아니다.
LEGAL_FORMS = frozenset({
    "주식회사", "(주)", "㈜", "(유)", "유한회사", "(자)", "합자회사", "(합)", "합명회사",
    "(재)", "재단법인", "(사)", "사단법인", "(의)", "의료법인",
})


def clean_listing_text(text: object) -> str:
    """목록에서 온 글자(제목·회사명)의 HTML 기호를 푼다.

    사람인이 제목 속성에 `&`를 한 번 더 감싸 넣어서, HTML을 읽고 나서도 `안드로이드&amp;ios`로
    남는다. 게시 중 공고 1,840건, 목록 2,892건의 제목이 이랬고 챗봇 카드에 그대로 나갔다.
    두 번 감싼 것도 있어 바뀌지 않을 때까지 푼다.

    띄어쓰기는 건드리지 않는다. 제목이 바뀌면 인덱스 지문이 바뀌어 다시 올리게 되는데,
    기호가 없는 제목까지 바꿀 이유가 없다.
    """
    text = str(text or "")
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return text.strip()


def clean_company_name(value: object) -> str:
    """회사명 끝의 버튼 글자·뱃지를 뗀다. 이미 깨끗하면 그대로 돌려준다."""
    tokens = clean_listing_text(value).split()
    while len(tokens) > 1:
        joined = " ".join(tokens)
        stripped = _TRAILING_UI_NOISE.sub("", joined).strip()
        if stripped and stripped != joined:
            tokens = stripped.split()
            continue
        last = tokens[-1]
        if last in BADGES:
            tokens.pop()
            continue
        if last.endswith("그룹") and len(last) > len("그룹"):
            rest = tokens[:-1]
            if all(token in LEGAL_FORMS for token in rest):
                break
            tokens = rest
            continue
        break
    return " ".join(tokens)
