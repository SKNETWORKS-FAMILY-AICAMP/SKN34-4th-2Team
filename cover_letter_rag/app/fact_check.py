"""후속 첨삭 수정안을 원문·확인된 답과 뜻으로 대조하고, 틀린 곳이 있으면 그 곳만 다시 쓰게 하는 검사.

서버 낱말 검사는 이미 본 모양(숫자 빠짐, 기술어 추가, "해 보지 않았다")만 막아, 한 번도 안 본 케이스로 잴 때마다
새 모양이 1~2건씩 나왔다(unseen~unseen5: 목적 표현으로 약해짐, 불확실한 답을 단정문으로 적음 등). 원문 옆에 답을
따로 붙이게 하면 막을 수 있지만 문장이 매끄럽지 않다(2026-09-15 사용자 결정: 매끄러움은 지킨다).

그래서 모델은 지금처럼 녹여 쓰고, 검사 모델이 세 가지를 찾는다: 원문 사실이 빠지거나 약해짐(weakened), 원문·확인된
답 어디에도 없는 사실(unsupported), 확신하지 못한 답을 단정으로 적음(uncertain). 걸리면 그 구절만 짚어 한 번 다시
쓰게 하고, 다시 쓴 수정안도 서버 검사와 이 검사를 다시 통과해야 바꾼다. 그래도 틀리면 근거 없는 사실은 보류하고,
약해진 사실은 안내만 붙인다(검사 모델도 틀릴 수 있어 답을 반영한 수정안까지 버리지 않는다).

검사 모델이 적은 구절이 원문·수정안에 실제로 있을 때만 믿는다. 비용을 줄이려고 원문과 달라진 내용 수정안
(변경 폭 0.15 이상, 턴당 4개까지)만, 한 턴에 여러 개면 동시에 묻는다.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from pydantic import Field

from app.models import StrictModel

# 변경 폭 0.245인 수정안이 원문 문장 하나를 지웠다(2026-09-15 한 번도 안 본 케이스). 검사는 평균 1.4초라 범위를 넓힌다.
FACT_CHECK_MIN_CHANGE_RATE = 0.15
MAX_FACT_CHECKS_PER_TURN = 4


class WeakenedFact(StrictModel):
    original_phrase: str = Field(description="원문에서 한 일·결과로 적힌 구절. 원문에 있는 그대로 연속 인용")
    revision_phrase: str = Field(default='', description="수정안에서 그 사실이 바뀐 구절. 빠졌으면 빈 문자열")
    change: str = Field(description="dropped(빠짐), purpose(목적·의도로 바뀜), plan(계획·예정으로 바뀜), "
                                    "role(맡음·참여로만 바뀜), learning(배움으로 바뀜) 중 하나")


class UnsupportedFact(StrictModel):
    revision_phrase: str = Field(description="수정안에 새로 들어간 사실 구절. 수정안에 있는 그대로 연속 인용")
    kind: str = Field(description="unsupported(원문·같은 항목·확인된 답 어디에도 없음) 또는 "
                                  "uncertain(확신하지 못한 답에만 있는데 단정으로 적음)")


class FactKeepCheck(StrictModel):
    weakened: list[WeakenedFact] = Field(default_factory=list)
    unsupported: list[UnsupportedFact] = Field(default_factory=list)


class FactRepair(StrictModel):
    revision: str = Field(description="지적된 곳만 고친 수정안. 원문 인용 자리에 그대로 들어갈 문장")


FACT_CHECK_SYSTEM = """너는 이력서 수정안을 원문과 근거에 대조한다. 두 가지만 적는다.
1. weakened: 원문에서 지원자가 이미 한 일·만든 것·얻은 결과로 적힌 구절 중, 수정안에서 빠졌거나 약해진 것.
   약해졌다는 것은 한 일이 목적·의도('~하기 위해'), 계획·예정, 맡음·참여만, 배움으로 바뀐 경우다.
   - 표현이나 어순만 바뀌고 한 일·결과가 그대로면 적지 않는다.
   - 확인된 답이 그 사실을 고치거나 뺐다면 약해진 것이 아니다.
   - 원문에 원래 목적·계획으로 적힌 것은 적지 않는다.
   - original_phrase는 원문에 있는 그대로의 연속 구절이다.
2. unsupported: 수정안에 새로 들어간 사실(한 일, 도구·기술, 숫자, 결과, 기간, 역할, 대상) 중 [원문], [같은 항목의 칸],
   [확인된 답] 어디에도 근거가 없는 것. [확신하지 못한 답]에만 있는 내용을 단정으로 적었으면 kind를 uncertain으로 한다.
   - 문장을 잇는 말이나 근거 있는 사실을 풀어 쓴 표현은 적지 않는다. 사실만 본다.
   - revision_phrase는 수정안에 있는 그대로의 연속 구절이다.
없으면 두 목록을 비운다."""

FACT_REPAIR_SYSTEM = """너는 이력서 수정안에서 지적된 곳만 고친다.
- [빠지거나 약해진 원문 사실]은 원문에 적힌 대로 한 일·결과로 다시 드러나게 넣는다.
- [근거 없는 내용]은 뺀다. 확신하지 못한 답에서 온 내용도 뺀다.
- 지적되지 않은 부분, 확인된 답을 반영한 부분, 문장 흐름은 그대로 둔다. 원문 말투(~했습니다체 등)를 따른다.
- 새 사실·숫자·기술 이름을 더하지 않는다. 원문 옆에 따로 덧붙이지 말고 한 흐름으로 쓴다.
- revision에는 원문 인용 자리에 들어갈 고친 수정안만 적는다."""


def _structured_chain(settings, system: str, human: str, schema):
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        use_responses_api=True,
        reasoning_effort='low',
        max_retries=0,
    )
    prompt = ChatPromptTemplate.from_messages([('system', system), ('human', human)])
    return prompt | model.with_structured_output(schema, method='json_schema')


def build_fact_checker(settings) -> Callable[[str, str, str], FactKeepCheck]:
    chain = _structured_chain(settings, FACT_CHECK_SYSTEM, '[원문]\n{original}\n\n[수정안]\n{revision}\n\n{context}',
                              FactKeepCheck)

    def check(original: str, revision: str, context: str) -> FactKeepCheck:
        return chain.invoke({'original': original, 'revision': revision, 'context': context})

    return check


def build_fact_repairer(settings) -> Callable[[str, str, str, str], str]:
    chain = _structured_chain(
        settings, FACT_REPAIR_SYSTEM,
        '[원문 인용]\n{original}\n\n[지금 수정안]\n{revision}\n\n{context}\n\n[고칠 곳]\n{problems}', FactRepair,
    )

    def repair(original: str, revision: str, context: str, problems: str) -> str:
        return chain.invoke({'original': original, 'revision': revision, 'context': context,
                             'problems': problems}).revision

    return repair


_CHANGE_WORDS = {'dropped': '빠졌어요', 'purpose': '목적 표현으로 바뀌었어요', 'plan': '계획 표현으로 바뀌었어요',
                 'role': '맡았다는 말로만 바뀌었어요', 'learning': '배웠다는 말로 바뀌었어요'}


def _squash(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def _group(path: str) -> str:
    return path.rsplit('.', 1)[0]


def _review_context(review, fields: dict, answers) -> tuple[str, str]:
    """검사·다시 쓰기에 줄 근거 글과, 검사 모델이 짚은 구절이 근거에 이미 있는지 볼 글."""
    from app.review_rules import split_uncertain_answer

    item_fields = [f'{path}: {value}' for path, value in fields.items()
                   if _group(path) == _group(review.field_path) and str(value or '').strip()]
    related = [answer for answer in answers if _group(answer.field_path) == _group(review.field_path)] or list(answers)
    confirmed, uncertain = [], []
    for answer in related:
        sure, unsure = split_uncertain_answer(answer.answer)
        if sure.strip():
            confirmed.append(sure.strip())
        uncertain.extend(unsure)
    context = '\n\n'.join([
        '[같은 항목의 칸]\n' + ('\n'.join(item_fields) or '없음'),
        '[확인된 답]\n' + ('\n'.join(confirmed) or '없음'),
        '[확신하지 못한 답 — 확인된 사실이 아니다]\n' + ('\n'.join(uncertain) or '없음'),
    ])
    sources = '\n'.join([*(str(value) for value in fields.values()), *confirmed, review.original_quote])
    return context, sources


def _real_problems(review, revision: str, result: FactKeepCheck | None, sources: str):
    """검사 모델이 적은 구절 중 원문·수정안에 실제로 있고, 근거에 그대로 있지 않은 것만 남긴다."""
    if not result:
        return [], []
    original = _squash(review.original_quote)
    weakened = [fact for fact in result.weakened
                if _squash(fact.original_phrase) and _squash(fact.original_phrase) in original
                and _squash(fact.original_phrase) not in _squash(revision)]
    unsupported = [fact for fact in result.unsupported
                   if _squash(fact.revision_phrase) and _squash(fact.revision_phrase) in _squash(revision)
                   and _squash(fact.revision_phrase) not in _squash(sources)]
    return weakened, unsupported


def _problem_text(weakened, unsupported) -> str:
    lines = [f"- 빠지거나 약해진 원문 사실: '{fact.original_phrase.strip()}'" for fact in weakened]
    lines += [f"- 근거 없는 내용{'(확신하지 못한 답)' if fact.kind == 'uncertain' else ''}: '{fact.revision_phrase.strip()}'"
              for fact in unsupported]
    return '\n'.join(lines)


def check_and_repair_revisions(generation, fields: dict, answers, checker, repairer, telemetry: dict,
                               reground: Callable[[list], None] | None = None) -> list[str]:
    """변경 폭이 큰 내용 수정안을 검사하고, 걸리면 한 번 다시 쓰게 한다. 경고 목록을 돌려준다.

    reground는 다시 쓴 수정안 목록에 서버 검사(원문 위치·숫자·기술어·답 반영)를 다시 돌리는 함수다.
    """
    if checker is None:
        return []
    targets = [
        review for review in generation.sentence_reviews
        if review.suggested_revision and review.new_item is None and review.edit_type == 'content'
        and (review.change_rate or 0) >= FACT_CHECK_MIN_CHANGE_RATE
    ][:MAX_FACT_CHECKS_PER_TURN]
    if not targets:
        return []
    started = time.monotonic()
    contexts = {id(review): _review_context(review, fields, answers) for review in targets}

    def check(review, revision, context=None):
        try:
            return checker(review.original_quote, revision, context or contexts[id(review)][0])
        except Exception:  # noqa: BLE001 — 검사가 실패해도 수정안은 그대로 보여 준다
            return None

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = list(pool.map(lambda review: check(review, review.suggested_revision), targets))
    problems = {}
    for review, result in zip(targets, results):
        weakened, unsupported = _real_problems(review, review.suggested_revision, result, contexts[id(review)][1])
        if weakened or unsupported:
            problems[id(review)] = (weakened, unsupported)
    telemetry.update(fact_checks=len(targets), fact_check_ms=round((time.monotonic() - started) * 1000),
                     fact_flagged=len(problems), fact_repairs=0, fact_repaired=0, fact_withheld=0, fact_notices=0)
    if not problems:
        return []

    warnings = []
    flagged = [review for review in targets if id(review) in problems]
    replaced = {}
    if repairer is not None:
        repair_started = time.monotonic()

        def repair(review):
            try:
                weakened, unsupported = problems[id(review)]
                text = repairer(review.original_quote, review.suggested_revision, contexts[id(review)][0],
                                _problem_text(weakened, unsupported))
            except Exception:  # noqa: BLE001 — 다시 쓰기가 실패하면 처음 수정안으로 판단한다
                return None
            text = str(text or '').strip()
            if not text or _squash(text) == _squash(review.suggested_revision):
                return None
            candidate = review.model_copy(deep=True, update={'suggested_revision': text})
            if reground is not None:
                reground([candidate])
            if not candidate.suggested_revision:
                return None  # 서버 검사에 걸렸다
            again = check(candidate, candidate.suggested_revision, contexts[id(review)][0])
            if again is None or any(_real_problems(candidate, candidate.suggested_revision, again,
                                                   contexts[id(review)][1])):
                return None
            return candidate

        with ThreadPoolExecutor(max_workers=len(flagged)) as pool:
            candidates = list(pool.map(repair, flagged))
        for review, candidate in zip(flagged, candidates):
            if candidate is not None:
                replaced[id(review)] = candidate
        telemetry.update(fact_repairs=len(flagged), fact_repaired=len(replaced),
                         fact_repair_ms=round((time.monotonic() - repair_started) * 1000))

    reviews = []
    for review in generation.sentence_reviews:
        if id(review) in replaced:
            reviews.append(replaced[id(review)])
            warnings.append(f'사실 검사에 걸린 곳을 고쳐 다시 쓴 수정안으로 바꿨습니다: {review.field_path}')
            continue
        if id(review) in problems:
            weakened, unsupported = problems[id(review)]
            if unsupported:
                review.suggested_revision = None
                review.status = 'unchanged'
                review.edit_type = 'none'
                review.confirmation_question = None
                review.change_rate = None
                review.change_rate_notice = None
                review.validation_issues = [*review.validation_issues,
                                            'uncertain_fact_written' if any(f.kind == 'uncertain' for f in unsupported)
                                            else 'unsupported_fact']
                telemetry['fact_withheld'] += 1
                warnings.append(f'근거 없는 사실이 들어간 수정안을 보류했습니다: {review.field_path}')
            elif weakened:
                fact = weakened[0]
                review.fact_notice = (f"원문의 '{fact.original_phrase.strip()}'이(가) 수정안에서 "
                                      f"{_CHANGE_WORDS.get(fact.change, '약해졌어요')}. 한 일이 그대로 드러나는지 확인해 주세요.")
                telemetry['fact_notices'] += 1
        reviews.append(review)
    generation.sentence_reviews = reviews
    return warnings
