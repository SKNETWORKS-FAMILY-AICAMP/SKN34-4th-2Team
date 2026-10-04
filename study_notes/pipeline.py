"""수업 자료 → 정리 노트.

파일별 분석·품질 검토·수정을 나누면 LLM을 4~8번 호출해 너무 느리다.
자료 전체를 한 번에 넣고 노트를 한 번에 받는다. 파일이 많은 날만 묶음으로 나눠 만들고 합친다.

노트는 **공부하라고 요약 정리한 것**이고 문제는 넣지 않는다. 복습 문제는 매일 출제하는 세트
(practice/)가 맡는다 — 그쪽은 실제로 돌려 검증하고, 같은 기수 학생이 모두 같은 문제를 푼다.
예전 노트 끝에 붙던 「복습 문제 · 정답과 해설」은 검증 없이 LLM 이 쓴 것이라 뺐다.
"""

from __future__ import annotations

import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from study_notes.grounding import ground_report

LEARNER_LEVEL = "수업을 일부 놓친 초보자"
MAX_CHARS_PER_FILE = 8_000
MAX_TOTAL_CHARS = 28_000

# 노트의 소제목 순서 — 공부 노트(2026-10-04). 예전 노트는 파일 순서로 수업 자료를 해설해(「~를 확인합니다」) 공부하기 어려웠다.
# 34기 14과목 하루씩 견주어 보니 개념 중심이 30~50% 짧으면서 비교 · 실수 · 점검할 거리가 더 많았다(사용자 결정: 새 형식, 습니다체).
NOTE_HEADS = (
    "오늘 꼭 알아야 할 것", "개념별 정리", "비교로 기억하기", "자주 하는 실수",
    "말로 설명해 보기", "이전 수업과 연결", "이 내용이 있는 파일",
)
# 예전 형식 노트의 소제목 — 「이전 수업」으로 읽을 때 알아본다(다시 만들기 전 노트가 남아 있을 수 있다)
LEGACY_HEADS = (
    "오늘의 핵심 한 문장", "전체 수업 흐름", "파일별 학습 내용", "핵심 코드와 개념",
    "이전 학습과의 연결", "실행 체크리스트", "내가 직접 해볼 실습", "포트폴리오 회고 포인트",
)
NO_PREVIOUS = "없음"
NO_PREVIOUS_LINE = "이어서 볼 이전 수업 노트가 없습니다."
# 2026-09-29 gpt-6-luna 로 python_basic 06-18 을 만들어 보니 코드 블록 16개가 수업 코드를 옮기지 않고 비슷하게 새로 쓴
# 것이었다. 이전 학습과의 연결은 이전 수업을 모른 채 써서 첫 수업에도 「이전에 배웠다」고 지어냈다. 그래서 소제목마다 쓰는 법을 적는다.
# 코드 블록 수는 {code_limit} — 묶음으로 나눠 만들 때 묶음마다 다 채우면 하루 노트가 너무 길어진다
HEAD_GUIDE = {
    "오늘 꼭 알아야 할 것": "3~5줄 글머리표. 오늘 수업에서 가장 중요한 사실을 짧게. 자료를 설명하지 말고(「~를 확인합니다」 금지) 개념 자체를 말한다",
    "개념별 정리": (
        "파일 순서가 아니라 개념(주제)마다 `### 개념 이름`. 같은 개념이 여러 파일에 나오면 한 곳에 모은다. 각 개념은:\n"
        "- **뜻**: 한 문장\n- **언제 쓰나**: 한 문장\n"
        "- 수업 코드 한 블록(꼭 필요한 개념만) — 수업 자료 코드를 그대로 옮기고(이름 · 값 · 문자열을 바꾸거나 여러 셀을 섞지 않는다, "
        "긴 셀은 이어진 핵심 줄만), 블록 바로 위 줄에 출처 경로를 백틱으로\n"
        "- **결과**: 코드에서 알 수 있으면 실제 출력값(예: `13`, `[1, 2, [3, 4]]`). 「출력합니다」처럼 쓰지 않는다\n"
        "- **헷갈리기 쉬운 점**: 초보자가 실제로 틀리는 지점이 있을 때만 한 번. 없으면 줄을 쓰지 않는다\n"
        "코드 블록은 모두 합쳐 {code_limit}개 이하. 코드가 없는 개념(이론)은 뜻 · 언제 쓰나 · **핵심 정리**만"
    ),
    "비교로 기억하기": "수업에 짝지어 볼 만한 것이 있을 때만 표로(행 2~6개). 없으면 이 소제목 자체를 쓰지 않는다",
    "자주 하는 실수": "수업 자료에 나온 오류 예시 · 주의할 점만. `무엇` → 왜 틀리고 어떻게 고치는지 한 줄씩. 없으면 소제목을 쓰지 않는다",
    "말로 설명해 보기": "스스로 설명해 볼 질문 3~4개(답은 쓰지 않는다 — 위 본문에 있다). 「왜」 「차이」 「언제」를 묻는다",
    "이전 수업과 연결": (
        f"위 「이전 수업」에 적힌 내용과만 잇는다. 「이전 수업」이 '{NO_PREVIOUS}'이면 이 소제목 아래에 '{NO_PREVIOUS_LINE}' 한 줄만 쓴다"
    ),
    "이 내용이 있는 파일": "개념 → 파일 경로 색인. `- 형 변환: 02_data-type/exercise.ipynb` 처럼 한 줄씩",
}


def _heads_text(heads: tuple[str, ...]) -> str:
    return "\n".join(f"## {h}" + (f"\n({HEAD_GUIDE[h]})" if h in HEAD_GUIDE else "") for h in heads)


NOTE_SYSTEM = (
    "당신은 AI 부트캠프 수강생이 복습할 공부 노트를 만드는 교육 전문가입니다.\n"
    "수업 자료를 해설하지 말고, 학생이 다시 읽고 이해 · 기억할 수 있게 개념 중심으로 정리하세요.\n"
    "모든 문장은 「~습니다 · ~합니다」체로 씁니다(「~다」 「~해요」로 끝내지 않습니다). 문장은 짧게, 핵심어는 굵게.\n"
    "수업에 없던 기능을 새로 가르치지 마세요(개념을 풀어 설명하는 일반 지식은 괜찮습니다). 문제와 정답은 넣지 마세요.\n"
    f"첫 줄은 반드시 `## {NOTE_HEADS[0]}` 이고, 그 앞에 아무것도 쓰지 마세요. 소제목은 아래 목록의 것만 `##` 로 씁니다.\n"
    "git 커밋 해시, '변경 커밋', '수업 날짜/범위' 메타 박스, '확인할 수 없음'은 쓰지 마세요."
)

NOTE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", NOTE_SYSTEM),
    (
        "human",
        "수업 범위: {scope_label}\n"
        "학습자 수준: {learner_level}\n\n"
        "이전 수업(같은 과목, 날짜순 요약):\n{previous}\n\n"
        "수업 자료:\n{materials}\n\n"
        "아래 소제목 순서대로 한국어 Markdown으로 작성하세요. 괄호 안은 쓰는 법이니 옮겨 적지 마세요.\n\n"
        + _heads_text(NOTE_HEADS),
    ),
])

# ── 파일이 많은 날 ────────────────────────────────────────────────
# 한 번에 넣으면 전체 예산(MAX_TOTAL_CHARS)에 걸려 뒤 파일이 「분량 제한으로 생략」된다.
# 그래서 BATCH_FILES 개씩 묶어 부분 노트를 동시에 만들고, 마지막에 개념끼리 모아 하나로 다시 쓴다.
# 개념 중심이라 부분 노트를 이어 붙이면 같은 개념이 묶음마다 흩어진다 — 합치는 호출이 개념을 모으고, 코드 블록은 부분 노트의
# 것을 글자 그대로 옮긴다(대조 grounding 이 다시 본다). web_server 45개 · web_client 26개 날로 확인했다(2026-10-04).
BATCH_FILES = 8
BATCH_WORKERS = 4
MERGE_CODE_BLOCKS = 12

MERGE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        NOTE_SYSTEM + "\n하루 수업 파일이 많아 파일 묶음마다 부분 노트를 만들었습니다. 이것을 하나의 공부 노트로 합칩니다.\n"
        "같은 개념은 하나로 모으고, 수업 흐름 순서로 개념을 놓습니다. 코드 블록과 그 위 경로 줄은 부분 노트의 것을 글자 그대로 옮기고"
        " 새로 짜지 않습니다. 부분 노트에 없는 내용은 더하지 않습니다. 개념을 빠뜨리지 마세요.",
    ),
    (
        "human",
        "수업 범위: {scope_label}\n"
        "학습자 수준: {learner_level}\n\n"
        "이전 수업(같은 과목, 날짜순 요약):\n{previous}\n\n"
        "부분 노트:\n{parts}\n\n"
        "아래 소제목 순서대로 하나의 노트로 작성하세요. 괄호 안은 쓰는 법이니 옮겨 적지 마세요.\n\n"
        + _heads_text(NOTE_HEADS),
    ),
])


class Material(TypedDict):
    path: str
    commit: str
    content: str
    truncated: bool


def study_notes_model_name() -> str:
    return (
        os.getenv("STUDY_NOTES_MODEL", "").strip()
        or os.getenv("LMS_NODE_MODEL", "").strip()
        or "gpt-6-luna"
    )


# 노트는 품질이 먼저다. 2026-09-29 python_basic 06-18: medium 35초 · 출력 3.8천 토큰, high 71초 · 7.1천 토큰.
# high 가 빠진 수업 내용(keyword.kwlist, % 포맷 …)과 실행 주의(미완성 셀)를 더 짚었다. 노트 하나에 2원 남짓 더 든다.
# 노트는 18:30 출제 뒤 미리 만들어 두므로 학생이 기다리는 일은 드물다. 복습 문제 출제는 출력이 많아 기본(medium) 그대로.
NOTE_REASONING_EFFORT = "high"


def _is_reasoning_model(model: str) -> bool:
    """reasoning_effort 를 받는 모델 — gpt-4o-mini 같은 모델에 보내면 400 이다(STUDY_NOTES_MODEL 로 바꿔 끼울 때)"""
    return not model.startswith(("gpt-4", "gpt-3"))


@lru_cache
def _llm() -> ChatOpenAI:
    model = study_notes_model_name()
    effort = {"reasoning_effort": NOTE_REASONING_EFFORT} if _is_reasoning_model(model) else {}
    # 파일이 많은 날은 묶음을 동시에 부른다. 과목 요약이 날짜 몇 개를 함께 만들면 분당 토큰 한도(429)에 닿는다
    # (2026-09-29 web_client 39개 파일, 한도 20만). SDK 가 429 를 기다렸다 다시 보내게 넉넉히.
    # high 는 호출 하나에 1분이 넘는다 — 120초로는 파일이 많은 묶음이 끊길 수 있다
    return ChatOpenAI(model=model, max_retries=4, timeout=240, **effort)


def sanitize_student_markdown(markdown: str) -> str:
    """학생이 볼 노트에서 git 커밋·빈 메타 문구를 제거한다."""
    text = markdown.replace("\r\n", "\n")
    lines: list[str] = []
    skipping_meta_quote = False
    for raw in text.split("\n"):
        stripped = raw.strip()
        meta_line = bool(
            re.match(
                r"^(?:>\s*)?(\*\*)?(변경\s*커밋|커밋|commit|수업\s*날짜|수업\s*범위)\*?\*?\s*[:：]",
                stripped,
                re.IGNORECASE,
            )
        )
        if stripped.startswith(">") and (
            meta_line or "확인할 수 없음" in stripped or skipping_meta_quote
        ):
            skipping_meta_quote = True
            continue
        skipping_meta_quote = False
        if meta_line or "확인할 수 없음" in stripped:
            continue
        if re.fullmatch(r"#+(\s*날짜별)?\s*수업\s*정리\s*", stripped):
            continue
        lines.append(raw)
    cleaned = "\n".join(lines)
    # 소제목을 「**오늘의 핵심 한 문장**」처럼 굵은 줄로 쓰는 일이 있다. 화면이 소제목으로 보이게 ## 로 맞춘다
    cleaned = re.sub(r"^[ \t]*\*\*([^*\n]{1,60})\*\*[ \t]*:?[ \t]*$", r"## \1", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"`[0-9a-fA-F]{7,40}`", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def response_text(response) -> str:
    """LLM 응답 본문을 글자로. 조각 목록으로 오는 모델도 있다. 실습 문제 생성(practice/generate.py)도 쓴다."""
    content = response.content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def _shares(lengths: list[int], budget: int) -> list[int]:
    """파일마다 쓸 글자 수 — 짧은 파일은 다 넣고, 남은 예산을 긴 파일끼리 고르게 나눈다(파일당 MAX_CHARS_PER_FILE 까지)."""
    shares = [0] * len(lengths)
    left = budget
    order = sorted(range(len(lengths)), key=lambda i: lengths[i])
    for n, i in enumerate(order):
        fair = left // (len(order) - n)
        shares[i] = min(lengths[i], MAX_CHARS_PER_FILE, fair)
        left -= shares[i]
    return shares


def pack_materials(materials: list[Material]) -> str:
    """수업 자료를 파일 제목과 함께 한 덩어리로. 전체 글자 수 예산을 넘으면 파일마다 고르게 줄인다.

    예전엔 앞 파일부터 채워 뒤 파일은 「분량 제한으로 생략」됐다. 출제는 그 파일에도 문제를 배정해서 LLM 이 「내용이
    없는 파일로는 못 낸다」며 하루를 통째로 거절했다(2026-09-29 LLM파트 08-19, 파일 6개 중 2개 생략)."""
    shares = _shares([len(item["content"]) for item in materials], MAX_TOTAL_CHARS)
    chunks: list[str] = []
    for item, share in zip(materials, shares):
        body = item["content"][:share]
        note = " (일부만)" if item["truncated"] or len(item["content"]) > len(body) else ""
        chunks.append(f"### {item['path']}{note}\n{body}")
    return "\n\n".join(chunks)


def _split_report_and_review(raw: str) -> tuple[str, str]:
    text = sanitize_student_markdown(raw)
    marker = re.search(r"\n---\s*\n+(##\s*복습 문제)", text)
    if marker:
        return text[: marker.start()].strip(), text[marker.start(1):].strip()
    heading = re.search(r"^##\s*복습 문제\s*$", text, re.MULTILINE)
    if heading:
        return text[: heading.start()].strip(), text[heading.start():].strip()
    return text, ""


def generate_study_note(
    *,
    scope_label: str,
    commits: list[str],
    materials: list[Material],
    previous: list[DayNote] | None = None,
) -> tuple[str, str]:
    """(reportMarkdown, reviewMarkdown)을 반환한다. LLM은 1회만 호출한다 — 파일이 BATCH_FILES 개를 넘으면
    묶음 수 + 1회(_note_in_batches).

    reviewMarkdown 은 늘 빈 글자다. 모델이 그래도 문제를 붙이면 잘라 버린다 — 자리는 예전 노트와
    같은 모양으로 돌려주려고 남겨 둔다.

    만든 노트는 모델이 본 자료(`pack_materials`)와 대조한다(`grounding.ground_report`, LLM 없음). 수업 파일에
    없는 코드 블록에는 표시를 달고, 본문에 든 이름 중 자료에 없는 것은 노트 끝에 모아 알린다.

    previous — 같은 과목의 이전 날짜 노트(LMS 가 골라 준다). 「이전 학습과의 연결」을 이것과만 잇게 한다.
    """
    if not materials:
        raise ValueError("분석할 수업 자료가 없습니다.")
    before = pack_previous(previous or [])
    if len(materials) > BATCH_FILES:
        report, packed = _note_in_batches(scope_label, materials, before)
    else:
        packed = pack_materials(materials)
        report = _note(scope_label, packed, before)
    report, stats = ground_report(report, packed)
    print(f"[노트 점검] {scope_label}: {stats.summary()}")
    return report, ""


# 이전 수업 — 최근 날짜 몇 개의 요점만. 노트 전체를 넣으면 자료 예산만큼 길어진다
PREVIOUS_HEADS = (NOTE_HEADS[0], "오늘의 핵심 한 문장", "전체 수업 흐름")
MAX_PREVIOUS_DAYS = 3
MAX_PREVIOUS_CHARS = 800


def pack_previous(previous: list[DayNote]) -> str:
    """이전 날짜 노트 → 「이전 수업」 글. 없으면 NO_PREVIOUS"""
    chunks = []
    for day in sorted(previous, key=lambda d: d["date"])[-MAX_PREVIOUS_DAYS:]:
        sections = _sections(day["report"])
        # 새 노트는 「오늘 꼭 알아야 할 것」, 다시 만들기 전 예전 노트는 「핵심 한 문장 · 흐름」
        text = "\n".join(sections[h] for h in PREVIOUS_HEADS if sections.get(h))
        if text:
            chunks.append(f"### {day['date']}\n{text[:MAX_PREVIOUS_CHARS]}")
    return "\n\n".join(chunks) or NO_PREVIOUS


# 핵심 코드 블록 수 — 노트 하나. 묶음으로 나눠 만들 때는 묶음 수로 나눈다(_note_in_batches)
CODE_BLOCKS_PER_NOTE = 10
_OTHER_H2 = re.compile(r"^##[ \t]+(?!(?:" + "|".join(map(re.escape, NOTE_HEADS)) + r")[ \t]*$)(.+)$", re.MULTILINE)
_PATH_LABEL = re.compile(r"^(#*[ \t]*)파일 경로[ \t]*:[ \t]*", re.MULTILINE)


def tidy_headings(report: str) -> str:
    """정해진 소제목(NOTE_HEADS)이 아닌 「## 」는 개념 소제목(###)으로 — 모델이 개념이나 코드 위 파일 경로를 ## 로 쓰면
    노트 뼈대가 깨진다. 「파일 경로: 」 머리말도 떼고, 첫 소제목 앞에 붙인 머리글도 뗀다."""
    report = _PATH_LABEL.sub(r"\1", _OTHER_H2.sub(r"### \1", report))
    first = report.find(f"## {NOTE_HEADS[0]}")
    return report[first:] if first > 0 else report


def _note(scope_label: str, packed: str, previous: str = NO_PREVIOUS, code_limit: int = CODE_BLOCKS_PER_NOTE) -> str:
    response = (NOTE_PROMPT | _llm()).invoke({
        "scope_label": scope_label,
        "learner_level": LEARNER_LEVEL,
        "previous": previous,
        "materials": packed,
        "code_limit": code_limit,
    })
    report, _review = _split_report_and_review(response_text(response))
    return tidy_headings(report)


def _batches(materials: list[Material]) -> list[list[Material]]:
    """경로순(같은 폴더끼리)으로 BATCH_FILES 개 이하씩, 묶음 크기는 고르게"""
    ordered = sorted(materials, key=lambda m: m["path"])
    count = -(-len(ordered) // BATCH_FILES)
    size = -(-len(ordered) // count)
    return [ordered[i:i + size] for i in range(0, len(ordered), size)]


def _sections(markdown: str) -> dict[str, str]:
    """「## 소제목」 → 본문. 정해진 소제목(새 · 예전 형식)이 아닌 것은 앞 소제목 본문에 붙여 둔다."""
    out: dict[str, str] = {}
    current = ""
    for line in markdown.split("\n"):
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match and (match.group(1) in NOTE_HEADS or match.group(1) in LEGACY_HEADS):
            current = match.group(1)
            out.setdefault(current, "")
            continue
        if current:
            out[current] += line + "\n"
    return {k: v.strip() for k, v in out.items()}


def _note_in_batches(scope_label: str, materials: list[Material], previous: str = NO_PREVIOUS) -> tuple[str, str]:
    """(노트, 모델이 본 자료 전체) — 묶음마다 부분 노트를 동시에 만들고, 개념끼리 모아 하나로 다시 쓴다."""
    batches = _batches(materials)
    packs = [pack_materials(b) for b in batches]
    code_limit = max(4, -(-MERGE_CODE_BLOCKS // len(packs)))
    with ThreadPoolExecutor(max_workers=min(BATCH_WORKERS, len(packs))) as pool:
        parts = list(pool.map(
            lambda i: _note(f"{scope_label} — 파일 묶음 {i + 1}/{len(packs)}", packs[i], previous, code_limit),
            range(len(packs)),
        ))
    part_sections = [_sections(p) for p in parts]
    response = (MERGE_PROMPT | _llm()).invoke({
        "scope_label": scope_label,
        "learner_level": LEARNER_LEVEL,
        "previous": previous,
        "parts": "\n\n".join(f"# 부분 노트 {i + 1}\n{p}" for i, p in enumerate(parts)),
        "code_limit": MERGE_CODE_BLOCKS,
    })
    merged = _sections(tidy_headings(sanitize_student_markdown(response_text(response))))
    blocks = []
    for head in NOTE_HEADS:
        # 합친 답에 빠진 소제목은 부분 노트를 이어 채운다(같은 글은 한 번 — 「이전 수업 노트가 없습니다」 등).
        # 개념 정리가 통째로 빠지면 부분 노트의 개념을 이어 붙인다 — 개념이 흩어져도 빠지는 것보다 낫다
        body = merged.get(head) or "\n\n".join(dict.fromkeys(s[head] for s in part_sections if s.get(head)))
        if body:
            blocks.append(f"## {head}\n{body}")
    return "\n\n".join(blocks), "\n\n".join(packs)


# ── 과목 전체 요약 ───────────────────────────────────────────────
# 과목의 수업 자료를 통째로 넣으면 파일이 수십 개라 한 번에 들어가지 않는다. 그래서 날짜별 노트(이미 요약한 것)를
# 모아 한 번 더 정리한다. 날짜 노트 하나가 1~3천 자라 한 과목(보통 2~8일)이 한 번에 들어간다.

MAX_CHARS_PER_DAY = 6_000
MAX_SUBJECT_CHARS = 48_000

SUBJECT_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 AI 부트캠프 한 과목의 수업을 한 장으로 정리하는 교육 전문가입니다.\n"
        "아래는 수업 날짜마다 만든 학습 노트입니다. 노트에 없는 내용은 지어내지 마세요.\n"
        "문제나 퀴즈는 넣지 마세요. 제목(#)으로 시작하지 마세요.",
    ),
    (
        "human",
        "과목: {subject}\n"
        "학습자 수준: {learner_level}\n\n"
        "날짜별 노트:\n{days}\n\n"
        "아래 제목 순서대로 한국어 Markdown으로 작성하세요.\n\n"
        "## 과목 한눈에 보기\n"
        "(이 과목에서 배운 것을 세 문장 안으로)\n"
        "## 날짜별 흐름\n"
        "(날짜마다 한 줄 — 'MM/DD: 핵심')\n"
        "## 핵심 개념 정리\n"
        "## 꼭 기억할 코드 패턴\n"
        "## 헷갈리기 쉬운 것\n"
        "## 이어서 공부할 것",
    ),
])


class DayNote(TypedDict):
    date: str
    report: str


def pack_days(days: list[DayNote]) -> str:
    """날짜 노트를 날짜순으로 한 덩어리로. 전체 예산을 넘으면 날짜마다 고르게 줄인다."""
    ordered = sorted(days, key=lambda d: d["date"])
    per_day = min(MAX_CHARS_PER_DAY, MAX_SUBJECT_CHARS // max(1, len(ordered)))
    chunks = []
    for day in ordered:
        body = day["report"].strip()
        cut = " (일부만)" if len(body) > per_day else ""
        chunks.append(f"### {day['date']}{cut}\n{body[:per_day]}")
    return "\n\n".join(chunks)


def generate_subject_summary(*, subject: str, days: list[DayNote]) -> str:
    """과목 전체 요약(Markdown). LLM 은 1회."""
    days = [d for d in days if d.get("report", "").strip()]
    if not days:
        raise ValueError("요약할 날짜 노트가 없습니다.")
    response = (SUBJECT_PROMPT | _llm()).invoke({
        "subject": subject,
        "learner_level": LEARNER_LEVEL,
        "days": pack_days(days),
    })
    report, _review = _split_report_and_review(response_text(response))
    return report
