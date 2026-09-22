# Firestore → PostgreSQL 이전 리포트

운영 Firestore는 읽기만 했다. jobs 스키마와 youtube_curriculum_cache 테이블은 만들지 않았다.

## 결정 3
- posts / post_comments: 생략 (0건)
- qna_threads / qna_messages: 생략 (0건)
- 레거시 studyNotes: 원본 1건 중 userId 없는 1건은 버림 (`yx8R7VUJmGFSsD0B0ZHF_prefix_05_langchain_01_langchain_overview`)
- 레거시 seating: seating_rooms 가 있어 레거시 layout/assignment 2건은 변환하지 않고 카운트만 함

## 경로별 건수

| Firestore 경로 | FS | Postgres 테이블 | PG |
| --- | ---: | --- | ---: |
| `users` | 34 | `users` | 34 |
| `cohorts` | 3 | `cohorts` | 3 |
| `studentIntakes` | 32 | `student_intakes` | 32 |
| `users/{uid}/todos` | 1 | `todos` | 1 |
| `users/{uid}/alertPopupDismissals` | 3 | `alert_popup_dismissals` | 3 |
| `…/attendances` | 1690 | `attendances` | 1624 |
| `…/rollCalls` | 15 | `roll_calls` | 15 |
| `…/notices` | 13 | `notices` | 13 |
| `…/resumes` | 31 | `resumes` | 25 |
| `…/resumes/{id}/feedback` | 15 | `resume_feedback` | 15 |
| `…/resumes/{id}/revisions` | 12 | `resume_revisions` | 12 |
| `…/submissions` | 6 | `record_submissions` | 2 |
| `…/assessmentSubmissions` | 4 | `assessment_submissions` | 0 |
| `…/assessments/{id}/questions` | 20 | `assessment_questions` | 20 |
| `aiGenerationLogs` | 190 | `ai_generation_logs` | 190 |
| `aiQuestionFeedback` | 261 | `ai_question_feedback` | 261 |
| `…/mileageTransactions` | 5 | `mileage_transactions` | 2 |
| `…/mileageProducts` | 6 | `mileage_products` | 6 |
| `…/projectTeams` | 5 | `project_teams` | 5 |
| `…/studySources` | 5 | `study_sources` | 5 |
| `…/formTasks` | 2 | `form_tasks` | 2 |
| `…/seatingRooms` | 1 | `seating_rooms` | 1 |
| `systemCache` | 1 | `system_cache` | 1 |
| `aiEvalRuns` | 1 | `ai_eval_runs` | 1 |

## 건수 불일치 원인

공통 원인: Firestore `users` 에 없는 uid `PKoHmb6H8VPhdKuH8b4r5id9PTy1` (삭제·미이전 계정). 이 uid를 가리키는 행은 FK 때문에 넣지 않았다. 잔액은 고치지 않았다.

| 경로 | FS | PG | 차이 | 원인 |
| --- | ---: | ---: | ---: | --- |
| attendances | 1690 | 1624 | 66 | 위 uid 출결 66건. unique (user_id, date_key) 병합은 0건 |
| resumes | 31 | 25 | +8 tailored / -14 orphan | 부모 14건이 위 uid. undocumented `tailoredResumes` 8건은 `resumes.base_resume_id` 로 합침 |
| record_submissions | 6 | 2 | 4 | 위 uid: `WefdiehTA0nwtsxVxDKD`, `Z8FUgJXQjjPZhvTEsbVm`, `uyiTYzDJY3YgWBujeQbZ`, `vLF56Cxo0c60e1pFpuZe` |
| mileage_transactions | 5 | 2 | 3 | 위 uid: `HGT00pEndXUh3Phy768z`, `J9fkyrNsGYV4K4jqPua4`, `bbuvqffxYNpARRwZXpfd` |
| assessment_submissions | 4 | 0 | 4 | 위 uid + 평가 문서도 없음 (`0SfOVS0pjN5CtZhMxU3Q`, `GfPpkqHFzGPTzzMhcwvM`, `jtXeRPgYmWTa9r2kjlCp`, `kRuDQnOJEPmHYyED5C3x`) |

건너뛴 이력서 id: `5y6kvVPk6fI44KZefVR2`, `8SQETkWEkbyGgExV3Aju`, `AD0WUKtxLNFWPDMuYJHD`, `GIdv7oJ6CiI8y5HHQAQN`, `GxvNcCgG051FPWWWGJuF`, `HUhyDuF6BqRbIYQp7Bx5`, `MaE9OpHWoyLYTb6SHkEU`, `RMEnBwv4we9LuNWWvpFh`, `matched_2627c154634f4bad19aea15c`, `matched_3356d5ea91cd66ad0941d3c3`, `matched_3c607155619219f39ce55e02`, `matched_8c08ac13838162202a3b328c`, `matched_b2db1f84f2b7cd2ce21db9cf`, `rrQ1cM00bN4Q6y7lrJ5V`

건너뛴 평가 제출 id: `0SfOVS0pjN5CtZhMxU3Q_PKoHmb6H8VPhdKuH8b4r5id9PTy1`, `GfPpkqHFzGPTzzMhcwvM_PKoHmb6H8VPhdKuH8b4r5id9PTy1`, `jtXeRPgYmWTa9r2kjlCp_PKoHmb6H8VPhdKuH8b4r5id9PTy1`, `kRuDQnOJEPmHYyED5C3x_PKoHmb6H8VPhdKuH8b4r5id9PTy1`


## 전체 Firestore 인벤토리

- `aiEvalRuns`: 1
- `aiGenerationLogs`: 190
- `aiQuestionFeedback`: 261
- `cohorts`: 3
- `cohorts/{c}/schedules`: 0
- `studentIntakes`: 32
- `systemCache`: 1
- `users`: 34
- `users/{uid}/alertPopupDismissals`: 3
- `users/{uid}/studyNotes`: 3
- `users/{uid}/todos`: 1
- `…/alertPopups`: 3
- `…/assessmentSubmissions`: 4
- `…/assessments`: 1
- `…/assessments/{id}/questions`: 20
- `…/assignments`: 0
- `…/assignments/{id}/submissions`: 0
- `…/attendances`: 1690
- `…/curriculum/meta`: 1
- `…/curriculumSheets`: 1
- `…/formTasks`: 2
- `…/formTasks/{id}/responses`: 0
- `…/inflearnPackages`: 0
- `…/materials`: 0
- `…/mileageCart`: 1
- `…/mileageProducts`: 6
- `…/mileageSettings/config`: 0
- `…/mileageTransactions`: 5
- `…/missionProgress`: 2
- `…/notices`: 13
- `…/posts`: 0
- `…/projectTeams`: 5
- `…/purchaseRequests`: 1
- `…/qna`: 0
- `…/recommendationEvents`: 1
- `…/resumes`: 31
- `…/resumes/{id}/feedback`: 15
- `…/resumes/{id}/revisions`: 12
- `…/rollCalls`: 15
- `…/scheduledNotices`: 1
- `…/seating/{layout,assignment}`: 2
- `…/seatingAssignments`: 1
- `…/seatingMeta/default`: 1
- `…/seatingRooms`: 1
- `…/studyNotes`: 1
- `…/studySources`: 5
- `…/submissions`: 6
- `…/userProgress`: 0
- `…/vectorMetadata/notices`: 1
- `…/weeklyTasks`: 0
- `…/youtubeCurriculumCache`: 4
- `…/youtubeRecommendations`: 0

## firebase_uid 매핑 실패 (중복 제거)

1건
- `PKoHmb6H8VPhdKuH8b4r5id9PTy1`

## mileage_balance vs SUM(amount)

전원 일치

## 발견·미매핑 (테이블 생성 안 함)

- `jobRequirementProfiles`: 12 keys=['createdAt', 'requirements']
- `resumes/*/aiApplications`: 4
- `resumes/*/aiReviews`: 12
- `resumes/*/tailoredResumes`: 8
- `resumes/GW6FtVm3m3ei82PtZsAm/aiApplications`: 0
- `resumes/GW6FtVm3m3ei82PtZsAm/aiReviews`: 0
- `resumes/GW6FtVm3m3ei82PtZsAm/tailoredResumes`: 0
- `resumes/OIQrPYLNp5MKZyc9W5vj/tailoredResumes`: 0
- `resumes/cCMdivZBs7zVh899oEJ7/aiReviews`: 0
- `resumes/matched_08d678459fb0937545ad9373/tailoredResumes`: 0
- `resumes/mock-demo_review_ai/aiReviews`: 0
- `resumes/mock-demo_review_ai/tailoredResumes`: 0
- `resumes/tulqVfSg7KpHXjLUciq4/aiApplications`: 0
- `resumes/tulqVfSg7KpHXjLUciq4/aiReviews`: 0

## 문서와 코드 차이

- cohorts.status archived → closed (cohort_36)
- undocumented path tailoredResumes (8 docs) flattened into resumes (ERD base_resume_id). aiReviews/aiApplications not loaded.
- legacy studyNotes yx8R7VUJmGFSsD0B0ZHF_prefix_05_langchain_01_langchain_overview dropped (no userId)
- jobRequirementProfiles / resumes/*/aiReviews / resumes/*/aiApplications 는 ERD 54경로에 없어 테이블을 만들지 않았다.
- users 문서의 추가 필드: createdBy

## ETL 오류

없음

## 다음에 사람이 해야 할 일

1. Pinecone `notice` 네임스페이스 재적재 (벡터 ID `{기수코드}_n{notices.id}_{청크번호}`)
2. youtubeCurriculumCache → Redis TTL
3. Storage URL은 Firestore 값을 그대로 둠. S3 복사는 후속
4. Django models.py / API, 챗봇 쿼리를 Postgres로 교체
5. job_matching_bot SQLite → jobs 스키마
6. 미매핑 컬렉션(jobRequirementProfiles, aiReviews, aiApplications) 스키마 결정
7. Flutter/React가 Firestore를 보지 않게 repository를 API로 교체

## 미매핑 3테이블 ETL (증분, DROP 없음)

- jobRequirementProfiles FS 12 → job_requirement_profiles PG 12
- aiReviews FS 194 → resume_ai_reviews PG 46
- aiApplications FS 106 → resume_ai_applications PG 28
- resume 매핑 없어 생략 226건 (고아 uid 이력서 하위 문서 포함)

## jobs 스키마

- `scripts/firestore_to_postgres/jobs_schema.sql` 적용됨
- `job_matching_bot/artifacts/job_store.sqlite` 없음 → 공고 행 ETL 건너뜀. `jobs.*` 건수 0
- `test_sqlite_store` 22 tests OK (Postgres 구현)

## Redis youtube 캐시

- 4키 이전: `curriculum:yt:cohort_34:{week_key}` TTL 12h
