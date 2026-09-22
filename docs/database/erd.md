# PostgreSQL Logical ERD

```mermaid
erDiagram
    COHORTS ||--o{ USERS : current_members
    COHORTS ||--|| COHORT_SEATING : has
    USERS ||--o{ SEAT_PRESENCES : checked
    COHORTS ||--o{ SEAT_PRESENCES : contains

    USERS ||--o{ ATTENDANCES : has
    COHORTS ||--o{ ATTENDANCES : history
    USERS ||--o{ ATTENDANCE_ISSUE_REPORTS : submits

    SUBMISSION_TASKS ||--o{ SUBMISSION_TASK_COHORTS : targets
    COHORTS ||--o{ SUBMISSION_TASK_COHORTS : receives
    SUBMISSION_TASKS ||--o{ SUBMISSION_RESPONSES : receives
    USERS ||--o{ SUBMISSION_RESPONSES : submits

    USERS ||--o{ RECORD_SUBMISSIONS : submits
    RECORD_SUBMISSIONS ||--o{ RECORD_SUBMISSION_FILES : contains

    COHORTS ||--o{ ASSESSMENTS : has
    ASSESSMENTS ||--o{ ASSESSMENT_QUESTIONS : contains
    ASSESSMENTS ||--o{ ASSESSMENT_SUBMISSIONS : receives
    USERS ||--o{ ASSESSMENT_SUBMISSIONS : submits
    ASSESSMENT_SUBMISSIONS ||--o{ ASSESSMENT_ANSWERS : contains
    ASSESSMENT_QUESTIONS ||--o{ ASSESSMENT_ANSWERS : answered
    ASSESSMENT_SUBMISSIONS ||--o{ ASSESSMENT_SCORE_ADJUSTMENTS : adjusted

    USERS ||--o{ MILEAGE_TRANSACTIONS : owns
    COHORTS ||--|| MILEAGE_SETTINGS : configures
    COHORTS ||--o{ MILEAGE_PRODUCTS : offers
    USERS ||--o{ PURCHASE_REQUESTS : requests
    PURCHASE_REQUESTS ||--o{ PURCHASE_REQUEST_ITEMS : contains
    PURCHASE_REQUESTS ||--o{ MILEAGE_TRANSACTIONS : causes

    USERS ||--o{ RESUMES : owns
    RESUMES ||--o{ RESUME_FEEDBACK : receives
    RESUMES ||--o{ RESUME_REVISIONS : versions

    USERS ||--o{ USER_SKILLS : has
    SKILLS ||--o{ USER_SKILLS : describes
    USERS ||--|| USER_JOB_PREFERENCES : configures

    PROJECT_TEAMS ||--o{ PROJECT_TEAM_MEMBERS : contains
    USERS ||--o{ PROJECT_TEAM_MEMBERS : joins
```

## Career projection
```text
PostgreSQL
User ─ UserSkill ─ Skill
  │
  ├─ Resume(content)
  └─ Project / Experience
                    │
Job ─ RequiredSkill ┘

        ↓ projector

Neo4j
(Student)-[:HAS_EXPERIENCE]->(Project)-[:USES]->(Skill)
(Skill)<-[:REQUIRES]-(Job)-[:POSTED_BY]->(Company)
```

Neo4j의 모든 핵심 node에는 PostgreSQL source ID를 보존한다.
