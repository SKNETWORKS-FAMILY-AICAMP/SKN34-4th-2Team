# 이력서 첨삭 v2 계약과 검증 범위

이 문서는 README의 초기 재첨삭 예시보다 우선합니다. 기존 Flutter 파일과 Firestore 규칙은 변경하지 않았습니다.

## 최초 첨삭

`POST /api/v1/resumes/reviews`, `Authorization: Bearer <Firebase ID token>`

```json
{"cohort_id":"cohort-1","resume_id":"resume-1","request_id":"review-001"}
```

클라이언트는 매 논리 요청마다 request_id를 생성하고 네트워크 재시도에는 같은 값을 사용합니다.
생략하면 서버가 생성하므로 클라이언트 중복 클릭 방지에는 도움이 되지 않습니다.
공고는 선택 입력 job_posting_text로 받으며 프로필 skills는 조회하지 않습니다.

응답의 핵심 필드:

| 필드 | 의미 |
|---|---|
| review_id | request_id와 동일한 결과 ID |
| input_hash | 원본 content 전체의 버전 해시(실제 LLM 입력 해시와 다름) |
| input_fields | 마스킹 후 모델에 전달된 필드별 원문 |
| item_refs | 필드와 원래 항목 ID 연결, 모델에는 보내지 않음 |
| excluded_fields | 기본정보·URL·내부 ID 등 제외 필드 |
| sentence_reviews | 원문, 수정 이유, 수정안, 근거 필드, 상태 |
| questions | 최대 10개의 우선순위 질문과 서버 생성 question_id |
| confirmation_questions | 우선 답할 상위 3개 질문 |
| diagnostics | 7개 기준별 issue/clear/not_evaluated |
| star_checks | 경험별 상황/과제/행동/결과 누락 요소 |
| changes | 이전 진단 기준 대비 resolved/unresolved/new/not_evaluated |
| telemetry | 모델·프롬프트 버전·지연·토큰 사용량·상태 |

문장 상태는 unchanged(수정 없음), formatting(서식 정리), improved(수정 제안), needs_confirmation(확인 필요)입니다.
이 상태는 첨삭 품질 인증이나 사실 검증 완료를 뜻하지 않습니다.
기존 section_reviews는 진단용이며 섹션 전체 수정안은 null입니다.

## 질문 답변 후 재첨삭

최초 응답에서 받은 정확한 값들을 사용합니다. question 텍스트는 호환용이며 서버 저장 질문으로 교체됩니다.

```json
{
  "cohort_id":"cohort-1",
  "resume_id":"resume-1",
  "request_id":"review-002",
  "previous_review_id":"review-001",
  "expected_input_hash":"최초 응답의 input_hash",
  "answers":[{
    "question_id":"최초 응답 questions의 question_id",
    "field_path":"projects[0].description",
    "question":"어떤 행동을 했나요?",
    "answer":"컴포넌트를 독립적으로 확인하는 환경을 구축했습니다."
  }]
}
```

원본 변경·순서 변경·항목 삭제 시 409 resume_version_changed를 반환합니다.
새 이력서로 먼저 첨삭을 다시 요청해야 합니다. 기존 답변을 자동 이동하지 않습니다.
항목 id가 없거나 중복이면 최초 진단은 가능하지만 답변 재사용은 409 stable_item_id_required입니다.
이전 결과와 같은 버전이면 기존 확인 답변을 누적합니다. 원본 변경 시 과거 답변은 이월하지 않습니다.
새 원본에 대한 변화 추적만 필요하면 previous_review_id를 보내고 answers와 expected_input_hash를 생략합니다.

## 근거와 개인정보

같은 프로젝트/경력의 형제 필드와 그 경험에 연결된 답변을 근거로 사용할 수 있습니다.
다른 항목의 기술·수치를 가져오면 보류합니다. 근거 인용이 어느 필드/답변에 있는지 evidence_sources에 기록합니다.
기술 별칭 비교를 유지하되 상위 카테고리화는 하지 않습니다.
이메일·한국 전화번호를 입력, 답변, 공고, 첨삭 초점에서 마스킹합니다.
자유서술의 모든 이름·주소·개인정보를 탐지하는 기능은 아닙니다.
답변은 사용자가 제공한 진술이며 외부 검증된 사실이 아닙니다.

## 저장과 중복 요청

결과 문서 경로는 기존 aiReviews/{request_id}입니다.
Firestore create의 원자적 충돌 검사로 선점하고 processing → complete 또는 failed로 기록합니다.
저장 구조는 response 아래 snake_case 응답 전체를 보관합니다. 기존 camelCase 결과 문서는 자동 마이그레이션하지 않습니다.
같은 request_id·입력으로 완료 결과를 재요청하면 저장된 결과를 돌려줍니다.
같은 ID의 다른 입력 또는 처리중/실패 요청은 409입니다.
실패 요청을 자동 재호출하지 않으며 모델 SDK 자동 재시도도 끕니다.
저장이 성공했으나 응답이 유실된 경우 저장된 response를 복구합니다.
모델 성공 후 저장 자체가 실패한 경우 결과를 별도 보관하지 못할 수 있습니다. 새 요청 ID 실행 전 운영자 확인이 필요합니다.
서버 종료로 processing이 남으면 자동 만료/재과금하지 않습니다. 운영 상태 복구 도구는 후속 과제입니다.
토큰 정보가 없으면 null이며 0으로 추정하지 않습니다. 오류 내용 대신 예외 종류만 저장합니다.

## 접근과 오류

Firebase uid, users/{uid}.isActive, cohortId, 이력서 userId를 서버에서 확인합니다.
이전 결과 조회도 같은 검사와 결과 소유권 확인을 거칩니다.
401 인증, 403 기수/활성상태, 404 타인 또는 없는 문서, 409 버전/중복, 422 입력, 503 외부 서비스 장애로 구분합니다.
Firestore Admin은 규칙을 우회하므로 이 검사들을 제거하면 안 됩니다.

## 남은 한계

- 의미적 환각 전부를 검증하지 못하며, 동일 숫자의 의미를 바꾸는 경우도 추가 평가가 필요합니다.
- 질문 중복 제거는 경험·topic 기준입니다. 모든 의미적 중복을 판정하는 별도 모델은 없습니다.
- 변화 추적은 진단 기준 단위이며 문장별 동일 이슈 추적은 아닙니다.
- 7개 진단/STAR는 모델 출력에 의존합니다. 미응답 기준은 통과로 간주하지 않고 not_evaluated로 채웁니다.
- Firestore 실제 통합·유료 모델 품질 평가·Flutter 화면·원본 적용·결과 조회 API·공고 ID 연결은 미검증/미구현입니다.
- 이번 작업은 외부 키를 사용한 실행 없이 가짜 모델/저장소로 테스트합니다.

JobStack resume/SKILL.md의 진단·STAR·변화 추적 개념을 설계 참고로 반영했습니다.
점수/등급, 개인정보 수집, 임의 성과 생성, 외부 크롤링 지침은 도입하지 않았습니다.
