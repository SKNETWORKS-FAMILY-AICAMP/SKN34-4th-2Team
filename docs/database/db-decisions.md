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
- seating_layouts/seating_cells/seats로 과도하게 세분화하지 않는다.
- 기수별 현재 좌석 배치를 JSONB로 저장한다.
- 과거 좌석 배치는 기본적으로 보존하지 않는다.

후보:
```text
cohort_seating
- cohort_id PK/FK
- room_number
- layout JSONB
- published
- updated_at
```

## DEC-006 교시별 착석 확인
- 강사가 교시마다 확인하는 실제 착석 여부는 출결과 별개의 업무 이력이다.
- 관계형 테이블로 저장한다.

후보:
```text
seat_presences
- id PK
- cohort_id FK
- user_id FK
- presence_date
- period
- state
- checked_by FK
- checked_at
- note
```

후보 제약:
```text
UNIQUE(cohort_id, user_id, presence_date, period)
```

## DEC-007 기존 Assignment 재검토
- 기존 코드/Firebase에는 assignments가 존재하지만 관리자 실제 메뉴에는 일반 교육 과제 생성 흐름이 확인되지 않았다.
- 기존 assignments를 PostgreSQL에 그대로 복제하지 않는다.

## DEC-008 설문·제출을 Submission Task로 재정의
실제 운영 예:
- 리소스 환급 영수증
- 설문조사 Google Form
- 위클리 체크 Google Form
- 출결 Form

후보:
```text
submission_tasks
submission_responses
```

## DEC-009 출결 Form과 Attendance 분리
```text
Submission Task (출결 Form)
→ Submission Response / 외부 응답
→ 출결 판단 입력
→ Attendance 최종 기록
```

## DEC-010 저장 방식 판단 기준
1. 왜 저장하는가?
2. 현재 상태인가 이력인가?
3. 누가 생성/수정/조회하는가?
4. 사용자당 하나인가 여러 개인가?
5. 계산 가능한 값인가?
6. JOIN/집계/무결성이 필요한가?
7. JSONB가 더 자연스러운가?
8. 삭제 시 다른 업무 기록의 의미가 훼손되는가?
