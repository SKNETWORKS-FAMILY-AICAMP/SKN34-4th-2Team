# Firestore → PostgreSQL 이전 리포트

> 2026-09-25 RDS `lms_migration_replay_20260923`(lms.0007)에 넣은 실행의 기록이다.
> 로컬 DB에 ETL 한 뒤 덤프를 한 트랜잭션으로 넣었다. RDS에 먼저 있던 기수 `cohort_34` · 공지 15건 ·
> 정책 문서 7건은 같은 번호로 다시 들어갔다(공지는 작성자만 채움).
> Firestore 에 없는 공부방 · 연습장 데이터(로컬 `practice.*` · `study.*`)는 `migrate_local_study.py` 로 함께 넣었다:
> 수업 저장소 +10 · 노트 +3 · 복습 문제 세트 20(문제 228) · 출제 범위 6 · 조직 연결 1 · 자동 출제 설정 1 · 실행 기록 7 · 튜터 대화 4.
> 건너뛴 행은 모두 삭제된 계정 `PKoHmb6H8VPhdKuH8b4r5id9PTy1`(Firestore users 에 없음)의 것이다.

운영 Firestore는 읽기만 했다. jobs 스키마와 youtube_curriculum_cache 테이블은 만들지 않았다.

## 결정 3
- posts / post_comments: 생략 (0건)
- qna_threads / qna_messages: 생략 (0건)
- 레거시 studyNotes: study_notes 합침 0건 / 원본 0건
- 레거시 seating: cohort_seating.layout JSONB로 변환

## 경로별 건수

| Firestore 경로 | FS | Postgres 테이블 | PG |
| --- | ---: | --- | ---: |
| `users` | 34 | `users` | 34 |
| `cohorts` | 3 | `cohorts` | 3 |
| `studentIntakes` | 32 | `student_intakes` | 32 |
| `users/{uid}/todos` | 1 | `todos` | 1 |
| `users/{uid}/alertPopupDismissals` | 3 | `alert_popup_dismissals` | 3 |
| `…/attendances` | 1690 | `attendances` | 1624 |
| `…/rollCalls` | 15 | `seat_presences` | 246 |
| `…/notices` | 16 | `notices` | 16 |
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
| `…/formTasks` | 2 | `submission_tasks` | 2 |
| `…/seatingRooms` | 1 | `cohort_seating` | 1 |
| `systemCache` | 1 | `system_cache` | 1 |
| `aiEvalRuns` | 1 | `ai_eval_runs` | 1 |

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
- `…/notices`: 16
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
- resumes 원본 · 사본 연결 2/2건 (baseResumeId · sourceTailoredResumeId)
- tailoredResumes 공고 스냅샷 · 첨삭 대화 → resume_tailorings 8/8건
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
