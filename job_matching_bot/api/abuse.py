"""모델을 부르기 전에 막는 말.

가드레일이 모델 판단에 기대면 확실하지 않다. 여기 걸리는 말은 **호출 없이** 막힌다.
얻는 것이 둘이다. 욕 한 마디에 돈과 1.5초를 쓰지 않는 것, 그리고 적어 둔 말만큼은
그날 모델이 어떻게 보든 상관없이 막힌다는 것.

한계도 분명하다. **적어 둔 말만 잡는다.** "친구 생일선물 뭐 사지?"는 어떤 목록에도
없다. 채용과 상관없는 말을 미리 다 적어 둘 수는 없으므로 나머지는 여전히 모델이
가르고(`off_topic`) 서비스가 정해진 말로 답한다. 이 파일은 그 앞에 놓인 한 겹이다.

**말 한 마디가 통째로 욕일 때만 막는다.** 문장 속에 들어 있는 것은 막지 않는다.
"미친 듯이 준비했는데 안 되네"는 하소연이지 시비가 아니다. 부분 일치로 막으면 진짜
취업 이야기를 하는 사람이 걸린다. 잘못 막는 쪽이 놓치는 쪽보다 나쁘다 — 놓친 말은
모델이 한 번 더 거르지만, 잘못 막힌 사람은 다시 물을 길이 없다.
"""

from __future__ import annotations

import re

# 통째로 들어오면 막을 말. 소문자로, 공백 없이 적는다.
ABUSE_WORDS = frozenset(
    {
        "바보",
        "멍청이",
        "멍청아",
        "등신",
        "머저리",
        "또라이",
        "호구",
        "병신",
        "븅신",
        "미친",
        "미친놈",
        "미친년",
        "개새끼",
        "새끼",
        "씨발",
        "시발",
        "씨발놈",
        "지랄",
        "개소리",
        "꺼져",
        "닥쳐",
        "엿먹어",
        "죽어",
        "짜증나",
        "fuck",
        "fuckyou",
        "shit",
        "stupid",
        "idiot",
        "asshole",
    }
)

# "바보야", "멍청아", "호구냐" 처럼 붙는 말. 떼고 다시 본다.
_SUFFIXES = ("야", "아", "냐", "네", "다", "임", "ㅋ", "ㅎ")

# 공백과 문장부호를 지운다. 한글·영문·숫자는 남는다.
_NOISE = re.compile(r"[\s\W_]+", re.UNICODE)
# 끝에 붙은 웃음과 울음. "바보ㅋㅋㅋ"도 같은 말이다.
_TRAILING = re.compile(r"[ㅋㅎㅠㅜ~]+$")


def _normalize(message: str) -> str:
    return _TRAILING.sub("", _NOISE.sub("", message).lower())


def _is_word(core: str) -> bool:
    """한 낱말인가. 같은 말을 반복한 것("바보바보")도 한 낱말로 본다."""
    if core in ABUSE_WORDS:
        return True
    return any(
        core == word * times
        for word in ABUSE_WORDS
        for times in range(2, len(core) // len(word) + 1)
        if len(core) >= len(word) * 2
    )


def is_abuse(message: str) -> bool:
    """이 말이 통째로 욕이면 True. 모델을 부르기 전에 본다."""
    core = _normalize(message)
    if not core:
        return False
    if _is_word(core):
        return True
    # "바보야"처럼 한 글자 붙은 것까지만 떼 본다. 더 떼면 문장을 낱말로 오인한다.
    for suffix in _SUFFIXES:
        if core.endswith(suffix) and _is_word(core[: -len(suffix)]):
            return True
    return False
