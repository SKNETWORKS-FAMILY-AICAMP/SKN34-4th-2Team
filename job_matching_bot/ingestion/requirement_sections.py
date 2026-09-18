"""공고 본문을 제목 기준으로 잘라 자격요건·우대사항·주요업무 구간을 찾는다.

사람인 공고 3,100건을 훑어 보면 본문 제목이 꽤 일정하다. "📋 자격요건", "자격요건",
"우대사항", "주요업무/담당업무" 같은 짧은 줄이 구간을 나누고, "근무조건", "전형절차",
"복리후생", "접수기간" 같은 줄이 구간을 끝낸다. 이 규칙만으로도 필수와 우대를
가를 수 있어서, LLM을 못 쓰는 규칙 경로(`coach.skill_source._rule_based`)가
전부 UNKNOWN으로 두던 것을 개선한다.

한계: 제목이 없는 공고(이미지뿐이거나 자유 서술)는 구간을 못 찾는다. 그때는
`split_sections`가 빈 결과를 돌려주고 호출부가 예전 방식으로 내려간다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 제목 줄 앞뒤에 붙는 장식(이모지·기호·번호)을 지운 뒤 비교한다.
_DECOR = re.compile(r"[\[\]■□●○◆◇▶►▷※•·ㆍ:：\-–—_=~*#<>()【】「」『』|/\\\xa0]|[0-9]+[.)]|[\U0001F300-\U0001FAFF☀-➿️]")
_MAX_HEADING_CHARS = 14

SECTION_HEADINGS: dict[str, tuple[str, ...]] = {
    "required": (
        "자격요건", "자격 요건", "지원자격", "지원 자격", "필수요건", "필수 요건", "필수자격",
        "필수 자격", "필수사항", "필수 사항", "필수조건", "필수 조건", "요구사항", "요구 사항",
        "요구역량", "요구 역량", "필수역량", "필수 역량", "자격조건", "자격 조건", "지원요건",
        # 3,100건에서 자주 나온 변형. "자격 및 우대사항"처럼 합쳐 쓴 제목은 필수로 본다.
        "공통 자격요건", "공통 지원자격", "자격사항", "필수", "필수 경험 및 능력", "필요역량",
        "필요 역량", "핵심역량", "핵심 역량", "포지션 및 자격요건", "자격 및 우대사항",
        "기타 필수 사항", "기타 필수사항", "상세요건", "상세 요건", "필수 경험",
        # 스타트업식 제목. "자격요건"이란 말을 안 쓰고 말하듯 나눈 공고가 저장소에
        # 665건 있었고, 그중 IT 151건이 요건 0자로 잡혀 인덱스에 못 올랐다.
        "이런 분을 찾습니다", "이런 분을 찾아요", "이런 분과 함께", "어떤 사람을 찾나요",
        "어떤 사람을 찾나요?", "함께할 분", "이런 분이 필요해요",
    ),
    "preferred": (
        "우대사항", "우대 사항", "우대조건", "우대 조건", "우대요건", "우대 요건", "우대",
        "우대 자격", "우대자격", "우대 경험", "우대경험",
        "이런 분이면 더욱 좋아요", "이런 분이면 더 좋아요", "이런 분이면 좋아요",
        "이런 경험이 있으면", "이런 경험이 있다면",
    ),
    "duties": (
        "주요업무", "주요 업무", "담당업무", "담당 업무", "업무내용", "업무 내용", "수행업무",
        "수행 업무", "직무내용", "직무 내용", "모집분야", "모집 분야", "모집부문", "모집 부문",
        "업무분야", "업무 분야", "업무", "담당", "직무", "포지션",
        "이런 일을 해요", "무슨 일을 하나요", "무슨 일을 하나요?", "하시게 될 일",
        "담당하게 될 업무", "합류하시면",
    ),
}

# 이 제목이 나오면 위 구간이 끝난 것으로 본다.
STOP_HEADINGS: tuple[str, ...] = (
    "근무조건", "근무 조건", "전형절차", "전형 절차", "채용절차", "채용 절차", "복리후생",
    "복지", "복지 및 혜택", "접수기간", "접수 기간", "접수방법", "접수 방법", "제출서류",
    "제출 서류", "유의사항", "유의 사항", "근무지", "근무지역", "급여", "고용형태", "근무형태",
    "근무시간", "근무일수", "기타", "기타사항", "회사소개", "기업소개", "지원방법", "지원 방법",
    "채용 프로세스", "채용프로세스", "접수기간 및 방법", "전형방법", "전형 방법",
)


@dataclass
class RequirementSections:
    required: list[str] = field(default_factory=list)
    preferred: list[str] = field(default_factory=list)
    duties: list[str] = field(default_factory=list)

    @property
    def found(self) -> bool:
        return bool(self.required or self.preferred or self.duties)


def _normalize_heading(line: str) -> str:
    cleaned = _DECOR.sub("", line)
    return " ".join(cleaned.split()).strip()


def heading_kind(line: str) -> str | None:
    """줄이 구간 제목이면 종류('required'/'preferred'/'duties'/'stop'), 아니면 None."""
    text = _normalize_heading(line)
    if not text or len(text) > _MAX_HEADING_CHARS:
        return None
    compact = text.replace(" ", "")
    for kind, names in SECTION_HEADINGS.items():
        for name in names:
            if compact == name.replace(" ", ""):
                return kind
    for name in STOP_HEADINGS:
        if compact == name.replace(" ", ""):
            return "stop"
    # "자격요건 (공통)"처럼 괄호 설명이 붙은 변형
    for kind, names in SECTION_HEADINGS.items():
        for name in names:
            key = name.replace(" ", "")
            if len(key) >= 4 and compact.startswith(key):
                return kind
    return None


_INLINE_PREFIX = re.compile(r"^[\[\(【「■□●○◆◇▶►▷※•·\s]*(?P<name>[가-힣 ]{2,8})[\]\)】」\s:：\-–—]+(?P<rest>\S.*)$")


def split_inline_heading(line: str) -> tuple[str, str] | None:
    """"[자격요건] PostgreSQL 경험" 처럼 제목과 내용이 한 줄에 있으면 (종류, 내용)을 돌려준다."""
    match = _INLINE_PREFIX.match(line)
    if not match:
        return None
    kind = heading_kind(match.group("name"))
    if kind is None:
        return None
    return kind, match.group("rest").strip()


def split_sections(description: str) -> RequirementSections:
    """본문을 제목으로 잘라 구간별 줄 목록을 돌려준다. 같은 구간이 여러 번 나오면 합친다."""
    sections = RequirementSections()
    current: str | None = None
    for raw in description.splitlines():
        line = raw.strip()
        if not line:
            continue
        kind = heading_kind(line)
        if kind is None:
            inline = split_inline_heading(line)
            if inline is not None:
                kind, line = inline
                if kind == "stop":
                    current = None
                    continue
                current = kind
                getattr(sections, current).append(line)
                continue
        if kind == "stop":
            current = None
            continue
        if kind is not None:
            current = kind
            continue
        if current is None:
            continue
        getattr(sections, current).append(line)
    return sections
