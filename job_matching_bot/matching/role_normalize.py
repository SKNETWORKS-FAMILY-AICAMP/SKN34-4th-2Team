"""직무 이름 표준화 — 같은 직무를 다르게 말해도 같은 공고를 찾게.

학생은 같은 직무를 여러 말로 묻는다. 「AI 엔지니어」 「AI엔지니어」 「인공지능 개발자」 「AI 개발자」는
같은 일인데, 검색은 말에 따라 결과가 갈렸다(2026-10-07, 신입 기준 직접 맞은 공고):

    AI 개발자 1,008 · AI 엔지니어 832 · 인공지능 개발자 480 · 인공지능 엔지니어 195 · AI엔지니어 5

까닭은 셋이다. 붙여 쓰면 그 글자 그대로만 찾았고, 「엔지니어」는 「개발자」를 찾지 않았고(반대는 찾는다),
직무 태그는 말한 그대로만 본다(사람인 태그에는 「AI개발자」가 많다).

규칙은 두 단계다. `skill_normalize`와 같은 모양이다.

1. 별칭 표로 접는다. 열쇠는 소문자 · 띄어쓰기 없앤 말. **확신이 있는 것만 넣는다** — 잘못 묶으면 엉뚱한
   공고가 섞인다. 처음에는 AI 계열만. 다른 직무는 결과를 보고 하나씩 늘린다.
2. 표에 없으면 영문과 한글이 붙은 곳을 띄운다. 「QA엔지니어」 → 「QA 엔지니어」, 「iOS개발자」 → 「iOS 개발자」.
   검색은 띄어 쓴 직무를 낱말 묶음으로 나눠 찾는다(`store_search.role_word_groups`).
"""

from __future__ import annotations

import re

# 표준 직무 ← 그 직무로 접을 말(소문자, 띄어쓰기 없음). 값은 검색이 가장 넓게 찾는 꼴로 둔다 —
# 「AI 개발자」는 (AI · 인공지능) + (개발 · developer · 엔지니어 · engineer · 프로그래머)로 찾고 태그
# 「AI개발자」에도 걸린다.
ROLE_ALIASES: dict[str, str] = {
    "ai개발자": "AI 개발자",
    "ai엔지니어": "AI 개발자",
    "ai개발": "AI 개발자",
    "aiengineer": "AI 개발자",
    "aideveloper": "AI 개발자",
    "인공지능개발자": "AI 개발자",
    "인공지능엔지니어": "AI 개발자",
    "인공지능개발": "AI 개발자",
}

_LATIN_THEN_HANGUL = re.compile(r"([A-Za-z0-9+#])([가-힣])")
_HANGUL_THEN_LATIN = re.compile(r"([가-힣])([A-Za-z])")


def canonical_role(name: str) -> str:
    """직무 이름을 검색에 쓸 꼴로. 모르는 말은 띄어쓰기만 맞추고 그대로 둔다."""
    text = " ".join(name.split())
    if not text:
        return text
    key = text.lower().replace(" ", "")
    if key in ROLE_ALIASES:
        return ROLE_ALIASES[key]
    return _HANGUL_THEN_LATIN.sub(r"\1 \2", _LATIN_THEN_HANGUL.sub(r"\1 \2", text))


def canonical_roles(names: list[str]) -> list[str]:
    """순서를 지키며 접고 겹친 것을 뺀다."""
    out: list[str] = []
    for name in names:
        role = canonical_role(name)
        if role and role not in out:
            out.append(role)
    return out
