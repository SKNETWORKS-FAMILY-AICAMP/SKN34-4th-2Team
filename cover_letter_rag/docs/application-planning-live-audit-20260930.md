# Phase 4A — Live LLM Audit

결론: **Answer Writer 진입 NO-GO**. 세 세트의 소규모 검증은 완료했지만 복합 Set A의 Planner가 현재 계약을 지키지 못했다.
자동 validation 통과와 실제 의미 품질을 구분한다. 사람 판정 칸은 모두 비워 두었다.

## A. Test Setup

- Branch: feature/resume-review-quality.
- Model: .env의 gpt-6-luna. provider 응답 model_name도 gpt-6-luna.
- Reasoning effort: .env의 medium 유지. 속도/비용 조정 없음.
- 기존 StructuredPlanningClient를 사용하고 주입 모델을 include_raw wrapper로 감싸 usage만 기록.
- Responses API, structured JSON schema. 자동 retry 0, timeout 180초.
- LangSmith tracing 비활성화. fictional fixture만 OpenAI API로 전송.
- Django/production DB/실제 사용자 데이터는 live harness에서 import/조회하지 않음.
- 3세트만 생성. A 최초 실패 후 prompt 원인 분류·최소 수정하여 A만 한 번 재실행. B/C는 각 한 번.
- 실제 API 호출 7회. offline recheck는 0회.

fixture의 오류 해결은 이미 주어진 정성적 결과로 result 분류했다. 정량 성과를 추가하지 않았다.
KKBOX의 예측 signal 관찰은 verification으로 구분했으며, 통과를 위해 사후 result로 바꾸지 않았다.

## B. Set A Result

원본 3문항을 줄바꿈과 1000자 표기까지 유지했다.

최초 Analyzer:

- Q1 company_motivation / preparation_effort, Q2 desired_work / differentiating_strength / supporting_experience를 분리.
- 하지만 모든 asks_for를 required=false로 표시.
- source_quote의 줄바꿈을 공백으로 바꾸어 exact quote 검증 실패.
- 실패 즉시 Planner 호출 생략. 최초 1회만 과금.

최소 prompt 수정 후 한 번 재실행:

- Q1/Q2의 요구 분리, required=true, 줄바꿈 인용 및 1000자 정책은 통과.
- Q3는 challenge/result만 추출했다. 요청한 personal_action은 별도 key로 추출되지 않음. schema 통과와 의미 완전성을 구분해야 한다.

Planner 실제 출력:

| 문항 | primary | core | story focus / Gap |
|---|---|---|---|
| Q1 | 없음 | 없음 | 회사 지원 이유 + 입사를 위한 준비 확인. company_motivation/preparation_effort high Gap |
| Q2 | exp-C | exp-C-2, exp-C-3 | churn 불균형 분석·metric 판단. supporting에는 exp-A 근거까지 사용 |
| Q3 | exp-C | exp-C-2, exp-C-3 | 불균형 문제·threshold 비교·예측 signal을 결과로 활용 |

**차단된 계약 위반**:

1. Q2 supporting의 exp-A-1/2/4/5가 선언한 primary Experience 범위 밖임.
2. Q2/Q3 result_evidence_ids에 fact_type=verification인 exp-C-5를 사용.
3. differentiating_strength Gap을 applicant_intent로 분류하면서 target_experience_id=exp-C를 부여.

독립 진단은 위 위반을 모두 기록했다. validator의 첫 오류만 보고 다른 문제를 놓치지 않았다.
유효한 Writer 입력으로 반환하지 않았다. 세 번째 샘플링/재실행은 하지 않았다.

의미 검토가 필요한 추가 관찰:

- 회사 맥락/구체적 지원 이유가 없으므로 company_motivation Gap은 타당한 방향이다. 오래 관심 있었다/제품을 썼다는 동기를 만들지 않았다.
- Q1의 준비 과정에 실제 프로젝트를 전혀 배정하지 않았다. 특정 회사에 지원하기 위한 과거 목적을 지어내지 않으려는 보수성인지, 관련 경험을 활용하지 못하는지 판단이 필요하다.
- Q2/Q3가 같은 core를 사용하되 분석 역량/도전 focus를 달리했다. 단순 ID 중복만으로 실패 처리하지 않았다. 다만 실제 Writer가 서로 다른 이야기를 만들 수 있을 정도로 focus가 분리됐는지는 사람 확인이 필요하다.
- supporting 근거가 많고 선언한 경험과 불일치한다. 현재 prompt/contract의 범위 설명이 충분하지 않다.

검토 파일: `evaluation/application_planning_live_results/offline_rechecks/A-attempt2.md`.
최초 실패 출력도 A-attempt1.json/md에 보존했다.

## C. Set B Result

Analyzer:

- Q1 collaboration/problem/solution/supporting_experience.
- Q2 problem/solution/supporting_experience.
- Q3 personal_action/technical_contribution.
- 원문 인용과 제한 null 검증 통과.

Planner는 세 문항 모두 exp-D를 사용했지만 서로 다른 focus와 core를 선택했다.

| 문항 | core | result | focus |
|---|---|---|---|
| Q1 | exp-D-4, exp-D-5 | exp-D-3 | contract 조율·협업 |
| Q2 | exp-D-5 | exp-D-3 | 불일치 재현·frontend/backend 수정 |
| Q3 | exp-D-1, exp-D-2 | 없음 | Django API와 React 직접 구현 |

불필요한 Gap은 없고 duplicate_story_warnings는 비어 있다.
같은 사건이라도 협업/기술 해결/구현 역량이라는 실제 다른 관점을 사용한 방향이다.

최초 validator는 result를 core/supporting에도 중복 등록하라는 조건 때문에 거부했다.
이는 존재하지 않는 사실이 아니라 계약상 불필요한 중복 선택 문제였다.
result를 독립 선택으로 인정하되 승인된 Experience 범위·active 상태·fact_type=result 검사는 유지했다.
저장된 동일 출력이 offline 재검증에서 통과했다. B를 다시 샘플링하지 않았다.

검토 파일: `evaluation/application_planning_live_results/offline_rechecks/B-attempt1.md`.
원래 거부와 변경 후 통과를 둘 다 표시했다.

## D. Set C Result

- Analyzer: challenge/result. 제한 없음 → character_limit=null.
- primary: exp-E.
- core: exp-E-2(반복 조회 감소 방향 코드 수정), exp-E-3(직접 구현).
- supporting: exp-E-1(pipeline 개선).
- result_evidence_ids: 빈 배열.
- challenge/result high Gap을 각각 exp-E에 연결.
- result proposal: 실제 확인한 변화나 성과가 있는지, 측정값/관찰 결과 요청.
- 50% 개선, 응답 시간 절반, 사용자 증가, 비용/만족도 개선을 생성하지 않았다.
- 숫자/성과 표현 후보 자동 경고 없음. 이는 의미 검증 전체를 보장하는 점수가 아니다.

서버 next_question은 첫 high Gap인 challenge다. result Gap도 계획에 있지만 가장 가치 높은 질문이 항상 먼저 선택된다고 보장하지는 않는다.
이 우선순위는 수동 검토 대상이며 성공을 위해 재실행하지 않았다.

검토 파일: `evaluation/application_planning_live_results/offline_rechecks/C-attempt1.md`.

## E. Deterministic Validation

확인한 부분:

- 문항 ID coverage/중복, source_quote 존재, counting policy 동일성.
- 실제 fixture Experience/Evidence ID 존재 및 선언한 Experience 범위.
- active Fact pool 밖의 참조 차단.
- result IDs의 실제 fact_type=result 검사.
- intent/context Gap의 Experience ID 혼합 차단.
- 전체 문항 계획, 동일 이야기 signature warning.
- Gap/story/rationale의 새 수치 및 성과 표현 후보 warning.

한계:

- live fixture는 한 가상 사용자 소유 active 근거만으로 구성했다. 실제 DB 소유권·inactive filtering은 별도 PostgreSQL 회귀 테스트에서 확인했다.
- Gap 문장이 아무 새 factual claim도 포함하지 않는다는 완전한 의미 보장은 하지 않았다. 규칙으로 잡을 수 있는 후보만 표시한다.
- 임의 overall score나 자동 human judgement를 만들지 않았다.

회귀 검증:

- PostgreSQL 기반 Django 전체 **91 passed**: 기존 90개 + result 독립 선택 회귀 1개.
- 기존 Resume Review v2 33 + tailored service 7 = **40 passed**.
- production RDS migration/조회/쓰기 없음.

## F. API Usage

| Set / attempt | Calls | Input tokens | Output tokens | API 호출 시간 합계 |
|---|---:|---:|---:|---:|
| A 최초 | 1 | 657 | 548 | 6.125초 |
| A 수정 후 1회 | 2 | 2,446 | 2,717 | 30.297초 |
| A 합계 | 3 | 3,103 | 3,265 | 36.422초 |
| B | 2 | 1,749 | 1,727 | 18.015초 |
| C | 2 | 1,361 | 745 | 9.485초 |
| 전체 | **7** | **6,213** | **5,737** | **63.922초** |

API 시간은 invoke duration 합계이며 단일 request latency/TTFT와 다르다.
세트 처리 시간은 A 최초 6.141초, A 재실행 30.313초, B 18.015초, C 9.516초.
output tokens는 provider usage 그대로이며 reasoning tokens를 포함한다. 별도로 더해 중복 계산하지 않았다.
usage 누락 호출 0. 비용 금액은 추정하지 않았다.

`usage-summary.json`에는 최초 live validation 상태가 유지된다. B의 수정 후 상태는 offline_rechecks에 별도로 기록되어 재실행처럼 계산되지 않는다.

## G. Issues Found

| 분류 | 문제 |
|---|---|
| Analyzer prompt/contract | 줄바꿈 exact quote, required 의미가 명확하지 않았음 |
| Deterministic validator | result 근거를 core/supporting에도 중복 등록하도록 불필요하게 강제 |
| Planner contract | primary Experience와 supporting Evidence 범위 불일치 |
| Planner contract / fixture interpretation | verification을 result 목록에 배정 |
| Planner concept boundary | intent Gap과 Experience-targeted Evidence Gap 혼합 |
| Analyzer semantic coverage | Q3 personal_action key 미추출 |
| Planner semantic quality | Q1 준비 경험 미배정, 과도한 보수성 가능성 |

Analyzer 결과를 Planner에 전달했고 Planner에 원래 문항 raw_text 전체를 다시 제공하지 않았다.
따라서 문항 구조화를 별도 call로 다시 수행하는 흐름은 아니다.
Planner Gap과 Python의 mandatory Gap 검사는 책임이 일부 겹친다. 현 결과에서 A의 문제가 이 중복으로 자동 해결되거나 가려지지 않았다.
최종 자기소개서 문장은 생성하지 않았다.

## H. Fixes Made

최소 수정:

1. Analyzer prompt에 exact newline quote와 required의 의미 두 문장 명시.
2. result 목록에서 승인된 실제 result 선택이면 충분하도록 중복 등록 요구 제거.
3. Analyzer/plan version v2로 증가하여 이전 cache를 자동 재사용하지 않도록 처리.
4. 실제 result가 독립 목록에 있어도 정상이라는 unit test 추가.

새 evaluation 파일:

- application_planning_cases.json: 정확히 A/B/C 3세트.
- application_planning_live.py: checkpoint·usage·사람 검토 출력, 자동 retry 없음.
- application_planning_recheck.py: 저장 출력만 재검증, 새 API 호출 없음.

DB 모델/migration, React, Writer, production API, reasoning effort는 변경하지 않았다.
가드를 느슨하게 해 A를 통과시키거나 근거 유형을 사후 변경하지 않았다.

공식 OpenAI 문서를 확인해 structured response와 reasoning 설정을 사용했다:
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Reasoning](https://developers.openai.com/api/docs/guides/reasoning).
공식 문서의 schema 준수와 제품 의미 품질을 동일시하지 않았다.

## I. Remaining Risks

- A에는 처리하지 않은 실제 Planner 실패가 남는다. 한 번의 제한된 retry 후 추가 호출하지 않았다.
- personal_action 및 preparation의 해석 완전성이 충분하지 않다.
- 주 경험과 보조 경험의 허용 범위, verification/result 분류, 의사 Gap의 대상 의미를 더 명확히 해야 한다.
- same-focus의 의미 중복은 exact signature만으로 검출하지 못할 수 있다.
- high Gap 가운데 어떤 질문이 최우선인지 현재 선택 방식이 단순하다.
- B/C 통과는 소수 대표 사례의 관찰이지 일반화된 품질 보장이 아니다.
- 사람 Review 칸은 아직 비어 있다. 사람이 직접 Writer에 줄 재료의 충분성을 판단해야 한다.

## J. Recommendation

**NO-GO: Answer Writer 구현으로 아직 넘어가지 않는다.**

먼저 A에서 드러난 Planner 데이터 계약과 의미 경계를 정리해야 한다.
다음 우선순위는 primary/supporting 경험 범위, result/verification, evidence/intent Gap 구분이다.
Q3 개인 행동 요구와 Q1 준비 경험 활용도 함께 검토한다.

B/C의 좋은 결과는 유지하되, 현재 A 계획을 좋은 Writer에게 그대로 넘겨도 된다고 판단할 수 없다.
이번에는 평가 결과를 성공으로 포장하지 않고 여기서 종료한다.
