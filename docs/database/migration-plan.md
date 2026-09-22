# Firestore / Legacy PostgreSQL → TO-BE Migration Plan

## Phase 1. Schema
1. Django managed models 작성
2. 초기 migration 생성
3. fresh local `lms` DB에서 `python manage.py migrate`
4. 기존 `schema.sql`의 DROP/CREATE 역할 종료

## Phase 2. Direct reuse
기존 ETL mapping을 대부분 유지:
- cohorts / users
- notices / scheduled_notices / alert_popups
- curriculum_*
- materials
- assessments 계열
- mileage 계열
- project_teams 계열
- study_* / AI log 계열
- resume 계열의 기본 row

## Phase 3. Transform
```text
form_tasks + form_responses
→ submission_tasks + submission_task_cohorts + submission_responses

record_submissions.file_urls[]
→ record_submission_files

legacy seating tables
→ cohort_seating.layout JSONB

roll_calls + roll_call_entries
→ seat_presences

users.skills[]
→ skills + user_skills

users.job_preferences
→ user_job_preferences
```

## Phase 4. S3
- Firebase Storage → S3 copy는 기존 작업 재사용
- old path → new S3 key mapping 보존
- TO-BE DB에는 key 중심으로 적재
- DB의 old Firebase/S3 full URL은 단계적으로 제거

## Phase 5. Validation
- source/target row count
- orphan FK
- duplicate UNIQUE key
- user mapping 실패
- S3 missing object
- mileage ledger balance
- assessment submission/answer consistency
- resume owner mapping
- skill normalization duplicates

## Phase 6. Graph/vector projection
PostgreSQL 적재 완료 후:
- Pinecone index rebuild
- Neo4j Career graph projection/rebuild

Pinecone/Neo4j 적재 실패가 PostgreSQL migration commit을 롤백시키지 않도록 비동기 projection으로 분리한다.
