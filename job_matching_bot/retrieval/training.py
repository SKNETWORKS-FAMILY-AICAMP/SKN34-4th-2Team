"""교육 과정 모집 공고 — 채용이 아니라 추천 · 검색에서 뺀다.

대기업 이름으로 올라와도 채용이 아닌 공고가 있다. 「[IBM] Cloud Native Dev base AI agent 6기」(대한상공회의소),
「SW 개발자 부트캠프 교육생 모집」 같은 것이다. 수강생에게 공고로 추천하면 안 된다.

교육 말을 둘로 나눈다(2026-09-30, 열린 공고 5만 8천 건의 제목을 보고 정했다).

- 강한 말(교육생 · 수강생 · 훈련생 · 연수생 · 부트캠프): 채용 말이 없으면 교육 과정이다.
  「(취업연계)[IBM] AI Agent 서비스 개발자 교육생 모집」은 개발자를 뽑는 게 아니라 교육생을 뽑는다
- 약한 말(국비 · K-디지털 · 교육과정 · 아카데미 · 「6기」): 채용 말도 직무 말도 없을 때만 교육 과정이다.
  「AI 백엔드 개발(이어드림스쿨, K-디지털 트레이닝 수료)」 「K-디지털트레이닝 출신 SW 개발자를 모십니다」는
  국비 · K-디지털 수료자를 뽑는 채용이다. 수강생에게 오히려 맞는 공고다

채용 말이 있으면 늘 채용이다 — 「AI 개발자 채용 (국비 교육 이수必)」, 「SBS아카데미게임학원 취업지원 담당자 채용」,
「채용연계형 · 채용약정형 부트캠프」, 「2026 AI 인재 1기 신입사원 공개채용」.

제목만 본다. 본문의 「신입 교육 과정 운영」은 복지 설명이라 채용 공고다.
같은 규칙이 lms_api/lms/featured_postings.py(공고 맞춤 지원 첫 화면 카드)에도 있다. 한쪽을 바꾸면 같이 바꾼다.
"""

from __future__ import annotations

import re

# 파이썬 · PostgreSQL 정규식에 같이 쓴다(PostgreSQL 은 \d · \s · 앞보기 (?!…) 를 읽는다)
STRONG = r"교육생|수강생|훈련생|연수생|부트캠프"
WEAK = r"국비|K-?디지털|K-?뉴딜|KDT|교육\s*과정|과정|아카데미|academy|\d+\s*기(?![가-힣])"
HIRE = r"채용|공채|사원|직원|담당자|강사|교사|초빙|정규직|인력|코치|박사후|연구원"
ROLE = r"개발|엔지니어|디자이너|수료|출신|우대|이수|모십니다|매니저|기획|운영|멘토|컨설턴트|담당|PM|신입|경력|총괄|팀장|부장|임원|engineer|developer"

_STRONG = re.compile(STRONG)
_WEAK = re.compile(WEAK, re.IGNORECASE)
_HIRE = re.compile(HIRE)
_ROLE = re.compile(ROLE, re.IGNORECASE)


def is_training(title: str | None) -> bool:
    """교육 과정 모집 공고인가."""
    text = title or ""
    if _HIRE.search(text):
        return False
    if _STRONG.search(text):
        return True
    return bool(_WEAK.search(text)) and not _ROLE.search(text)


def sql_exclusion(column: str = "title") -> tuple[str, list[str]]:
    """교육 과정을 빼는 WHERE 조건과 값. `is_training` 과 같은 판정이다."""
    text = f"COALESCE({column}, '')"
    clause = f"NOT ({text} !~ %s AND ({text} ~ %s OR ({text} ~* %s AND {text} !~* %s)))"
    return clause, [HIRE, STRONG, WEAK, ROLE]
