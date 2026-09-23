# Firestore / Legacy PostgreSQL → TO-BE Migration Plan

> 상태: **통합 실행 기준**
>
> `feature/test/scripts/firestore_to_postgres/schema.sql`은 AS-IS 마이그레이션 스키마로 보고,
> 최종 TO-BE 스키마는 Django managed models + migrations가 소유한다.

## 1. Legacy → TO-BE 매핑

| Legacy (`feature/test`) | TO-BE | 처리 |
|---|---|---|
| `cohorts` | `cohorts` | 유지, 컬럼 정리 |
| `users` | `users` | 유지, 인증/skills/job_preferences/file 컬럼 정리 |
| `student_intakes` | `student_intakes` | 유지 |
| `todos` | `todos` | 유지 |
| `system_cache` | `system_cache` | 제한적 유지 |
| `schedules` | `schedules` | 유지 |
| `curriculum_pdfs` | `curriculum_pdfs` | 유지, URL → storage key |
| `curriculum_sheets` | `curriculum_sheets` | 유지, storage path 정리 |
| `curriculum_rows` | `curriculum_rows` | 유지 |
| `materials` | `materials` | 유지, file URL → storage key |
| `attendances` | `attendances` | 변환: final daily attendance 중심 |
| `roll_calls` + `roll_call_entries` | `seat_presences` | 통합 변환 |
| `seating_rooms` + `seating_cells` + `seating_assignments` + `seat_assignments` | `cohort_seating` | 현재 레이아웃 JSONB로 변환 |
| `project_teams` | `project_teams` | 유지 |
| `project_team_members` | `project_team_members` | 유지 |
| `scheduled_notices` | `scheduled_notices` | 유지 |
| `notices` | `notices` | 유지, author_name 제거 후보 / image key화 |
| `alert_popups` | `alert_popups` | 유지 |
| `alert_popup_dismissals` | `alert_popup_dismissals` | 유지 |
| `assignments` | - | 초기 TO-BE에서 제외 |
| `assignment_submissions` | - | 초기 TO-BE에서 제외 |
| `record_submissions` | `record_submissions` | 변환 |
| `record_submissions.file_urls[]` | `record_submission_files` | 분리 |
| `weekly_tasks` | - / `submission_tasks` | 실제 사용 데이터 확인 후 generic submission으로 흡수 |
| `weekly_progress` | 파생값 우선 | 가능하면 제출 데이터에서 계산 |
| `form_tasks` | `submission_tasks` | 변환 |
| `form_responses` | `submission_responses` | 변환 |
| - | `submission_task_cohorts` | 신규 |
| `assessments` | `assessments` | 유지 + lifecycle/status 정리 |
| `assessment_questions` | `assessment_questions` | 유지 |
| `assessment_submissions` | `assessment_submissions` | 유지 |
| `assessment_answers` | `assessment_answers` | 유지 |
| `assessment_score_adjustments` | `assessment_score_adjustments` | 유지 |
| `practice.sets` | `practice_sets` | cohort_code를 cohort_id FK로 매핑 |
| `practice.problems` | `practice_problems` | set FK와 문제 순서/유형 보존 |
| `practice.attempts` | `practice_attempts` | user_uid를 user_id FK로 매핑 |
| `practice.reports` | `practice_reports` | user_uid를 user_id FK로 매핑 |
| `practice.reviews` | `practice_reviews` | decided_by_uid를 users FK로 매핑 |
| `practice.coverage` | `practice_coverage` | cohort_code를 cohort_id FK로 매핑 |
| `mileage_transactions` | `mileage_transactions` | 유지, ledger semantics 강화 |
| `mileage_settings` | `mileage_settings` | 유지 |
| `mileage_products` | `mileage_products` | 유지 |
| `purchase_requests` | `purchase_requests` | 유지 |
| `purchase_request_items` | `purchase_request_items` | 유지, snapshot 정책 명시 |
| `mileage_cart_items` | `mileage_cart_items` | 서버 장바구니 사용 시 유지 |
| `mission_progress` | `mission_progress` 또는 파생 | 적립 규칙 구현에 필요한 범위만 유지 |
| `resumes` | `resumes` | 유지, `content JSONB` |
| `resumes.sections` | `resumes.content.section_status` | 섹션 완성 상태로 병합, 충돌 리포트 |
| `resumes.base_resume_id` / `tailoredResumes` | `resumes.base_resume_id` | self FK로 파생 관계 보존 |
| `resumes.linked_job_id` | `resumes.linked_job_id` | stable job ID 보존, jobs 관리 전환 후 FK 승격 검토 |
| `resume_feedback` | `resume_feedback` | 유지, 표시 이름 중복 제거 |
| `resume_feedback_reads` | `resume_feedback_reads` | 유지 |
| `resume_revisions` | `resume_revisions` | 유지, JSONB snapshot |
| `users.skills text[]` | `skills` + `user_skills` | 정규화 |
| `users.job_preferences jsonb` | `user_job_preferences` | 1:1 분리 |
| `inflearn_packages` | `inflearn_packages` | 유지 |
| `youtube_recommendations` | `youtube_recommendations` | 유지 |
| `recommendation_events` | `recommendation_events` | 유지 |
| `study_sources` | `study_sources` | 유지 |
| `study_notes` | `study_notes` | 유지 |
| `ai_generation_logs` | `ai_generation_logs` | 유지 |
| `ai_question_feedback` | `ai_question_feedback` | 유지 |
| `ai_eval_runs` | `ai_eval_runs` | 유지 |
| `job_requirement_profiles` | `job_requirement_profiles` | 유지 |
| `resume_ai_reviews` | `resume_ai_reviews` | 유지 |
| `resume_ai_applications` | `resume_ai_applications` | 유지 |
| `posts`, `post_comments` | - | 초기 통합 제외 |
| `qna_threads`, `qna_messages` | - | 초기 통합 제외 |
| `youtube_curriculum_cache` | Redis | PostgreSQL에 만들지 않음 |

## 2. 신규 TO-BE 테이블

```text
cohort_seating
seat_presences
attendance_issue_reports

submission_tasks
submission_task_cohorts
submission_responses

record_submission_files

skills
user_skills
user_job_preferences

job_required_skills      # Career AI에서 요구기술 구조화 시
project_skills           # 프로젝트-기술 연결이 필요할 때
```

## 3. users 변환

### 유지
- id
- firebase_uid: migration용 legacy identity로 당분간 유지 가능
- email
- personal_email
- display_name
- role
- cohort_id
- is_active
- must_change_password
- motto
- social_links
- birth_date
- mileage_balance (cache 사용 시)
- last_login / created_at / updated_at

### 이동/제거
```text
skills text[]
→ skills + user_skills

job_preferences JSONB
→ user_job_preferences.preferences

photo_url / photo_storage_path
→ photo_storage_key
```

### 인증
기존 plaintext `password` 의미를 그대로 유지하지 않는다.

최종 Django에서는:
```text
Django password hash
set_password()
check_password()
```

또는 Custom User Model(`AbstractBaseUser`)을 사용한다.

## 4. 출결 변환

Legacy:
```text
attendances
- date_key
- status
- status_source
- check_in_time
- check_out_time
- form_attendance_type
- official_leave_*
```

TO-BE:
```text
attendances
- id
- user_id
- cohort_id
- attendance_date
- check_in_at
- check_out_at
- status
- data_source
- finalized_by NULL
- finalized_at NULL
- created_at
- updated_at
UNIQUE(user_id, attendance_date)
```

변환 원칙:
- `date_key` → `attendance_date`
- 단순 `time` 값은 날짜와 결합해 timestamptz로 변환 가능하면 변환
- `form_attendance_type`, `official_leave_*`는 최종 attendance에 무리하게 유지하지 않고 `attendance_issue_reports`로 분리 가능한 데이터를 이동
- 원천/예시 데이터 구분을 `data_source`에 보존

## 5. 좌석 변환

Legacy 관계형 레이아웃:
```text
seating_rooms
seating_cells
seating_assignments
seat_assignments
```

TO-BE:
```text
cohort_seating
- cohort_id PK/FK
- room_number
- layout JSONB
- published
- updated_at
```

현재 공개된 좌석 배치만 JSONB로 직렬화한다.
과거 방/셀 이력은 TO-BE 핵심 이력으로 이전하지 않는다.

교시별 실제 착석 확인:
```text
roll_calls + roll_call_entries
→ seat_presences
```

## 6. 제출 변환

```text
form_tasks
→ submission_tasks

form_tasks.cohort_id
→ submission_task_cohorts(task_id, cohort_id)

form_responses
→ submission_responses
```

Google 응답 ID는:
```text
google_response_id
→ external_response_id
```

로 일반화한다.

## 7. 기록실 변환

Legacy `record_submissions`의 유형별 컬럼:
```text
cert_type
week_number
week_label
link
quiz_score
learning_date
learning_content
is_team_study
```

TO-BE:
```text
record_submissions.details JSONB
```

예:
```json
{"cert_type":"PCCE"}
{"week_number":3,"is_team_study":true}
{"week_number":4,"link":"https://..."}
{"quiz_score":85}
{"learning_date":"2026-09-01","learning_content":"..."}
```

삭제:
```text
mileage_granted
mileage_amount
```

마일리지 적립 여부는 `mileage_transactions`에서 판단한다.

파일:
```text
file_urls[]
→ record_submission_files(storage_key, original_filename, ...)
```

## 8. Assessment

기존 구조를 거의 그대로 재사용한다.

필수 정리:
- `choices text[]`, `accepted_answers text[]`는 현재 두 문항 유형에서는 유지 가능
- `auto_score` / `final_score` 분리 유지
- `(assessment_id, user_id)` UNIQUE 유지
- `graded_by`, `graded_at` 필요 시 명시
- 응시 이력이 있는 assessment는 hard delete 금지 정책
- thumbnail은 `thumbnail_storage_key` 중심

## 9. Mileage

원장:
```text
mileage_transactions
```

원칙:
- 거래 immutable
- 적립/환불 = +
- 구매/차감/소멸 = -
- 승인 시 purchase 거래 생성
- 승인 취소 시 refund/reversal 거래 생성
- 종강 + 14일 후 expiry 거래 생성

`users.mileage_balance`를 유지하면:
```text
ledger INSERT + cached balance UPDATE
```
를 반드시 동일 DB transaction으로 처리한다.

## 10. Resume / Career

Resume 문서는:
```text
resumes.content JSONB
```
유지.

기본 이력서와 공고 맞춤 이력서는 같은 `resumes` 테이블에서 관리한다.
```text
base_resume_id -> resumes.id (ON DELETE SET NULL)
linked_job_id  -> 대상 채용공고 stable ID
```

Legacy `sections JSONB`는 버리지 않고 `content.section_status`로 병합한다. 동일 키가 양쪽에
있을 때의 우선순위와 충돌 건수는 ETL mapping 및 migration report에 남긴다.
맞춤 이력서의 소유자는 base resume의 소유자와 같아야 하며, 자기 자신을 base로
참조할 수 없다.

관계 검색 축은 별도:
```text
skills
user_skills
user_job_preferences
```

Neo4j/Pinecone은 PostgreSQL 적재 완료 이후 rebuild 가능한 projection으로 처리한다.

## 11. File/S3 변환

기존 Firebase Storage → S3 object copy는 그대로 재사용한다.

DB:
```text
s3://bucket/path/file.pdf
```
전체 값을 canonical 값으로 두기보다:
```text
path/file.pdf
```
형태의 `storage_key`를 우선 저장한다.

적용 대상:
- users profile image
- curriculum PDF/sheet
- materials
- record files
- assessment thumbnail
- notice image

## 12. Django migration 전환

### 개발자 로컬 DB
현재 DB는 공유 데이터가 아니므로 통합 시 fresh DB 재생성을 기본 전략으로 한다.

```powershell
dropdb lms
createdb lms

python manage.py migrate
python manage.py import_legacy_data
```

실제 명령 이름은 구현 시 결정한다.

### 스키마 소유권
```text
Django models + migrations = schema owner
ETL/import command         = data owner
S3 migration               = binary object migration
```

통합 이후 ETL이 `DROP SCHEMA public`을 수행하면 안 된다.

## 13. 검증

필수 검증:
- source/target row count
- orphan FK 0건
- UNIQUE violation 0건
- 누락 user mapping
- S3 missing object
- attendance UNIQUE(user,date)
- assessment UNIQUE(assessment,user)
- record file count
- mileage ledger sum ↔ cache balance
- duplicate canonical skills
- resume owner/revision mapping
- base resume/tailored resume owner mismatch 0건
- base_resume_id self reference 0건
- linked_job_id 매핑 실패 및 legacy sections 병합 충돌 리포트

## 14. 적재 순서

```text
1. cohorts
2. users
3. student_intakes / todos
4. curriculum / schedules / materials
5. notices
6. project teams
7. attendance + seating
8. submission tasks/responses
9. records + files
10. assessments
11. mileage
12. resumes/feedback/revisions
13. skills/job preferences/career AI
14. study/AI logs
15. S3 key reconciliation
16. validation
17. Pinecone rebuild
18. Neo4j projection
```

## 15. 통합 성공 기준

아래를 만족하면 DB 설계를 구현 단계로 Freeze한다.

- Django migration만으로 빈 DB 생성 가능
- ETL이 schema를 drop/create하지 않음
- legacy→TO-BE mapping 누락 없음
- 핵심 FK/UNIQUE 제약 적용
- S3 key 기준 통일
- 인증 plaintext 제거
- 검증 스크립트 통과
- Pinecone/Neo4j 없이도 LMS 핵심 기능 동작
