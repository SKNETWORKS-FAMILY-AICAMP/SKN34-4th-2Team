"""LangSmith 로 보내는 추적에서 개인정보를 가린다.

추적(LANGSMITH_TRACING=true)을 켜면 LLM 호출의 입력 · 출력이 LangSmith 서버(국외)로 간다.
이력서 · 학생 문맥에는 이름 · 연락처가 들어 있어, 보내기 전에 가린다. 개발할 때 내용을 보면서
품질을 고치려는 용도다. 운영은 내용을 아예 보내지 않는다(LANGSMITH_HIDE_INPUTS/OUTPUTS=true).

- 키로 가린다: 기본정보의 이름 · 연락처 · 이메일 · 생년월일, 학생 표시 이름 같은 칸은 통째로.
  프로젝트 · 기술 이름도 `name` 키를 쓰므로 `name` 을 다 가리지는 않는다.
- 글 속 패턴을 가린다: 이메일 · 휴대폰 · 전화 · 주민번호 · 개인 링크(깃허브 · 블로그) · 「이름: ○○○」.
  이름은 패턴으로 다 잡을 수 없다. 내용까지 보는 추적은 데모 · 테스트 계정으로만 한다.

통합 서버가 앱을 다 불러온 뒤(.env 가 환경변수로 들어온 뒤), 첫 추적보다 먼저 부른다.
LANGSMITH_ANONYMIZE=false 면 가리지 않는다.
"""

from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger(__name__)

# 통째로 가리는 칸. 어디에 있든 이 이름이면 가린다
_PERSON_KEYS = {
    'displayName', 'display_name', 'userDisplayName', 'userName', 'user_name', 'studentName',
    'student_name', 'authorName', 'author_name', 'fullName', 'full_name', 'realName',
    'email', 'phone', 'phoneNumber', 'phone_number', 'mobile', 'birthDate', 'birth_date', 'address',
}
# 기본정보(basicInfo) 안에서만 가리는 칸 — 밖에서는 프로젝트 · 기술 이름이다
_BASIC_INFO_KEYS = {'name', 'githubUrl', 'blogUrl', 'portfolioUrl', 'url'}

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+'), '[이메일]'),
    (re.compile(r'(?<!\d)\d{6}\s*-\s*[1-4]\d{6}(?!\d)'), '[주민번호]'),
    (re.compile(r'(?<![\d-])(?:\+82[-\s]?)?0?1[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?![\d-])'), '[전화번호]'),
    (re.compile(r'(?<![\d-])0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}(?![\d-])'), '[전화번호]'),
    (
        re.compile(
            r'https?://(?:www\.)?(?:github\.com|gitlab\.com|velog\.io|[\w-]+\.tistory\.com|blog\.naver\.com'
            r'|(?:[\w-]+\.)?linkedin\.com|[\w-]+\.notion\.site|[\w-]+\.github\.io)[^\s"\'<>)\]]*'
        ),
        '[개인 링크]',
    ),
    (re.compile(r'((?:이름|성명|학생명|작성자)\s*[:：]\s*)[^\s,·|/\n]{2,10}'), r'\1[이름]'),
]


def mask_value(value: str, path: list[str | int]) -> str:
    """추적에 들어가는 글자 하나(값)를 가린다. path 는 그 값이 들어 있는 키 경로다."""
    last = path[-1] if path else None
    if isinstance(last, str):
        if last in _PERSON_KEYS:
            return '[가림]' if value.strip() else value
        if last in _BASIC_INFO_KEYS and 'basicInfo' in path:
            return '[가림]' if value.strip() else value
    for pattern, replacement in _PATTERNS:
        value = pattern.sub(replacement, value)
    return value


def enable_trace_privacy() -> bool:
    """전역 LangSmith 클라이언트에 가리기를 붙인다. 붙였으면 True."""
    if os.environ.get('LANGSMITH_TRACING', os.environ.get('LANGCHAIN_TRACING_V2', '')).lower() not in ('true', '1'):
        return False
    if os.environ.get('LANGSMITH_ANONYMIZE', 'true').lower() in ('false', '0'):
        logger.warning('LangSmith 추적의 개인정보 가리기를 껐습니다(LANGSMITH_ANONYMIZE=false).')
        return False
    import langsmith
    from langsmith import run_trees
    from langsmith.anonymizer import create_anonymizer

    anonymizer = create_anonymizer(mask_value)
    # LangChain 추적기는 이 전역 클라이언트를 같이 쓴다. 처음 만들 때 가리기를 넣는다
    client = run_trees.get_cached_client(anonymizer=anonymizer)
    if getattr(client, '_anonymizer', None) is not anonymizer:
        # 누가 먼저 만들었다 — 이미 나간 추적은 못 가리지만 이후 것은 가린다
        client._anonymizer = anonymizer  # noqa: SLF001
    langsmith.configure(client=client)
    logger.info('LangSmith 추적에서 개인정보를 가립니다.')
    return True
