# PLAYDATA LMS PostgreSQL Redesign - Schema Draft

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

현재는 고용24 연동 요구가 확정되지 않았으므로 생성하지 않는다.
