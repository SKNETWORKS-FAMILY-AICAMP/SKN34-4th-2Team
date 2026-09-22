# PLAYDATA LMS PostgreSQL Redesign - DB Decision Log

## DEC-001 사용자-기수 관계
- 사용자당 현재 역할 하나.
- 학생/강사는 현재 기수를 최대 하나만 가진다.
- users.cohort_id 사용.
- cohort_memberships는 만들지 않는다.

## DEC-002 역할 이력 미관리
- user.role은 현재 역할만 표현한다.
- 학생→강사 등 역할 변경 이력은 별도 관리하지 않는다.

## DEC-003 Firestore 1:1 복제 금지
- 기존 collection/document 구조를 관계형 테이블로 그대로 옮기지 않는다.
- 실제 업무 프로세스를 재정의한 뒤 TO-BE 스키마를 설계한다.

## DEC-004 정규화 원칙
- 정규형 이름 자체보다 중복/갱신 이상/참조 무결성 방지가 목적이다.
- userDisplayName 같은 표시용 중복값은 기본적으로 제거한다.
- 거래 당시 가격 등 역사적 의미가 필요한 값은 snapshot 저장 가능하다.

## DEC-005 좌석 배치
- 기수별 현재 좌석 배치를 JSONB로 저장한다.
- 과거 좌석 배치는 기본적으로 보존하지 않는다.

## DEC-006 교시별 착석 확인
- 강사/관리자가 교시마다 확인하는 실제 착석 여부는 최종 출결과 별개의 업무 이력이다.
- 자리 확인 결과는 Attendance 상태를 직접 변경하지 않는다.
- 관계형 테이블로 저장한다.

## DEC-007 기존 Assignment 재검토
- 기존 코드/Firebase의 assignments를 PostgreSQL에 그대로 복제하지 않는다.

## DEC-008 설문·제출을 Submission Task로 재정의
- 실제 운영 예: 리소스 환급 영수증, 설문조사, 위클리 체크, 기타 행정 제출물.
- 후보 엔터티: submission_tasks, submission_responses.

## DEC-009 출결 Form과 Attendance 분리
- 출결 이슈 제출은 일반 Submission Task에서 분리한다.
- 출결 이슈 제출 기록은 Attendance의 입력 데이터일 수 있으나 동일한 레코드가 아니다.

## DEC-010 저장 방식 판단 기준
1. 왜 저장하는가?
2. 현재 상태인가 이력인가?
3. 누가 생성/수정/조회하는가?
4. 사용자당 하나인가 여러 개인가?
5. 계산 가능한 값인가?
6. JOIN/집계/무결성이 필요한가?
7. JSONB가 더 자연스러운가?
8. 삭제 시 다른 업무 기록의 의미가 훼손되는가?

## DEC-011 Submission Task는 복수 기수 배포 가능
- 한 기수 배포가 주 사용 사례지만 동일 제출 항목을 여러 기수에 배포할 수 있다.
- submission_tasks.cohort_id 단일 FK 대신 N:M 관계를 사용한다.

## DEC-012 제출 방식은 외부 Form에 고정하지 않음
- TO-BE에서는 내부 제출도 허용한다.
- submission_method 후보: external_form, internal_form, file_upload, link.

## DEC-013 제출 상태는 가능한 한 파생값으로 계산
- due_at과 submitted_at으로 pending/submitted/late/overdue를 계산한다.
- 중복 상태 저장으로 인한 불일치를 피한다.

## DEC-014 출결 이슈 제출은 별도 엔터티
- 학생이 특정 날짜의 출결 이슈를 개별 제출한다.
- attendance_issue_reports 엔터티로 설계한다.

## DEC-015 Attendance는 학생/날짜별 최종 일일 출결
- attendances는 학생별 날짜별 최종 업무 상태를 저장한다.
- UNIQUE(user_id, attendance_date)를 기본 제약으로 둔다.
- cohort_id는 과거 출결의 발생 당시 기수를 보존하기 위해 저장한다.

## DEC-016 고용24 원천 출결과 LMS Attendance 분리
- 실제 운영의 입실/퇴실/외출/조퇴 원천은 고용24 비콘 출결이다.
- 현재 프로젝트는 실시간 연동이 어려워 예시 출결 데이터를 사용한다.
- 향후 고용24 연동이 생기더라도 원천 이벤트와 최종 Attendance는 분리한다.
- 현재 단계에서는 원천 이벤트 전용 테이블을 강제하지 않고, 연동 요구가 확정되면 attendance_events/import_batches를 추가 검토한다.

## DEC-017 출결 Google Form은 판단 근거
- 출결 Google Form은 매니저가 출결 이슈와 병가/휴가 등 서류 필요 상황을 파악하기 위한 입력이다.
- Google Form 응답이 최종 Attendance 상태를 자동 결정하지 않는다.
- issue_type과 최종 attendance.status는 독립적으로 유지한다.

## DEC-018 기록실 승인/반려 권한은 관리자
- 기록실 제출 검토는 관리자 업무로 정의한다.
- 강사는 기록 승인/반려 권한을 갖지 않는 것을 기본으로 한다.

## DEC-019 반려 후 재제출은 새 기록 생성
- 반려된 record_submissions 행을 수정하여 재제출하지 않는다.
- 학생이 다시 제출하면 새로운 record_submissions 행을 생성한다.
- 기존 반려 기록은 감사/이력 목적으로 유지한다.

## DEC-020 기록실 증빙 파일은 별도 엔터티
- 한 제출에 여러 증빙 파일을 허용한다.
- 파일 바이트는 S3에 저장한다.
- PostgreSQL에는 record_submission_files로 storage key와 메타데이터를 저장한다.
- record_submissions.file_urls 배열은 사용하지 않는다.

## DEC-021 기록실 유형별 상세는 JSONB 우선
- 기록실 다섯 유형은 공통 필드는 유사하지만 상세 필드 구성이 다르다.
- 현재 규모와 조회 요구를 고려해 record_submissions.details JSONB를 우선 사용한다.
- 향후 유형별 통계/무결성 요구가 커지면 상세 테이블로 승격한다.

## DEC-022 기록 승인과 마일리지 적립 연결
- 승인된 기록이 미션 규칙을 충족하면 마일리지 적립을 자동 생성한다.
- 마일리지의 회계 원장은 mileage_transactions이다.
- record_submissions의 mileage_granted/mileage_amount를 원장으로 사용하지 않는다.
- 동일 record_submission에서 동일 자동 보상이 중복 생성되지 않도록 idempotency 제약을 둔다.

## DEC-023 마일리지 회수는 원거래 수정이 아닌 반대 거래
- 승인 취소/운영 조정 등으로 회수가 필요할 경우 기존 적립 거래를 삭제/수정하지 않는다.
- 별도의 음수 mileage transaction을 생성한다.
- 관리자 수동 조정은 기록실 승인 흐름과 별개의 마일리지 관리 기능으로 유지한다.
