# Firestore → PostgreSQL 이전 리포트

> 이 문서는 과거 ETL 실행의 건수·오류 기록이며 현재 기준 DB
> `lms_migration_replay_20260923`의 실데이터 현황을 뜻하지 않는다.

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
| `users/{uid}/alertPopupDismissals` | 3 | `alert_popup_dismissals` | 0 |
| `…/attendances` | 1690 | `attendances` | 1624 |
| `…/rollCalls` | 15 | `seat_presences` | 246 |
| `…/notices` | 15 | `notices` | 15 |
| `…/resumes` | 31 | `resumes` | 25 |
| `…/resumes/{id}/feedback` | 15 | `resume_feedback` | 15 |
| `…/resumes/{id}/revisions` | 12 | `resume_revisions` | 0 |
| `…/submissions` | 6 | `record_submissions` | 2 |
| `…/assessmentSubmissions` | 4 | `assessment_submissions` | 0 |
| `…/assessments/{id}/questions` | 20 | `assessment_questions` | 0 |
| `aiGenerationLogs` | 190 | `ai_generation_logs` | 190 |
| `aiQuestionFeedback` | 261 | `ai_question_feedback` | 261 |
| `…/mileageTransactions` | 5 | `mileage_transactions` | 2 |
| `…/mileageProducts` | 6 | `mileage_products` | 6 |
| `…/projectTeams` | 5 | `project_teams` | 5 |
| `…/studySources` | 5 | `study_sources` | 5 |
| `…/formTasks` | 2 | `submission_tasks` | 2 |
| `…/seatingRooms` | 1 | `cohort_seating` | 1 |
| `systemCache` | 1 | `system_cache` | 1 |
| `aiEvalRuns` | 1 | `ai_eval_runs` | 0 |

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
- `…/notices`: 15
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

- INSERT INTO alert_popup_dismissals VALUES (%s,%s,%s) ON CONFLICT DO NOTHING: column "date_key" is of type date but expression is of type smallint
LINE 1: INSERT INTO alert_popup_dismissals VALUES ($1,$2,$3) ON CONF...
                                                   ^
HINT:  You will need to rewrite or cast the expression.
- INSERT INTO alert_popup_dismissals VALUES (%s,%s,%s) ON CONFLICT DO NOTHING: column "date_key" is of type date but expression is of type smallint
LINE 1: INSERT INTO alert_popup_dismissals VALUES ($1,$2,$3) ON CONF...
                                                   ^
HINT:  You will need to rewrite or cast the expression.
- INSERT INTO alert_popup_dismissals VALUES (%s,%s,%s) ON CONFLICT DO NOTHING: column "date_key" is of type date but expression is of type smallint
LINE 1: INSERT INTO alert_popup_dismissals VALUES ($1,$2,$3) ON CONF...
                                                   ^
HINT:  You will need to rewrite or cast the expression.
- INSERT INTO assessments (legacy_id, cohort_id, title, tags, max_score, start_at, end_at, t: invalid input syntax for type json
DETAIL:  Token "mini" is invalid.
CONTEXT:  JSON data, line 1: {mini...
unnamed portal parameter $4 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"단어를 숫자로 변환하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"모델을 간단하게 만들기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found "}".
CONTEXT:  JSON data, line 1: {"워드 임베딩"}
unnamed portal parameter $9 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found "}".
CONTEXT:  JSON data, line 1: {"프롬프트 설계"}
unnamed portal parameter $9 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"데이터를 시각화하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found "}".
CONTEXT:  JSON data, line 1: {"데이터 정제"}
unnamed portal parameter $9 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"텍스트와 이미지",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"데이터 수집",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Token "CNN" is invalid.
CONTEXT:  JSON data, line 1: {CNN...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"모델을 처음부터 학습하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"더 많은 데이터 처리",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"데이터를 시각화하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: ...든 단어를 동일하게 처리하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"프롬프트의 길이",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"소규모 데이터 처리",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"모델의 성능을 저하시킨다",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"더 많은 데이터 처리",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"데이터의 양을 늘리기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found ",".
CONTEXT:  JSON data, line 1: {"모델의 출력을 다양화하기 위해",...
unnamed portal parameter $7 = '...'
- INSERT INTO assessment_questions (legacy_id, assessment_id, "order", type, prompt, points,: invalid input syntax for type json
DETAIL:  Expected ":", but found "}".
CONTEXT:  JSON data, line 1: {"비전-언어 모델"}
unnamed portal parameter $9 = '...'
- INSERT INTO mission_progress VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s): column "coding_pcce" is of type boolean but expression is of type smallint
LINE 1: INSERT INTO mission_progress VALUES ($1,$2,$3,$4,$5,$6,$7,$8...
                                                         ^
HINT:  You will need to rewrite or cast the expression.
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO resume_revisions: column "created_by" of relation "resume_revisions" does not exist
LINE 2: ...         (legacy_id,resume_id,revision_no,content,created_by...
                                                             ^
- INSERT INTO recommendation_events (legacy_id, cohort_id, user_id, recommendation_id, youtu: invalid input syntax for type json
DETAIL:  Expected ":", but found "}".
CONTEXT:  JSON data, line 1: ...어모델) · 자연어-이미지 멀티모달"}
unnamed portal parameter $7 = '...'
- INSERT INTO ai_eval_runs (legacy_id, prompt_version, model, source, total_cases, passed, a: invalid input syntax for type json
DETAIL:  Token "notice_project_mix" is invalid.
CONTEXT:  JSON data, line 1: {notice_project_mix...
unnamed portal parameter $9 = '...'

## 다음에 사람이 해야 할 일

1. Pinecone `notice` 네임스페이스 재적재 (벡터 ID `{기수코드}_n{notices.id}_{청크번호}`)
2. youtubeCurriculumCache → Redis TTL
3. Storage URL은 Firestore 값을 그대로 둠. S3 복사는 후속
4. Django models.py / API, 챗봇 쿼리를 Postgres로 교체
5. job_matching_bot SQLite → jobs 스키마
6. 미매핑 컬렉션(jobRequirementProfiles, aiReviews, aiApplications) 스키마 결정
7. Flutter/React가 Firestore를 보지 않게 repository를 API로 교체
