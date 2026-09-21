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

상태 후보: `planned / active / closed`

## users
```text
users
- id PK
- cohort_id FK NULL
- email UNIQUE
- personal_email
- password  # Django hashed password field
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
```

제약 후보:
```text
UNIQUE(cohort_id, user_id, presence_date, period)
```

## submission_tasks
```text
submission_tasks
- id PK
- cohort_id FK
- title
- description
- task_type
- submission_method
- form_url
- guide_url
- due_at
- published
- created_by FK
- created_at
- updated_at
```

## submission_responses
```text
submission_responses
- id PK
- task_id FK
- user_id FK
- status
- submitted_at
- external_response_id
- file_url
- link_url
- created_at
- updated_at
```

제약 후보:
```text
UNIQUE(task_id, user_id)
```

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
