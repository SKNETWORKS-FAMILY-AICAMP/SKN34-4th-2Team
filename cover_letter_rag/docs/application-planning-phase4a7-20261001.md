# Phase 4A.7 — Planner Gap Sufficiency

브랜치: `feature/resume-review-quality`. 신규 migration/DB schema/RDS/React/UI/Analyzer/Writer/production API 변경 없음. 기존 미커밋 작업은 보존했고 커밋/푸시는 하지 않았다.

이번 변경 파일:

- `app/application_planning/models.py`
- `app/application_planning/engine.py`
- `tests/test_application_planning_contracts.py`
- `evaluation/application_planning_live.py`
- `evaluation/application_planning_phase4a7_recheck.py`
- `evaluation/application_planning_phase4a7_results/`의 라이브 JSON/사람 검토용 Markdown/사용량
- 본 보고서

## A. Root Cause

Phase4A.6 A2는 준비 경험을 실제 선택했지만, 그 경험을 **그 회사 입사를 목적으로** 수행했는지 불명확하다는 이유로 preparation_effort Gap을 만들었다. 실제 직무 준비 자료의 부재와 회사 특정 목적/인과관계 미확인을 혼동했다.

기존 prompt에는 준비와 동기를 분리하라는 방향이 있었지만 ‘현재 자료로 요구사항을 작성할 수 있는가’라는 판단 계약은 없었다. Validator는 참조/정보 출처를 검사했을 뿐 같은 요구를 충족했다고 생각하면서 재질문하는 모순을 직접 검사할 수 없었다. 기존 fact_type 존재 여부 억제 또한 실제 충분성을 대체할 수 없었다.

## B. Sufficiency Contract

Assignment에 작고 내부적인 `requirement_coverage` 목록을 추가했다. DB 모델이 아니라 기존 Plan JSON 내부의 Pydantic 계약이다.

```text
requirement: 해당 asks_for key
status: satisfied | partial | missing
evidence_ids: 선택한 승인 applicant 근거
reason: 해당 요구를 충족/미충족하는 의미 근거
blocking_missing_information: 작성에 꼭 필요한 미확인 자료; 없으면 빈 문자열
```

satisfied는 이미 신뢰성 있게 작성 가능한 상태다. partial은 항상 질문할 상태가 아니다. 단순 보완 가능성만 있다면 blocker와 Gap이 없다. missing/partial에서 실제 핵심 자료가 없을 때만 Gap을 만든다.

새 모델-facing scoped schema는 coverage를 필수로 받고, 승인 Evidence ID enum을 적용한다. 과거 저장된 offline/mock Plan은 coverage 없이도 읽을 수 있게 유지했다. Plan VERSION을 v4로 바꿔 기존 v3 live 캐시를 새 의미 계약으로 재사용하지 않는다. Analyzer 버전/계약은 그대로다.

[OpenAI structured output 공식 문서](https://developers.openai.com/api/docs/guides/structured-outputs)의 명시적 schema/enum 지침을 확인했다. Schema 적합성을 의미 정확성으로 간주하지는 않는다.

## C. Gap Generation Change

Planner는 각 요구를 먼저 평가하고 다음 경우에만 질문을 제안한다.

- 승인된 현재 자료로 신뢰성 있는 답변이 어렵다.
- 최종 작성에 중요한 구체적 자료가 실제 빠져 있다.
- Evidence/확인된 의사/회사 자료로 이미 해결되지 않았다.
- 기존 topic/경험 질문을 반복하지 않는다.
- 답변을 받으면 필요한 Writer material이 실제 늘어난다.

직무 관련 프로젝트/교육/학습/기술 활용은 preparation_effort로 활용할 수 있다. ‘귀사 입사를 위해 수행했다’는 목적을 증명하는 것으로 확장하지 않는다. 개인 동기와 회사 정보는 여전히 별도 출처다.

## D. Redundant Question Fix

충분한 준비 경험에 대해 목적/시점/추가 준비를 재확인하지 않도록 일반 의미 계약을 명시했다. 특정 fixture ID, Python 키워드 수, Evidence 개수로 sufficiency를 판정하거나 preparation Gap을 강제 삭제하지 않는다.

기존 `gap_key(category, target Experience, requirement)`와 질문 이력/답변 confirmation_key를 재사용한다. 이미 물은 같은 topic의 question_proposal은 비우고 부족 정보 기록 자체는 남긴다. 같은 실행의 다른 문항에서 같은 topic 질문이 또 나오면 중복 제안도 비운다. 한 번에 next_question은 최대 하나다.

이 방식은 같은 의미를 canonical topic key로 표현했을 때 문구가 달라도 중복을 막는다. 서로 다른 잘못된 key에 분류된 임의 자연어 질문의 의미 동일성까지 Python이 증명하는 것은 아니다. 그것은 Planner의 의미 분류 책임이다.

## E. Validator Changes

Deterministic 검사:

- coverage는 해당 문항의 asks_for 전체를 정확히 한 번씩 다뤄야 한다.
- coverage 근거는 그 문항에 실제 선택한 승인 Evidence여야 한다.
- satisfied + 같은 applicant 요구 Gap은 reject한다. Gap을 조용히 삭제해 PASS시키지 않는다.
- satisfied + blocking missing information은 reject한다.
- coverage가 있는 Gap은 essential blocker 설명이 있어야 한다. optional detail은 Gap 근거가 아니다.
- satisfied 경험 요구에는 승인 근거가 필요하다.
- satisfied result에는 선택한 실제 result Evidence가 필요하다.
- satisfied intent에는 topic_resolved 개인 의사 답변이 필요하다. 경험으로 동기를 충족시키지 못한다.
- 기존 scope/active/type/ownership 경계, 결과가 없을 때 result Gap 보완은 유지한다.

target_context는 applicant 요구와 다른 출처다. 개인 의사가 확인됐다고 회사 정보가 생긴 것은 아니므로 별도 회사 정보 Gap은 독립적으로 유지할 수 있다.

새 coverage가 있는 Plan에서는 ‘특정 fact_type 하나가 존재한다’는 과거 억제가 LLM의 실제 essential Gap 판단을 덮어쓰지 않도록 했다. 과거 mock/저장 자료의 동작은 호환 경로로 유지한다. Python은 문장 의미, 기술 관련성, 키워드 개수로 충분성을 판단하지 않는다.

## F. Unit Tests

순수 테스트 **82건 PASS**: 기존 70건 유지 + 12건 추가.

추가 사례는 충분한 준비/회사 동기 분리, satisfied와 Gap 모순, partial-but-improvable, optional clarification 차단, 일부 경험이 있어도 실제 역할 Gap 유지, action-only 결과 Gap, 허위 satisfied result/intent 차단, paraphrase topic dedupe, 새 wire coverage 필수, coverage 참조/완전성, fact_type 존재만으로 실제 Gap 억제 금지다.

테스트에서 의미 판단 결과를 명시적으로 공급해 계약을 검증했다. 이 단위 테스트가 실제 LLM 의미 성능을 증명한다고 주장하지 않는다.

## G. Set A Before / After

같은 fixture/질문/모델 **gpt-6-luna / medium**을 사용했다. Analyzer는 수정하지 않고 기존 A2 validated 분석을 재사용했다. 실제 새 Planner 호출은 1회다.

| 항목 | Phase4A.6 A2 | Phase4A.7 A1 |
|---|---|---|
| Q1 preparation_effort | 이미 경험 선택했으나 high 재질문 | satisfied, Gap/준비 추가 질문 없음 |
| Q1 company_motivation | applicant_intent Gap | 유지 |
| Q1 회사 정보 | target_context Gap | 유지 |
| Q2 desired_work | 확인된 답변 사용 | satisfied, 유지 |
| Q2 differentiating_strength | 추가 강점 확인 질문 | 실제 지표 판단/threshold 경험으로 satisfied, 불필요 질문 없음 |
| Q3 result | exp-B-3 오류 해결 | 동일한 실제 오류 해결 result 사용 |

Q1은 exp-C의 실제 데이터 분석/지표 판단/threshold 비교/signal 확인을 직무 준비로 사용한다. 회사 특정 목적이나 새로운 결과는 주장하지 않는다. 다음 질문은 개인 회사 지원 동기 하나다. Q3는 실제 오류 추적·수정 및 협업, 확인된 오류 해결을 사용하며 없는 수치/성과를 추가하지 않는다.

Agent가 raw/validated 결과와 근거를 직접 읽어 이번 재질문 교정 기준을 충족한다고 판단한 뒤 B/C를 요청했다. 사람 평가 칸은 비워 두었고 자동 JSON의 HUMAN_REVIEW_REQUIRED도 유지했다. 사용자가 직접 승인한 결과로 기록하지 않았다.

## H. Set B Regression

새 Planner 1회. 같은 exp-D를 재사용하지만:

- Q1: 팀원과 contract 조율 및 공동 문제 해결
- Q2: 오류 재현/양쪽 코드 수정이라는 기술 문제 해결
- Q3: Django API/React 화면 연동이라는 직접 구현

으로 초점과 core 근거가 다르다. 불필요한 질문 없음. 실제 D-3 해결 결과를 Q1/Q2에 사용하며, 결과를 요구하지 않는 Q3에는 결과를 강제 추가하지 않는다. 참조 검사 PASS, 숫자 후보 경고 0. 다른 초점이라도 최종 prose 중복 가능성은 이후 Writer에서 확인해야 한다.

## I. Set C Regression

새 Planner 1회. action/implementation은 선택하되 result 배열은 비었다. challenge/result 모두 missing이며 해당 경험의 구체적 난관과 실제 결과를 묻는다. 성과 수치, 속도/효율 향상 등 확인되지 않은 결과를 만들지 않았다.

story_focus의 ‘확인된 성과’는 작성 계획상 필요한 요소이지 확보된 결과가 아니다. result coverage가 missing인 상태에서 Writer가 이 계획 문구를 실제 성과 진술로 복사하면 안 된다. 이번에는 Writer를 만들지 않았다.

## J. LLM Usage

| Set | 새 API calls | input tokens | output tokens | API latency | pipeline latency |
|---|---:|---:|---:|---:|---:|
| A | 1 Planner | 3,050 | 2,393 | 21,657 ms | 21,704 ms |
| B | 1 Planner | 2,336 | 1,718 | 14,906 ms | 14,953 ms |
| C | 1 Planner | 1,994 | 806 | 8,531 ms | 8,578 ms |
| 합계 | **3** | **7,380** | **4,917** | **45,094 ms** | **45,235 ms** |

Analyzer API calls 0, 추가 Judge 0, A retry 0, 자동 retry 0. 출력 토큰은 provider usage 값이며 reasoning 사용량을 포함할 수 있다. 사용량 누락 호출 0. LangSmith tracing을 비활성화했다.

최초 실행은 자동 승인 검토에서 과거 승인 범위 문제로 차단되어 API 호출 0이었다. 이번 사용자의 첨부 20/24/27절 실행 지시와 가상 fixture 전체 내용을 확인해 새 명시적 승인 근거를 제시한 뒤 정상 실행했다. 우회하거나 거절된 명령을 간접 실행하지 않았다.

Runner는 같은 checkpoint를 덮어쓰거나 반복 샘플링하지 않는다. B/C는 A contract PASS 및 필수 Q1 조건 + 명시적 검토 flag 이후에만 허용한다. 최종 validator 교정 후 저장 결과를 offline으로 재검사했고 A/B/C 모두 동일 결과였다. 이 재검사 호출 수는 0이다.

## K. Full Regression

- 순수 core/Planner/맞춤 이력서 계약: **82 PASS**.
- 최종 로컬 PostgreSQL suite: **116 PASS**, 104.538초.
- React: **44개 파일 / 269 PASS**; React 변경 없음.
- `git diff --check`: PASS.

PostgreSQL suite에는 Application Workspace, Question/Answer/Plan, RecruitRole, Experience/Evidence persistence, ownership, stale/cache/concurrency, Local E2E mock API가 포함된다. 기존 테스트 runner의 격리 테스트 DB 생성/기존 migration 구성/제거 외에 migration 실행 없음. migration graph는 기존 0014까지다. RDS 및 production DB 접속 없음.

## L. Local E2E Regression

기존 mock 기본값과 recorded A2 replay를 변경하지 않았다. 새 coverage는 기존 UI 계약에 추가적인 내부 정보일 뿐이며 UI는 기존 필드로 계속 표시한다. 새 live Planner도 동일한 StructuredPlanningClient 경로에서 동작한다.

정확한 기존 loopback Django 프로세스를 확인해 8002 서버만 재시작했다. 실제 HTTP login/catalog/Application reopen/mock plan 요청 모두 PASS, mock mode 유지, 문항 3개/Tailored ID 2 유지, 데이터 개수 변화 없음. credential/token은 출력하지 않았다.

**주의:** 기본 mock은 과거 A2 결과를 재생하므로 화면의 과거 preparation Gap/semantic NO-GO 안내가 이번 새 live 검증 결과로 자동 교체되지는 않는다. 이번 작업의 React/UI/API/fixture 기록 범위를 넓혀 과거 결과를 덮어쓰지 않았다. 새 결과 확인은 이번 evaluation 자료에서 한다.

## M. Remaining Risks

1. 세 개의 single sample 검증이며, 모든 사용자 문항/경험에서 재질문이 없어졌다는 통계적 보장은 아니다.
2. LLM이 실제 부족한 정보를 satisfied로 잘못 판단할 가능성은 남아 있다. Validator는 참조/상태 모순을 검사할 뿐 의미 판정을 대체하지 않는다.
3. phase4A.6 과거 mock 데이터는 유지했다. UI에 최신 검토 샘플을 동기화하는 별도 작업은 하지 않았다.
4. 회사 지원 동기와 회사 정보, C의 결과는 실제로 없다. 인터뷰를 줄이려고 이 정보를 만들어서는 안 된다.
5. 이야기 초점/근거 선택이 좋아도 최종 문장 품질은 아직 검증하지 않았다. Writer 구현은 이번 범위 밖이다.
6. 사람 검토 칸은 비어 있다. Agent 검토와 사용자의 최종 제품 판단을 구분한다.

## N. Phase 4B Go / No-Go

**Phase4A.7의 재질문 교정과 A/B/C 회귀 기준: PASS.** 준비 경험 재질문은 사라졌고, 필요한 동기/회사 정보/결과 Gap은 유지됐다.

그러나 사용자가 요구한 ‘좋은 Writer가 최종 답변을 작성하기에 충분한 자료가 A/B/C 모두 있는가’를 자료 완비 기준으로 엄격히 적용하면:

- A: 준비/기술 경험은 충분하지만 회사 동기/회사 정보는 추가 입력 필요.
- B: YES — 선택한 근거로 작성 가능한 협업/문제 해결/직접 구현 자료가 있다.
- C: NO — 요구된 실제 결과와 난관 자료가 없으므로 완성 답변에 부족하다.

따라서 **자료 완비 조건의 Phase4B는 아직 NO-GO**다. 이는 C의 결과를 지어내거나 진짜 Gap을 지워서 해결할 문제가 아니다. 필요한 자료를 확보하거나, 다음 지시에서 ‘충분하지 않을 때 작성 보류하는 Writer를 구현한다’는 착수 기준을 명확히 해야 한다. 이번에 Writer 구현으로 범위를 넓히지 않았다.

반대로 Planner 산출물이 ‘작성 가능한 근거와 반드시 확인해야 할 자료를 좋은 Writer에게 정확히 전달하는가’라는 계획 품질 기준에서는 A/B/C 모두 유효하다. 이 판단과 최종 답변 자료가 모두 확보됐다는 판단은 다르다.
