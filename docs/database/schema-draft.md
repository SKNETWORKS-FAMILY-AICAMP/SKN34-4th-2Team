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
PRIMARY KEY(user_id, skill_id)

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
