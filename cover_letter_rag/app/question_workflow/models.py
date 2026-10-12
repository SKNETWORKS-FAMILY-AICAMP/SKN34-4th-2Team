"""공고 맞춤 첨삭 흐름의 입출력 모양. 모델이 내는 것(…Out)과 화면에 돌려줄 것을 나눈다."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import Field

from app.models import StrictModel

SourceKind = Literal['resume', 'memo', 'note', 'posting']


@dataclass(frozen=True)
class Source:
    """답에 쓸 수 있는 재료 한 조각. 문장은 이 id 로 근거를 단다."""

    id: str
    kind: SourceKind
    label: str
    text: str
    question_id: str = ''  # 메모 · 질문 답은 그 문항에서만 쓴다
    group: str = ''  # 그 문항의 묶음 — 같은 묶음 하위 문항끼리는 메모 · 질문 답을 함께 쓴다


@dataclass
class QuestionInput:
    id: str
    text: str
    limit: int | None = None
    memo: str = ''
    notes: list[dict[str, str]] = field(default_factory=list)  # 앞서 낸 질문에 학생이 한 답 [{question, answer}]
    # 상위 문항(묶음 제목) — 「목표 달성 경험 › ①목표와 이유 / ②문제와 해결」처럼 한 주제를 나눈 하위 문항이면 그 주제
    group: str = ''
    # 지금 답 칸에 있는 글(학생이 쓴 것 · 저장한 초안) — 문항별로 쓸 때 다른 문항에서 이미 쓴 이야기를 되풀이하지 않게
    written: str = ''


# ── 1. 계획: 문항 전부를 한 번에 보고 문항마다 쓸 재료를 나눈다 ──

class PartOut(StrictModel):
    key: str = Field(description='문항이 묻는 것 하나를 짧게. 예: 지원 동기, 입사 준비 노력, 협업 과정, 결과')
    quote: str = Field(description='그 요구가 적힌 문항 원문의 일부를 그대로')
    required: bool = True


class MissingOut(StrictModel):
    part_key: str = Field(description='재료가 없는 요구(parts 의 key)')
    question: str = Field(description='학생에게 물을 한 문장. 무엇을 · 어떻게 · 결과가 어땠는지 답할 수 있게')


class BeatOut(StrictModel):
    point: str = Field(description='답의 이 대목에서 말할 것 한 줄. 예: Stacking 이 검증에서 무너진 것을 확인함')
    part_key: str = Field(description='이 대목이 답하는 요구(parts 의 key)')
    source_ids: list[str] = Field(default_factory=list, description='이 대목의 근거 재료 id. 재료가 없으면 빈 목록')
    question: str = Field(default='', description='재료가 없을 때만 학생에게 물을 질문 한 문장. 재료가 있으면 빈 문자열')


class QuestionPlanOut(StrictModel):
    question_id: str
    parts: list[PartOut] = Field(min_length=1)
    # 공고마다 문항이 다르다 — 정해진 유형이 아니라 그 문항 문구에서 읽는 사람이 확인할 것을 뽑고, 그걸 채우는 뼈대를 세운다
    checks: list[str] = Field(default_factory=list,
                              description='이 문항을 읽는 채용 담당자가 답에서 확인하려는 것 2~4개. 문항 문구에서 끌어낸다')
    outline: list[BeatOut] = Field(default_factory=list, description='checks 를 채우는 답의 흐름 4~7개, 읽히는 순서대로')
    lead_source_ids: list[str] = Field(description='이 답의 중심 경험 재료 id. 다른 문항과 중심이 겹치지 않게')
    support_source_ids: list[str] = Field(default_factory=list, description='곁들일 재료 id')
    angle: str = Field(description='이 답이 보여 줄 것 한 문장. 같은 경험을 여러 문항에 쓰면 문항마다 다른 면')
    missing: list[MissingOut] = Field(default_factory=list, description='outline 의 question 으로 다 묻지 못한 것만. 보통 빈 목록')


class PlanOut(StrictModel):
    questions: list[QuestionPlanOut]


# ── 2. 쓰기 ──

class SentenceOut(StrictModel):
    text: str = Field(description='답 문장 하나. 「-습니다」체')
    source_ids: list[str] = Field(description='이 문장의 근거 재료 id. 하나 이상')
    part_key: str = Field(description='이 문장이 답하는 요구(parts 의 key)')
    new_paragraph: bool = Field(default=False, description='이 문장에서 문단을 새로 시작하면 true')
    requirement_ids: list[str] = Field(
        default_factory=list,
        description='이 문장 속 경험이 보여 주는 공고 요건의 재료 id(J-…). 요건 이름만 꺼낸 문장이나 닿는 요건이 없으면 빈 목록')


class DraftOut(StrictModel):
    sentences: list[SentenceOut]


# ── 3. 검토: 근거보다 세게 말한 문장 · 빠진 요구 · 흐름 · 학생에게 물을 것 ──

class OverstatedOut(StrictModel):
    index: int = Field(description='문장 번호(0부터)')
    reason: str


class ReviewOut(StrictModel):
    overstated: list[OverstatedOut] = Field(default_factory=list)
    unanswered_parts: list[str] = Field(default_factory=list, description='답하지 않은 요구의 key')
    flow_issues: list[str] = Field(default_factory=list, description='반복 · 나열 · 어색한 연결')
    memo_missing: list[str] = Field(default_factory=list, description='답에 들어가지 않은 메모 내용')
    questions: list[str] = Field(default_factory=list, description='더 좋은 답에 필요한 재료를 묻는 질문, 최대 3개')


# ── 4. 한 벌 검토: 자소서 전체에서 같은 이야기를 두 문항 이상 자세히 쓴 곳 ──

class OverlapOut(StrictModel):
    story: str = Field(description='겹친 이야기를 짧게 부르는 이름. 예: 경력 7년 공고 추천 개선')
    question_ids: list[str] = Field(min_length=2, description='그 이야기를 자세히 쓴 문항 id')
    keep: str = Field(description='그 이야기를 자세히 남길 문항 id — 문항이 묻는 것과 가장 잘 맞는 곳')
    reason: str = Field(description='keep 을 고른 이유 한 문장')


class OverlapsOut(StrictModel):
    overlaps: list[OverlapOut] = Field(default_factory=list)


# ── 5. 이름표: 다 쓴 문장마다 보여 주는 공고 요건 — 근거가 된 말을 문장에서 그대로 따온다 ──

class TagEvidenceOut(StrictModel):
    requirement_id: str = Field(description='공고 요건 id')
    evidence: str = Field(description='그 요건을 보여 주는 말을 문장에서 그대로 따온 것(몇 글자~한 구절)')


class SentenceTagOut(StrictModel):
    index: int
    tags: list[TagEvidenceOut] = Field(default_factory=list)


class TagsOut(StrictModel):
    sentences: list[SentenceTagOut] = Field(default_factory=list)
