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
    "- sql_query: SQL 조회 문제(수업 자료가 SQL일 때만). 브라우저의 SQLite에서 채점한다.\n"
    "  setupSql은 수업에 나온 테이블 이름·열 이름 그대로 2~3개 테이블을 만들고 행을 5~15개씩 넣는 스크립트.\n"
    "  SQLite에서 도는 표준 SQL로 쓴다(AUTO_INCREMENT · ENGINE · COMMENT · USE 금지, 기본 키는 INTEGER PRIMARY KEY).\n"
    "  referenceSolution은 SELECT 문 하나(수업에서 배운 WHERE · ORDER BY · GROUP BY · JOIN 등을 쓴다). 결과는 1~20행.\n"
    "  NOW() · RAND() 처럼 실행할 때마다 달라지는 함수는 쓰지 않는다.\n"
    "  채점은 결과 값만 비교한다(열 이름은 안 본다). 그래서 prompt에 쓸 테이블, 결과에 낼 열과 그 순서,\n"
    "  정렬 기준을 모두 적는다(예: 「tbl_menu에서 가격이 10000원 이상인 메뉴의 이름과 가격을 가격 높은 순으로」).\n"
    "  starterCode는 비워 두거나 `-- 여기에 조회문을 쓰세요` 한 줄\n"
    "- web_task: 웹 실습(수업 자료가 HTML · CSS 또는 페이지를 다루는 JavaScript일 때). 학생은 HTML 문서를 고쳐 요구대로 만든다.\n"
    "  starterCode는 <style>을 포함한 짧은 HTML 문서(40줄 이하), referenceSolution은 요구대로 고친 전체 문서.\n"
    "  HTML · CSS 수업이면 <script>를 쓰지 않는다. 파일 지시에 'HTML + JavaScript'라고 적힌 몫은 문서 안의 <script>(바깥 src 금지)로\n"
    "  페이지를 다루는 문제를 낸다(요소 찾기 · 글자 · 클래스 · 인라인 스타일 바꾸기 · 이벤트 처리). 이때 검사문은 먼저 click(선택자) ·\n"
    "  type(선택자, '글자')로 동작을 흉내 낸 뒤 결과를 본다. 예: check(type('#item', '사과') && click('#add') && count('#list li') === 1, '누르면 항목이 생겨요');\n"
    "  스크립트가 바꾼 스타일은 css() 대신 style(선택자, 'CSS 속성'), 클래스는 hasClass(선택자, '이름'), 입력값은 value(선택자)로 본다.\n"
    "  모양을 고루 섞는다 — 빈칸 채우기(starterCode의 /* ① */ · <!-- ① --> 자리를 채움), 고치기(잘못된 속성 · 태그 · 선택자 하나),\n"
    "  처음부터 만들기(요구한 요소를 새로 씀).\n"
    "  hiddenTests는 검사문 2~5줄, 한 줄에 하나: check(조건, '학생에게 보일 한국어 문장');\n"
    "  조건에는 이 도우미만 쓴다: $(선택자) · $$(선택자) · has(선택자) · count(선택자) · text(선택자) · attr(선택자, 속성) · css(선택자, 'CSS 속성').\n"
    "  한 줄 식만 쓴다(반복문 · 함수 정의 · => 금지). 예: check(css('.menu', 'display') === 'flex', '메뉴가 가로 한 줄로 놓여요');\n"
    "  css()는 그 요소에 직접 선언한 개별 속성만 검사한다(display · justify-content · align-items · flex-direction · position ·\n"
    "  text-align · font-weight · width · margin-top · grid-template-columns 같은 것). 부모에게서 물려받는 값(font-size 등)과\n"
    "  줄임 속성(margin · padding · border · background · font · list-style)은 검사하지 않는다. 색은 'rgb(0, 0, 255)' 꼴, 길이는 '16px' 꼴,\n"
    "  grid-template-columns는 쓴 그대로('1fr 2fr')다. 화면 크기에 따라 달라지는 실제 너비 · 위치는 검사하지 않는다.\n"
    "  검사하는 선택자 · id · class · 태그 · 글자는 모두 prompt나 starterCode에 나온 것이어야 한다. 속성값은 그 결과로 설명해도 된다\n"
    "  (예: '메뉴가 가로 한 줄로 놓이고 가운데 정렬되게').\n"
    "- JavaScript 코드 문제: 파일 지시에 'JavaScript'라고 적힌 몫은 code_output · code_blank · code_fix · code_write · code_scratch를\n"
    "  JavaScript로 내고 문제마다 \"language\": \"javascript\"를 넣는다. 위 파이썬 규칙 대신 이 규칙을 따른다:\n"
    "  수업의 핵심 JavaScript만 쓴다(자료형 · 형 변환 · 연산자 · 스코프 · 함수 · 배열 · 객체). document · window · require · fetch ·\n"
    "  setTimeout · Math.random · Date.now · prompt · alert · eval은 쓰지 않는다. code_output은 console.log로 숫자 · 짧은 글자 · true/false를\n"
    "  한두 줄만 찍는다. hiddenTests는 한 줄에 하나씩 assert(조건, '학생에게 보일 한국어 문장'); 2~4개(assert는 채점기가 준다,\n"
    "  code_scratch는 3~5개). 빈칸은 __1__ · __2__ 로 비운다. 코드와 테스트는 한 스크립트로 이어서 돈다.\n"
    "hiddenTests는 starterCode·referenceSolution 뒤에 같은 변수 공간에서 이어서 실행된다(web_task는 문서를 읽은 뒤 검사문만 돈다).\n"
    "hiddenTests에 정답 코드를 다시 쓰지 않는다.\n"
)

# 2026-09-29 코드 문제 138개를 문제 문장 · 시작 코드만 보고 다시 풀어 보니 10개(7%)가 맞게 풀어도 떨어졌다.
# 테스트가 문장에 없는 키 이름 · 형식 · 자료형을 요구하거나, 수업 코드의 값 · 공식을 외워야 하거나,
# 시작 코드 설명과 테스트가 어긋나거나, 테스트가 쓰는 모듈을 import 하지 않았다(모범답안의 import 에 기댐).
PROBLEM_RULES = (
    "문제 규칙 (학생은 문제 문장과 시작 코드만 보고 푼다):\n"
    "- 수업에서 배운 개념·기법을 새 상황에 적용하는 문제를 낸다. 수업 코드의 세부(키 이름 · 데이터 값 · 독특한 공식)를\n"
    "  기억해야만 풀 수 있는 문제는 내지 않는다. '수업처럼', '수업 코드와 같은' 같은 말을 답의 근거로 쓰지 않는다\n"
    "- 테스트가 요구하는 키 이름 · 데이터 값 · 공식 · 입출력 형식 · 입력 자료형(리스트인지 numpy 배열인지 등)은 모두\n"
    "  prompt나 starterCode에 적는다\n"
    "- hiddenTests는 prompt와 starterCode에 적힌 조건만 검사한다. 적히지 않은 형식 · 자료형 · 경계값을 몰래 검사하지 않는다\n"
    "- hiddenTests가 쓰는 모듈(math, numpy 등)은 hiddenTests 안에서 import 한다\n"
    "- starterCode의 docstring · 주석은 hiddenTests가 기대하는 반환값과 같게 쓴다\n"
    "- 문제마다 다른 개념을 묻는다. 같은 함수 · 같은 코드를 종류만 바꿔(빈칸 → 버그 고치기 → 처음부터 짜기) 다시 내지 않는다\n"
    "- 연습(exercise)과 문제(question) 파일이 같은 내용을 다루면 그 내용은 한 번만 낸다\n"
    "- 테이블 이름 · 값만 바꾼 같은 틀의 문제를 되풀이하지 않는다\n"
)

SCHEMA = (
    '{{"problems": [{{\n'
    '  "kind": "concept | code_output | code_blank | code_fix | code_write | code_scratch | sql_query | web_task",\n'
    '  "topic": "짧은 주제 (예: 딕셔너리 컴프리헨션)",\n'
    '  "sourceFiles": ["근거가 된 수업 파일 경로"],\n'
    '  "prompt": "학생에게 보일 문제 문장",\n'
    '  "choices": [], "answerIndex": 0,\n'
    '  "starterCode": "", "expectedStdout": "", "blankAnswers": [],\n'
    '  "referenceSolution": "", "hiddenTests": "", "setupSql": "",\n'
    '  "explanation": "정답 해설 2~3문장",\n'
    '  "language": "python | javascript (코드 문제만)"\n'
    "}}]}}"
)

GENERATE_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "당신은 AI 부트캠프 수업 자료로 복습 실습 문제를 만드는 출제자입니다.\n"
        "반드시 수업 자료에 나온 개념과 코드 패턴으로만 출제하고, 자료에 없는 내용은 내지 마세요.\n"
        "문제 문장과 해설은 한국어로 씁니다. 응답은 JSON 객체 하나입니다.\n\n"
        + RULES + "\n" + PROBLEM_RULES + "\n" + KIND_GUIDE,
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
        + RULES + "\n" + PROBLEM_RULES + "\n" + KIND_GUIDE,
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
    막히거나 코드 문제를 포기했고, gpt-5.6-luna는 18문제가 한 번에 통과했다. 지금 기본값은 챗봇과 같은 gpt-6-luna."""
    return os.getenv("PRACTICE_MODEL", "").strip() or "gpt-6-luna"


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
    if isinstance(data.get("error"), str) and data["error"].strip():
        # 모델이 출제를 거절하며 이유를 적을 때가 있다(요청 개수와 자료가 안 맞을 때 등) — 버리지 말고 남긴다
        batch.rejected.append(f"모델이 출제하지 않은 이유: {data['error'].strip()[:300]}")
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
