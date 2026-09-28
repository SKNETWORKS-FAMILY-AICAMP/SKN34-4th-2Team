"""회사 자기소개서 문항 답변 — 공고 요건을 뽑고, 이력서에서 근거를 찾아, 사용자가 정한 문항대로 쓴다.

기존 첨삭(문장 다듬기 → 경험 보완 → 지원동기 → 자기소개서)은 그대로 두고 따로 돈다. 그 첨삭은 고정된 여섯 칸을
고치고, 지원동기에 「OO의 OO 직무에 지원한 이유는 다음과 같습니다」 같은 틀 문장을 붙였다. 여기서는 공고 맞춤
이력서에 담긴 회사 문항(content.companyQuestions)마다 답을 새로 쓴다.

모델이 쓴 문장은 코드가 다시 본다.
- 문장마다 근거 인용이 있어야 한다. 이력서 원문 · 사용자 답변 · 공고 원문 중 하나에 그대로 있어야 남는다
- 근거 어디에도 없는 숫자가 든 문장은 버린다 — 부풀린 성과가 여기서 걸린다
- 틀 문장은 버린다
- 글자 수(공백 포함) 제한을 넘기지 않는다. 넘치면 뒤 문장부터 뺀다
재료가 모자라면 억지로 채우지 않고, 이 문항에 닿는 공고 요건 중 이력서에서 확인되지 않는 것을 질문으로 낸다.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from app.job_requirements import JobRequirement
from app.models import StrictModel
from app.resume_review import _unsupported_numbers, extract_review_fields
from app.review_workflow import ReviewInputError

Basis = Literal['resume', 'answer', 'posting']
MAX_GAPS = 3
MIN_QUOTE = 4
# 내용 없이 자리만 채우는 틀 문장. 모델에 쓰지 말라고 하지만, 써 오면 코드가 뺀다
TEMPLATE_SENTENCE = re.compile(r'다음과\s*같습니다|아래와\s*같습니다|이유는\s*크게|첫째[,\s].*둘째')


class AnswerSentenceOut(StrictModel):
    text: str = Field(description='답변 문장 하나. 한국어, 존댓말 대신 「-습니다」체')
    basis: Basis = Field(description='resume=이력서 원문, answer=사용자 보충 답변, posting=공고 원문')
    quote: str = Field(description='이 문장의 근거. basis 가 가리키는 글에서 연속된 일부를 그대로 옮긴다')
    requirement_ids: list[str] = Field(default_factory=list, description='이 문장이 보여 주는 공고 요건 id')


class GapQuestionOut(StrictModel):
    requirement_id: str = Field(description='이력서에서 확인되지 않는 공고 요건 id. 요건과 무관하면 빈 문자열')
    question: str = Field(description='사용자에게 물을 한 문장. 무엇을 · 어떻게 · 결과가 어땠는지 답할 수 있게')


class QuestionAnswerOut(StrictModel):
    sentences: list[AnswerSentenceOut] = Field(default_factory=list)
    gaps: list[GapQuestionOut] = Field(default_factory=list)


QUESTION_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ('system', """너는 한국어 자기소개서를 함께 쓰는 코치다. 지원자가 정한 회사 문항 하나에 답을 쓴다.

규칙
1. 모든 문장은 근거가 있어야 한다. 근거는 [이력서], [보충 답변], [공고] 셋 중 하나에서 연속된 글을 그대로 옮긴 quote 로 붙인다.
   근거에 없는 경험 · 기술 · 역할 · 숫자 · 회사 정보는 쓰지 않는다. 그럴듯해 보여도 쓰지 않는다.
2. 회사 · 직무 이야기는 [공고]에 적힌 것만 쓴다. 매출 · 성장률 · 사업 계획처럼 공고에 없는 회사 정보는 쓰지 않는다.
3. 문항이 묻는 것에 답한다. 공고 요건 중 이 문항과 닿는 것을 이력서 경험으로 보여 준다.
4. 「지원한 이유는 다음과 같습니다」, 「첫째, 둘째」처럼 내용 없는 틀 문장, 「완벽히 부합」 「획기적으로」 같은 과장은 쓰지 않는다.
5. 글자 수 제한(공백 포함)을 넘지 않는다. 재료가 모자라면 짧게 쓴다. 채우려고 늘리지 않는다.
6. 이 문항에 필요한데 이력서에서 확인되지 않는 것이 있으면 gaps 에 질문으로 낸다(최대 3개). 이미 [보충 답변]에서 답한 것은 다시 묻지 않는다."""),
    ('human', """[회사 · 공고] {company} · {title}

[문항] {question}
[글자 수 제한] {limit}

[공고 요건] (id · 구분 · 요건 · 공고 원문)
{requirements}

[이력서] (항목 경로: 원문)
{resume}

[보충 답변] (앞서 질문에 지원자가 답한 것)
{answers}

[공고] 원문
{job_text}"""),
])


def build_question_answer_generator(settings) -> Callable[[dict], QuestionAnswerOut]:
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        use_responses_api=True,
        reasoning_effort=settings.openai_reasoning_effort,
        max_retries=0,
    )
    chain = QUESTION_ANSWER_PROMPT | model.with_structured_output(QuestionAnswerOut, method='json_schema')
    return chain.invoke


def _squash(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def ground_answer(
    generated: QuestionAnswerOut,
    *,
    fields: dict[str, str],
    answers: list[dict[str, str]],
    job_text: str,
    requirement_ids: set[str],
    limit: int | None,
) -> dict[str, Any]:
    """모델이 쓴 답을 근거와 대조하고 글자 수에 맞춘다. 화면에 줄 모양으로 돌려준다."""
    sources = {
        'resume': '\n'.join(fields.values()),
        'answer': '\n'.join(a.get('answer', '') for a in answers),
        'posting': job_text,
    }
    haystacks = {basis: _squash(text) for basis, text in sources.items()}
    evidence = '\n'.join(sources.values())
    kept: list[dict[str, Any]] = []
    dropped = 0
    for sentence in generated.sentences:
        text = sentence.text.strip()
        quote = _squash(sentence.quote)
        grounded = len(quote) >= MIN_QUOTE and quote in haystacks[sentence.basis]
        if not text or not grounded or TEMPLATE_SENTENCE.search(text) or _unsupported_numbers(text, evidence):
            dropped += 1
            continue
        kept.append({
            'text': text,
            'basis': sentence.basis,
            'quote': sentence.quote.strip(),
            'requirement_ids': [r for r in sentence.requirement_ids if r in requirement_ids],
        })
    # 제한을 넘으면 뒤 문장부터 뺀다. 앞 문장이 문항에 곧바로 답하는 문장이라서다
    while limit and kept and len(' '.join(s['text'] for s in kept)) > limit:
        kept.pop()
        dropped += 1
    asked = {_squash(a.get('question', '')) for a in answers}
    gaps = []
    for gap in generated.gaps:
        question = gap.question.strip()
        if not question or _squash(question) in asked:
            continue
        gaps.append({'requirement_id': gap.requirement_id if gap.requirement_id in requirement_ids else '',
                     'question': question})
        if len(gaps) >= MAX_GAPS:
            break
    draft = ' '.join(s['text'] for s in kept)
    return {'draft': draft, 'char_count': len(draft), 'limit': limit, 'sentences': kept,
            'dropped': dropped, 'gaps': gaps}


def _requirements_text(requirements: list[JobRequirement]) -> str:
    if not requirements:
        return '정리된 요건 없음'
    labels = {'must': '필수', 'preferred': '우대', 'task': '주요 업무'}
    return '\n'.join(f'{r.id} · {labels.get(r.group, r.group)} · {r.label} · "{r.posting_quote}"' for r in requirements)


def write_question_answer(
    *,
    tailored: dict,
    question_id: str,
    answers: list[dict[str, str]],
    job: dict,
    requirements: list[JobRequirement],
    generator: Callable[[dict], QuestionAnswerOut],
) -> dict[str, Any]:
    """공고 맞춤 이력서(tailored)의 회사 문항 하나에 답을 쓴다."""
    content = tailored.get('content') or {}
    questions = content.get('companyQuestions') if isinstance(content, dict) else None
    question = next((q for q in questions or [] if isinstance(q, dict) and q.get('id') == question_id), None)
    if question is None or not str(question.get('question') or '').strip():
        raise ReviewInputError('company_question_not_found')
    fields, _excluded = extract_review_fields(content)
    if not fields:
        raise ReviewInputError('resume is empty')
    limit = question.get('limit')
    limit = int(limit) if isinstance(limit, (int, float)) and limit > 0 else None
    source = job.get('source') or {}
    generated = generator({
        'company': source.get('company') or '확인 불가',
        'title': source.get('title') or '확인 불가',
        'question': str(question['question']).strip(),
        'limit': f'{limit}자 (공백 포함)' if limit else '없음 — 700자 안쪽으로',
        'requirements': _requirements_text(requirements),
        'resume': '\n'.join(f'{path}: {value}' for path, value in fields.items()),
        'answers': json.dumps(answers, ensure_ascii=False) if answers else '없음',
        'job_text': job.get('text') or '',
    })
    result = ground_answer(
        generated, fields=fields, answers=answers, job_text=job.get('text') or '',
        requirement_ids={r.id for r in requirements}, limit=limit,
    )
    return {'question_id': question_id, 'question': str(question['question']),
            'requirements': [{'id': r.id, 'group': r.group, 'label': r.label} for r in requirements], **result}
