"""노트가 수업 자료에 없는 것을 지어내지 않았는지 — 만든 직후 한 번 본다. LLM 을 부르지 않는다.

두 가지를 본다.

1. **코드 블록**: 줄마다 수업 자료에 있는지 공백을 빼고 견준다. 노트는 한 줄 호출을 여러 줄로
   나누거나 들여쓰기를 바꾸므로 글자 그대로는 절반 가까이 어긋난다(2026-09-28 기존 노트 34~52%).
   공백을 빼면 모양만 바꾼 코드는 맞는다. 그래도 절반 넘게 없으면 「수업 파일에 그대로 있는 코드가
   아니다」라고 블록 아래에 적는다. 지우지는 않는다 — 설명하려고 줄여 쓴 코드도 공부에 쓸모가 있다.
   설명용 구조도(「입력: 1 × 28 × 28」)나 주석은 코드로 세지 않는다.
2. **본문의 이름**: 본문에 `이름` 으로 적은 함수 · 인자 · 모델 · 파일 이름이 자료에 있는지 본다.
   없는 것은 지우지 않고 노트 끝에 모아 알린다.

처음에는 문장 점검을 LLM 에게 맡겼다(노트와 자료를 주고 근거 없는 사실을 고르게). 실제 노트 두 개로
돌려 보니 고른 14개가 **모두 자료에 있는 것**이었다(`padding='same'`, `gpt-5.6-luna` …). 믿을 수
없어 걷어 내고, 확인할 수 있는 이름 대조로 바꿨다.

화면(React)의 「연습장에서 열기」도 같은 규칙(공백 빼고 견주기 · 코드처럼 생긴 줄만)으로 파일을 찾는다
(lms_react/src/features/study/lessonCode.ts).
"""

from __future__ import annotations

import builtins
import re
from dataclasses import dataclass, field

FENCE = re.compile(r"(```[^\n]*\n)(.*?)(```)", re.S)
INLINE = re.compile(r"`([^`\n]+)`")
CODE_LIKE = re.compile(
    r"[=(){}\[\]]|^(import|from|def|class|return|for|if|elif|else|while|with|try|except|print|lambda|yield|async|await)\b"
)
# 이름처럼 생긴 것 — 점 · 밑줄 · 괄호 · 대문자가 섞인 식별자, 파일 이름. `0~1` · `(N, H, W)` 같은 값 표기는 아니다
NAME_LIKE = re.compile(r"^[A-Za-z_][\w.]*(\(\))?$|^[\w./-]+\.(py|ipynb|pt|csv|json|jpg|png|md|txt|h5)$")
NOT_FROM_LESSON = "> 수업 파일에 그대로 있는 코드가 아니에요 — 설명하려고 줄이거나 새로 쓴 코드예요."
MISSING_HEAD = "> 수업 파일에서 찾지 못한 이름:"
# 파이썬 기본 이름(print · len · NameError …) — 수업 자료에 없어도 설명하는 것이 당연하다
BUILTIN_NAMES = frozenset(dir(builtins))


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def significant_lines(code: str) -> list[str]:
    """견줄 만한 줄 — 주석 · 흐름도 · 설명 글 · 너무 짧은 줄은 뺀다."""
    out = []
    for raw in code.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or re.match(r"^[→↓>\-*]", line):
            continue
        if len(compact(line)) < 6 or not CODE_LIKE.search(line):
            continue
        out.append(line)
    return out


@dataclass
class GroundingReport:
    code_blocks: int = 0
    marked_blocks: int = 0
    names: int = 0
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"코드 블록 {self.code_blocks}개 중 수업 파일에 없는 것 {self.marked_blocks}개 · "
                f"본문 이름 {self.names}개 중 못 찾은 것 {len(self.missing)}개")


def mark_ungrounded_code(report: str, material_text: str, stats: GroundingReport) -> str:
    """수업 자료에 절반 넘게 없는 코드 블록 아래에 표시를 단다."""
    haystack = compact(material_text)

    def check(match: re.Match[str]) -> str:
        lines = significant_lines(match.group(2))
        if not lines:
            return match.group(0)
        stats.code_blocks += 1
        hits = sum(1 for line in lines if compact(line) in haystack)
        if hits * 2 >= len(lines):
            return match.group(0)
        stats.marked_blocks += 1
        return f"{match.group(0)}\n{NOT_FROM_LESSON}"

    return FENCE.sub(check, report)


def missing_names(report: str, material_text: str, stats: GroundingReport) -> list[str]:
    """본문(코드 블록 밖)에 `이름` 으로 적었는데 자료에 없는 이름. 적은 차례대로, 한 번씩."""
    haystack = compact(material_text).lower()
    prose = FENCE.sub("", report)
    seen: list[str] = []
    for raw in INLINE.findall(prose):
        name = raw.strip()
        if not NAME_LIKE.match(name) or len(name) < 3 or name in seen or name.removesuffix("()") in BUILTIN_NAMES:
            continue
        seen.append(name)
    stats.names = len(seen)
    # 괄호를 뗀 이름으로 찾는다 — 노트는 `relu()` 로, 자료는 F.relu(x) 로 적는다
    missing = [n for n in seen if compact(n.removesuffix("()")).lower() not in haystack]
    stats.missing = missing
    return missing


def ground_report(report: str, material_text: str) -> tuple[str, GroundingReport]:
    """노트를 수업 자료에 맞춰 본다. 고쳐 쓴 노트와 무엇을 봤는지를 돌려준다."""
    stats = GroundingReport()
    grounded = mark_ungrounded_code(report, material_text, stats)
    missing = missing_names(report, material_text, stats)
    if missing:
        names = ", ".join(f"`{n}`" for n in missing[:12])
        grounded = f"{grounded.rstrip()}\n\n{MISSING_HEAD} {names} — 노트가 설명하려고 든 이름이에요. 수업 코드와 다를 수 있어요."
    return grounded, stats
