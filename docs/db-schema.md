# DB 스키마 (Firestore → PostgreSQL)

기준 문서: [DB 스키마 (ERD 초안) — Firestore → PostgreSQL](https://app.notion.com/p/DB-ERD-Firestore-PostgreSQL-3e204cafa8368141beb3dbcd7b6ef424)

DDL: [`scripts/firestore_to_postgres/schema.sql`](../scripts/firestore_to_postgres/schema.sql)  
ETL: [`scripts/firestore_to_postgres/etl.py`](../scripts/firestore_to_postgres/etl.py)  
검증: [`docs/migration-report.md`](migration-report.md)

`youtube_curriculum_cache` 는 Redis. `posts` / `qna` 는 운영 건수 0이라 테이블을 만들지 않았다.  
`jobs` 스키마 DDL: [`scripts/firestore_to_postgres/jobs_schema.sql`](../scripts/firestore_to_postgres/jobs_schema.sql). SQLite 파일이 없어 공고 행 ETL은 건너뛰었다.

## 실행

서비스 계정 JSON은 `secrets/` (gitignore). Postgres URL은 환경 변수만 쓴다.

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS = "C:\Users\playdata2\SKN34-4th-2Team\secrets\firebase-adminsdk.json"
$env:FIREBASE_PROJECT_ID = "skn34-3rd-2team"
$env:DATABASE_URL = "postgresql://postgres:<password>@127.0.0.1:5432/lms"
python scripts/firestore_to_postgres/etl.py
```

운영 Firestore는 읽기만 한다. `etl.py`는 `lms`의 `public` 스키마를 지우고 다시 만든다.

## 만든 테이블

계정·기수: `cohorts`, `users`, `student_intakes`, `todos`, `alert_popup_dismissals`, `system_cache`  
수업: `schedules`, `curriculum_pdfs`, `curriculum_sheets`, `curriculum_rows`, `materials`, `attendances`, `roll_calls`, `roll_call_entries`  
좌석: `seating_rooms`, `seating_cells`, `seating_assignments`, `seat_assignments`, `project_teams`, `project_team_members`  
공지: `notices`, `scheduled_notices`, `alert_popups`  
과제·기록: `assignments`, `assignment_submissions`, `record_submissions`, `weekly_tasks`, `weekly_progress`, `form_tasks`, `form_responses`  
평가: `assessments`, `assessment_questions`, `assessment_submissions`, `assessment_answers`, `assessment_score_adjustments`  
마일리지: `mileage_transactions`, `mileage_settings`, `mileage_products`, `purchase_requests`, `purchase_request_items`, `mileage_cart_items`, `mission_progress`  
이력서: `resumes`, `resume_feedback`, `resume_feedback_reads`, `resume_revisions`  
학습실: `inflearn_packages`, `youtube_recommendations`, `recommendation_events`, `study_sources`, `study_notes`  
AI: `ai_generation_logs`, `ai_question_feedback`, `ai_eval_runs`  
첨삭: `job_requirement_profiles`, `resume_ai_reviews`, `resume_ai_applications`

## 의도적으로 안 만든 것

| 대상 | 이유 |
| --- | --- |
| `posts`, `post_comments` | 결정 3, 운영 0건 |
| `qna_threads`, `qna_messages` | 결정 3, 운영 0건 |
| `youtube_curriculum_cache` | 결정 5, Redis |
| `jobs.*` (데이터) | SQLite `job_store.sqlite` 없음. 스키마만 생성 |
| `jobRequirementProfiles` 등 | `job_requirement_profiles` / `resume_ai_*` 로 증분 ETL 완료 |

표 · 칸 설명: [`docs/db-tables.md`](db-tables.md) — `describe_schema.py` 가 실제 DB 에서 만든다.
