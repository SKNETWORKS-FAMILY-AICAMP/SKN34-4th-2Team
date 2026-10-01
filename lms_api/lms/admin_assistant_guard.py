"""관리자 AI 어시스턴트 입력 가드.

탈옥 · 프롬프트 유출 시도는 모델 판단에 맡기지 않고 **호출 전에** 막는다.
운영 문장과 겹치지 않도록 분명한 표현만 적는다. 잡담 · 코딩 요청은 시스템 프롬프트가 거절한다.
"""

from __future__ import annotations

import re
import unicodedata

_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("injection", re.compile(
        r"(이전|위|앞|기존)(의)?\s*(모든\s*)?(지시|지침|프롬프트)\S*\s*(모두\s*|전부\s*|다\s*)?(무시|잊어|잊고)"
    )),
    ("injection", re.compile(r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules)")),
    ("injection", re.compile(r"(너의|네|당신의)\s*(규칙|지침|제약)\S*\s*(무시|해제|풀어)")),
    ("prompt_leak", re.compile(r"시스템\s*프롬프트\S*\s*(보여|출력|알려|공개|말해)")),
    ("prompt_leak", re.compile(r"system\s*prompt")),
    ("jailbreak", re.compile(r"developer\s*mode|jailbreak|탈옥")),
)


# 학생이 쓴 출결 사유 · 기록 제목이 도구 결과로 모델에 들어간다. 어시스턴트에게 시키는 말투만 잡는다.
_STUDENT_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("instruction", re.compile(
        r"(어시스턴트|assistant|챗봇|chatbot|(?<![a-z])(ai|gpt)(?![a-z]))\S*\s*.{0,40}"
        r"(제안|발송|등록|보내|공지|알림)\S*\s*(하라|해라|해줘|해 줘|하세요|할 것)"
    )),
    ("tool_syntax", re.compile(r"propose_\w+|target_user_ids|all_students|tool_calls?|function_call")),
    ("role_tag", re.compile(r"(^|[\s\[<])(system|assistant|developer|시스템)\s*[:\]>]")),
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip().lower()


def _match(patterns, text: str) -> str | None:
    normalized = _normalize(text)
    for reason, pattern in patterns:
        if pattern.search(normalized):
            return reason
    return None


def check_message(text: str) -> str | None:
    """막아야 하면 사유, 아니면 None"""
    return _match(_PATTERNS, text)


def check_student_text(text: str) -> str | None:
    """학생 글에 모델을 부리려는 문장이 있으면 사유, 아니면 None"""
    return check_message(text) or _match(_STUDENT_PATTERNS, text)
