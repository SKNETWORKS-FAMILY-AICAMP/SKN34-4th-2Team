"""공고 맞춤 첨삭 흐름 — 문항 전부를 계획하고, 문항마다 쓰고, 검토해서 한 번 고친다.

지금 화면의 문항 답(question_answers.py)은 문항 하나씩 따로 쓴다. 그래서 세 답이 같은 경험으로 시작하고,
메모 일부를 빼먹고, 글자 수가 많이 남아도 더 묻지 않았다(2026-10-08 로컬 비교). 여기서는
1. 계획: 문항 전부를 한 번에 보고 문항이 묻는 것을 나누고, 문항마다 중심 경험을 겹치지 않게 정한다
2. 쓰기: 문항마다 정해진 재료로 쓴다. 문장마다 재료 id 를 단다
3. 검사: 코드가 근거 id · 숫자 · 틀 문장 · 메모 사용 · 요구 답변 · 글자 수를 본다. 모델이 근거보다 세게 말한 문장을 찾는다
4. 고쳐 쓰기: 문제가 있으면 한 번만 고쳐 쓰고, 둘 중 문제가 적은 쪽을 고른다
막혀도 답을 비우지 않는다. 남은 문제와 학생에게 물을 질문을 같이 돌려준다.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.job_requirements import JobRequirement
from app.question_answers import TEMPLATE_SENTENCE
from app.question_workflow.models import (
    DraftOut, OverlapsOut, PartOut, PlanOut, QuestionInput, QuestionPlanOut, ReviewOut, Source, TagsOut,
)
from app.resume_review import _unsupported_numbers, extract_review_fields
from app.review_workflow import ReviewInputError

MAX_QUESTIONS = 3
SHORT_RATIO = 0.6  # 제한의 60% 아래면 짧은 답이다 — 질문으로 재료를 더 받는다
FILL_RATIO = 0.5  # 제한의 50% 아래인데 안 쓴 중심 재료가 있으면 그 재료로 살을 붙여 다시 쓴다
# 빽빽한 문장 — 이만큼 길거나 숫자가 이만큼 많으면 나누라고 고쳐 쓴다(「…연결했고 …통과시키며 …확인했습니다」 129자)
DENSE_CHARS = 120
DENSE_NUMBERS = 3
NUMBER = re.compile(r'\d[\d,.]*')
# 메모 조각: 「/」 · 줄바꿈으로 나눈다(「Python·Django」의 가운뎃점은 나누지 않는다)
MEMO_SPLIT = re.compile(r'\s*(?:/|\n)\s*')
KIND_LABELS = {'resume': '이력서', 'memo': '메모', 'note': '학생 답', 'posting': '공고'}
GROUP_LABELS = {'must': '필수', 'preferred': '우대', 'task': '주요 업무'}
# 요건 이름의 낱말 — 영문 기술명(Python · REST · C++)과 두 글자 이상 한글
REQUIREMENT_WORDS = re.compile(r'[A-Za-z][A-Za-z0-9+#.]*|[가-힣]{2,}')
# 어느 요건에나 붙는 말 — 이름표가 문장과 닿는지 볼 때 세지 않는다
COMMON_WORDS = {'서비스', '개발', '경험', '능력', '이해', '활용', '사용', '기반', '관련', '업무', '역량', '수행', '설계', '운영'}
COMPANY_FACING = re.compile(r'귀사|당사|지원했|지원합니다|지원하게|입사')


def _tag_fits(label: str, sentence: str) -> bool:
    """요건 이름의 핵심 낱말이 문장에 하나라도 있어야 이름표를 단다.
    모델이 「LXP를 만든 프로젝트」에 「Python」을 다는 일이 있었다(2026-10-10 이름표 검증, 정밀도 0.56)."""
    words = [w.casefold() for w in REQUIREMENT_WORDS.findall(label) if w not in COMMON_WORDS]
    text = sentence.casefold()
    return not words or any(w in text for w in words)


def _names_tech(label: str, sentence: str) -> bool:
    """요건의 영문 기술명이 문장에 모두 있다 — 모델이 안 달아도 코드가 단다.
    모델은 「Python FastAPI 로 구현하고 LangChain 을 …」에도 이름표를 안 다는 일이 많았다(재현율 0.35)."""
    latin = [w.casefold() for w in REQUIREMENT_WORDS.findall(label) if w.isascii() and len(w) >= 2]
    text = sentence.casefold()
    return bool(latin) and all(w in text for w in latin)
# 회사에 내는 글에 들어가면 안 되는 설명 — 「확인된 자료에 없어 제시하지 않겠습니다」
META_SENTENCE = re.compile(r'(?:자료|재료|근거|수치)[^.]{0,15}(?:없어|없으므로|확인되지\s*않아)[^.]{0,25}(?:않겠|않습니다|생략)|(?:제시|언급)하지\s*않겠')
# 지원자에게 묻는 말 — 「~하셨는지 알려 주시면 좋겠습니다」 「~였나요?」. 답은 지원자 본인의 글이다(2026-10-08 실제 이력서 시험)
ASKS_APPLICANT = re.compile(r'(?:하|되|맡으|겪으|있으)셨|알려\s*주|주시면|말씀해|[가-힣]나요\?|\?\s*$')
SAME_QUESTION = 0.6  # 띄어쓰기를 뺀 두 질문이 이만큼 같으면 같은 질문이다
MIN_TRIM_RATIO = 0.5  # 겹침을 줄여 다시 쓴 답이 원래 답의 이 비율보다 짧으면 원래 답을 둔다


def _squash(text: str) -> str:
    return re.sub(r'\s+', '', str(text or ''))


def build_sources(content: dict, questions: list[QuestionInput], job_text: str,
                  requirements: list[JobRequirement]) -> list[Source]:
    """이력서 칸 · 공고 · 요건 · 문항별 메모 조각 · 학생 답을 재료 목록으로 만든다."""
    fields, _excluded = extract_review_fields(content)
    sources = [Source(f'R{i + 1}', 'resume', path, text) for i, (path, text) in enumerate(fields.items())]
    # 공고도 줄 단위로 — 통째로 하나면 공고를 근거로 쓴 문장 밑에 공고 전체가 인용으로 붙었다(2026-10-10)
    lines = [line.strip() for line in job_text.splitlines() if len(line.strip()) >= 2]
    sources += [Source(f'P{i + 1}', 'posting', '공고 원문', line) for i, line in enumerate(lines)]
    sources += [Source(f'J-{r.id}', 'posting', f'{GROUP_LABELS.get(r.group, r.group)} · {r.label}', r.posting_quote)
                for r in requirements]
    for qi, q in enumerate(questions, start=1):
        pieces = [p for p in MEMO_SPLIT.split(q.memo or '') if p.strip()]
        sources += [Source(f'M{qi}-{k}', 'memo', '지원자 메모', p.strip(), q.id) for k, p in enumerate(pieces, start=1)]
        sources += [Source(f'A{qi}-{k}', 'note', n.get('question', ''), n.get('answer', '').strip(), q.id)
                    for k, n in enumerate(q.notes, start=1) if n.get('answer', '').strip()]
    return sources


def _lines(sources: list[Source], lead: set[str] = frozenset()) -> str:
    return '\n'.join(f'[{s.id}] ({"중심 · " if s.id in lead else ""}{KIND_LABELS[s.kind]} · {s.label}) {s.text}'
                     for s in sources) or '없음'


def _length_rule(limit: int | None) -> str:
    if not limit:
        return '제한이 없다. 700자 안쪽으로 쓰고, 재료가 모자라면 짧게 쓴다.'
    # 한국어 자소서 한 문장은 대략 80~100자 — 문장 수로 말해야 모델이 일찍 멈추지 않는다(2026-10-11, 1000자 문항에 230자)
    return (f'{limit}자(공백 포함)를 넘지 않는다. 재료가 넉넉하면 {int(limit * 0.7)}~{int(limit * 0.95)}자, '
            f'대략 {max(3, round(limit * 0.7 / 90))}~{max(4, round(limit * 0.95 / 90))}문장으로 쓴다. '
            '채울 때는 중심 이야기 하나를 깊게 — 재료 안에서 상황 배경 → 내가 한 일과 그렇게 판단한 이유 → 결과 → 배운 점 · 그 뒤에 적용한 것 순서로 보탠다. '
            '다른 사건 · 다른 프로젝트를 덧붙여 분량을 채우지 않는다. '
            '재료가 모자라면 짧게 쓰고, 늘리려고 같은 말을 되풀이하지 않는다.')


@dataclass
class Checked:
    """초안 하나를 검사한 결과. 문제 수(score)가 적은 초안을 고른다."""

    kept: list[dict[str, Any]]
    dropped: list[dict[str, str]]
    memo_unused: list[str]
    unanswered: list[str]
    over_limit: bool
    review: ReviewOut = field(default_factory=ReviewOut)
    # 제한의 절반도 못 채웠는데 계획이 고른 중심 재료 중 아직 안 쓴 것 — 있으면 고칠 것으로 친다(재료가 정말 없으면 빈 목록)
    unused_lead: list[str] = field(default_factory=list)
    dense: list[str] = field(default_factory=list)  # 나눠야 할 빽빽한 문장
    length: str = ''

    @property
    def score(self) -> int:
        # 문제 수만 세면 문장이 적은 짧은 초안이 늘 이긴다. 채울 재료가 남은 짧은 답은 문제 하나로 친다
        return (len(self.dropped) + len(self.memo_unused) + len(self.unanswered) + int(self.over_limit)
                + int(bool(self.unused_lead)) + len(self.dense)
                + len(self.review.overstated) + len(self.review.unanswered_parts) + len(self.review.memo_missing)
                + len(self.review.flow_issues))

    def issues(self) -> list[str]:
        out = [f'근거가 맞지 않아 뺀 문장: 「{d["text"]}」({d["reason"]})' for d in self.dropped]
        out += [f'메모를 안 씀: 「{m}」' for m in self.memo_unused]
        out += [f'메모 내용이 빠짐: {m}' for m in self.review.memo_missing]
        out += [f'답하지 않은 요구: {p}' for p in dict.fromkeys(self.unanswered + self.review.unanswered_parts)]
        out += [f'{o.index + 1}번 문장이 근거보다 셈: {o.reason}' for o in self.review.overstated]
        out += [f'흐름: {f}' for f in self.review.flow_issues]
        if self.over_limit:
            out.append('글자 수를 넘음')
        out += [f'빽빽한 문장 — 한 가지 일씩 나눈다(60~90자, 숫자 둘까지, 세부 내용은 남긴다): 「{d}」' for d in self.dense]
        if self.unused_lead:
            # 다른 사건을 붙여 채우면 「서로 다른 실패를 한 답에 넣어 배운 점이 흐려진다」(2026-10-11 채점)
            out.append(f'글자 수가 많이 남음({self.length}). 아래 재료 중 지금 이야기와 같은 사건의 것으로만 상황 배경 · 판단 이유 · 결과 · 배운 점을 보탠다.'
                       ' 다른 사건 · 다른 프로젝트의 재료면 쓰지 않고 짧은 채로 둔다'
                       ' — 재료에 있는 것만: ' + ' / '.join(self.unused_lead))
        return out


class QuestionWorkflow:
    """llm 은 plan(dict)->PlanOut, write(dict)->DraftOut, review(dict)->ReviewOut 를 가진다(시험에서는 가짜를 넣는다)."""

    def __init__(self, llm, *, max_workers: int = 4):
        self.llm = llm
        self.max_workers = max_workers

    def run(self, *, content: dict, questions: list[QuestionInput], job: dict,
            requirements: list[JobRequirement], only: str | None = None,
            saved_plan: dict[str, Any] | None = None) -> dict[str, Any]:
        """문항 전체를 쓴다. only 를 주면 그 문항만 다시 쓴다 — saved_plan(앞서 돌려준 plan)이 있으면 계획을 다시 세우지 않는다.
        한 문항만 쓸 때는 한 벌 검토(겹침) · 필수 요건 확인을 하지 않는다. 둘 다 문항 전체를 봐야 한다."""
        source = job.get('source') or {}
        company, title = source.get('company') or '확인 불가', source.get('title') or '확인 불가'
        sources = build_sources(content, questions, job.get('text') or '', requirements)
        targets = [q for q in questions if only is None or q.id == only]
        if not targets:
            raise ReviewInputError('company_question_not_found')
        started = time.perf_counter()
        plans = self._saved_plans(questions, saved_plan, sources) if only is not None and saved_plan else None
        if plans is None:
            plan = self.llm.plan({
                'company': company, 'title': title,
                'questions': '\n'.join(
                    f'- {q.id}: {q.text.strip()} (글자 수 {q.limit or "제한 없음"})' for q in questions),
                'sources': _lines(sources),
            })
            plans = {p.question_id: p for p in plan.questions}
            plans = {q.id: self._clean_plan(q, plans.get(q.id), sources) for q in questions}
        plan_seconds = time.perf_counter() - started
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            answers = list(pool.map(
                lambda q: self._answer(q, plans, questions, sources, company, title), targets))
        overlaps, coverage = [], None
        if only is None:
            answers, overlaps = self._spread(questions, answers, plans, sources, company, title)
        self._tag(answers, requirements)
        if only is None:
            coverage = self._coverage(questions, answers, requirements, sources)
        return {'plan_seconds': round(plan_seconds, 1), 'overlaps': overlaps, 'coverage': coverage, 'only': only,
                'plan': {qid: p.model_dump() for qid, p in plans.items()}, 'questions': answers}

    def _saved_plans(self, questions, saved: dict[str, Any], sources) -> dict[str, QuestionPlanOut] | None:
        """화면이 들고 있던 계획. 문항이 바뀌었거나 모양이 틀리면 None — 계획을 다시 세운다."""
        try:
            plans = {qid: QuestionPlanOut.model_validate(raw) for qid, raw in saved.items()}
        except (ValidationError, TypeError, AttributeError):
            return None
        if any(q.id not in plans for q in questions):
            return None
        return {q.id: self._clean_plan(q, plans[q.id], sources) for q in questions}

    # ── 이름표: 다 쓴 문장을 한 번에 읽고 요건 이름표를 단다 — 따온 근거가 문장에 있어야 남는다 ──
    def _tag(self, answers, requirements) -> None:
        """쓰면서 함께 다는 이름표는 한글 업무 요건(「품질 평가·개선」)을 자주 놓쳤다(2026-10-10 검증, 재현율 0.42~0.55).
        다 쓴 뒤 이름표만 다는 호출을 한 번 더 한다. 모델이 따온 근거(evidence)가 문장에 그대로 없으면 버린다."""
        tagger = getattr(self.llm, 'tag', None)
        flat = [s for a in answers for s in a['sentences']]
        if tagger is None or not requirements or not flat:
            return
        by_id = {r.id: r for r in requirements}
        out = tagger({
            'requirements': '\n'.join(f'{r.id} · {GROUP_LABELS.get(r.group, r.group)} · {r.label} · "{r.posting_quote}"'
                                      for r in requirements),
            'sentences': '\n'.join(f'{i}. {s["text"]}' for i, s in enumerate(flat)),
        })
        for t in out.sentences:
            if not 0 <= t.index < len(flat):
                continue
            s = flat[t.index]
            if COMPANY_FACING.search(s['text']):
                continue
            for tag in t.tags:
                rid = tag.requirement_id.removeprefix('J-')
                evidence = _squash(tag.evidence)
                if rid not in by_id or len(evidence) < 2 or evidence not in _squash(s['text']):
                    continue
                if f'J-{rid}' not in s['requirement_ids']:
                    r = by_id[rid]
                    s['requirement_ids'].append(f'J-{rid}')
                    s['requirements'].append({'id': rid, 'label': f'{GROUP_LABELS.get(r.group, r.group)} · {r.label}'})
                s.setdefault('requirement_evidence', {})[rid] = tag.evidence.strip()

    # ── 필수 요건 확인: 한 벌 어디에도 안 닿은 필수 요건 — 이력서에 있으면 알리고, 없으면 묻는다 ──
    @staticmethod
    def _coverage(questions, answers, requirements, sources) -> dict[str, Any]:
        covered = {i[2:] for a in answers for s in a['sentences'] for i in s['requirement_ids']}
        resume = '\n'.join(s.text for s in sources if s.kind == 'resume').casefold()
        unused, missing = [], []
        for r in requirements:
            if r.group != 'must' or r.id in covered:
                continue
            words = [w.casefold() for w in REQUIREMENT_WORDS.findall(r.label)]
            latin = [w for w in words if w.isascii()]
            korean = [w for w in words if not w.isascii()]
            # 영문 기술명은 모두 있어야, 한글뿐이면 절반 넘게 있어야 이력서에 있다고 본다(「서비스」 「개발」은 어디에나 있다)
            found = (all(w in resume for w in latin) if latin
                     else bool(korean) and sum(w in resume for w in korean) * 2 > len(korean))
            (unused if found else missing).append({'id': r.id, 'label': r.label, 'posting_quote': r.posting_quote})
        if missing and answers:
            # 가장 직무와 닿는 답(요건 이름표가 많은 답)에 묻는다 — 지원 동기 문항보다 역량 문항이 맞다
            target = max(answers, key=lambda a: (sum(len(s['requirement_ids']) for s in a['sentences']), a['limit'] or 0))
            notes = next((q.notes for q in questions if q.id == target['question_id']), [])
            asked = {_squash(n.get('question', '')) for n in notes}
            extra = [f'공고 필수 요건 「{m["label"]}」 관련 경험이 있다면 알려 주세요. 해 본 적이 없으면 비워 두세요.'
                     for m in missing]
            target['questions'] = [x for x in extra if _squash(x) not in asked] + target['questions']
            target['questions'] = target['questions'][:MAX_QUESTIONS + 1]
        return {
            'requirements': [{'id': r.id, 'group': r.group, 'label': r.label, 'covered': r.id in covered}
                             for r in requirements],
            'unused_must': unused, 'missing_must': missing,
        }

    # ── 한 벌 검토: 같은 이야기를 여러 문항에서 자세히 썼으면 가장 맞는 문항 하나에만 남긴다 ──
    def _spread(self, questions, answers, plans, sources, company, title):
        """문항별로 따로 쓰면 가장 잘 맞는 경험이 같을 때 세 답이 같은 이야기를 한다(2026-10-08 실제 이력서 시험).
        한 벌을 읽고 겹친 이야기를 찾아, 남길 문항이 아닌 곳은 그 이야기를 줄여 다시 쓴다. 화면에는 무엇을 줄였는지 알린다."""
        overlap = getattr(self.llm, 'overlap', None)
        written = [(q, a) for q, a in zip(questions, answers) if a['draft']]
        if overlap is None or len(written) < 2:
            return answers, []
        ids = {q.id for q in questions}
        found = overlap({'answers': '\n\n'.join(
            f'[{q.id}] 문항: {q.text.strip()}\n답: {a["draft"]}' for q, a in written)}).overlaps
        notices, redo = [], {}
        for o in found:
            qids = [i for i in dict.fromkeys(o.question_ids) if i in ids]
            if len(qids) < 2:
                continue
            keep = o.keep if o.keep in qids else qids[0]
            others = [i for i in qids if i != keep]
            notices.append({'story': o.story, 'keep': keep, 'others': others, 'reason': o.reason})
            for i in others:
                redo.setdefault(i, []).append((o.story, keep))
        if not redo:
            return answers, notices
        text = {q.id: q.text.strip() for q in questions}

        def guidance(qid: str) -> str:
            lines = [f'- 「{story}」 이야기는 다른 문항(「{text[keep][:40]}」)에서 자세히 쓴다. 이 답에서는 한 문장 이하로만 언급하거나 빼고,'
                     ' 이 문항과 맞는 다른 경험이 재료에 있으면 그 경험을 중심으로 쓴다. 맞는 다른 경험이 없으면 이 문항의 강조점에 맞는 부분만 짧게 쓴다.'
                     for story, keep in redo[qid]]
            return '[다른 문항과 겹침 — 꼭 지킨다]\n' + '\n'.join(lines)

        targets = [q for q in questions if q.id in redo]
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            redone = dict(zip([q.id for q in targets], pool.map(
                lambda q: self._answer(q, plans, questions, sources, company, title, guidance=guidance(q.id)), targets)))
        out, unchanged = [], set()
        for q, a in zip(questions, answers):
            new = redone.get(q.id)
            if new is None:
                out.append(a)
            elif new['draft'] and len(new['draft']) >= len(a['draft']) * MIN_TRIM_RATIO:
                out.append({**new, 'trimmed_overlap': [s for s, _ in redo[q.id]]})
            else:
                # 줄이면 비거나 반 넘게 짧아진다(1000자 문항이 153자가 된 적이 있다) — 겹치는 편이 빈약한 답보다 낫다.
                # 원래 답을 두고, 다른 경험을 쓰려면 메모로 정하라고 알린다
                unchanged.add(q.id)
                out.append({**a, 'overlap_unchanged': [s for s, _ in redo[q.id]]})
        for n in notices:
            n['unchanged'] = [i for i in n['others'] if i in unchanged]
            n['others'] = [i for i in n['others'] if i not in unchanged]
        return out, notices

    # ── 계획 정리: 남의 메모 · 없는 id 를 지운다. 계획이 빠진 문항은 문항 전체를 요구 하나로 본다 ──
    @staticmethod
    def _allowed(q: QuestionInput, sources: list[Source]) -> dict[str, Source]:
        return {s.id: s for s in sources if not s.question_id or s.question_id == q.id}

    def _clean_plan(self, q: QuestionInput, plan: QuestionPlanOut | None, sources: list[Source]) -> QuestionPlanOut:
        allowed = self._allowed(q, sources)
        if plan is None:
            return QuestionPlanOut(question_id=q.id, parts=[PartOut(key='답', quote=q.text.strip())],
                                   lead_source_ids=[], angle='')
        return plan.model_copy(update={
            'lead_source_ids': [i for i in plan.lead_source_ids if i in allowed],
            'support_source_ids': [i for i in plan.support_source_ids if i in allowed],
        })

    # ── 문항 하나: 쓰기 → 검사 → (문제 있으면) 한 번 고쳐 쓰기 ──
    def _answer(self, q, plans, questions, sources, company, title, guidance: str = '') -> dict[str, Any]:
        started = time.perf_counter()
        plan = plans[q.id]
        allowed = self._allowed(q, sources)
        # 쓰기에는 이 문항이 쓸 수 있는 재료를 모두 준다. 계획이 고른 것은 「중심」으로 표시만 한다 —
        # 고른 것만 주면 다른 문항과 나누다가 이 답에 필요한 사실(원인 재현 · 조율)까지 빠졌다(2026-10-08 채점)
        lead = set(plan.lead_source_ids + plan.support_source_ids)
        offered = list(allowed.values())
        others = '\n'.join(
            f'- {o.text.strip()[:60]} → {plans[o.id].angle} (중심 재료: {", ".join(plans[o.id].lead_source_ids) or "없음"})'
            for o in questions if o.id != q.id) or '없음'
        payload = {
            'company': company, 'title': title, 'question': q.text.strip(),
            'parts': ', '.join(f'{p.key}{"" if p.required else "(선택)"}' for p in plan.parts),
            'angle': plan.angle or '문항에 곧바로 답한다', 'others': others, 'sources': _lines(offered, lead),
            'memo': '\n'.join(f'[{s.id}] {s.text}' for s in offered if s.kind == 'memo') or '없음',
            'length_rule': _length_rule(q.limit), 'retry': guidance,
        }
        first = self.llm.write(payload)
        checked = self._check(q, plan, first, allowed)
        rewrites = 0
        if checked.score:
            previous = '\n'.join(f'{i + 1}. {s["text"]}' for i, s in enumerate(checked.kept))
            retry = ((guidance + '\n\n' if guidance else '') + '[앞 초안]\n' + (previous or '(남은 문장 없음)') + '\n\n[고칠 것]\n'
                     + '\n'.join(f'- {x}' for x in checked.issues())
                     + '\n위 문제를 고쳐 처음부터 다시 쓴다. 재료에 없는 것으로 채우지 않는다.')
            second = self._check(q, plan, self.llm.write({**payload, 'retry': retry}), allowed)
            rewrites = 1
            if second.score <= checked.score:
                checked = second
        return self._result(q, plan, checked, allowed, rewrites, time.perf_counter() - started)

    def _check(self, q: QuestionInput, plan: QuestionPlanOut, draft: DraftOut, allowed: dict[str, Source]) -> Checked:
        kept, dropped = [], []
        for s in draft.sentences:
            text = s.text.strip()
            if not text:
                continue
            ids = list(dict.fromkeys(s.source_ids))
            unknown = [i for i in ids if i not in allowed]
            cited = '\n'.join(allowed[i].text for i in ids if i in allowed)
            reason = ('근거 id 없음' if not ids else f'쓸 수 없는 재료 {unknown}' if unknown
                      else '틀 문장' if TEMPLATE_SENTENCE.search(text)
                      else '글 밖의 설명' if META_SENTENCE.search(text)
                      else '지원자에게 묻는 말' if ASKS_APPLICANT.search(text)
                      else '근거에 없는 숫자' if _unsupported_numbers(text, cited + '\n' + q.text) else '')
            if reason:
                dropped.append({'text': text, 'reason': reason})
                continue
            # 요건 이름표는 실제 공고 요건(J-…)만 남긴다. 근거로 공고 요건을 인용했으면 그것도 이름표다
            reqs = [i for i in dict.fromkeys([*s.requirement_ids, *ids])
                    if i.startswith('J-') and i in allowed and _tag_fits(allowed[i].label.split(' · ', 1)[-1], text)]
            # 지원자 경험을 쓴 문장만. 「귀사의 LLM·RAG 업무에 지원했습니다」처럼 회사를 향한 문장은 경험이 아니다
            if any(allowed[i].kind != 'posting' for i in ids) and not COMPANY_FACING.search(text):
                reqs += [i for i in allowed if i.startswith('J-') and i not in reqs
                         and _names_tech(allowed[i].label.split(' · ', 1)[-1], text)]
            kept.append({'text': text, 'source_ids': ids, 'part_key': s.part_key, 'new_paragraph': s.new_paragraph,
                         'requirement_ids': reqs})
        used = {i for s in kept for i in s['source_ids']}
        memo_unused = [allowed[i].text for i in allowed if allowed[i].kind == 'memo' and i not in used]
        answered = {_squash(s['part_key']) for s in kept}
        unanswered = [p.key for p in plan.parts if p.required and _squash(p.key) not in answered]
        over = bool(q.limit) and len(_join(kept)) > q.limit
        checked = Checked(kept, dropped, memo_unused, unanswered, over)
        checked.dense = [s['text'] for s in kept
                         if len(s['text']) > DENSE_CHARS or len(NUMBER.findall(s['text'])) >= DENSE_NUMBERS]
        chars = len(_join(kept))
        if q.limit and chars < q.limit * FILL_RATIO:
            checked.length = f'{chars}/{q.limit}자'
            checked.unused_lead = [f'[{i}] {allowed[i].text[:80]}' for i in plan.lead_source_ids + plan.support_source_ids
                                   if i in allowed and allowed[i].kind == 'resume' and i not in used][:6]
        if kept:
            checked.review = self.llm.review({
                'question': q.text.strip(),
                'parts': ', '.join(p.key for p in plan.parts),
                'length': f'{len(_join(kept))}자 / 제한 {q.limit or "없음"}',
                'sentences': '\n'.join(
                    f'{i}. {s["text"]}\n   근거: ' + ' | '.join(f'[{x}] {allowed[x].text}' for x in s['source_ids'])
                    for i, s in enumerate(kept)),
                'memo': '\n'.join(s.text for s in allowed.values() if s.kind == 'memo') or '없음',
                'notes': '\n'.join(f'- {n.get("question", "")}: {n.get("answer", "")}' for n in q.notes) or '없음',
            })
            # 모델이 아니라고 한 요구는 코드 검사(part_key 글자 맞춤)보다 모델 판단을 따른다
            if not checked.review.unanswered_parts:
                checked.unanswered = []
        return checked

    @staticmethod
    def _result(q, plan, checked: Checked, allowed, rewrites, seconds) -> dict[str, Any]:
        overstated = {o.index for o in checked.review.overstated}
        final = [s for i, s in enumerate(checked.kept) if i not in overstated]
        trimmed = 0
        while q.limit and final and len(_join(final)) > q.limit:
            final.pop()
            trimmed += 1
        draft = _join(final)
        asked = {_squash(n.get('question', '')) for n in q.notes}
        still_missing = set(checked.unanswered + checked.review.unanswered_parts)
        candidates = [m.question for m in plan.missing if m.part_key in still_missing or not final]
        candidates += checked.review.questions
        questions: list[str] = []
        for c in (c.strip() for c in candidates):
            if c and _squash(c) not in asked and not any(
                    SequenceMatcher(None, _squash(c), _squash(x)).ratio() >= SAME_QUESTION for x in questions):
                questions.append(c)
        return {
            'question_id': q.id, 'question': q.text, 'draft': draft, 'char_count': len(draft), 'limit': q.limit,
            'short': bool(q.limit) and len(draft) < q.limit * SHORT_RATIO,
            'sentences': [{**s, 'sources': [{'kind': allowed[i].kind, 'label': allowed[i].label, 'text': allowed[i].text}
                                            for i in s['source_ids']],
                           'requirements': [{'id': i[2:], 'label': allowed[i].label} for i in s['requirement_ids']]}
                          for s in final],
            'removed': checked.dropped + [{'text': checked.kept[o.index]['text'], 'reason': '근거보다 셈: ' + o.reason}
                                          for o in checked.review.overstated if o.index < len(checked.kept)],
            'trimmed_for_limit': trimmed, 'issues': checked.issues(), 'questions': questions[:MAX_QUESTIONS],
            'angle': plan.angle, 'parts': [p.key for p in plan.parts], 'rewrites': rewrites,
            'seconds': round(seconds, 1),
        }


def _join(sentences: list[dict[str, Any]]) -> str:
    out = ''
    for i, s in enumerate(sentences):
        sep = '' if i == 0 else ('\n' if s.get('new_paragraph') else ' ')
        out += sep + s['text']
    return out


def build_workflow_llm(settings):
    """질문 답 쓰기(question_answers.py)와 같은 모델 설정으로 계획 · 쓰기 · 검토 체인을 만든다."""
    from types import SimpleNamespace

    from langchain_openai import ChatOpenAI

    from app.question_workflow.prompts import OVERLAP_PROMPT, PLAN_PROMPT, REVIEW_PROMPT, TAG_PROMPT, WRITE_PROMPT

    model = ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, use_responses_api=True,
                       reasoning_effort=settings.openai_reasoning_effort, max_retries=0, timeout=180)

    def chain(prompt, out) -> Callable[[dict], Any]:
        return (prompt | model.with_structured_output(out, method='json_schema')).invoke

    return SimpleNamespace(plan=chain(PLAN_PROMPT, PlanOut), write=chain(WRITE_PROMPT, DraftOut),
                           review=chain(REVIEW_PROMPT, ReviewOut), overlap=chain(OVERLAP_PROMPT, OverlapsOut),
                           tag=chain(TAG_PROMPT, TagsOut))
