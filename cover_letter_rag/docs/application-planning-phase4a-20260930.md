# Application Questions / Planning — Phase 4A

> 후속 live 검증 변경: `application-planning-live-audit-20260930.md` 참고.
> Analyzer/plan version은 v2로 갱신되었고 result Evidence는 core/supporting에 중복 등록하지 않아도 선택된 근거로 인정한다.
> 아래 본문은 최초 Phase 4A 구현 당시의 기록이다.

## A. Changed Files

이번 단계에서 추가:

- `cover_letter_rag/app/application_planning/__init__.py`
- `cover_letter_rag/app/application_planning/models.py`
- `cover_letter_rag/app/application_planning/engine.py`
- `lms_api/lms/application_question_store.py`
- `lms_api/lms/migrations/0013_application_questions_answers.py`
- `lms_api/lms/test_application_planning.py`
- 이 보고서.

수정:

- `lms_api/lms/models.py`: 문항/답변/계획 managed model 추가, Lower import 위치 정리.
- `lms_api/lms/test_application_workspace.py`: 이전 migration 테스트가 종료 시 실제 최신 leaf를 복구하도록 변경.

기존 미커밋 변경은 보존했다. v1, Resume Review v2 core, React, production API, Experience/Evidence 스키마는 변경하지 않았다.

## B. Migration / DB Models

실제 단일 migration graph:

```text
0011_resume_experience_evidence
 → 0012_application_workspace
 → 0013_application_questions_answers
```

새 managed tables:

| Table | 주요 필드 / 관계 |
|---|---|
| application_questions | UUID id; application FK CASCADE; order; raw_text; nullable character_limit; count_unit; nullable include_spaces; source_type/reference; import_key; analysis JSON; analysis_version/input_hash; timestamps |
| application_answers | UUID id; question FK CASCADE; answer_key; content; source_type; status; nullable target_experience FK SET_NULL; confirmation_key; topic_resolved; timestamps |
| application_plans | application OneToOne PK CASCADE; input_hash; version; content JSON; timestamps |

문항 unique(application, import_key), 답변 unique(question, answer_key).
문항의 양수 limit 및 count_unit CHECK. PositiveIntegerField의 음수 방지 제약도 생성된다.
Question은 Application 1:N이고 Answer는 Question 1:N이다. 초안과 여러 보완 답변을 별도 answer_key로 저장할 수 있다.
default draft key는 수정 시 동일 행을 갱신한다.
계획은 최신 하나를 versioned JSON으로 저장하며 과거 plan audit archive는 이번 범위가 아니다.

Django CASCADE/SET_NULL은 ORM 삭제 정책이다. 물리 PostgreSQL FK는 기존 프로젝트처럼 NO ACTION이므로 raw SQL delete에는 별도 처리가 필요하다.
Production RDS 적용은 하지 않았다.

## C. Question Snapshot Strategy

`import_questions`는 전달받은 원문 string을 그대로 저장한다. 외부 source 실시간 join은 없다.
source_type: manual / recruit_role / job_posting / document_extraction / legacy.
source_reference는 출처 locator이며 본문을 대체하지 않는다.

같은 source/type/reference/order/raw_text의 SHA256 import_key는 동일 행을 반환한다.
import retry는 사용자가 수정한 snapshot을 덮어쓰지 않는다.
외부 원문이 변경된 새 세트를 명시적으로 import하면 새 snapshot 행이 생길 수 있다.
기존 세트의 자동 삭제/교체나 의미 기반 source dedupe는 구현하지 않았다.

## D. Question Analyzer Contract

`PlanningClient.analyze(questions[], optional target_context)` 한 batch structured call.
`AnalysisBatch.questions[]`는 입력 문항 ID를 빠짐없이 한 번씩 포함한다.

예시(계약 설명용 ID; live 결과가 아님):

```json
{
  "questions": [{
    "question_id": "q1",
    "asks_for": [
      {"key": "company_motivation", "required": true, "source_quote": "지원 이유"},
      {"key": "preparation_effort", "required": true, "source_quote": "준비 노력"}
    ],
    "constraints": {"character_limit": 1000, "count_unit": "characters", "include_spaces": true}
  }]
}
```

이 예시의 원문은 `지원 이유와 준비 노력 (1000자 이내, 공백 포함)`이다.
Python은 ID coverage, 중복 asks_for key, exact source quote, constraints 동일성을 검사한다.
원문을 분석 결과로 덮어쓰지 않는다. 문항 요구의 의미적 해석 정확도까지 exact quote가 보장하는 것은 아니다.

`StructuredPlanningClient`는 주입된 LangChain-compatible model의 `with_structured_output`을 사용한다.
모델/키/환경을 import 시 초기화하지 않으며 서비스 호출자는 client를 명시적으로 주입한다.
실제 모델은 이번 단계에서 연결/호출하지 않았다.

## E. asks_for Taxonomy

```text
company_motivation, role_motivation, preparation_effort, desired_work,
differentiating_strength, supporting_experience, challenge, problem,
personal_action, technical_contribution, collaboration, difficulty,
solution, result, lesson, growth, future_plan
```

작은 Literal contract로 관리하며 확장 시 중앙 정의와 tests를 변경한다.
복합 문항은 asks_for 배열로 유지한다.

## F. Character Limit Policy

`parse_constraints`가 원문의 명시적인 숫자+자/글자/byte/바이트 표현만 읽는다.
한 가지 명확한 값이면 저장하며 제한이 없으면 null이다.
여러 다른 제한이 있으면 character_limit=null, count_unit=unknown으로 남긴다.
공백 포함/제외가 명확할 때만 bool, 없거나 충돌하면 null이다.
제한이 없는 일반 문항의 count_unit 기본값은 characters지만 제한 자체를 추정하지 않는다.
Analyzer가 constraints를 임의 변경하면 전체 batch를 저장하지 않는다.
실제 byte counting/encoding 및 최종 답변 길이 검사는 Writer 단계 이후 범위다.

## G. Application Planner Contract

```text
PlanningInput
  application_id
  questions[]: QuestionAnalysis
  experiences[]: id/title/kind/active Fact[]
  target_context: 선택적 회사/공고/요건
  answers[]: 문서/의사 확인 맥락, Evidence 아님
  previous_question_keys[]: 호출자가 전달한 확인 이력

ApplicationPlan.assignments[]
  question_id
  primary_experience_ids[]
  story_focus
  core_evidence_ids[]       (최대 2)
  supporting_evidence_ids[]
  result_evidence_ids[]
  missing_information[]
  rationale

PlanningResult
  plan
  duplicate_story_warnings[]
  next_question: Gap | null (최대 하나)
```

DB-free core와 Django persistence adapter를 분리했다. Planner는 한 batch structured call에서 matching/selection/focus/gap을 함께 수행한다.
Ranker나 Gap Planner 추가 LLM call은 없다.

## H. Experience Assignment

대상 Application의 base Resume Binding이 참조하는 사용자 소유 active Experience만 입력한다.
선택 기준은 문항 요구와 실제 경험의 직접 기여/기술적 구현/결과 관련성이다.
Planner가 전체 문항을 함께 보고 primary Experience와 rationale을 반환한다.
Python은 존재 여부·소유권·입력 범위를 검증한다. 경험 다양성을 강제하지 않는다.
fake 테스트는 배정 계약을 확인하며 실제 모델의 배정 품질을 증명하지 않는다.

## I. Evidence Selection

기존 `load_active_evidence`를 재사용해 resume_stated/user_asserted만 전달한다.
uncertain conflict가 연결된 active 사실도 기존 로직에 따라 제외한다.
superseded/contradicted/retracted/uncertain ID나 다른 Experience의 ID는 output에서 차단한다.
core/supporting 중복은 차단한다. result는 선택된 실제 fact_type=result Evidence여야 한다.
공고 요건, 자기소개서 초안, 사용자 의사는 Evidence ID가 될 수 없다.
과거 Resume 본문을 Planner에 주지 않으며 새 Evidence를 생성하지 않는다.

## J. Story Duplication

signature = primary Experience IDs + core Evidence IDs + result Evidence IDs + 정규화한 story_focus.
동일 signature의 문항들을 warning으로 반환한다. 같은 Experience ID만으로 중복 판정하지 않는다.
다른 focus 또는 다른 core/result 선택이면 허용한다. warning은 failure가 아니다.
focus 표현만 바꾼 의미상 같은 이야기까지 검출하는 semantic similarity는 미구현이다.

## K. Gap Detection

Gap은 key/category/target_experience_id/reason/importance/question_proposal을 갖는다.
category는 applicant_evidence / applicant_intent / target_context로 구분한다.

- 필요한 경험 근거가 없으면 경험 정보 Gap.
- 결과를 요구하는데 result Evidence가 없으면 결과 Gap. 성과를 추론하지 않는다.
- 기존 result가 있는데 선택하지도 Gap으로 설명하지도 않으면 plan을 차단한다.
- 지원동기/희망/포부는 명시적 사용자 의사 확인이 없으면 intent Gap.
- 경험 Gap은 선택한 Experience ID를 반드시 지정한다.
- 아직 Experience 자체가 없는 경우에는 null로 남겨 경험 선택/등록이 먼저 필요함을 표현한다. 가짜 Experience ID는 만들지 않는다.
- intent/target context Gap은 Experience Evidence로 위장하지 않도록 target_experience_id를 null로 제한한다.

최종 사용자 질문 후보는 high 중 하나만 반환한다. medium/low를 채우기 위한 반복 질문은 하지 않는다.
문항 순서로 deterministic하게 처리하지만 전체 문항의 정보 가치 순위를 완전히 최적화하는 시스템은 아니다.

## L. Question Dedupe

category + target Experience(or application) + topic key로 dedupe한다.
확인 이력은 previous_question_keys, 저장된 confirmed Answer의 confirmation_key, 기본 fact_type 존재 여부를 참고한다.
답변을 받았음과 정보가 해결됨을 분리했다.

`topic_resolved=true`는 confirmed 사용자 의사 topic에만 명시적으로 설정할 수 있다.
`모른다`는 답변은 해당 질문을 재요청하지 않되 Gap은 남는다.
Answer는 문서이며 Evidence 자동 extraction을 하지 않는다. 경험 사실 Gap 해결은 active Evidence가 필요하다.
과거 v1/v2 질문 로그 전체를 자동 수집하는 integration은 없으며 history adapter가 key를 전달해야 한다.
완전한 의미 기반 dedupe는 이번 범위가 아니다.

## M. Stale / Version Strategy

analysis version = question-analysis-v1, plan version = application-plan-v1.
문항 raw_text 수정 시 analysis JSON/version/input_hash를 즉시 비운다.
질문 집합·constraints·Target Context hash가 달라도 재분석이 필요하다.
plan hash에는 분석 결과, owned active Experience/Evidence, Evidence history의 상태/수정 시각, 사용자 문서/확인 metadata, Target Context/요건, history keys와 version이 들어간다.

입력 hash 일치 시에만 plan을 재사용한다. 이벤트 기반 전파는 없다.
LLM 호출 전후 hash가 달라지면 결과를 저장하지 않고 retry가 필요하다고 반환한다.
분석이 stale한 경우 plan 조회도 재분석 필요 오류를 반환한다.
구조화된 응답이 입력 Pydantic 객체를 alias해 검증 기준을 바꾸지 못하도록 입력을 deep copy한다.

## N. PostgreSQL Tests

격리 PG16 / localhost:55439 / test_resume_review_v2 / resume_v2_test_admin만 사용했다.
production settings를 선택하면 test discovery guard가 거부한다.

검증 범위:

- 0013 apply → rollback to 0012 → reapply.
- 기존 Application/Resume/Experience/Evidence/Binding JSON rows 보존.
- 세 테이블의 실제 생성.
- 동시 동일 import 2건 → 동일 Question ID 한 행.
- Application 소유권과 Experience/Evidence 범위 차단.
- Application 삭제 시 Question/Answer/Plan ORM CASCADE, 공유 Evidence 유지.
- Question 삭제 시 Answer ORM CASCADE.

rollback은 새 Question/Answer/Plan rows를 삭제한다. 운영 데이터 무손실 downgrade를 뜻하지 않는다.
Production RDS 및 공용 DB migration은 실행하지 않았다.

## O. Existing Regression Tests

최종 동일 실행에서 Django 90개 모두 통과:

- Phase 4A 34개(기능 32 + PostgreSQL 전용 2).
- Application workspace 19개.
- 기존 Experience/Evidence persistence/PostgreSQL 32개.
- 기존 mocked Resume write/delete 5개.

별도 pytest: Resume Review v2 33 + tailored service 7 = 40개 통과.
makemigrations --check --dry-run: No changes detected.
Django check 및 git diff --check 통과.
테스트용 base cluster에 표시된 migrate plan은 미적용 0012/0013이며 실제 적용 검증은 별도 disposable test database에서 수행했다.

## P. Optional Live LLM Results

live test는 실행하지 않았다. 이번 단계는 domain contract 우선이므로 fake structured outputs로 검사했다.
복합 문항/3문항 동시 계획/의사 Gap/결과 Gap/동일 이야기 경고를 검사했지만, 실제 기업 문항에서의 해석·관련성 품질은 확인 필요다.
향후 선택적 수동 평가 3세트 이하로 확인할 수 있다. 이를 완료된 품질 검증으로 표시하지 않는다.

## Q. API Usage

실제 LLM API 호출 0회, 과금 input/output tokens 0, API latency는 측정 대상 없음.
계약상 cold path는 batch Analyzer 1 + batch Planner 1 = 2회.
분석 재사용 시 Planner만 1회, 분석/plan 모두 재사용 시 0회.
자동 retry, 별도 Ranker, Gap Planner, Writer call은 없다.
fake client 호출 횟수로 cache 동작을 검사했다. 실제 모델별 token/latency는 미측정이다.

## R. Remaining Risks

1. 실제 모델의 asks_for 해석·경험 관련성·Gap 중요도 품질은 아직 검증하지 않았다.
2. exact source quote는 의미적 정당성 자체를 보장하지 않는다. story_focus/rationale의 자연어 설명도 최종 사실 검증을 통과한 답변이 아니다.
3. 최소 길이 parser는 복잡한 괄호/문항별 상이한 제한/별도 UI 입력을 완전히 해석하지 않는다. 불명확하면 사람이 확인해야 한다.
4. dedupe와 story warning은 deterministic 근사다. 표현이 다른 같은 이야기나 세부 결과 확인 필요성은 놓칠 수 있다.
5. 호출 전후 hash 검사는 변경을 감지하지만 전체 Evidence 변경에 대한 전역 serializable workflow나 event propagation은 아니다. 이후 재사용 시에는 다시 hash를 확인한다.
6. source import 갱신 정책은 snapshot 추가/원래 import retry 보존이다. 외부 변경을 자동 replace하는 UI는 없다.
7. 기존 v1 질문 history 연결, production route/React 연결, 공용 RDS 적용은 미실시다.
8. 경험이 전혀 없으면 경험 Gap의 target ID는 null이다. 실제 보완 답변을 Evidence로 반영하기 전 Experience 선택/생성이 필요하다.
9. topic_resolved는 명시적 사용자 의사 확인 metadata다. 문서 내용을 독립적으로 외부 검증했다는 뜻이 아니다.
10. Answer final Writer, Answer Fact/Quality Validator, sentence provenance는 의도적으로 미구현이다.

## S. Go / No-Go

GO: 현재 contract를 기준으로 독립 Answer Writer/Fact Validator/Quality Validator의 offline 구현을 시작할 수 있다.
전체 Application Plan을 먼저 확정하고 approved Evidence만 Writer에 전달해야 한다.

NO-GO: 실제 기업 자기소개서 품질 검증 완료 선언, production v1 교체, React E2E 완료 선언.
실서비스 적용 전에는 소수 기업 문항 세트를 사람이 검토해 Analyzer/Planner의 의미 품질을 확인해야 한다.
