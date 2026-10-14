# Phase 4A.6 — Application Planner 교정 결과

브랜치: `feature/resume-review-quality`. 신규 migration/DB 모델/React/Writer/RDS
변경 없음. 기존 미커밋 작업은 보존했다. **계약 검증 PASS와 의미 품질 PASS를
구분하며, 이번 Phase 전체 완료 및 Phase4B GO는 선언하지 않는다.**

## A. Root Cause

기존 Phase4A.5 Set A는 Q2에 exp-C만 선언하면서 exp-A 근거를 섞었고,
verification인 exp-C-5를 result로 사용했다. Q2 differentiating_strength를
applicant_intent로 분류하면서 경험 target까지 붙였다. 당시 Python validator가
첫 scope 위반을 차단했으므로 잘못된 Plan은 저장/승인되지 않았다.

원인은 검사가 전혀 없었던 것이 아니라 모델에게 전달된 책임 경계가 불명확했던
점이다. 추상적인 '승인된 근거만 사용'은 '보조 근거도 선언된 경험에 속해야 함'을
충분히 설명하지 않았고, 측정/발견과 결과를 구분할 의미 기준도 약했다.
기존 'high gap에는 경험을 특정한 질문' 지시는 의사/회사 정보 Gap과 충돌했다.

추가로 이번 A 1차 실행에서 core max=2를 맞추려고 여러 ID를 한 문자열에 합치는
계약 오류가 실제 발생했다. 결과를 쪼개거나 자동 고치지 않고 승인 ID enum으로
모델의 출력 범위를 제한한 뒤 마지막 1회 재검증했다.

## B. Contract Changes

- 전체 Plan shape는 유지: assignment, primary/core/supporting/result, gaps,
  story_focus, rationale. 추가 분석 단계나 Writer 호출 없음.
- Gap.category는 `experience_evidence / applicant_intent / target_context`.
- 과거 `applicant_evidence`는 입력 경계에서 새 이름으로 변환해 오프라인 자료를
  읽을 수 있다. 새 schema에는 과거 이름을 노출하지 않는다.
- VERSION은 application-plan-v3. 이전 v2 캐시를 의미가 달라진 계획으로 재사용하지
  않는다. Analyzer prompt/contract/ANALYSIS_VERSION은 변경하지 않았다.
- primary/result/core/supporting 필드에 scope/의미/atomic-ID 설명을 추가했다.
- 호출별 ScopedApplicationPlan은 기존 output을 상속하되, 경험/근거 ID를 입력의
  승인 목록 enum으로 제한한다. 원소 하나는 ID 하나이며 문자열을 임의 분해하지
  않는다. result enum에는 active fact_type=result만 들어간다. 결과가 없으면 빈
  배열만 허용한다. API 호출 수는 증가하지 않는다.

Structured-output schema 설계에 [OpenAI 공식 문서](https://developers.openai.com/api/docs/guides/structured-outputs)의
명확한 필드 설명과 enum 계약을 참고했다. 이 구현에서 schema 적합성은 의미
정확성의 대체물이 아니며, 실제 A의 결과도 이 구분을 적용해 판단한다.

## C. Experience Scope Fix

각 assignment의 core/supporting/result 모든 ID는 선언된 primary Experience의
근거여야 한다. 여러 Experience를 쓰려면 모두 선언해야 한다. Unknown, 다른
Experience, 중복 primary, 겹치는 core/supporting tier는 거부한다.
같은 Experience를 다른 focus로 재사용하는 기존 정책은 유지했다.

wire enum은 잘못된 ID/쉼표로 묶인 ID를 방지한다. 문항과 경험의 의미적 적합성은
LLM의 책임이며 Python으로 '키워드가 맞으니 이 프로젝트'를 강제하지 않았다.

## D. Result Semantics Fix

Prompt는 action/implementation=수행, verification=측정·비교·확인,
result=행동 이후 확인된 변화/달성을 구분한다. 숫자 없는 오류 해결도 실제
result Evidence이면 허용한다. '적용/비교했다'를 결과로 승격하지 않는다.

Python은 active fact_type=result를 검사한다. 결과가 필요한 문항에서 결과가
없으면 result Gap을 생성하고, 이미 있는 결과를 선택하지 않으면 명시적 설명을
요구한다. result가 core/supporting에도 중복 선택되어야 한다는 조건은 없다.
근거 텍스트 자체의 fact_type 오류까지 regex로 판정하는 기능은 추가하지 않았다.

## E. Gap Classification Fix

- 경험 사실 Gap: 실제 선택한 Experience target 필수.
- 사용자 의사 Gap: target=None. 회사 동기/희망 등 의사 topic을 경험 사실로
  분류하거나 강점/행동/결과 topic을 의사로 분류하면 거부한다.
- 회사/직무 자료 Gap: target=None. next_question으로 반환하지 않는다.
- target_context/company_motivation Gap만 있다고 개인 지원동기가 해결됐다고
  보지 않는다. 필요한 applicant_intent Gap은 별도로 남긴다.
- 확인된 의사 답변, 과거 질문 dedupe, 실제 존재하는 근거에 대한 반복 질문
  억제는 유지한다. 과거 dedupe key의 이름도 변환한다.

한 번에 반환하는 next_question은 최대 하나다. Gap 제안 여러 개를 전부 사용자에게
질문한 것처럼 표시하지 않는다. 다만 A의 **Q1 준비 노력 Gap 과잉 보수성은 남아 있다**.

## F. Deterministic Validator Changes

scope, active state, fact_type, IDs, schema를 검사한다. 소유권은 기존 Django
planning_input이 소유한 bound Experience/active Evidence를 구성하는 경계에서
검사하며, 오프라인 순수 validator가 DB 소유권을 새로 조회하지는 않는다.

Input Pydantic object를 나중에 mutate해 inactive state를 넣어도 거부한다.
RecruitRole/Job IDs는 승인 applicant Evidence 목록에 없으면 거부한다.
최종 문장에 대한 semantic fact checker/quality validator는 이번 범위에 없다.

기존 무경험 workspace에서 target=None 경험 Gap을 허용하던 동작은 이번의
'경험 질문에는 실제 target 필수' 계약과 충돌했다. 근거/경험이 필요한데 bound
Experience가 전혀 없으면 명시적으로 blocked/error이며 가짜 ID를 만들지 않는다.
의사만 필요한 workspace는 Experience 없이도 계획할 수 있다. 기존 회귀 테스트도
새 명시적 계약에 맞춰 이 차이를 검사한다.

## G. Unit Tests

신규 순수 계약 테스트 30개: 모든 tier의 다른 경험 거부, 명시적 multi-experience,
action/implementation/verification result 승격 거부, 정성 result 허용,
결과 없는 Gap, Gap target/source 일치, 회사 Gap과 개인 동기 분리, target 자료를
질문으로 반환하지 않기, 비활성 상태, 승인되지 않은 Target ID, 과거 category/dedupe
호환, next_question 최대 1개, 준비 사실과 동기 분리, wire enum/빈 결과 계약.

기존 v2 core/맞춤 이력서 40개와 합쳐 **70개 PASS**, 외부 API 호출 없음.

## H. Set A Before / After

fixture 전체 및 모델/추론 강도 동일 여부를 비교해 둘 다 True를 확인했다.
모델 gpt-6-luna, reasoning_effort medium. fixture/문항 내용은 변경하지 않았다.

| 항목 | Phase4A.5 A | 이번 A 2차 |
|---|---|---|
| Q1 준비 근거 | primary/근거 없음 | exp-A + exp-C, core A-1/C-4, supporting A-2/C-3 |
| Q2 scope | exp-C만 선언하고 exp-A 섞음 | exp-A/exp-C 모두 선언, 범위 위반 없음 |
| Q2 강점 Gap | applicant_intent + 경험 target | experience_evidence + exp-C target |
| Q3 result | C-5 verification을 result로 사용 | exp-B-3 실제 오류 해결 result |
| 회사 동기/정보 | 두 원인이 섞임 | intent와 target_context 두 Gap으로 분리 |
| 다음 질문 | validator 실패로 없음 | company_motivation 1개, 경험 target 없음 |

이번 1차는 joined-ID 2개가 발견되어 FAIL이었다. 필수 wire 계약 교정 후 2차는
Analyzer/Python Planner 검증 PASS, 전체 reference violation 0, 숫자 경고 0,
duplicate warning 0. Q3는 오류 추적/수정 B-5와 결과 B-3를 사용한다.

그러나 **의미 품질 전체 PASS는 아니다**. Q1은 준비 경험을 선택했음에도:

> 데이터 분석 프로젝트 경험은 확인되지만, 해당 프로젝트나 별도의 학습을 입사를 위해 준비한 노력으로 수행했는지는 확인되지 않았다.

라는 high preparation_effort Gap을 남겼다. 필요한 실제 수행 정보와 '입사를 위한
목적' 확인을 분리하지 못해 준비 사실을 다시 물을 위험이 있다. 다음 단계의
Writer에게 작성 가능한 준비 내용을 지나치게 보류하게 할 수 있으므로 남은
의미 문제로 기록한다. Python으로 이 Gap을 삭제해 통과시키지 않았다.

A 2차 Analyzer는 Q3를 challenge/result로 추출했고 personal_action 별도 ask는
없었지만 Plan에는 실제 행동 B-5가 포함됐다. Analyzer를 새 규칙으로 바꾸지 않았다.

실제 결과: `evaluation/application_planning_phase4a6_results/A-attempt1.{json,md}`,
`A-attempt2.{json,md}`. 사람 판정 칸은 모두 비어 있다.

## I. Set B Regression

**이번 phase 실제 LLM 재실행 안 함**: A의 의미 품질 통과를 선언하지 않았으므로
사용자의 조건에 따라 보류했다. 이전 B 원본을 현재 계약으로 오프라인 재검사한
결과는 PASS이며 같은 exp-D / 다른 focus 정책과 승인된 result를 유지한다.
이는 새 prompt/model 출력의 라이브 회귀 검증을 대신하지 않는다.

## J. Set C Regression

**이번 phase 실제 LLM 재실행 안 함**. 기존 C 원본 오프라인 재검사는 PASS이며
result=[], experience_evidence/result Gap을 유지한다. 신규 prompt/schema를
실제 호출한 C 결과라고 주장하지 않는다.

B/C 오프라인 자료: `application_planning_phase4a6_results/offline_rechecks/`.
각 파일에는 '새 API 호출 0, 사용량은 과거 자료' 표시가 있다.

## K. LLM Usage

| 실행 | API calls | input tokens | output tokens | API 구간 합 |
|---|---:|---:|---:|---:|
| A 1차 | 2 (Analyzer+Planner) | 2,896 | 3,839 | 39,015 ms |
| A 필수 계약 교정 후 2차 | 2 | 3,072 | 3,274 | 30,765 ms |
| 이번 B/C | 0 | 0 | 0 | 0 |
| 합계 | **4** | **5,968** | **7,113** | **69,780 ms** |

출력 토큰에는 provider가 보고한 reasoning token이 포함된다. 전체 pipeline
시간은 A 1차 39,062 ms / 2차 30,797 ms로 API 구간 합과 구분한다.
실패 실행 사용량도 포함하며 사용량 누락 호출은 0. 재실행 한도 소진 후 추가
샘플링, 자동 retry, 별도 Judge LLM, v1 재실행을 하지 않았다. LangSmith 전송은 껐다.

## L. Existing Regression Tests

기존 PostgreSQL 전체 회귀 115개를 격리 127.0.0.1:55439 설정으로 실행했다.
Experience/Evidence, Workspace, 질문/답변, RecruitRole, concurrency 및 기존
resume write/delete 테스트 포함. **최종 115개 PASS, 115.827초**.
순수 테스트 70개와 합쳐 185개 PASS. 이는 LLM 의미 평가 통과 수가 아니라
deterministic/regression 테스트 수다. `makemigrations --check --dry-run`은
No changes detected, Django check는 문제 없음, `git diff --check`도 통과했다.
테스트 runner의 격리 DB 생성/기존 migration 회귀 외에 migrate를 수동 실행하지
않았고, 신규 migration/DB 모델을 만들지 않았다. RDS는 접근하지 않았다.

## M. Remaining Risks

1. Q1 preparation Gap 과잉 보수성: 준비 사실이 없는 것과 '입사 목적' 미확인을
   구분해야 한다. 일반 의미 계약으로 교정해야 하며 regex/fixture hard-code로
   강제 삭제해서는 안 된다. 현재 라이브 예산은 소진되어 새 교정 후 라이브
   검증은 별도 승인/다음 지시가 필요하다.
2. B/C의 신규 prompt 라이브 회귀 미검증. 오프라인 replay만 통과했다.
3. fact_type 자체가 잘못 부여된 근거의 의미까지 Python이 보증하지 않는다.
4. story_focus/rationale의 의미·질문 가치·지나친 비교 우월성 확인 질문은 사람이
   검토해야 한다. 경고 0은 의미 정확성의 증명이 아니다.
5. 무경험 workspace의 경험 요구는 명시적으로 blocked. 경험 수집 UI/새 테이블은
   이번에 만들지 않았다.
6. 기존 전역 Users.delete의 legacy table 문제는 여전히 별도 미해결이다.

## N. Go / No-Go

**Phase4A.6: PARTIAL. Phase4B Writer 착수: NO-GO.**

scope/result/wire-ID 계약과 정보 종류 분리는 개선됐지만, A Q1의 남은 의미 문제와
실제 B/C 회귀 미검증을 남긴 상태에서 전체 완료로 표시하지 않는다. 다음은
Q1 계획을 검토하고, 작성 가능한 준비 사실과 목적/동기 보완을 구분하는 최소
교정 후 제한된 라이브 검증 여부를 결정하는 것이다. Writer/Validator 구현으로
진행하거나 결과를 사람이 승인한 것으로 기록하지 않았다.

이번 수정 파일: application_planning/models.py, engine.py,
tests/test_application_planning_contracts.py, lms/test_application_planning.py,
evaluation/application_planning_live.py, application_planning_recheck.py,
application_planning_phase4a6_recheck.py 및 본 보고서/생성 결과 파일.
커밋/푸시는 이번 요청에 포함되지 않아 수행하지 않았다.
