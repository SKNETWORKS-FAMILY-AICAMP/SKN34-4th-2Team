"""경험 항목마다 상황·과제·행동·결과(STAR)가 원문에 있는지 판정하고, 그 판정으로 질문을 거른다.

모델은 요소마다 원문 인용을 낸다. 서버는 인용이 그 항목의 원문이나 그 항목에 연결된 확인 답변에 실제로
있을 때만 "있음"으로 둔다. 인용이 없거나 확인되지 않으면 "빠짐"이다(요건 판정의 met과 같은 규칙).

쓰는 곳:
- 앱: 미리보기의 경험 항목 밑에 네 칸으로 보여 준다. 사용자가 무엇을 보완할지 한눈에 본다.
- 서버: 이미 행동·결과가 적힌 항목을 다시 파고드는 질문과 틀 질문을 거른다(2026-09-15 앱 피드백).
"""
from __future__ import annotations

import re

from app.models import STAR_ELEMENTS, StarCheck
from app.review_rules import EXPERIENCE_SECTION_PATTERN, star_action_quote_has_method

# 경험을 서술하는 칸. 지원동기·입사 후 포부는 경험 서술이 아니라 판정하지 않는다.
STAR_TARGET = re.compile(
    rf'(?:{EXPERIENCE_SECTION_PATTERN})\[\d+\]\.description'
    r'|selfIntroduction\.(?:intro|challenge|growth|strengthsWeaknesses)\.body'
)
STAR_LABELS = {'situation': '상황', 'task': '과제', 'action': '행동', 'result': '결과'}
# 결과로 인정하는 인용 종류. 모델이 종류를 고르고 서버는 이 목록만 결과로 본다. 종류를 내지 않은 예전 판정(None)은
# 그대로 받는다. 낱말 목록으로 결과를 가려내면 "0으로 만들었습니다" 같은 처음 보는 표현을 놓쳤다(2026-09-15).
RESULT_KINDS = {'metric_change', 'state_change', 'verification', 'recognition', None}


def _squash(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def star_targets(fields: dict[str, str]) -> list[str]:
    return [path for path, value in fields.items() if STAR_TARGET.fullmatch(path) and len(_squash(value)) >= 6]


def ground_star_judgements(judgements, fields, answers, previous_checks=None, judged_paths=None):
    """모델 판정을 인용 대조로 확정한다.

    - judged_paths: 이번 첨삭에서 판정한 칸. 후속 첨삭은 답한 항목만 다시 판정하고 나머지는 이전 판정을 잇는다.
    - 같은 칸 판정이 여러 개면 처음 것만 쓴다.
    """
    warnings = []
    previous = {check['field_path']: check for check in (previous_checks or []) if check.get('field_path') in fields}
    judged_paths = set(judged_paths if judged_paths is not None else star_targets(fields))
    answers_by_path: dict[str, list[str]] = {}
    for answer in answers:
        answers_by_path.setdefault(answer.field_path, []).append(str(answer.answer))
    checks: dict[str, StarCheck] = {}
    for judgement in judgements:
        path = judgement.field_path
        if path not in judged_paths or path in checks:
            continue
        haystacks = [_squash(fields.get(path, '')), *(_squash(text) for text in answers_by_path.get(path, []))]
        present, quotes = [], {}
        for element in STAR_ELEMENTS:
            quote = str(getattr(judgement, f'{element}_quote') or '').strip()
            if not quote:
                continue
            if not any(_squash(quote) and _squash(quote) in haystack for haystack in haystacks):
                warnings.append(f'STAR 인용 불일치: {path} {STAR_LABELS[element]}')
            elif element == 'action' and not star_action_quote_has_method(quote):
                warnings.append(f'STAR 행동 인용에 방법이 없음: {path}')
            elif element == 'result' and judgement.result_kind not in RESULT_KINDS:
                warnings.append(f'STAR 결과 인용이 결과가 아님({judgement.result_kind}): {path}')
            else:
                present.append(element)
                quotes[element] = quote[:200]
        missing = [element for element in STAR_ELEMENTS if element not in present]
        checks[path] = StarCheck(
            field_path=path, present=present, missing=missing, quotes=quotes,
            reason=str(judgement.missing_reason or '').strip()[:200] if missing else '',
        )
    ordered = []
    for path in fields:
        if path in checks:
            ordered.append(checks[path])
        elif path in previous and path not in judged_paths:
            ordered.append(StarCheck.model_validate(previous[path]))
    return ordered, warnings


def mark_answered_star_elements(checks, answers, questions_by_id, sentence_reviews):
    """후속 첨삭: 답변이 그 항목의 내용 수정안에 반영됐으면, 질문이 묻던 STAR 요소를 "있음"으로 바꾼다.

    수정안은 이미 답변 반영 검증(require_answer_reflection)을 통과한 것만 남아 있다. 답변의 앞부분을 근거 인용으로 둔다.
    """
    by_path = {check['field_path']: dict(check) for check in checks}
    for answer in answers:
        topic = (questions_by_id.get(answer.question_id) or {}).get('topic')
        check = by_path.get(answer.field_path)
        if topic not in STAR_LABELS or check is None:
            continue
        reflected = any(
            review.field_path == answer.field_path and review.suggested_revision and review.edit_type == 'content'
            for review in sentence_reviews
        )
        if not reflected:
            continue
        present = [element for element in STAR_ELEMENTS if element in set(check.get('present') or []) | {topic}]
        missing = [element for element in STAR_ELEMENTS if element not in present]
        by_path[answer.field_path] = {
            **check, 'present': present, 'missing': missing,
            'quotes': {**(check.get('quotes') or {}), topic: str(answer.answer)[:60]},
            'reason': check.get('reason', '') if missing else '',
        }
    return [by_path[check['field_path']] for check in checks]


def star_by_path(checks) -> dict[str, StarCheck]:
    return {(c.field_path if isinstance(c, StarCheck) else c['field_path']):
            (c if isinstance(c, StarCheck) else StarCheck.model_validate(c)) for c in checks}


def has_elements(check: StarCheck | None, *elements: str) -> bool:
    return check is not None and all(element in check.present for element in elements)
