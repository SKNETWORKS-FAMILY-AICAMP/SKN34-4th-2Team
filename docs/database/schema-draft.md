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
