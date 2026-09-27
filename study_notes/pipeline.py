"""수업 자료 → 정리 노트.

파일별 분석·품질 검토·수정을 나누면 LLM을 4~8번 호출해 너무 느리다.
자료 전체를 한 번에 넣고 노트를 한 번에 받는다.

노트는 **공부하라고 요약 정리한 것**이고 문제는 넣지 않는다. 복습 문제는 매일 출제하는 세트
(practice/)가 맡는다 — 그쪽은 실제로 돌려 검증하고, 같은 기수 학생이 모두 같은 문제를 푼다.
예전 노트 끝에 붙던 「복습 문제 · 정답과 해설」은 검증 없이 LLM 이 쓴 것이라 뺐다.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

LEARNER_LEVEL = "수업을 일부 놓친 초보자"
MAX_CHARS_PER_FILE = 8_000
MAX_TOTAL_CHARS = 28_000

NOTE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 AI 부트캠프 수업자료를 학습 노트로 정리하는 교육 전문가입니다.\n"
        "학습자가 코드를 다시 실행할 수 있게 구체적으로 쓰되, 자료에 없는 내용은 지어내지 마세요.\n"
        "git 커밋 해시, '변경 커밋', '수업 날짜/범위' 메타 박스, '확인할 수 없음'은 쓰지 마세요.\n"
        "제목(#)으로 시작하지 마세요.",
    ),
    (
        "human",
        "수업 범위: {scope_label}\n"
        "학습자 수준: {learner_level}\n\n"
        "수업 자료:\n{materials}\n\n"
        "아래 제목 순서대로 한국어 Markdown으로 작성하세요. 문제나 퀴즈는 넣지 마세요.\n\n"
        "## 오늘의 핵심 한 문장\n"
        "## 전체 수업 흐름\n"
        "## 파일별 학습 내용\n"
        "## 핵심 코드와 개념\n"
        "## 이전 학습과의 연결\n"
        "## 실행 체크리스트\n"
        "## 내가 직접 해볼 실습\n"
        "## 포트폴리오 회고 포인트",
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
        or "gpt-5.6-luna"
    )


@lru_cache
def _llm() -> ChatOpenAI:
    return ChatOpenAI(model=study_notes_model_name(), max_retries=1, timeout=120)


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


def pack_materials(materials: list[Material]) -> str:
    """수업 자료를 파일 제목과 함께 한 덩어리로. 전체 글자 수 예산을 넘으면 뒤 파일은 줄이거나 뺀다."""
    budget = MAX_TOTAL_CHARS
    chunks: list[str] = []
    for item in materials:
        if budget <= 0:
            chunks.append(f"### {item['path']}\n(분량 제한으로 생략)")
            continue
        body = item["content"][: min(MAX_CHARS_PER_FILE, budget)]
        budget -= len(body)
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
) -> tuple[str, str]:
    """(reportMarkdown, reviewMarkdown)을 반환한다. LLM은 1회만 호출한다.

    reviewMarkdown 은 늘 빈 글자다. 모델이 그래도 문제를 붙이면 잘라 버린다 — 자리는 예전 노트와
    같은 모양으로 돌려주려고 남겨 둔다.
    """
    if not materials:
        raise ValueError("분석할 수업 자료가 없습니다.")
    response = (NOTE_PROMPT | _llm()).invoke({
        "scope_label": scope_label,
        "learner_level": LEARNER_LEVEL,
        "materials": pack_materials(materials),
    })
    report, _review = _split_report_and_review(response_text(response))
    return report, ""


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
