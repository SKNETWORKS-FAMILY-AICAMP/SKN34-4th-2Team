# Cutover report

브랜치 `feature/test`. 운영 Firestore는 읽기만 했다. 시크릿·비밀번호는 이 문서에 없다.

## 0. 미매핑 3테이블

- DDL: `scripts/firestore_to_postgres/schema_extra.sql` (기존 lms DROP 없음)
- ETL: `scripts/firestore_to_postgres/etl_extra.py`
- jobRequirementProfiles FS 12 → `job_requirement_profiles` PG 12
- aiReviews FS 194 → `resume_ai_reviews` PG 46
- aiApplications FS 106 → `resume_ai_applications` PG 28
- resume 매핑 없어 생략 226건 (고아 uid `PKoHmb6H8VPhdKuH8b4r5id9PTy1` 하위 문서 포함)
- `tailoredResumes` 새 테이블 없음 (`resumes.base_resume_id`)

## 1. jobs 스키마

- DDL: `scripts/firestore_to_postgres/jobs_schema.sql` (스키마명 `jobs`)
- `job_matching_bot/ingestion/sqlite_store.py` 가 Postgres(psycopg). 클래스명 `SqliteJobStore` 유지
- `test_sqlite_store`: 22 tests OK
- SQLite `job_matching_bot/artifacts/job_store.sqlite` **없음** → 공고 행 ETL 건너뜀. 운영 `jobs.*` 건수 전부 0
- `resumes.linked_job_id` 에 jobs FK 없음
- Django 모델 없음
- 평가/검색 스크립트 `retrieval/store_search.py` 등 일부는 아직 sqlite3 파일 경로를 연다 (ingestion store는 Postgres)

## 2. Redis youtube 캐시

- TTL 12시간 (`functions/src/youtubeRecommendations.ts` 의 `CACHE_TTL_MS`)
- RESP2
- 옮긴 키 4건:
  - `curriculum:yt:cohort_34:20260831`
  - `curriculum:yt:cohort_34:20260831_v2`
  - `curriculum:yt:cohort_34:20260907_v2`
  - `curriculum:yt:cohort_34:20260914_v2`
- Postgres 테이블 없음

## 3. S3

- 대상 버킷: `skn34-4th-2team-lms`
- 원본 Storage는 지우지 않음
- IAM PutObject/ListBucket 부여 후 `migrate_s3.py` 재실행
- copied=18, postgres_url_updates=4, failed=0

## 4. Django LMS API

- 위치: `lms_api/`
- `python manage.py check` 이슈 0 (`on_delete` 를 PROTECT/SET_NULL/CASCADE 로 통일, unmanaged)
- 인증: 세션 + 헤더 `X-Firebase-Uid` (Flutter Auth 브리지). `users.email` + `users.firebase_uid`
- `GET /api/bootstrap` camelCase 스냅샷
- `POST /api/command` 공지/할일/프로필/마일리지/커리큘럼 PDF/좌석 publish
- 공지 저장/삭제: `lms/services.py` `schedule_notice_vector` → `transaction.on_commit`
- 예약 공지: Celery beat `publish_due_notices`
- 마일리지: `SELECT … FOR UPDATE`
- `lms_api` 에 `firebase_admin` / Firestore import 없음

## 5. Pinecone 공지 재적재

- 명령: `lms_api` 에서 `python manage.py reindex_notices`
- 벡터 ID: `{cohorts.code}_n{notices.id}_{청크번호}`
- upserted=19, notices=13
- smoke: cohort=`cohort_34`, hits=3

## 6. 챗봇

- `chatbot/firebase_student_context.py` Postgres + Redis + S3 목록
- 학생 문맥 경로에 `firebase_admin.firestore` 없음
- qna·posts 조회 키 제거, assessments published only, seating published room only
- 생성 로그: `ai_generation_logs` INSERT

## 7. 앱

### React
- `lms_react/src/data/repository.ts` 가 `/api/bootstrap` 및 공지 POST/PATCH/DELETE
- firebase 패키지 없음
- `npm test`: 50 passed, **1 failed** (`이용 안내 투어 > 다음을 누르면 스텝의 화면으로 옮겨 간다` — 화면 타이틀. 화면은 수정하지 않음)

### Flutter
- `LmsRepository`, seating / curriculum / mileage / auth repository 가 `LmsApiClient`(Django) 호출
- Firestore CRUD 호출은 repository 바깥에서 제거
- `firestoreProvider` 는 정의만 남김 (구독 0)
- Auth/Storage SDK는 예외: `firebase_core` / `firebase_auth` / `firebase_storage`, bootstrap `Firebase.initializeApp`
- Cloud Functions callable(학생 계정 생성·비밀번호)은 Auth 쪽에 남아 있음
- 모델 `fromFirestore` import 는 파서. 호출은 repository가 아님

### cover_letter_rag
- tailored create/list/get/save session/delete/promote → `resumes` (+ `sections._tailored`)
- `resume_ai_reviews` / `resume_ai_applications` / `job_requirement_profiles` Postgres
- `apply_or_undo` Postgres 트랜잭션
- 테스트 더블만 in-memory Firestore 모양 (`gateway.store`)
- `verify_id_token` 은 Firebase Auth

## 아직 Firestore를 보는 파일

완료 기준의 런타임 CRUD 목록 (Auth/Storage SDK 예외).

### 0 (앱 repository CRUD)
- Flutter `LmsRepository` 및 seating/curriculum/mileage/auth repository: HTTP
- React: firebase 패키지 없음
- chatbot 학생 문맥: Firestore 없음
- lms_api: Firestore 없음

### Auth/Storage SDK만 (예외로 명시)
- Flutter `firebase_core` / `firebase_auth` / `firebase_storage`
- `lib/shared/services/storage_service.dart`
- `chatbot/api.py` 의 ID 토큰 검증 (있다면 Auth만)
- `cover_letter_rag` `auth.verify_id_token`

### ETL/마이그레이션 전용 (런타임 앱 아님)
- `scripts/firestore_to_postgres/etl.py`, `etl_extra.py`, `inventory.py`, `migrate_s3.py`, `migrate_youtube_redis.py`

### 모델 fromFirestore (파서 import, CRUD 호출 아님)
- `lib/shared/models/*.dart`, seating/curriculum 모델

### 아직 SQLite 파일을 직접 여는 공고봇 평가 경로
- `job_matching_bot/retrieval/store_search.py`
- `job_matching_bot/evaluation/*`
- ingestion `sqlite_store.py` 는 Postgres

## 운영자가 해야 할 남은 일

1. `job_store.sqlite` 가 생기면 jobs 스키마 ETL
2. React 투어 테스트 1건은 화면 미수정 정책으로 남김
