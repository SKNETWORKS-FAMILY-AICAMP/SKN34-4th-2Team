"""수업 자료 → 정리 노트.

파일별 분석·품질 검토·수정을 나누면 LLM을 4~8번 호출해 너무 느리다.
자료 전체를 한 번에 넣고 노트+복습 문제를 한 번에 받는다.
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
        "아래 두 블록을 한국어 Markdown으로 이어서 작성하세요.\n"
        "첫 블록과 둘째 블록 사이에는 줄 하나에 --- 만 넣으세요.\n\n"
        "## 오늘의 핵심 한 문장\n"
        "## 전체 수업 흐름\n"
        "## 파일별 학습 내용\n"
        "## 핵심 코드와 개념\n"
        "## 이전 학습과의 연결\n"
        "## 실행 체크리스트\n"
        "## 내가 직접 해볼 실습\n"
        "## 포트폴리오 회고 포인트\n\n"
        "---\n\n"
        "## 복습 문제\n"
        "- 개념 확인 문제 3개\n"
        "- 코드 흐름 문제 2개\n"
        "- 응용 문제 1개\n\n"
        "## 정답과 해설\n"
        "각 문제의 정답과 짧은 해설을 작성하세요.",
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
    """(reportMarkdown, reviewMarkdown)을 반환한다. LLM은 1회만 호출한다."""
    if not materials:
        raise ValueError("분석할 수업 자료가 없습니다.")
    response = (NOTE_PROMPT | _llm()).invoke({
        "scope_label": scope_label,
        "learner_level": LEARNER_LEVEL,
        "materials": pack_materials(materials),
    })
    return _split_report_and_review(response_text(response))
