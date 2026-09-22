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

state 후보:
`confirmed / held`

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

## attendances
```text
attendances
- id PK
- user_id FK
- cohort_id FK
- attendance_date
- check_in_at NULL
- check_out_at NULL
- status NULL
- data_source
- finalized_by FK NULL
- finalized_at NULL
- created_at
- updated_at
UNIQUE(user_id, attendance_date)
```

status 후보:
`present / late / early_leave / absent / official_leave`

data_source 후보:
`mock / manual / employment24_import`

## attendance_issue_reports
```text
attendance_issue_reports
- id PK
- user_id FK
- cohort_id FK
- attendance_date
- issue_type
- leave_type NULL
- reason
- submitted_at
- source
- external_response_id NULL
- review_status NULL
- reviewed_by FK NULL
- reviewed_at NULL
- created_at
- updated_at
```

issue_type 후보:
`late / early_leave / outing / absent / leave`

leave_type 후보:
`sick_leave / vacation / official / other`

source 후보:
`google_form / internal_form / manual`

## record_submissions
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
```

type:
`certification / study / blog / study_cert / precourse_quiz`

status:
`pending / approved / rejected`

details 예시:
```json
{"cert_type": "PCCE"}
{"week_number": 3, "is_team_study": true}
{"week_number": 4, "link": "https://..."}
{"learning_date": "2026-09-22", "learning_content": "..."}
{"quiz_score": 85}
```

반려 후 재제출은 기존 행 수정이 아니라 새 행 생성.

## record_submission_files
```text
record_submission_files
- id PK
- submission_id FK
- storage_key
- original_filename
- content_type
- file_size
- uploaded_at
```

- 실제 파일 바이트는 S3에 저장.
- 한 submission에 여러 파일 허용.

## mileage_transactions (기록실 연계 기준 초안)
```text
mileage_transactions
- id PK
- user_id FK
- cohort_id FK
- amount
- transaction_type
- record_submission_id FK NULL
- reversed_transaction_id FK NULL
- reason
- created_by FK NULL
- created_at
```

transaction_type 후보:
`record_reward / admin_adjustment / purchase / reversal`

제약 방향:
- record_reward는 동일 record_submission에 대해 중복 생성되지 않아야 한다.
- reversal은 기존 거래를 삭제/수정하지 않고 음수 거래로 남긴다.
- 관리자 수동 조정은 record_submission_id 없이 생성 가능하다.

## 향후 검토 후보
```text
attendance_events
- id PK
- user_id FK
- cohort_id FK
- occurred_at
- event_type
- source
- external_id
```

## 아직 확정하지 않은 영역
- assessments
- resumes/career
- skills/job preferences
- mileage 전체 규칙/상품/구매
- learning/curriculum
- community
- AI/LLMOps
