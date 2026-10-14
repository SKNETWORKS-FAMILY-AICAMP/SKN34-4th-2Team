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
from collections import Counter
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from app.job_requirements import JobRequirement
from app.models import StrictModel
from app.resume_review import _unsupported_numbers, extract_review_fields
from app.review_workflow import ReviewInputError

Basis = Literal['resume', 'answer', 'posting']
FocusMode = Literal['single', 'multiple', 'none']
MAX_GAPS = 3
MIN_QUOTE = 4
# 내용 없이 자리만 채우는 틀 문장. 모델에 쓰지 말라고 하지만, 써 오면 코드가 뺀다
TEMPLATE_SENTENCE = re.compile(r'다음과\s*같습니다|아래와\s*같습니다|이유는\s*크게|첫째[,\s].*둘째')


class AnswerSourceRef(StrictModel):
    basis: Basis
    source_id: str = Field(description='이력서 field path, answer:번호, 또는 posting')
    quote: str = Field(description='그 source_id 원문 안의 끊기지 않는 정확한 인용')


class AnswerSentenceOut(StrictModel):
    text: str = Field(description='답변 문장 하나. 한국어, 존댓말 대신 「-습니다」체')
    sources: list[AnswerSourceRef] = Field(default_factory=list, description='이 문장의 주요 사실을 직접 뒷받침하는 출처. 복수 가능')
    # Older stored/offline candidates can still be checked, but new output uses sources.
    basis: Basis | None = None
    quote: str = ''
    requirement_ids: list[str] = Field(default_factory=list, description='이 문장이 보여 주는 공고 요건 id')


class GapQuestionOut(StrictModel):
    requirement_id: str = Field(description='이력서에서 확인되지 않는 공고 요건 id. 요건과 무관하면 빈 문자열')
    question: str = Field(description='사용자에게 물을 한 문장. 무엇을 · 어떻게 · 결과가 어땠는지 답할 수 있게')
    kind: Literal['clarification', 'experience_choice'] = 'clarification'


class QuestionAnswerOut(StrictModel):
    sentences: list[AnswerSentenceOut] = Field(default_factory=list)
    gaps: list[GapQuestionOut] = Field(default_factory=list)
    focus_mode: FocusMode = 'none'
    focus_source_ids: list[str] = Field(default_factory=list)
    focus_reason: str = ''


QUESTION_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ('system', """너는 한국어 자기소개서를 함께 쓰는 코치다. 지원자가 정한 회사 문항 하나에 답을 쓴다.

규칙
1. 먼저 문항이 요구하는 답의 구성 요소와 적합한 경험을 고른다. focus_mode는 한 경험 중심이면 single,
   여러 경험이 자연스러우면 multiple, 경험 선택이 불필요하면 none이다. 사용한 경험 ID를 focus_source_ids에 넣고
   선택 이유를 짧게 쓴다. [메모]는 이번 문항에 쓰고 싶은 방향이고 [과거 답변]은 사실 자료다.
   한 경험이 필요한 문항에서 메모와 과거 답변이 다른 경험을 가리키고 선택이 불명확하면 문장을 쓰지 말고
   gaps에 어느 경험을 중심으로 쓸지 묻는다. 이미 선택 답을 받았다면 다시 묻지 않는다.
2. 모든 문장은 sources에 그 문장의 사실을 직접 뒷받침하는 출처 ID와 연속된 정확한 quote를 붙인다.
   하나의 문장에 여러 사실이 있으면 여러 출처를 붙인다. 다른 프로젝트의 수치나 역할을 섞지 않는다.
   근거에 없는 경험 · 기술 · 역할 · 숫자 · 회사 정보는 쓰지 않는다. 그럴듯해 보여도 쓰지 않는다.
3. 회사 · 직무에 대한 확정 사실은 [공고]로만 뒷받침한다. [메모]의 회사 정보는 지원자 진술이지 공식 공고가 아니다.
   정리된 공고 요건이 없으면 직무 맞춤이 확인됐다고 말하지 말고 문항·이력서 중심으로 답한다.
4. 문항의 각 요구 요소에 답한다. 이미 [이력서]의 동기·입사 초기 계획·성장 방향에 있는 정보부터 활용하되,
   원문 전체를 보존할 필요는 없다. 공고 요건 중 문항과 관련된 것만 선택한다.
5. 내용 없는 틀 문장과 과장을 피한다. 글자 수 제한은 상한이지 목표가 아니다.
6. gaps는 답이 문항의 핵심을 실질적으로 개선할 때만 낸다(최대 3개). 빈 분량이나 모든 미확인 요건을
   채우려고 묻지 말고, 이미 [이력서]·[과거 답변]에 있는 내용은 표현을 바꿔 다시 묻지 않는다."""),
    ('human', """[회사 · 공고] {company} · {title}

[문항] {question}
[글자 수 제한] {limit}

[공고 요건] (id · 구분 · 요건 · 공고 원문)
{requirements}

[이력서] (출처 ID=항목 경로: 원문)
{resume}

[경험 선택 후보] (ID · 이름)
{experience_options}

[이번 문항에서 명시적으로 선택한 경험]
{selected_experience}

[메모·과거 답변] (answer:번호 · source_type · 질문 · 지원자 진술)
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


_EXPERIENCE_SECTIONS = {
    'projects': 'name', 'experience': 'company', 'education': 'school',
    'trainingExperience': 'course', 'otherActivities': 'name',
}


def _experience_options(content: dict, fields: dict[str, str]) -> dict[str, dict[str, str]]:
    """Use stable item IDs, never array positions, as choice identities."""
    options = {}
    for section, title_key in _EXPERIENCE_SECTIONS.items():
        for index, item in enumerate(content.get(section) or []):
            if not isinstance(item, dict):
                continue
            item_id, title = str(item.get('id') or '').strip(), str(item.get(title_key) or '').strip()
            prefix = f'{section}[{index}]'
            if not item_id or not title or not any(path.startswith(prefix + '.') for path in fields):
                continue
            key = f'{section}:{item_id}'
            if key in options:
                raise ReviewInputError('duplicate_experience_id')
            options[key] = {'label': title, 'prefix': prefix}
    return options


def _owner_of_path(path: str, options: dict[str, dict[str, str]]) -> str | None:
    return next((owner for owner, item in options.items() if path.startswith(item['prefix'] + '.')), None)


def _project_mentions(text: str, fields: dict[str, str], options: dict[str, dict[str, str]]) -> set[str]:
    """Only detect ambiguous user focus; token matches never become applicant facts."""
    tokens = {owner: {token.lower() for token in re.findall(r'[A-Za-z][A-Za-z0-9_+-]{2,}|[가-힣]{3,}',
        item['label'] + ' ' + fields.get(item['prefix'] + '.techStack', ''))} for owner, item in options.items()}
    frequency = Counter(token for values in tokens.values() for token in values)
    unique = {owner: {token for token in values if frequency[token] == 1} for owner, values in tokens.items()}
    words = {token.lower() for token in re.findall(r'[A-Za-z][A-Za-z0-9_+-]{2,}|[가-힣]{3,}', text)}
    return {owner for owner, values in unique.items() if words & values}


def _selected_experience(answers: list[dict[str, str]], options: dict[str, dict[str, str]]) -> str | None:
    for item in reversed(answers):
        if item.get('source_type') != 'selection':
            continue
        chosen = str(item.get('selected_experience_id') or '').strip()
        if not chosen:
            # Legacy free-text selection is not an identity. Do not fall back to older choices.
            return None
        if chosen not in options:
            raise ReviewInputError('selected_experience_not_found')
        return chosen
    return None


def _ambiguous_single_focus(answers: list[dict[str, str]], fields: dict[str, str],
                            options: dict[str, dict[str, str]], mode: FocusMode, selected: str | None) -> list[str]:
    if mode != 'single' or selected or len(options) < 2:
        return []
    memo = set().union(*(_project_mentions(a.get('answer', ''), fields, options) for a in answers
        if a.get('source_type') == 'memo'))
    history = set().union(*(_project_mentions(a.get('answer', ''), fields, options) for a in answers
        if a.get('source_type', 'answer') == 'answer'))
    if memo and history and memo.isdisjoint(history):
        return sorted(memo | history)
    return []


def _resolve_sources(sentence: AnswerSentenceOut, catalog: dict[Basis, dict[str, str]]) -> list[AnswerSourceRef]:
    if sentence.sources:
        return sentence.sources
    # Old model candidates: accept a quote only if its owning source is unique.
    if not sentence.basis or not sentence.quote:
        return []
    owners = [source_id for source_id, content in catalog[sentence.basis].items()
              if len(_squash(sentence.quote)) >= MIN_QUOTE and _squash(sentence.quote) in _squash(content)]
    return [AnswerSourceRef(basis=sentence.basis, source_id=owners[0], quote=sentence.quote)] if len(owners) == 1 else []


def ground_answer(
    generated: QuestionAnswerOut,
    *,
    fields: dict[str, str],
    answers: list[dict[str, str]],
    job_text: str,
    requirement_ids: set[str],
    limit: int | None,
    selected_project: str | None = None,
    experience_options: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """모델이 쓴 답을 근거와 대조하고 글자 수에 맞춘다. 화면에 줄 모양으로 돌려준다."""
    catalog: dict[Basis, dict[str, str]] = {
        'resume': fields,
        'answer': {f'answer:{index}': item.get('answer', '') for index, item in enumerate(answers)
                   if item.get('source_type') != 'selection'},
        'posting': {'posting': job_text},
    }
    options = experience_options or {}
    kept: list[dict[str, Any]] = []
    dropped = 0
    for sentence in generated.sentences:
        text = sentence.text.strip()
        refs = _resolve_sources(sentence, catalog)
        grounded = bool(refs) and all(ref.source_id in catalog[ref.basis]
            and len(_squash(ref.quote)) >= MIN_QUOTE
            and _squash(ref.quote) in _squash(catalog[ref.basis][ref.source_id]) for ref in refs)
        project_owners = {_owner_of_path(ref.source_id, options) for ref in refs if ref.basis == 'resume'} - {None}
        for ref in refs:
            if ref.basis == 'answer' and ref.source_id in catalog['answer']:
                # Text mentions are a conservative conflict signal, never a choice identity.
                project_owners.update(_project_mentions(catalog['answer'][ref.source_id], fields, options))
        mixed_project_number = len(project_owners) > 1 and bool(_unsupported_numbers(text, ''))
        if (not text or not grounded or TEMPLATE_SENTENCE.search(text)
                or selected_project and project_owners - {selected_project}
                or mixed_project_number
                or _unsupported_numbers(text, '\n'.join(ref.quote for ref in refs))):
            dropped += 1
            continue
        primary = refs[0]
        kept.append({
            'text': text,
            'basis': primary.basis,
            'quote': primary.quote.strip(),
            'sources': [dict(ref.model_dump(),source_type=answers[int(ref.source_id.split(':')[1])].get('source_type','answer')
                if ref.basis == 'answer' else ref.basis) for ref in refs],
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
                     'question': question, 'kind': gap.kind})
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
    options = _experience_options(content, fields)
    selected = _selected_experience(answers, options)
    latest_selection = next((a for a in reversed(answers) if a.get('source_type') == 'selection'), None)
    if latest_selection is not None and not latest_selection.get('selected_experience_id'):
        if not options:
            raise ReviewInputError('selectable_experience_not_found')
        return {'question_id': question_id, 'question': str(question['question']),
            'requirements': [{'id': r.id, 'group': r.group, 'label': r.label} for r in requirements],
            'requirements_status': 'available' if requirements else 'unavailable',
            'experience_options': [dict(id=key, label=value['label']) for key, value in options.items()],
            'focus': {'source_ids': [], 'labels': [], 'reason': '이전 자유 입력 선택은 경험 ID로 확인할 수 없습니다.'},
            'draft': '', 'char_count': 0, 'limit': limit, 'sentences': [], 'dropped': 0,
            'gaps': [{'requirement_id': '', 'question': '이번 문항에서 중심으로 쓸 경험을 다시 선택해 주세요.',
                      'kind': 'experience_choice', 'options': [dict(id=key, label=value['label'])
                                                         for key, value in options.items()]}]}
    generated = generator({
        'company': source.get('company') or '확인 불가',
        'title': source.get('title') or '확인 불가',
        'question': str(question['question']).strip(),
        'limit': f'{limit}자 (공백 포함)' if limit else '없음 — 700자 안쪽으로',
        'requirements': _requirements_text(requirements),
        'resume': '\n'.join(f'{path}: {value}' for path, value in fields.items()),
        'experience_options': '\n'.join(f"{owner} · {item['label']}" for owner, item in options.items()) or '없음',
        'selected_experience': f"{selected} · {options[selected]['label']}" if selected else '없음',
        'answers': json.dumps([dict(source_id=f'answer:{index}',source_type=item.get('source_type','answer'),
            question=item.get('question',''),answer=item.get('answer','')) for index,item in enumerate(answers)
            if item.get('source_type') != 'selection'],
            ensure_ascii=False) if answers else '없음',
        'job_text': job.get('text') or '',
    })
    conflict = _ambiguous_single_focus(answers, fields, options, generated.focus_mode, selected)
    if conflict:
        choice = '이번 문항에서 중심으로 쓸 경험을 하나 골라 주세요.'
        result = dict(draft='',char_count=0,limit=limit,sentences=[],dropped=0,
            gaps=[dict(requirement_id='',question=choice,kind='experience_choice',
                       options=[dict(id=owner,label=options[owner]['label']) for owner in conflict])])
    else:
        focused = selected or (generated.focus_source_ids[0] if generated.focus_mode == 'single'
            and len(generated.focus_source_ids) == 1 and generated.focus_source_ids[0] in options else None)
        result = ground_answer(generated, fields=fields, answers=answers, job_text=job.get('text') or '',
            requirement_ids={r.id for r in requirements}, limit=limit, selected_project=focused,
            experience_options=options)
        for gap in result['gaps']:
            if gap['kind'] == 'experience_choice':
                gap['options'] = [dict(id=owner, label=item['label']) for owner, item in options.items()]
    focus_ids = [owner for owner in dict.fromkeys(generated.focus_source_ids) if owner in options]
    if selected:
        focus_ids = [selected]
    return {'question_id': question_id, 'question': str(question['question']),
            'requirements': [{'id': r.id, 'group': r.group, 'label': r.label} for r in requirements],
            'requirements_status': 'available' if requirements else 'unavailable',
            'experience_options': [dict(id=key, label=value['label']) for key, value in options.items()],
            'focus': {'source_ids': focus_ids, 'labels': [options[owner]['label'] for owner in focus_ids],
                      'reason': generated.focus_reason if not conflict else '지원자 입력이 서로 다른 경험을 가리킵니다.'},
            **result}
