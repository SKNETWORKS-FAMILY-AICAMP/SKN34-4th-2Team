# DB 표 문서

> 이 문서는 `scripts/firestore_to_postgres/describe_schema.py` 가 실제 DB 에서 만든다. 손으로 고치지 말고,
> 표를 바꾼 뒤 스크립트를 다시 돌린다. 표 설명 · 칸 메모는 스크립트 안의 `TABLES` · `NOTES` 에 적는다.

## 한눈에

| 스키마 | 무엇 | 만드는 파일 |
|---|---|---|
| `public` | LMS 본 데이터(Firestore 에서 옮겨 온 것) | `schema.sql`, `schema_extra.sql` — `etl.py` 가 **지우고 다시 만든다** |
| `practice` | 복습 문제 · 풀이 기록 · 신고 | `practice_schema.sql`, 세트 적재는 `load_practice.py` |
| `jobs` | 공고 수집 결과 | `jobs_schema.sql` (`CREATE SCHEMA jobs` 후 그 안에서 실행) |

(파일은 모두 `scripts/firestore_to_postgres/` 에 있다.)

## 공통 규칙

- **id** — 대부분 `id bigint`(자동 증가) + `legacy_id`(Firestore 문서 id). API 는 `legacy_id` 가 있으면 그것을, 없으면 `id` 를 화면 id 로 보낸다.
- **사용자 · 기수를 가리킬 때** — `public` 안에서는 `user_id` · `cohort_id`(숫자) 외래키. `public` 밖(`practice`)에서는
  `users.firebase_uid` · `cohorts.code` 로 가리킨다. ETL 이 `public` 을 다시 만들면 숫자 id 가 바뀌기 때문이다.
- **시각** — `timestamptz`. 날짜만이면 `date`(`date_key` 등).
- **jsonb** — 이력서 내용, 노트 파일 목록 같은 구조 값. 지금 `lms_api` 는 jsonb 를 **JSON 글자로** 돌려준다
  (화면이 받는 입구 `lms_react/src/data/bootstrap.ts` 의 `parseJsonb` 에서 푼다).
- **표 읽는 법** — 아래 칸 표의 「키」: PK 기본키, UQ 고유, FK → 참조 대상.

## 차례

- 계정 · 기수: `cohorts`, `users`, `student_intakes`, `todos`, `alert_popup_dismissals`, `system_cache`
- 수업 · 출결: `schedules`, `curriculum_sheets`, `curriculum_rows`, `curriculum_pdfs`, `materials`, `attendances`, `roll_calls`, `roll_call_entries`
- 좌석 · 프로젝트 팀: `seating_rooms`, `seating_cells`, `seating_assignments`, `seat_assignments`, `project_teams`, `project_team_members`
- 공지: `notices`, `scheduled_notices`, `alert_popups`
- 과제 · 기록 · 설문: `assignments`, `assignment_submissions`, `record_submissions`, `weekly_tasks`, `weekly_progress`, `form_tasks`, `form_responses`
- 성취도평가: `assessments`, `assessment_questions`, `assessment_submissions`, `assessment_answers`, `assessment_score_adjustments`
- 마일리지: `mileage_settings`, `mileage_transactions`, `mission_progress`, `mileage_products`, `mileage_cart_items`, `purchase_requests`, `purchase_request_items`
- 이력서: `resumes`, `resume_feedback`, `resume_feedback_reads`, `resume_revisions`, `resume_ai_reviews`, `resume_ai_applications`, `job_requirement_profiles`
- 학습실 · 공부방: `inflearn_packages`, `youtube_recommendations`, `recommendation_events`, `study_sources`, `study_notes`
- AI 기록: `ai_generation_logs`, `ai_question_feedback`, `ai_eval_runs`
- 복습 문제 (practice 스키마): `sets`, `problems`, `attempts`, `reports`, `reviews`, `coverage`
- 공고 (jobs 스키마): `jobs`, `job_tags`, `list_jobs`, `list_jobs_search`, `list_seen`, `list_sweeps`, `link_checks`, `runs`

## 계정 · 기수

### `public.cohorts`

기수(반). `code`(예: cohort_34)가 화면 · API 에서 쓰는 기수 id 다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `code` | varchar |  |  | UQ | 화면 · API 의 기수 id |
| `name` | varchar |  |  |  |  |
| `description` | text | 예 |  |  |  |
| `term_number` | integer | 예 |  |  |  |
| `classroom_name` | varchar | 예 |  |  |  |
| `status` | varchar |  |  |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `start_date` | date | 예 |  |  |  |
| `end_date` | date | 예 |  |  |  |
| `published_seating_room_id` | bigint | 예 |  | FK → `seating_rooms.id` | 학생에게 보이는 강의실(seating_rooms.id) |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.users`

계정 — 학생 · 강사 · 관리자. 화면의 사용자 id 는 `firebase_uid` 다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `firebase_uid` | varchar | 예 |  | UQ | 화면 · API 의 사용자 id. ETL 로 `id` 가 새로 매겨져도 이 값은 그대로다 |
| `email` | varchar | 예 |  | UQ |  |
| `password` | varchar |  | `` |  | ⚠ 지금은 평문으로 저장 · 비교한다. 배포 전 해시로 바꿔야 한다 |
| `personal_email` | varchar | 예 |  |  |  |
| `display_name` | varchar |  | `` |  |  |
| `role` | varchar |  |  |  | student · instructor · admin |
| `cohort_id` | bigint | 예 |  | FK → `cohorts.id` (RESTRICT) |  |
| `seat_number` | integer | 예 |  |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `must_change_password` | boolean |  | `false` |  |  |
| `motto` | varchar | 예 |  |  |  |
| `skills` | text[] |  | `{}[]` |  |  |
| `social_links` | jsonb |  | `{}` |  |  |
| `job_preferences` | jsonb |  | `{}` |  |  |
| `birth_date` | date | 예 |  |  |  |
| `photo_url` | varchar | 예 |  |  |  |
| `photo_storage_path` | varchar | 예 |  |  |  |
| `mileage_balance` | integer |  | `0` |  |  |
| `last_login` | timestamptz | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.student_intakes`

학생 사전 설문(전공 · 수준 · 희망 직무 등). 학생 한 명에 한 줄.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `user_id` | bigint |  |  | PK · FK → `users.id` (RESTRICT) |  |
| `education_major` | varchar |  | `` |  |  |
| `current_status` | varchar |  | `` |  |  |
| `weekly_study_hours` | varchar |  | `` |  |  |
| `programming_level` | varchar |  | `` |  |  |
| `collaboration_tools` | varchar |  | `` |  |  |
| `ai_llm_experience` | varchar |  | `` |  |  |
| `motivation` | text |  | `` |  |  |
| `desired_role` | text |  | `` |  |  |
| `post_completion_goal` | text |  | `` |  |  |
| `awards` | text |  | `` |  |  |
| `project_links` | text |  | `` |  |  |
| `team_role` | text |  | `` |  |  |
| `self_learning_style` | text |  | `` |  |  |
| `slump_overcome_experience` | text |  | `` |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `created_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.todos`

대시보드 할 일.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `title` | varchar |  |  |  |  |
| `is_completed` | boolean |  | `false` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.alert_popup_dismissals`

알림 팝업 「오늘 하루 보지 않기」 기록.

여러 칸 키: PK (user_id, popup_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `popup_id` | bigint |  |  | FK → `alert_popups.id` (CASCADE) |  |
| `date_key` | date | 예 |  |  |  |

### `public.system_cache`

외부에서 받아 둔 값(자격 시험 일정 등). `key` 로 찾는다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `key` | varchar |  |  | PK |  |
| `data` | jsonb |  | `{}` |  |  |
| `synced_at` | timestamptz | 예 |  |  |  |

## 수업 · 출결

### `public.schedules`

기수의 하루 교시표(`sessions`).

여러 칸 키: UQ (cohort_id, date_key)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `date_key` | date |  |  |  |  |
| `sessions` | jsonb |  | `[]` |  |  |
| `current_session_index` | integer | 예 |  |  |  |

### `public.curriculum_sheets`

업로드한 커리큘럼 표 한 벌.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `file_name` | varchar | 예 |  |  |  |
| `storage_path` | varchar | 예 |  |  |  |
| `source` | varchar | 예 |  |  |  |
| `uploaded_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `uploaded_at` | timestamptz | 예 |  |  |  |

추가 인덱스 1개.

### `public.curriculum_rows`

커리큘럼 한 줄 = 수업 하루. `day_index` 가 N일차, `date_label` 은 날짜 글자.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `sheet_id` | bigint |  |  | FK → `curriculum_sheets.id` (CASCADE) |  |
| `day_index` | integer | 예 |  |  |  |
| `date_label` | varchar | 예 |  |  | 날짜 글자(예: 2026년 6월 16일 화요일) — date 형식이 아니다 |
| `subject` | varchar | 예 |  |  |  |
| `topic` | varchar | 예 |  |  |  |
| `detail` | text | 예 |  |  |  |
| `order` | integer | 예 |  |  |  |

### `public.curriculum_pdfs`

기수의 커리큘럼 PDF 한 장.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cohort_id` | bigint |  |  | PK · FK → `cohorts.id` (RESTRICT) |  |
| `full_pdf_url` | varchar | 예 |  |  |  |
| `full_pdf_file_name` | varchar | 예 |  |  |  |
| `published` | boolean |  | `false` |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.materials`

수업 자료 파일.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `file_url` | varchar | 예 |  |  |  |
| `file_name` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.attendances`

학생의 하루 출결. 학생 · 날짜마다 한 줄.

여러 칸 키: UQ (user_id, date_key)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `date_key` | date |  |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `status_source` | varchar | 예 |  |  |  |
| `check_in_time` | time | 예 |  |  |  |
| `check_out_time` | time | 예 |  |  |  |
| `form_attendance_type` | varchar | 예 |  |  |  |
| `official_leave_used` | boolean | 예 |  |  |  |
| `official_leave_type` | varchar | 예 |  |  |  |
| `official_leave_other` | varchar | 예 |  |  |  |
| `recorded_at` | timestamptz | 예 |  |  |  |

### `public.roll_calls`

강사 「자리 확인」 — 날짜 · 교시마다 한 번.

여러 칸 키: UQ (cohort_id, date_key, period_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `date_key` | date |  |  |  |  |
| `period_id` | varchar |  |  |  |  |
| `carried_from_period_id` | varchar | 예 |  |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.roll_call_entries`

자리 확인의 학생별 상태(확인 · 보류).

여러 칸 키: PK (roll_call_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `roll_call_id` | bigint |  |  | FK → `roll_calls.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `state` | varchar |  |  |  |  |

## 좌석 · 프로젝트 팀

### `public.seating_rooms`

강의실 틀. 기수마다 여럿, 그중 하나를 확정해 학생에게 보인다(`cohorts.published_seating_room_id`).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `room_number` | varchar | 예 |  |  |  |
| `rows` | integer | 예 |  |  |  |
| `cols` | integer | 예 |  |  |  |
| `max_students` | integer | 예 |  |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.seating_cells`

강의실 격자의 칸 — 좌석 · 강사석 · 출입문만 둔다(빈 칸은 없다).

여러 칸 키: UQ (room_id, seat_id) · UQ (room_id, row, col)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `room_id` | bigint |  |  | FK → `seating_rooms.id` (CASCADE) |  |
| `seat_id` | varchar |  |  |  | 좌석은 번호('1'…), 강사석 · 출입문은 '행_열' |
| `row` | integer | 예 |  |  |  |
| `col` | integer | 예 |  |  |  |
| `label` | varchar | 예 |  |  |  |
| `type` | varchar |  |  |  |  |
| `group_id` | varchar | 예 |  |  | 같은 책상(테이블) 묶음. 강사석은 __instructor__, 출입문은 __door__ |

### `public.seating_assignments`

강의실별 배치 상태 — 작성 중(draft) · 확정(published).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `room_id` | bigint |  |  | PK · FK → `seating_rooms.id` (CASCADE) |  |
| `status` | varchar |  |  |  |  |
| `published_at` | timestamptz | 예 |  |  |  |
| `published_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `updated_at` | timestamptz | 예 |  |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |

### `public.seat_assignments`

좌석에 앉은 학생. 한 강의실에서 한 학생은 한 자리.

여러 칸 키: PK (room_id, cell_id) · UQ (room_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `room_id` | bigint |  |  | FK → `seating_assignments.room_id` (CASCADE) |  |
| `cell_id` | bigint |  |  | FK → `seating_cells.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |

### `public.project_teams`

프로젝트 팀.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `name` | varchar | 예 |  |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `color_index` | integer | 예 |  |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.project_team_members`

팀원.

여러 칸 키: PK (team_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `team_id` | bigint |  |  | FK → `project_teams.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |

## 공지

### `public.notices`

게시판 공지. 디스코드에서 들어온 공지 · 벡터 색인 상태도 담는다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `content` | text | 예 |  |  |  |
| `author_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `author_name` | varchar | 예 |  |  |  |
| `is_favorite` | boolean |  | `false` |  |  |
| `priority` | integer |  | `0` |  |  |
| `source` | varchar | 예 |  |  |  |
| `channel_label` | varchar | 예 |  |  |  |
| `discord_message_id` | varchar | 예 |  | UQ |  |
| `discord_channel_id` | varchar | 예 |  |  |  |
| `discord_channel_type` | varchar | 예 |  |  |  |
| `scheduled_notice_id` | bigint | 예 |  | FK → `scheduled_notices.id` (SET NULL) |  |
| `image_url` | varchar | 예 |  |  |  |
| `vector_chunk_count` | integer |  | `0` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.scheduled_notices`

예약 공지 — 정해진 시각에 notices 로 발행된다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `content` | text | 예 |  |  |  |
| `author_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `is_favorite` | boolean |  | `false` |  |  |
| `repeat_type` | varchar | 예 |  |  |  |
| `publish_time` | time | 예 |  |  |  |
| `publish_at` | timestamptz | 예 |  |  |  |
| `weekday` | integer | 예 |  |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `last_published_at` | timestamptz | 예 |  |  |  |
| `next_publish_at` | timestamptz | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

추가 인덱스 1개.

### `public.alert_popups`

로그인하면 뜨는 알림 팝업.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `content` | text | 예 |  |  |  |
| `author_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `is_active` | boolean |  | `true` |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `link_url` | varchar | 예 |  |  |  |
| `start_time` | time | 예 |  |  |  |
| `end_time` | time | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

## 과제 · 기록 · 설문

### `public.assignments`

과제.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `due_date` | timestamptz | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.assignment_submissions`

과제 제출 파일.

여러 칸 키: PK (assignment_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `assignment_id` | bigint |  |  | FK → `assignments.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `file_url` | varchar | 예 |  |  |  |
| `file_name` | varchar | 예 |  |  |  |
| `file_size_bytes` | bigint | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `submitted_at` | timestamptz | 예 |  |  |  |

### `public.record_submissions`

기록실 제출(자격증 · 스터디 · 블로그 · 학습 인증 · 프리코스 퀴즈) — 승인되면 마일리지.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `type` | varchar |  |  |  |  |
| `status` | varchar |  |  |  |  |
| `title` | varchar | 예 |  |  |  |
| `review_comment` | text | 예 |  |  |  |
| `reviewed_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `reviewed_at` | timestamptz | 예 |  |  |  |
| `cert_type` | varchar | 예 |  |  |  |
| `file_urls` | text[] |  | `{}[]` |  |  |
| `start_at` | timestamptz | 예 |  |  |  |
| `end_at` | timestamptz | 예 |  |  |  |
| `week_number` | integer | 예 |  |  |  |
| `week_label` | varchar | 예 |  |  |  |
| `link` | varchar | 예 |  |  |  |
| `quiz_score` | integer | 예 |  |  |  |
| `learning_date` | date | 예 |  |  |  |
| `learning_content` | text | 예 |  |  |  |
| `is_team_study` | boolean | 예 |  |  |  |
| `mileage_granted` | boolean |  | `false` |  |  |
| `mileage_amount` | integer |  | `0` |  |  |
| `submitted_at` | timestamptz | 예 |  |  |  |

### `public.weekly_tasks`

주간 과제 목록.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `due_date` | timestamptz | 예 |  |  |  |
| `total_count` | integer | 예 |  |  |  |

### `public.weekly_progress`

학생별 주간 과제 진행.

여러 칸 키: PK (cohort_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `completed_count` | integer |  | `0` |  |  |
| `total_count` | integer |  | `0` |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.form_tasks`

구글폼 설문 · 제출 과제.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `form_url` | varchar | 예 |  |  |  |
| `notion_guide_url` | varchar | 예 |  |  |  |
| `due_at` | timestamptz | 예 |  |  |  |
| `published` | boolean |  | `true` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.form_responses`

설문 응답 여부(구글폼에서 가져온 것).

여러 칸 키: PK (task_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `task_id` | bigint |  |  | FK → `form_tasks.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `source` | varchar | 예 |  |  |  |
| `google_response_id` | varchar | 예 |  | UQ |  |
| `submitted_at` | timestamptz | 예 |  |  |  |

## 성취도평가

### `public.assessments`

평가. 커리큘럼 N일차 범위(`day_from` ~ `day_to`)로 문항을 만든다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `tags` | text[] |  | `{}[]` |  |  |
| `max_score` | integer | 예 |  |  |  |
| `start_at` | timestamptz | 예 |  |  |  |
| `end_at` | timestamptz | 예 |  |  |  |
| `thumbnail_url` | varchar | 예 |  |  |  |
| `thumbnail_path` | varchar | 예 |  |  |  |
| `published` | boolean |  | `false` |  |  |
| `created_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |
| `curriculum_sheet_id` | bigint | 예 |  | FK → `curriculum_sheets.id` (SET NULL) |  |
| `day_from` | integer | 예 |  |  |  |
| `day_to` | integer | 예 |  |  |  |
| `subject_filter` | varchar | 예 |  |  |  |

### `public.assessment_questions`

평가 문항. `source_day` · `source_topic` 은 문항이 나온 수업 — 틀린 문항을 그날 복습으로 잇는 데 쓴다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `assessment_id` | bigint |  |  | FK → `assessments.id` (CASCADE) |  |
| `order` | integer | 예 |  |  |  |
| `type` | varchar | 예 |  |  |  |
| `prompt` | text | 예 |  |  |  |
| `points` | integer | 예 |  |  |  |
| `choices` | text[] |  | `{}[]` |  |  |
| `correct_index` | integer | 예 |  |  |  |
| `accepted_answers` | text[] |  | `{}[]` |  |  |
| `explanation` | text | 예 |  |  |  |
| `origin` | varchar | 예 |  |  |  |
| `ai_log_id` | bigint | 예 |  | FK → `ai_generation_logs.id` (SET NULL) |  |
| `ai_draft_id` | varchar | 예 |  |  |  |
| `prompt_version` | varchar | 예 |  |  |  |
| `source_day` | integer | 예 |  |  | curriculum_rows.day_index |
| `source_topic` | varchar | 예 |  |  |  |

### `public.assessment_submissions`

학생의 응시. 평가 · 학생마다 한 줄.

여러 칸 키: UQ (assessment_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `assessment_id` | bigint |  |  | FK → `assessments.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `auto_total_score` | integer | 예 |  |  |  |
| `total_score` | integer | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `submitted_at` | timestamptz | 예 |  |  |  |

### `public.assessment_answers`

응시의 문항별 답과 점수.

여러 칸 키: PK (submission_id, question_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `submission_id` | bigint |  |  | FK → `assessment_submissions.id` (CASCADE) |  |
| `question_id` | bigint |  |  | FK → `assessment_questions.id` (CASCADE) |  |
| `value` | jsonb | 예 |  |  |  |
| `auto_score` | integer | 예 |  |  |  |
| `final_score` | integer | 예 |  |  |  |
| `is_correct` | boolean | 예 |  |  |  |

### `public.assessment_score_adjustments`

강사가 점수를 고친 기록.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `submission_id` | bigint |  |  | FK → `assessment_submissions.id` (CASCADE) |  |
| `question_id` | bigint | 예 |  | FK → `assessment_questions.id` (SET NULL) |  |
| `previous` | integer | 예 |  |  |  |
| `next` | integer | 예 |  |  |  |
| `adjusted_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `adjusted_at` | timestamptz | 예 |  |  |  |
| `note` | text | 예 |  |  |  |

## 마일리지

### `public.mileage_settings`

기수의 마일리지 규칙(카테고리 한도 · 적립 규칙).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cohort_id` | bigint |  |  | PK · FK → `cohorts.id` (RESTRICT) |  |
| `category_limits` | jsonb |  | `{}` |  |  |
| `accrual_rules` | jsonb |  | `{}` |  |  |
| `updated_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.mileage_transactions`

마일리지 적립 · 차감 내역.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `amount` | integer |  |  |  |  |
| `reason` | varchar | 예 |  |  |  |
| `type` | varchar | 예 |  |  |  |
| `related_id` | varchar | 예 |  |  |  |
| `adjusted_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.mission_progress`

미션 진행(학습 인증 · 퀴즈 · 코딩 테스트 · 블로그)과 지급 여부.

여러 칸 키: PK (cohort_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `study_cert_count` | integer |  | `0` |  |  |
| `study_cert_granted` | integer |  | `0` |  |  |
| `quiz_pass_count` | integer |  | `0` |  |  |
| `quiz_granted` | integer |  | `0` |  |  |
| `coding_pcce` | boolean |  | `false` |  |  |
| `coding_pccp` | boolean |  | `false` |  |  |
| `coding_pcsql` | boolean |  | `false` |  |  |
| `coding_granted` | integer |  | `0` |  |  |
| `blog_weeks` | int4[] |  | `{}::integer[]` |  |  |
| `blog_units_granted` | int4[] |  | `{}::integer[]` |  |  |
| `study_week_keys` | text[] |  | `{}[]` |  |  |
| `study_granted` | boolean |  | `false` |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.mileage_products`

마일리지 상품.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `name` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `image_url` | varchar | 예 |  |  |  |
| `category` | varchar | 예 |  |  |  |
| `pricing_type` | varchar | 예 |  |  |  |
| `fixed_price` | integer | 예 |  |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.mileage_cart_items`

학생 장바구니.

여러 칸 키: PK (user_id, product_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `product_id` | bigint |  |  | FK → `mileage_products.id` (CASCADE) |  |
| `quantity` | integer |  | `1` |  |  |
| `unit_price` | integer | 예 |  |  |  |
| `purchase_link` | varchar | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.purchase_requests`

구매 요청.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `total_amount` | integer | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `student_note` | text | 예 |  |  |  |
| `manager_memo` | text | 예 |  |  |  |
| `manager_purchase_link` | varchar | 예 |  |  |  |
| `processed_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `processed_at` | timestamptz | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.purchase_request_items`

구매 요청에 담긴 상품.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `request_id` | bigint |  |  | FK → `purchase_requests.id` (CASCADE) |  |
| `product_id` | bigint | 예 |  | FK → `mileage_products.id` (SET NULL) |  |
| `product_name` | varchar | 예 |  |  |  |
| `category` | varchar | 예 |  |  |  |
| `pricing_type` | varchar | 예 |  |  |  |
| `unit_price` | integer | 예 |  |  |  |
| `quantity` | integer | 예 |  |  |  |
| `purchase_link` | varchar | 예 |  |  |  |

## 이력서

### `public.resumes`

이력서. 기본 이력서 하나(`is_base_resume`)와, 공고에 맞춰 만든 맞춤 이력서(`base_resume_id` = 원본).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `status` | varchar | 예 |  |  | writing · ready(작성 중), submitted(피드백 요청), approved · completed(승인) |
| `content` | jsonb |  | `{}` |  |  |
| `sections` | jsonb |  | `{}` |  | 섹션별 채움 여부 { basicInfo: true, … } |
| `is_base_resume` | boolean |  | `false` |  |  |
| `base_resume_id` | bigint | 예 |  | FK → `resumes.id` (SET NULL) | 맞춤 이력서면 원본 이력서(resumes.id) |
| `source_tailored_resume_id` | bigint | 예 |  | FK → `resumes.id` (SET NULL) | AI 첨삭 작업본을 편집기로 옮긴 사본이면 그 작업본 |
| `linked_job_id` | varchar | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.resume_feedback`

강사 · 관리자의 섹션별 피드백과 답글(`parent_id`).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `resume_id` | bigint |  |  | FK → `resumes.id` (CASCADE) |  |
| `parent_id` | bigint | 예 |  | FK → `resume_feedback.id` (SET NULL) |  |
| `section_key` | varchar | 예 |  |  |  |
| `content` | text | 예 |  |  |  |
| `author_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.resume_feedback_reads`

피드백을 읽었는지.

여러 칸 키: PK (feedback_id, user_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `feedback_id` | bigint |  |  | FK → `resume_feedback.id` (CASCADE) |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `read_at` | timestamptz | 예 |  |  |  |

### `public.resume_revisions`

저장할 때마다 남기는 이전 판.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `resume_id` | bigint |  |  | FK → `resumes.id` (CASCADE) |  |
| `title` | varchar | 예 |  |  |  |
| `content` | jsonb |  | `{}` |  |  |
| `saved_at` | timestamptz | 예 |  |  |  |

### `public.resume_ai_reviews`

AI 첨삭 결과.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `resume_id` | bigint |  |  | FK → `resumes.id` (CASCADE) |  |
| `user_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `fingerprint` | varchar | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `response` | jsonb | 예 |  |  |  |
| `telemetry` | jsonb | 예 |  |  |  |
| `payload` | jsonb |  | `{}` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.resume_ai_applications`

AI 첨삭 제안을 이력서에 적용한 기록(되돌리기용).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `resume_id` | bigint |  |  | FK → `resumes.id` (CASCADE) |  |
| `user_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `fingerprint` | varchar | 예 |  |  |  |
| `kind` | varchar | 예 |  |  |  |
| `before` | jsonb | 예 |  |  |  |
| `after_hash` | varchar | 예 |  |  |  |
| `response` | jsonb | 예 |  |  |  |
| `source_id` | varchar | 예 |  |  |  |
| `undone_by` | varchar | 예 |  |  |  |
| `payload` | jsonb |  | `{}` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.job_requirement_profiles`

직무별 요구 역량 목록(AI 첨삭 · 공고 매칭 재료).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `key` | varchar |  |  | PK |  |
| `requirements` | jsonb |  | `[]` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

## 학습실 · 공부방

### `public.inflearn_packages`

배정된 인프런 강의 묶음.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `subject` | varchar | 예 |  |  |  |
| `type` | varchar | 예 |  |  |  |
| `summary` | text | 예 |  |  |  |
| `units` | jsonb |  | `[]` |  |  |
| `courses` | jsonb |  | `[]` |  |  |
| `is_published` | boolean |  | `false` |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `published_at` | timestamptz | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.youtube_recommendations`

이번 주 커리큘럼 추천 영상.

여러 칸 키: UQ (cohort_id, video_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `video_id` | varchar | 예 |  |  |  |
| `title` | varchar | 예 |  |  |  |
| `youtube_url` | varchar | 예 |  |  |  |
| `thumbnail_url` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `tags` | text[] |  | `{}[]` |  |  |
| `is_published` | boolean |  | `false` |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.recommendation_events`

추천 영상 클릭 · 반응 기록.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `user_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `recommendation_id` | bigint | 예 |  | FK → `youtube_recommendations.id` (SET NULL) |  |
| `youtube_video_id` | varchar | 예 |  |  |  |
| `user_skills` | text[] |  | `{}[]` |  |  |
| `matched_tags` | text[] |  | `{}[]` |  |  |
| `action` | varchar | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

### `public.study_sources`

공부방 수업 저장소(GitHub). 노트와 복습 문제의 재료.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `cohort_id` | bigint |  |  | FK → `cohorts.id` (RESTRICT) |  |
| `title` | varchar | 예 |  |  |  |
| `repo_url` | varchar | 예 |  |  |  |
| `branch` | varchar | 예 |  |  |  |
| `allowed_prefixes` | text[] |  | `{}[]` |  |  |
| `is_active` | boolean |  | `true` |  |  |
| `sort_order` | integer | 예 |  |  |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.study_notes`

학생별 복습 노트. 범위는 `scope_type`(date · prefix · files) + `scope_key`.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `user_id` | bigint |  |  | FK → `users.id` (RESTRICT) |  |
| `source_id` | bigint | 예 |  | FK → `study_sources.id` (SET NULL) |  |
| `status` | varchar | 예 |  |  |  |
| `scope_type` | varchar | 예 |  |  | date · prefix(폴더) · files |
| `scope_value` | jsonb | 예 |  |  |  |
| `scope_key` | varchar | 예 |  |  | date 면 '2026-09-15', prefix 면 'prefix_…', files 면 'files_<해시>' |
| `report_markdown` | text | 예 |  |  |  |
| `review_markdown` | text | 예 |  |  |  |
| `error_message` | text | 예 |  |  |  |
| `message` | text | 예 |  |  |  |
| `files` | jsonb |  | `[]` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

## AI 기록

### `public.ai_generation_logs`

LLM 생성 기록(문항 초안 등) — 모델 · 토큰 · 지연.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `type` | varchar | 예 |  |  |  |
| `cohort_id` | bigint | 예 |  | FK → `cohorts.id` (RESTRICT) |  |
| `created_by` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `prompt_version` | varchar | 예 |  |  |  |
| `model` | varchar | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `error_message` | text | 예 |  |  |  |
| `latency_ms` | integer | 예 |  |  |  |
| `token_in` | integer | 예 |  |  |  |
| `token_out` | integer | 예 |  |  |  |
| `details` | jsonb |  | `{}` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

추가 인덱스 1개.

### `public.ai_question_feedback`

AI 문항 초안을 강사가 채택 · 수정 · 버렸는지.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `log_id` | bigint | 예 |  | FK → `ai_generation_logs.id` (SET NULL) |  |
| `draft_id` | varchar | 예 |  |  |  |
| `cohort_id` | bigint | 예 |  | FK → `cohorts.id` (RESTRICT) |  |
| `outcome` | varchar | 예 |  |  |  |
| `type` | varchar | 예 |  |  |  |
| `prompt_version` | varchar | 예 |  |  |  |
| `assessment_id` | bigint | 예 |  | FK → `assessments.id` (SET NULL) |  |
| `question_id` | bigint | 예 |  | FK → `assessment_questions.id` (SET NULL) |  |
| `source_day` | integer | 예 |  |  |  |
| `source_topic` | varchar | 예 |  |  |  |
| `actor_id` | bigint | 예 |  | FK → `users.id` (SET NULL) |  |
| `created_at` | timestamptz | 예 |  |  |  |
| `updated_at` | timestamptz | 예 |  |  |  |

### `public.ai_eval_runs`

프롬프트 평가 실행 결과.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar | 예 |  | UQ |  |
| `prompt_version` | varchar | 예 |  |  |  |
| `model` | varchar | 예 |  |  |  |
| `source` | varchar | 예 |  |  |  |
| `total_cases` | integer | 예 |  |  |  |
| `passed` | integer | 예 |  |  |  |
| `accuracy` | numeric | 예 |  |  |  |
| `avg_latency_ms` | integer | 예 |  |  |  |
| `failed_ids` | text[] |  | `{}[]` |  |  |
| `created_at` | timestamptz | 예 |  |  |  |

## 복습 문제 (practice 스키마)

### `practice.sets`

수업 날짜별 복습 문제 묶음. 기수 공용. `legacy_id` 가 화면의 세트 id.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `legacy_id` | varchar |  |  | UQ |  |
| `cohort_code` | varchar |  |  |  | cohorts.code — 외래키가 아니다(ETL 이 public 을 다시 만들어도 이어지게) |
| `source_title` | varchar |  | `` |  |  |
| `lesson_date` | date |  |  |  |  |
| `day_label` | varchar |  | `` |  |  |
| `title` | varchar |  | `` |  |  |
| `files` | jsonb |  | `[]` |  |  |
| `model` | varchar |  | `` |  |  |
| `created_at` | timestamptz |  | `now()` |  |  |

추가 인덱스 1개.

### `practice.problems`

세트 안의 문제. `idx` 는 세트 안 순서(0부터). `hidden_tests` 는 채점용 — 학생 화면에 안 보인다.

여러 칸 키: UQ (set_id, idx)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `set_id` | bigint |  |  | FK → `sets.id` (CASCADE) |  |
| `idx` | integer |  |  |  |  |
| `kind` | varchar |  |  |  |  |
| `topic` | varchar |  | `` |  |  |
| `prompt` | text |  | `` |  |  |
| `source_files` | jsonb |  | `[]` |  |  |
| `explanation` | text |  | `` |  |  |
| `choices` | jsonb |  | `[]` |  |  |
| `answer_index` | integer | 예 |  |  |  |
| `starter_code` | text |  | `` |  |  |
| `expected_stdout` | text |  | `` |  |  |
| `blank_answers` | jsonb |  | `[]` |  |  |
| `reference_solution` | text |  | `` |  |  |
| `hidden_tests` | text |  | `` |  |  |
| `packages` | jsonb |  | `[]` |  |  |

### `practice.attempts`

학생별 풀이 기록. 한 문제에 한 줄 — 다시 풀면 `tries` 가 는다.

여러 칸 키: PK (user_uid, problem_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `user_uid` | varchar |  |  |  | users.firebase_uid — 외래키가 아니다(같은 이유) |
| `problem_id` | bigint |  |  | FK → `problems.id` (CASCADE) |  |
| `passed` | boolean |  |  |  |  |
| `tries` | integer |  | `1` |  |  |
| `answered_at` | timestamptz |  | `now()` |  |  |

추가 인덱스 1개.

### `practice.reports`

「이 문제 이상해요」 신고. 한 문제에 한 사람 한 번.

여러 칸 키: UQ (user_uid, problem_id)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `user_uid` | varchar |  |  |  | users.firebase_uid |
| `problem_id` | bigint |  |  | FK → `problems.id` (CASCADE) |  |
| `reason` | varchar |  |  |  | unclear · answer · tests · offtopic · other |
| `note` | text |  | `` |  |  |
| `created_at` | timestamptz |  | `now()` |  |  |

추가 인덱스 1개.

### `practice.reviews`

강사 결정(숨김 · 다시 보이기). 없으면 서로 다른 학생 2명의 신고로 숨긴다.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `problem_id` | bigint |  |  | PK · FK → `problems.id` (CASCADE) |  |
| `decision` | varchar |  |  |  | hidden · kept |
| `decided_by_uid` | varchar |  |  |  |  |
| `decided_at` | timestamptz |  | `now()` |  |  |

### `practice.coverage`

출제 범위 기록 — 수업 파일마다 어디까지 문제로 냈는지(다음 날은 새 셀로만).

여러 칸 키: PK (cohort_code, source_title)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cohort_code` | varchar |  |  |  |  |
| `source_title` | varchar |  |  |  |  |
| `data` | jsonb |  | `{}` |  |  |
| `updated_at` | timestamptz |  | `now()` |  |  |

## 공고 (jobs 스키마)

### `jobs.jobs`

공고 한 건(상세). `job_id` 가 id.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `job_id` | varchar |  |  | PK |  |
| `source` | varchar | 예 |  |  |  |
| `source_job_id` | varchar | 예 |  |  |  |
| `source_url` | varchar | 예 |  |  |  |
| `company` | varchar | 예 |  |  |  |
| `company_type` | varchar | 예 |  |  |  |
| `title` | varchar | 예 |  |  |  |
| `description` | text | 예 |  |  |  |
| `required_skills` | jsonb |  | `[]` |  |  |
| `preferred_skills` | jsonb |  | `[]` |  |  |
| `career_type` | varchar | 예 |  |  |  |
| `min_career_years` | integer | 예 |  |  |  |
| `education` | varchar | 예 |  |  |  |
| `region` | varchar | 예 |  |  |  |
| `employment_type` | varchar | 예 |  |  |  |
| `posted_at` | varchar | 예 |  |  |  |
| `deadline` | varchar | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `content_hash` | varchar | 예 |  |  |  |
| `parser_version` | varchar | 예 |  |  |  |
| `field_provenance` | jsonb |  | `{}` |  |  |
| `tech_stack` | jsonb |  | `[]` |  |  |
| `keywords` | jsonb |  | `[]` |  |  |
| `body_is_image` | boolean |  | `false` |  |  |
| `required_majors` | jsonb |  | `[]` |  |  |
| `required_major_terms` | jsonb |  | `[]` |  |  |
| `required_certifications` | jsonb |  | `[]` |  |  |
| `required_certification_groups` | jsonb |  | `[]` |  |  |
| `required_language_tests` | jsonb |  | `[]` |  |  |
| `military_required` | boolean |  | `false` |  |  |
| `preferred_majors` | jsonb |  | `[]` |  |  |
| `preferred_major_terms` | jsonb |  | `[]` |  |  |
| `preferred_certifications` | jsonb |  | `[]` |  |  |
| `preferred_language_tests` | jsonb |  | `[]` |  |  |
| `first_seen_at` | timestamptz |  |  |  |  |
| `last_seen_at` | timestamptz |  |  |  |  |
| `missing_runs` | integer |  | `0` |  |  |
| `revisions` | integer |  | `0` |  |  |
| `embed_hash` | varchar | 예 |  |  |  |
| `indexed_embed_hash` | varchar | 예 |  |  |  |
| `indexed_at` | timestamptz | 예 |  |  |  |
| `group_key` | varchar | 예 |  |  |  |

추가 인덱스 5개.

### `jobs.job_tags`

공고의 기술 · 키워드 태그.

여러 칸 키: PK (job_id, kind, value)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `job_id` | varchar |  |  | FK → `jobs.job_id` (CASCADE) |  |
| `kind` | varchar |  |  |  |  |
| `value` | varchar |  |  |  |  |

추가 인덱스 1개.

### `jobs.list_jobs`

목록 페이지에서 본 공고(상세를 받기 전 단계).

여러 칸 키: PK (source_job_id, source)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `source_job_id` | varchar |  |  |  |  |
| `job_id` | varchar |  |  |  |  |
| `source_url` | varchar | 예 |  |  |  |
| `company` | varchar | 예 |  |  |  |
| `title` | varchar | 예 |  |  |  |
| `keywords` | jsonb |  | `[]` |  |  |
| `region` | varchar | 예 |  |  |  |
| `career_type` | varchar | 예 |  |  |  |
| `min_career_years` | integer | 예 |  |  |  |
| `education` | varchar | 예 |  |  |  |
| `employment_type` | varchar | 예 |  |  |  |
| `condition_text` | text | 예 |  |  |  |
| `deadline` | varchar | 예 |  |  |  |
| `support_text` | varchar | 예 |  |  |  |
| `seen_at` | timestamptz |  |  |  |  |
| `first_seen_at` | timestamptz | 예 |  |  |  |
| `source` | varchar |  | `SARAMIN_POC` |  |  |

추가 인덱스 2개.

### `jobs.list_jobs_search` (뷰)

목록 공고 검색용 뷰.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `source_job_id` | varchar | 예 |  |  |  |
| `job_id` | varchar | 예 |  |  |  |
| `source_url` | varchar | 예 |  |  |  |
| `company` | varchar | 예 |  |  |  |
| `title` | varchar | 예 |  |  |  |
| `keywords` | jsonb | 예 |  |  |  |
| `region` | varchar | 예 |  |  |  |
| `career_type` | varchar | 예 |  |  |  |
| `min_career_years` | integer | 예 |  |  |  |
| `education` | varchar | 예 |  |  |  |
| `employment_type` | varchar | 예 |  |  |  |
| `status` | varchar | 예 |  |  |  |
| `deadline` | varchar | 예 |  |  |  |
| `tech_stack` | jsonb | 예 |  |  |  |
| `description` | varchar | 예 |  |  |  |
| `seen_at` | timestamptz | 예 |  |  |  |
| `first_seen_at` | timestamptz | 예 |  |  |  |
| `source` | varchar | 예 |  |  |  |

### `jobs.list_seen`

목록에서 본 기록(직무 분류별).

여러 칸 키: PK (source_job_id, cat_mcls, source)

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `source_job_id` | varchar |  |  |  |  |
| `cat_mcls` | varchar |  |  |  |  |
| `seen_at` | timestamptz |  |  |  |  |
| `first_seen_at` | timestamptz | 예 |  |  |  |
| `source` | varchar |  | `SARAMIN_POC` |  |  |

추가 인덱스 2개.

### `jobs.list_sweeps`

직무 분류별 목록 수집 한 번.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `cat_mcls` | varchar |  |  | PK |  |
| `swept_at` | timestamptz |  |  |  |  |
| `total_count` | integer | 예 |  |  |  |
| `seen` | integer | 예 |  |  |  |

### `jobs.link_checks`

공고 링크가 살아 있는지 확인한 기록.

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `job_id` | varchar |  |  | PK |  |
| `checked_at` | timestamptz |  |  |  |  |
| `alive` | boolean |  |  |  |  |

### `jobs.runs`

수집 배치 한 번의 결과(새 공고 · 갱신 · 만료 수).

| 칸 | 형식 | 비어도 됨 | 기본값 | 키 · 참조 | 메모 |
|---|---|---|---|---|---|
| `id` | bigint |  | 자동 증가 | PK |  |
| `started_at` | timestamptz |  |  |  |  |
| `finished_at` | timestamptz | 예 |  |  |  |
| `source` | varchar | 예 |  |  |  |
| `new` | integer | 예 |  |  |  |
| `updated` | integer | 예 |  |  |  |
| `unchanged` | integer | 예 |  |  |  |
| `expired` | integer | 예 |  |  |  |
| `removed` | integer | 예 |  |  |  |
| `observed` | integer | 예 |  |  |  |
| `still_missing` | integer | 예 |  |  |  |
| `vectors` | integer | 예 |  |  |  |
| `error` | text | 예 |  |  |  |
