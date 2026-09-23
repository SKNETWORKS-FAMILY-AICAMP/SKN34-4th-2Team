# PostgreSQL Logical Schema - Freeze Candidate

## Identity
```text
cohorts
users
student_intakes
todos
```

## Seating / Attendance
```text
cohort_seating
seat_presences
attendances
attendance_issue_reports
```

## Submission
```text
submission_tasks
submission_task_cohorts
submission_responses
```

## Records
```text
record_submissions
- id PK
- user_id FK
- cohort_id FK
- type
- title
- details JSONB
- status
- submitted_at
- reviewed_by FK NULL
- reviewed_at NULL
- review_comment NULL
- created_at
- updated_at

record_submission_files
- id PK
- submission_id FK
- storage_key
- original_filename
- content_type
- file_size
- uploaded_at
```

## Assessment
```text
assessments
assessment_questions
assessment_submissions
assessment_answers
assessment_score_adjustments
```

## Practice
```text
practice_sets
- id PK
- legacy_id UNIQUE
- cohort_id FK
- source_title
- lesson_date
- day_label
- title
- source_files JSONB
- generation_model
- created_at

practice_problems
- id PK
- set_id FK
- position
- kind CHECK(concept, code_output, code_blank, code_fix, code_write)
- topic
- prompt
- source_files JSONB
- explanation
- choices JSONB
- answer_index NULL
- starter_code
- expected_stdout
- blank_answers JSONB
- reference_solution
- hidden_tests
- packages JSONB
UNIQUE(set_id, position)

practice_attempts
- user_id FK
- problem_id FK
- passed
- tries
- answered_at
PRIMARY KEY(user_id, problem_id)

practice_reports
- id PK
- user_id FK
- problem_id FK
- reason CHECK(unclear, answer, tests, offtopic, other)
- note
- created_at
- updated_at
UNIQUE(user_id, problem_id)

practice_reviews
- problem_id PK/FK
- decision CHECK(hidden, kept)
- decided_by_id FK
- decided_at

practice_coverage
- cohort_id FK
- source_title
- data JSONB
- updated_at
UNIQUE(cohort_id, source_title)
```

`hidden_tests`와 `reference_solution`은 저장은 하되 학생용 serializer/schema에서 제외한다.
학생 코드 실행은 별도 격리 runner의 책임이다.

## Mileage
```text
mileage_transactions
mileage_settings
mileage_products
purchase_requests
purchase_request_items
mileage_cart_items   -- 서버 저장 장바구니 사용 시
```

## Resume
```text
resumes
- id PK
- user_id FK
- title
- status
- content JSONB
- is_base_resume
- base_resume_id FK -> resumes.id NULL, ON DELETE SET NULL
- linked_job_id NULL
- revision_count
- created_at
- updated_at

resume_feedback
- id PK
- resume_id FK
- section_key
- content
- author_id FK
- parent_id FK NULL
- created_at

resume_feedback_reads
- resume_id FK
- user_id FK
- feedback_id FK
- read_at
PRIMARY KEY(resume_id, user_id, feedback_id)

resume_revisions
- id PK
- resume_id FK
- revision_no
- content JSONB
- created_by FK
- created_at
UNIQUE(resume_id, revision_no)
```

Resume 제약/검증:
```text
CHECK(base_resume_id IS NULL OR base_resume_id <> id)
기본 이력서(is_base_resume=true)는 base_resume_id가 NULL
base resume와 tailored resume의 user_id 일치: Django service validation
legacy sections JSONB는 ETL에서 content.section_status로 병합
linked_job_id는 jobs 스키마가 Django 관리 대상으로 확정되기 전까지 stable job ID로 저장하고,
이후 가능한 경우 jobs FK로 승격
```

## Skills / Career Profile
```text
skills
- id PK
- canonical_name UNIQUE
- category NULL
- created_at

user_skills
- user_id FK
- skill_id FK
- proficiency NULL
- source NULL
- evidence JSONB NULL
- updated_at
id PK
UNIQUE(user_id, skill_id)

user_job_preferences
- user_id PK/FK
- preferences JSONB
- updated_at
```

향후 Resume content에서 기술을 추출할 때 `user_skills`를 자동 덮어쓰지 않고 source/evidence 기준으로 upsert한다.

## Career AI / Job Matching
```text
job_requirement_profiles
resume_ai_reviews
resume_ai_applications
```

추가 bridge 후보:
```text
job_required_skills
- job_id
- skill_id FK
- importance NULL
- evidence_text NULL

project_skills
- project_source_id
- skill_id FK
```

`jobs` 원본 스키마는 기존 jobs schema를 우선 재사용한다.
`lms.0003_jobs_schema`가 `jobs_schema.sql`의 테이블·인덱스·view를 고정된
migration snapshot으로 생성한다. 운영 `jobs` schema에서 수집기의 런타임 DDL은
제거했으며, 테스트 격리 schema에서만 자동 생성한다.
기존 수집 데이터가 있는 환경에서는 migration 적용 전 중복·컬럼 타입을 먼저 검증한다.

## Policy / FAQ 원본 (물리 스키마 적용, 적재 경로 미완료)

현재 정책 ingestion은 파일/Notion에서 추출한 본문을 Pinecone에 직접 upsert한다.
PostgreSQL source-of-truth 원칙을 지키려면 다음 두 계층이 필요하다.

```text
policy_documents
- id, source_key UNIQUE, source_type, source_name, source_url
- storage_key NULL, title, is_active, created_at, updated_at

policy_document_revisions
- id, document_id FK, revision_no, content_sha256, extracted_text
- source_updated_at NULL, ingested_at, extraction_metadata JSONB
- UNIQUE(document_id, revision_no)
```

`source_key`는 기존 `SourceSection.document_key`와 같은 안정 식별자로 매핑한다.
PDF 등의 원본 바이트는 S3 key로, Notion은 원본 URL로 가리키고 추출 본문은
revision에 보존한다. Pinecone chunk에는 document/revision ID와 content hash를
담아 재생성할 수 있어야 한다. 현재 revision은 해당 document의 가장 큰
`revision_no`로 결정하며, 중복 상태를 만들지 않기 위해 별도의
`current_revision_id` 포인터는 두지 않는다. `lms.0004_policy_documents`로
두 테이블과 제약을 검증 DB에 적용했다. `import_policy_sources`로 파일/Notion의
추출 본문을 PostgreSQL에 revision으로 저장할 수 있다. 검증 DB의 로컬
Markdown·CSV 원본 7건에서 재실행 시 중복 revision이 생기지 않음을 확인했다.
`project_policy_index`의 PostgreSQL → Pinecone 스테이징 projection은
미리보기까지 확인했다. 실제 Pinecone 쓰기와 원본 파일의 S3 key 대조는
아직 검증하지 않았다.

## Curriculum / Class
```text
schedules
curriculum_pdfs
curriculum_sheets
curriculum_rows
materials
```

파일 필드는 URL보다 `storage_key` 우선.

## Team
```text
project_teams
project_team_members
```

## Notice
```text
notices
scheduled_notices
alert_popups
alert_popup_dismissals
```

## Study
```text
inflearn_packages
youtube_recommendations
recommendation_events
study_sources
study_notes
```

## AI Operations
```text
ai_generation_logs
ai_question_feedback
ai_eval_runs
```

## System
```text
system_cache
```

## Redis only
```text
youtube_curriculum_cache
celery broker/cache
temporary AI/job state when appropriate
```

## Not in initial integration
```text
posts
post_comments
qna_threads
qna_messages
legacy assignments
```

## 반드시 제거/변환할 legacy 표현
```text
users.skills text[]                  -> skills + user_skills
users.job_preferences JSONB          -> user_job_preferences.preferences
record_submissions.file_urls[]       -> record_submission_files
form_tasks/form_responses            -> submission_tasks/submission_responses
seating_rooms/cells/assignments      -> cohort_seating JSONB (current layout)
roll_calls/roll_call_entries         -> seat_presences
```


# Physical Constraint / Index Checklist

## 필수 UNIQUE
```text
cohorts(cohort_number or code)
users(email)
cohort_seating(cohort_id)
seat_presences(cohort_id, user_id, presence_date, period)
attendances(user_id, attendance_date)
submission_task_cohorts(task_id, cohort_id)
submission_responses(task_id, user_id)
assessment_submissions(assessment_id, user_id)
practice_sets(legacy_id)
practice_problems(set_id, position)
practice_attempts(user_id, problem_id)
practice_reports(user_id, problem_id)
practice_coverage(cohort_id, source_title)
resume_revisions(resume_id, revision_no)
resumes(user_id) WHERE is_base_resume = true   -- 사용자별 기본 이력서 1개 정책 채택 시 partial UNIQUE
skills(canonical_name)
user_skills(user_id, skill_id)
```

## 필수/권장 INDEX
```text
users(cohort_id, role)
attendances(cohort_id, attendance_date)
seat_presences(cohort_id, presence_date, period)
submission_tasks(due_at, published)
submission_responses(task_id, submitted_at)
record_submissions(user_id, status, submitted_at)
record_submissions(cohort_id, type, status)
assessments(cohort_id, published, start_at, end_at)
assessment_submissions(assessment_id, submitted_at)
practice_sets(cohort_id, lesson_date DESC)
practice_attempts(problem_id)
practice_reports(problem_id)
mileage_transactions(user_id, created_at DESC)
purchase_requests(cohort_id, status, created_at DESC)
resumes(user_id, updated_at DESC)
resumes(base_resume_id)
resumes(linked_job_id)
resume_feedback(resume_id, created_at)
user_skills(skill_id)
scheduled_notices(is_active, next_publish_at)
notices(cohort_id, created_at DESC)
```

## FK 삭제 정책 기본
```text
업무 이력 부모(users/cohorts)       -> RESTRICT 또는 soft deactivate
종속 child(answer/file/item 등)     -> CASCADE
검토자/작성자처럼 부가 참조         -> SET NULL
```

업무 이력 데이터는 사용자 삭제로 함께 사라지지 않도록 한다.

## 물리 구현 점검 (2026-09-23)

- `lms.0001_initial`은 검증용 PostgreSQL에서 적용되었으며 Django managed 테이블이 생성되었다. 이는 운영 DB 적용을 의미하지 않는다.
- 위 인덱스 체크리스트 중 빠져 있던 assessments, assessment_submissions, mileage_transactions, purchase_requests, scheduled_notices, notices의 복합 인덱스 6개를 `lms.0002_physical_indexes`로 정의했다.
- `job_requirement_profiles`, `resume_ai_reviews`, `resume_ai_applications`는 이미 Django 모델과 초기 migration에 있다. 별도 신규 생성 대상이 아니다.
- `jobs` 원본 schema는 `lms.0003_jobs_schema`가 소유한다. 검증 DB의 7개 테이블 및 view 생성과 수집기 연결을 확인했다. 실제 일일 크롤러·Pinecone 전체 회귀와 운영 배포는 별도 검증이 필요하다.
- 정책/FAQ 원본 및 revision 테이블은 `lms.0004_policy_documents`로 추가했고 `import_policy_sources`의 로컬 Markdown·CSV 7건 적재·재실행을 검증했다. `project_policy_index`는 7건/56개 chunk의 미리보기만 확인했다. 기존 Pinecone 직접 적재 경로가 남아 있고 전체 corpus/실제 쓰기는 미검증이므로 정책 ETL 완료로 간주하지 않는다.
- Django `on_delete` 설정과 실제 PostgreSQL FK의 `ON DELETE` 동작은 다르다. 현재 DB FK는 `NO ACTION`이므로, 위 삭제 정책은 ORM 수준 정책이며 직접 SQL 삭제에는 적용되지 않는다.
