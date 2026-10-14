# Local Resume E2E — User-facing UX Cleanup

검증일: 2026-10-01. 브랜치: `feature/resume-review-quality`.
이번 변경은 로컬 미리보기 UI와 React 테스트에 한정한다. 기존 미커밋 변경은 보존했다. 커밋/푸시는 하지 않았다.

변경 파일:

- `lms_react/src/features/jobApply/LocalResumeE2E.tsx`
- `lms_react/src/features/jobApply/localResumeE2E.css`
- `lms_react/src/__tests__/localResumeE2E.test.tsx`
- 이 보고서

## A. UI Problems Found

기존 화면은 Application/Experience/Evidence UUID, 문항 출처 enum, asks_for key, assertion_state, Planner 필드명, 테이블별 개수, Binding JSON, semantic NO-GO를 기본 화면에 직접 출력했다. 관계 조회 실패 시 ID 자체를 표시했다. 정상 처리 문구와 버튼도 내부 컴포넌트 이름을 사용했다. API 오류 원문이 사용자에게 노출됐다.

조사 결과 UUID는 실제 문장에 덧붙여 저장된 것이 아니라 JSX에서 문장 옆에 직접 출력하거나 관계 조회 fallback으로 표시한 것이었다. UUID 일괄 삭제 정규식은 도입하지 않았다.

## B. Hidden Internal Fields

기본 화면에서 다음을 숨겼다.

- Application/Resume/Experience/Evidence/Question의 내부 식별자
- source_type, assertion_state 및 asks_for 내부 key
- primary_experience_ids, core_evidence_ids, supporting_evidence_ids, result_evidence_ids
- missing_information의 category/key/target ID와 raw story_focus 필드명
- counts, bindings, ai_mode, semantic_status, raw API 오류

데이터를 삭제하지 않았다. React key, select value, URL의 재열기 ID, state, API payload와 idempotency key는 기존 구조를 유지한다. 브라우저 주소에는 재열기에 필요한 application UUID가 계속 존재한다. 비노출 검증 대상은 사용자 화면 본문이다.

## C. User-facing Labels

| 내부 개념 | 사용자 표현 |
|---|---|
| primary experience | 활용할 경험 |
| core evidence | 강조할 내용 |
| supporting evidence | 함께 활용할 내용 |
| result evidence | 확인된 결과 |
| story focus | 이 문항에서 강조할 포인트 |
| missing information | 추가로 필요한 정보 |

enum은 번역한 상태 목록을 늘리는 대신 기본 화면에서 생략했다. 실제 프로젝트 기술명 Python, XGBoost, PR-AUC, FastAPI, API contract 등은 경험 내용이므로 유지했다.

## D. Experience / Evidence UI

문항 카드 안에 경험 이름 → 작성 포인트 → 핵심 사실 → 보조 사실 → 확인된 결과 순으로 표시한다. 경험은 기존 Badge, 사실은 bullet list를 사용한다. 기존의 모든 경험/사실을 먼저 출력하던 중복 개요는 제거했다.

resume_stated/user_asserted만 사용자 사실 목록에 표시한다. superseded 등 inactive 사실은 숨긴다. 관계 조회 실패 시 UUID 대신 연결된 정보를 확인할 수 없다는 안내를 표시한다. 실제 사용자 문장에 있는 UUID 모양의 텍스트는 훼손하지 않는다.

결과 사실이 없는 문항에는 결과 섹션을 만들지 않는다. 실제 mock 화면에서는 3개 문항 중 문항 3에만 결과 섹션이 있었다.

## E. Gap UI

추가 정보는 question_proposal을 우선 표시하고, 없으면 reason을 표시한다. 관련 경험은 이름으로 보여 준다. 질문이 있는 경우 reason은 보조 설명으로 표시한다. category/key/importance는 출력하지 않는다.

질문과 이유 내용 자체는 기존 Planner 결과 그대로다. Q1 preparation_effort 재확인 문제를 숨기거나 고치지 않았다.

## F. Developer Panel

화면 하단의 `개발자 정보 보기` details는 기본 접힘이다. 펼쳤을 때만 JSON DOM을 생성한다. 패널에는 API prefix, AI mode, 선택한 role/resume ID, 전체 workspace, 원시 오류가 있다. workspace 내부에서 기존 ID, Planner 결과, counts, bindings, semantic 상태를 확인할 수 있다.

JWT, 로그인 암호, 요청 Authorization 헤더는 패널에 넣지 않는다. 새로고침 시 다시 접힌 상태다.

## G. Buttons / Status Copy

- 미리보기 시작하기
- 이 공고에 맞게 준비하기 / 지원 준비 계속하기
- 맞춤 이력서 준비
- 문항 가져오기
- 문항 분석
- 작성 방향 분석

문항 분석 중에는 `문항을 분석하고 있습니다…`, 작성 방향 분석 중에는 `활용할 경험과 작성 방향을 정리하고 있습니다…`를 표시한다. 버튼 busy/분석 선행 조건은 유지했다. 내부 성공 enum 대신 한국어 완료 문구를 사용한다. 오류는 친절한 재시도 안내로 표시하며 원문은 개발자 패널에 둔다.

## H. Mock Data Cleanup

DB와 fixture 파일은 변경하지 않았다. 이 로컬 화면에만 정확한 fixture title alias를 적용했다.

| 저장된 가상 자료 제목 | 화면 제목 |
|---|---|
| 가상 E2E 데이터 기업 | 데이터 서비스 기업 (예시) |
| Data Analyst / AI Service | AI 서비스 데이터 분석 직무 |
| 가상 학생 기본 이력서 | 데이터 분석가 지원 이력서 |
| KKBOX churn analysis | KKBOX 고객 이탈 분석 |

회사/직무의 미제공 정보, 기술 스택, 성과, 채용 형태를 새로 만들지 않았다. 경험/사실의 실제 의미와 ID는 그대로다.

## I. React Tests

전체: `npm.cmd test -- --maxWorkers=2` — **44개 파일, 269건 통과**.
최종 세부 UI 테스트: **3건 통과**.
타입 검사/production build: **통과**. 기존 500KB 이상 chunk 경고는 남아 있다.

신규/보강 검증:

- 기존 로그인 → 선택 → Application → Tailored → 문항 → 분석 요청 흐름
- 기본 화면의 실제 UUID/내부 key/enum 비노출
- 경험 사실 및 추가 질문 표시
- 펼친 패널에서 ID/NO-GO 확인, 접으면 다시 비노출
- 알 수 없는 관계의 ID fallback 금지
- inactive 사실 숨김, 실제 사용자 UUID 문자열 보존
- 사용자 오류/개발자 오류 분리 및 로그인 비밀 미출력

최초 unrestricted parallel 전체 실행은 기존 app.test 로그인 관련 18건이 실패했다. 해당 파일 단독 실행 28건은 통과했고, 전체 maxWorkers=2 실행도 269건 모두 통과했다. 실패 원인을 확정하지 않았으며, 이 UX 변경으로 production 로그인 코드를 수정하지 않았다.

## J. Backend Regression

로컬 전용 entry/settings로 다음 suite 실행: **116건 통과**.

- Local E2E API
- Application Workspace
- Application Planning
- RecruitRole Context
- Resume/Experience/Evidence Store
- PostgreSQL persistence

별도 Python 계약 테스트: **70건 통과**.

테스트는 loopback PostgreSQL 전용 테스트 DB에서 수행했다. Django test runner가 테스트 DB를 생성·구성·제거하는 기존 절차는 사용했지만, 미리보기 기본 DB의 migration graph/schema를 변경하거나 migrate 명령을 실행하지 않았다. 신규 migration 파일 없음. RDS/production DB 접근 없음. 실제 LLM 호출 없음.

## K. Browser Smoke Test

실제 Vite 5180 → Django 8002 → 로컬 PostgreSQL 55439, AI mock에서 확인했다.

1. 가상 로그인과 catalog 조회
2. 저장된 Application 재열기
3. 공고/이력서 선택, 기존 idempotency key로 재생성 요청
4. Tailored 재사용, 문항 가져오기, 문항 분석, 작성 방향 분석
5. 개발자 패널 펼침/접힘
6. 새로고침으로 기존 Application과 선택 상태 복원

모든 관련 로컬 API HTTP 응답은 서버 로그에서 200을 확인했다.
기본 body visible text 검사 결과 UUID false, 금지 내부 key/enum/Planner/Analyzer 노출 목록 빈 배열이었다. 사실/질문은 존재했다. 브라우저 console error 기록은 빈 목록이었다.

반복 전후 수량: Resume 2, Experience 3, Evidence 17, Binding 6, Application 1, Question 3으로 동일했다. 기존 Application UUID와 Tailored ID 2가 유지됐다. mock mode와 semantic NO-GO도 유지됐다.

기존 브라우저 탭은 CDP focus timeout으로 조작이 막혔다. 해당 탭을 닫거나 반복 생성/종료하지 않고, 별도 검증 탭 한 개에서 위 흐름을 완료했다. 검증 탭은 결과 확인용으로 열어 두었다.

## L. Screenshots / Visual Description

실제 실행 화면 캡처:

- `C:/Users/MoonSungHo/Documents/ChatGPT/SKN-4th Project/local-resume-e2e-ux-20261001.jpg`
- `C:/Users/MoonSungHo/Documents/ChatGPT/SKN-4th Project/local-resume-e2e-ux-gaps-20261001.jpg`

기존 Card/Button/Badge/Select/TabPage와 색상 변수를 사용한다. 상단은 공고/이력서 선택, 다음은 준비 상태와 분석 버튼, 아래는 문항별 경험/사실/질문 카드다. 작은 개발 미리보기 배지만 유지한다. 새로운 디자인 시스템은 만들지 않았다.

실제 기본 desktop viewport에서 잘림/가로 overflow 없이 시각 검토했다. 모바일 전용 viewport 검증은 하지 않았으며, 선택 요약의 600px 이하 1열 CSS만 제공한다.

## M. Remaining UX Issues

- Q1 preparation_effort 재확인 문제는 별도 semantic Phase이며 미해결이다.
- 일부 story_focus/reason이 길거나 분석 보고서 말투다. 이번에는 결과 의미를 수정하지 않았다.
- Q3 핵심 사실과 결과에 같은 사실이 들어가는 중복은 원래 Plan에 존재한다. UI cleanup에서 selection을 임의로 바꾸지 않았다.
- 이전 URL을 새 session에서 열면 저장된 공고 선택 정보가 없어 공고를 다시 선택해야 한다. DB 관계를 추측해 표시하지 않는다.
- 최종 자기소개서 작성/답변 저장/production React 전환은 이 화면의 범위가 아니다.
- 모바일 실기기와 접근성 심층 점검은 후속이다.

## N. Go / No-Go

**GO — 로컬 사용자 흐름 및 UI 사용감 검토용.** 내부 ID 없이 공고 → 이력서 → 문항 → 경험 → 사실 → 추가 질문을 이해할 수 있으며, 기존 mock E2E는 동작한다.

**NO-GO — production 배포 또는 Planner 의미 품질 합격.** UI 정리가 Q1 semantic 문제 해결을 의미하지 않는다. 기존 NO-GO를 개발자 패널에 그대로 보존했다. DB/RDS/LLM/production API/Writer/v1은 이번 작업에서 변경하지 않았다.
