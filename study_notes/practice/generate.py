"""수업 자료 → 실습 문제 초안(LLM).

노트 생성 호출과 따로 부른다. 노트는 마크다운, 문제는 JSON이라 한 응답에 섞으면
파싱이 흔들리고 문제만 다시 만들 수도 없다.

LLM이 쓴 정답 출력은 믿지 않는다. verify.py가 실제로 돌려 본 결과로 채운다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from study_notes.pipeline import LEARNER_LEVEL, Material, pack_materials, response_text
from study_notes.practice.increments import KIND_MIX, kind_counts_text
from study_notes.practice.models import PracticeProblem, parse_draft

RULES = (
    "코드 규칙 (브라우저 안의 파이썬에서 채점하므로 반드시 지킨다):\n"
    "- 표준 라이브러리(collections, itertools, math, re, json, dataclasses 등)와 numpy, pandas만 쓴다\n"
    "- 파일 읽기·쓰기, 네트워크, input(), os/sys/subprocess 금지\n"
    "- 수업 자료가 파일을 읽는다면, 그 데이터를 흉내 낸 작은 샘플을 코드 안에 리스트·딕셔너리로 직접 넣는다\n"
    "  (pandas면 pd.DataFrame({{...}})로 만든다. read_csv 금지)\n"
    "- random은 random.seed(숫자)를 먼저 부른다. 현재 시각(datetime.now 등)은 쓰지 않는다\n"
    "- 1초 안에 끝나는 짧은 코드 (10~20줄)\n"
    "- torch·transformers·cv2·openai 같은 모델·영상 라이브러리는 쓸 수 없다. 그런 수업이면 모델 호출은 빼고\n"
    "  수업 코드 안의 순수 계산 부분으로 코드 문제를 낸다. 예: 합성곱 출력 크기 공식, IoU 계산,\n"
    "  numpy 코사인 유사도로 top-k 고르기, 파일 이름에서 정규식으로 번호 뽑기, 이미지 배열 shape 바꾸기\n"
    "- 그런 계산 부분도 없으면 코드 문제 대신 concept 문제를 낸다\n"
    "- 수업 내용과 상관없는 일반 문법 문제(예: 리스트 합 구하기, arange 출력)는 내지 않는다\n"
)

KIND_GUIDE = (
    "문제 종류:\n"
    "- concept: 개념 확인 객관식. choices 4개, answerIndex(0부터)\n"
    "- code_output: 코드를 읽고 출력을 예상하는 문제. starterCode는 print로 숫자·짧은 값 1~2줄만 출력한다.\n"
    "  학생이 손으로 적어야 하므로 딕셔너리·배열 전체나 긴 소수를 출력하지 않는다(소수는 round(x, 2)).\n"
    "  expectedStdout에 네가 예상한 출력을 적는다\n"
    "- code_blank: 빈칸 채우기. starterCode에서 핵심 식 1~3곳을 __1__, __2__ 로 비운다(번호는 1부터).\n"
    "  blankAnswers는 빈칸 순서대로 들어갈 한 줄짜리 짧은 식, hiddenTests는 assert 문 2~4개.\n"
    "  빈칸은 수업의 핵심(정규식 패턴, 인덱스, 조건식, 공식)에 둔다. 변수 이름 같은 사소한 곳은 비우지 않는다\n"
    "- code_fix: 디버깅. 수업에서 실수하기 쉬운 버그가 딱 하나 있는 코드를 고치는 문제\n"
    "  (예: 인덱스 하나 차이, 잘못된 비교 키, 채널 순서, 반복문 종료 조건). 문제 문장에 증상을 적는다.\n"
    "  starterCode는 버그가 있는 코드, referenceSolution은 고친 전체 코드, hiddenTests는 assert 문 2~4개\n"
    "- code_write: 함수를 직접 작성하는 문제. starterCode는 함수 이름·인자·docstring과 pass만 있는 코드,\n"
    "  referenceSolution은 완성한 함수, hiddenTests는 assert 문 2~4개 (경계값 하나 포함)\n"
    "- code_scratch: 빈 에디터에서 함수 전체를 처음부터 짜는 문제. 학생은 뼈대를 보지 못하므로 prompt에\n"
    "  함수 이름과 인자(예: `max_pool2x2(matrix)`), 예시 입력과 그 결과를 한 쌍 이상 반드시 적는다.\n"
    "  수업 코드의 핵심 흐름(반복·조건·자료 구조 다루기)을 학생이 직접 구현하게 한다.\n"
    "  starterCode는 학생이 「뼈대 받기」를 눌렀을 때만 보이는 함수 이름·인자·docstring과 pass만 있는 코드,\n"
    "  referenceSolution은 5~20줄의 완성 함수, hiddenTests는 assert 문 3~5개 (prompt의 예시 하나, 경계값 하나 포함)\n"
    "hiddenTests는 starterCode·referenceSolution 뒤에 같은 변수 공간에서 이어서 실행된다.\n"
    "hiddenTests에 정답 코드를 다시 쓰지 않는다.\n"
)

SCHEMA = (
    '{{"problems": [{{\n'
    '  "kind": "concept | code_output | code_blank | code_fix | code_write | code_scratch",\n'
    '  "topic": "짧은 주제 (예: 딕셔너리 컴프리헨션)",\n'
    '  "sourceFiles": ["근거가 된 수업 파일 경로"],\n'
    '  "prompt": "학생에게 보일 문제 문장",\n'
    '  "choices": [], "answerIndex": 0,\n'
    '  "starterCode": "", "expectedStdout": "", "blankAnswers": [],\n'
    '  "referenceSolution": "", "hiddenTests": "",\n'
    '  "explanation": "정답 해설 2~3문장"\n'
    "}}]}}"
)

GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 AI 부트캠프 수업 자료로 복습 실습 문제를 만드는 출제자입니다.\n"
        "반드시 수업 자료에 나온 개념과 코드 패턴으로만 출제하고, 자료에 없는 내용은 내지 마세요.\n"
        "문제 문장과 해설은 한국어로 씁니다. 응답은 JSON 객체 하나입니다.\n\n"
        + RULES + "\n" + KIND_GUIDE,
    ),
    (
        "human",
        "수업 범위: {scope_label}\n"
        "학습자 수준: {learner_level}\n\n"
        "수업 자료:\n{materials}\n\n"
        "다음 개수로 출제하세요: {kind_counts}.\n"
        "{focus_note}\n"
        "응답 형식:\n" + SCHEMA,
    ),
])

REPAIR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 실습 문제 검수자입니다. 아래 문제들은 실제로 실행해 보니 검증에 실패했습니다.\n"
        "실패 이유를 보고 같은 주제·같은 종류로 고쳐서 다시 내세요. 고칠 수 없으면 새 문제로 바꿔도 됩니다.\n"
        "응답은 JSON 객체 하나이고, 받은 문제와 같은 순서·같은 개수로 냅니다.\n\n"
        + RULES + "\n" + KIND_GUIDE,
    ),
    (
        "human",
        "실패한 문제와 이유:\n{failures}\n\n응답 형식:\n" + SCHEMA,
    ),
])


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, response: Any) -> None:
        meta = getattr(response, "usage_metadata", None) or {}
        self.calls += 1
        self.input_tokens += int(meta.get("input_tokens", 0))
        self.output_tokens += int(meta.get("output_tokens", 0))


@dataclass
class DraftBatch:
    problems: list[PracticeProblem] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def practice_model_name() -> str:
    """노트와 따로 둔다. 2026-09 멀티모달 수업 3일 비교에서 gpt-4o-mini는 torch·cv2를 쓰다
    막히거나 코드 문제를 포기했고, gpt-5.6-luna는 18문제가 한 번에 통과했다."""
    return os.getenv("PRACTICE_MODEL", "").strip() or "gpt-5.6-luna"


@lru_cache
def _llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=practice_model_name(),
        max_retries=1,
        # 하루 12문제를 한 번에 받는다 — 8문제 때의 120초로는 빠듯하다
        timeout=240,
        model_kwargs={"response_format": {"type": "json_object"}},
    )


def _parse_batch(text: str) -> DraftBatch:
    batch = DraftBatch()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        batch.rejected.append(f"JSON 파싱 실패: {exc.msg}")
        return batch
    raws = data.get("problems") if isinstance(data, dict) else None
    if not isinstance(raws, list):
        batch.rejected.append("problems 배열이 없음")
        return batch
    for raw in raws:
        problem, reason = parse_draft(raw)
        if problem:
            batch.problems.append(problem)
        else:
            batch.rejected.append(reason)
    return batch


def generate_drafts(
    *,
    scope_label: str,
    materials: list[Material],
    usage: Usage,
    focus_note: str = "",
    kind_counts: str = "",
) -> DraftBatch:
    """focus_note — 파일 단위 출제(increments.DayPlan.focus_note)의 「새 부분에서만 · 파일별 개수」 지시
    kind_counts — 종류별 개수 글. 비우면 하루 구성(KIND_MIX: 개념 2 + 코드 10)"""
    if not materials:
        raise ValueError("출제할 수업 자료가 없습니다.")
    response = (GENERATE_PROMPT | _llm()).invoke({
        "scope_label": scope_label,
        "learner_level": LEARNER_LEVEL,
        "materials": pack_materials(materials),
        "focus_note": focus_note,
        "kind_counts": kind_counts or kind_counts_text(KIND_MIX),
    })
    usage.add(response)
    return _parse_batch(response_text(response))


def repair_drafts(failures: list[tuple[PracticeProblem, str]], *, usage: Usage) -> DraftBatch:
    if not failures:
        return DraftBatch()
    listing = [
        {"problem": problem.to_json(), "failure": reason}
        for problem, reason in failures
    ]
    response = (REPAIR_PROMPT | _llm()).invoke({
        "failures": json.dumps(listing, ensure_ascii=False, indent=1),
    })
    usage.add(response)
    return _parse_batch(response_text(response))
