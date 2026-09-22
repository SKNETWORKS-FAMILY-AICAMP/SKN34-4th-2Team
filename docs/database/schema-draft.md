# PLAYDATA LMS PostgreSQL Redesign - Schema Draft

> 확정 전 논리 스키마 초안.

## cohorts
```text
cohorts
- id PK
- cohort_number UNIQUE
- name
- description
- start_date
- end_date
- status
- classroom_name
- created_at
- updated_at
```

## users
```text
users
- id PK
- cohort_id FK NULL
- email UNIQUE
- personal_email
- password
- display_name
- role
- phone
- birth_date
- photo_url
- motto
- is_active
- must_change_password
- last_login_at
- created_at
- updated_at
```

## cohort_seating
```text
cohort_seating
- cohort_id PK/FK
- room_number
- layout JSONB
- published
- updated_at
```

## seat_presences
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
UNIQUE(cohort_id, user_id, presence_date, period)
```

## submission_tasks
```text
submission_tasks
- id PK
- title
- description
- submission_method
- form_url NULL
- guide_url NULL
- due_at
- published
- created_by FK
- created_at
- updated_at
```

## submission_task_cohorts
```text
submission_task_cohorts
- task_id FK
- cohort_id FK
PRIMARY KEY(task_id, cohort_id)
```

## submission_responses
```text
submission_responses
- id PK
- task_id FK
- user_id FK
- submitted_at
- source
- external_response_id NULL
- file_url NULL
- link_url NULL
- created_at
- updated_at
UNIQUE(task_id, user_id)
```

상태는 기본적으로 저장하지 않고 계산:
`pending / overdue / submitted / late`

## attendance_issue_reports
```text
attendance_issue_reports
- id PK
- user_id FK
- cohort_id FK
- attendance_date
- issue_type
- reason
- submitted_at
- review_status
- reviewed_by FK NULL
- reviewed_at NULL
- created_at
- updated_at
```

issue_type 후보:
`late / early_leave / outing / absent / official_leave`

## 아직 확정하지 않은 영역
- attendances 상세 스키마
- record submissions
- assessments
- resumes/career
- skills/job preferences
- mileage
- learning/curriculum
- community
- AI/LLMOps
