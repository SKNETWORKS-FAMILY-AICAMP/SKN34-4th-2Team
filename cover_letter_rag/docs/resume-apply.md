# 선택 수정안 적용·되돌리기 API

두 API는 Firebase 인증이 필요합니다. OpenAI/Pinecone은 호출하지 않습니다.
Flutter 화면과 Firestore 규칙은 변경하지 않았습니다.

## 적용

POST /api/v1/resumes/reviews/apply

```json
{
  "cohort_id": "cohort-id",
  "resume_id": "resume-id",
  "request_id": "apply-001",
  "review_id": "이전-첨삭-ID",
  "expected_input_hash": "첨삭 응답의 64자리 input_hash",
  "selected_indices": [0, 2]
}
```

selected_indices는 저장된 sentence_reviews 배열의 0부터 시작하는 위치입니다.
본문이나 수정문을 클라이언트가 전송하지 않으며 서버 저장 수정안만 사용합니다.
원본 버전이 동일하고 status가 improved/formatting인 수정안만 적용 가능합니다.
중복 선택, 보류된 수정안은 422, 원문 변경/중복 출현/겹치는 수정안/승인 완료는 409입니다.
같은 필드의 여러 수정은 원문 위치 기준 뒤에서부터 적용하며 부분 성공은 없습니다.
마스킹된 연락처가 수정문에 포함되면 자동 적용을 차단합니다.

응답: operation_id, 적용 후 input_hash, changed_fields.
클라이언트는 성공 후 이력서를 다시 읽어 편집 화면의 오래된 값으로 덮어쓰지 않아야 합니다.
남은 수정안을 추가 적용하려면 변경된 이력서로 새 첨삭을 받아야 합니다.

## 되돌리기

POST /api/v1/resumes/reviews/undo

```json
{
  "cohort_id": "cohort-id",
  "resume_id": "resume-id",
  "request_id": "undo-001",
  "application_id": "apply-001",
  "expected_input_hash": "적용 응답의 input_hash"
}
```

해당 적용 직후의 내용과 현재 원본이 같을 때만 적용 전 content 전체로 복원합니다.
그 이후 사용자가 수정했거나 이미 되돌린 경우 409이며 자동 병합하지 않습니다.
같은 request_id와 같은 입력의 재시도는 이전 성공 응답을 반환합니다.
이 응답의 해시는 해당 작업 당시의 결과이며, 이후 별도 편집이 발생했다면 현재 문서를 다시 조회해야 합니다.

## 저장·권한

cohorts/{cohortId}/resumes/{resumeId}/aiApplications/{request_id}에
변경 전 content, 변경 후 해시, 작업 종류, 원본 결과 ID, 소유자, 시각을 보관합니다.
백업에는 원본 개인정보가 포함될 수 있으므로 서버 권한으로만 접근하며 클라이언트 직접 읽기 규칙은 추가하지 않습니다.
기존 revisions/feedback 스키마·revisionCount를 변경하지 않습니다.
문장 교체만 허용하므로 기존 섹션 완료 여부는 유지합니다.
사용자 활성상태/기수/소유권/승인상태, 원본/결과 조회, 백업·원본 변경을 하나의 트랜잭션으로 실행합니다.
approved 또는 completed 이력서는 적용과 복원을 차단합니다.

가짜 트랜잭션 테스트는 구현 로직을 검사하며 실제 Firestore 동시성 검증은 별도 필요합니다.
