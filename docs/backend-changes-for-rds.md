# feature/change_react 백엔드 변경 · RDS 통합 전 확인 사항

> 작성 2026-09-24 · 기준 브랜치 `feature/change_react` (원격 `9330614` + 미커밋 일부)
> 대상: RDS 통합 담당(`feature/postgresql-integration`)
> 비밀번호 · 키는 적지 않았다. 필요하면 따로 전달한다.

---

## 1. 먼저 정해야 할 것 (요청)

| # | 요청 | 이유 |
|---|---|---|
| 1 | **새 DB 설계가 확정인지** 알려 주기 | 우리 코드가 쓰는 테이블 중 새 설계에 없는 게 있다(3장). 확정이면 우리 쪽을 맞춘다 |
| 2 | **`study.*` 테이블 5개를 설계에 넣을지** 정하기 | 공부방 자동 출제 · 튜터가 새로 만든 테이블. 새 설계에 없다 |
| 3 | **`jobs` 적재 일정** 정하기 | 로컬 공고를 RDS `lms_migration_replay_20260923`에 넣을 준비가 끝났다(5장). 아직 넣지 않았다 |
| 4 | **크롤러 전용 DB 계정** 만들기 | 지금 `.env`는 `project_admin`(관리자). 크롤러는 `jobs` 스키마 읽기 · 쓰기만 있으면 된다 |
| 5 | **RDS 비밀번호 변경** | 공인 IP로 열려 있는데 비밀번호가 약하다(6장) |

---

## 2. 우리 브랜치의 백엔드 변경

### 2-1. Django API (`lms_api/lms/api.py`)

| 경로 | 내용 | 커밋 |
|---|---|---|
| `POST /api/resume-review` | 첨삭 창이 대화를 이어 가는 필드 추가: `requestId`, `expectedInputHash`, `expectedJobHash`, `reviewPhase`(gap_audit), `previousReviewId`, `answers` | `00d2530` |
| `POST /api/resume-review/context` | 첨삭할 이력서 · 공고 스냅샷과 `input_hash` | `00d2530` |
| `POST /api/resume-review/tailored` | 공고 맞춤 사본 만들기(이미 있으면 그 사본) | `00d2530` |
| `POST /api/resume-review/tailored/get` | 맞춤 사본과 저장된 첨삭 대화 | `00d2530` |
| `POST /api/resume-review/session` | 첨삭 대화를 맞춤 사본에 저장 | `00d2530` |
| `POST /api/resume-review/promote` | 맞춤 사본을 편집용 이력서(`matched_…`)로 옮기기 | `00d2530` |
| `GET /api/postings/{job_id}` | **로그인 없이 공개.** 공고 원문 한 건 + 같은 공고의 사이트별 링크(`links`, `group_key` 묶음). 새 탭은 로그인 정보(sessionStorage)를 못 받아서 공개로 둠 | `dccdcf1`, `9330614` |
| ~~`POST /api/jobs/linked`~~ | **삭제.** 연결 공고는 `/api/postings`로 읽는다 | `dccdcf1` |

`/api/postings`는 Django DB 연결로 `jobs.jobs`를 바로 읽는다. 쓰는 칸은 다음과 같다. RDS에서도 `jobs` 스키마가 Django와 같은 DB에 있어야 한다.
- `job_id`, `source`, `source_url`, `company`, `title`, `description`, `region`
- `career_type`, `min_career_years`, `employment_type`, `education`, `deadline`, `status`
- `required_skills`, `preferred_skills`, `body_is_image`, `group_key`

### 2-2. AI 서버 (`cover_letter_rag`, 통합 서버 8001)

**Django용 창구(`/proxy`)**
- Django가 학생을 확인한 뒤 uid로 부르는 창구다. 바깥에 열지 않는다.
- `reviews/proxy`는 원래 있었고, 나머지 5개를 추가했다:
  - `POST /api/v1/resumes/review-context/proxy`
  - `POST /api/v1/resumes/tailored/proxy`
  - `POST /api/v1/resumes/tailored/get/proxy`
  - `POST /api/v1/resumes/tailored/session/proxy`
  - `POST /api/v1/resumes/tailored/promote/proxy`

**DB에 쓰는 동작이 생김** (`firebase_gateway.py`, `dccdcf1`)
- **대상:** Firestore에서 옮겨 온 맞춤 사본(`resumes.legacy_id = '원본/tailored/tailored_…'`)
- **문제:** 이 사본들은 `resumes.sections._tailored`(공고 스냅샷 · 첨삭 대화)가 비어 있다. 그래서 사본 만들기는 404, 스냅샷 확인은 `tailored_resume_job_changed`로 막혔다.
- **동작:** 이런 사본을 열면 지금 공고 스냅샷으로 `sections._tailored`를 채우고, `linked_job_id`가 비었으면 채운다. 연결된 공고와 같을 때만 채운다.
- **ETL 쪽 요청:** 새 ETL에서 이 정보를 같이 옮겨 주면 이 보정은 필요 없어진다.

**LangSmith 추적 개인정보 가리기** (미커밋, `trace_privacy.py`)
- 추적을 켜면 LLM 입력 · 출력이 LangSmith(국외)로 간다. 그래서 기본정보 이름 · 연락처 · 이메일, 글 속 전화 · 이메일 · 주민번호 · 개인 링크를 가려서 보낸다.
- 운영은 `LANGSMITH_HIDE_INPUTS=true`, `LANGSMITH_HIDE_OUTPUTS=true`로 내용을 아예 안 보내는 것을 권한다.

### 2-3. 공부방 · 연습장 (같은 브랜치, 다른 작업)

주요 커밋: `7712eac`, `6ed78b4`, `95b39b9`, `b2780e1`, `afe7eab`, `940907e`, `a4902b1`
- 공부방 노트를 AI 서버에 연결
- 기수에 GitHub 조직 · 강사 계정을 연결하면 수업 저장소를 자동으로 올림
- 매일 18:30 복습 문제 자동 출제
- 강사 · 학생이 직접 문제 만들기
- 연습장 튜터(3단계 힌트)

이 작업들이 쓰는 테이블은 `practice.*`와 새 `study.*`다(3장).

### 2-4. 환경변수 (`.env.example`)

| 키 | 변경 |
|---|---|
| `CHATBOT_URL`, `JOBS_URL` | AI 서버 로컬 포트를 **8001**로 통일(`f95a052`). 둘 다 같은 통합 서버를 가리킨다 |
| `LMS_AI_SHARED_TOKEN` | 로컬 `.env`에 `LMS_AI_SHAREDTOKEN`으로 잘못 적혀 있던 것을 고쳤다. 각자 `.env`를 확인할 것 |
| `STUDY_NOTES_URL` | 공부방 노트만 다른 서버에 띄울 때(비우면 `JOBS_URL`) |
| `AWS_S3_BUCKET` | 예시 값 `skn34-4th-2team-lxp` |
| `DB_NAME` | 로컬 `.env`를 `lms_migration_replay_20260923`로 바꿈. 지금 로컬 Django는 `DATABASE_URL`(로컬 Docker)을 쓴다 |

---

## 3. 새 DB 설계와 다른 테이블

우리 코드가 쓰는데 `feature/postgresql-integration`의 Django 모델(67개 테이블)에 없는 테이블이다.

| 우리가 쓰는 테이블 | 새 설계 | 쓰는 코드 |
|---|---|---|
| `seating_rooms`, `seating_cells`, `seating_assignments`, `seat_assignments` | 없음. `cohort_seating`, `seat_presences`로 바뀐 것으로 보임 | `bootstrap_service.py`, `commands.py`, `seating_commands.py`, `chatbot/firebase_student_context.py` |
| `roll_calls`, `roll_call_entries` | 없음 | `bootstrap_service.py`, `content_commands.py` |
| `form_tasks`, `form_responses` | `submission_tasks`, `submission_responses` | `bootstrap_service.py`, `commands.py`, `content_commands.py`, `chatbot/firebase_student_context.py` |
| `practice.sets`, `practice.problems`, `practice.attempts`, `practice.reports`, `practice.reviews`, `practice.coverage` (`practice` 스키마) | `practice_sets` 등 (`public` 스키마) | `practice_service.py`, `practice_auto.py`, `practice_tutor.py`, `practice_custom.py` |
| `study.github_owners`, `study.practice_jobs`, `study.practice_runs`, `study.practice_settings`, `study.tutor_turns` | **없음** | `study_source_service.py`, `practice_auto.py`, `practice_custom.py`, `practice_tutor.py` |

**두 브랜치를 가상으로 병합한 결과**
- 파일 12개가 충돌한다.
- 크게 겹치는 곳: `bootstrap_service.py`(4곳), `StudyRoomScreen.tsx`(5곳), `ResumeScreens.tsx`(4곳), `repository.ts`, `study_notes/api.py`(3곳씩), `etl.py`(2곳)
- 공부방 노트를 AI 서버에 연결하는 작업은 양쪽에 따로 있다(`f58f965` ↔ `7712eac`). 어느 쪽을 살릴지 정해야 한다.

---

## 4. `jobs` 스키마 (채용공고)

| 항목 | 상태 |
|---|---|
| 칸 | 로컬 `jobs` 7개 테이블과 RDS `0003_jobs_schema`가 **칸 105개까지 같다** |
| 로컬 건수 (09-24 17:10) | 공고 79,720 · `job_tags` 949,138 · `list_jobs` 263,875 · `list_seen` 440,803 · `link_checks` 588 · `list_sweeps` 29 · `runs` 7 |
| RDS 건수 | 7개 테이블 모두 **0건** |
| 크롤러 저장 코드 | 우리 `sqlite_store.py`는 열 때 `CREATE SCHEMA`, `ALTER TABLE ADD COLUMN`을 한다. 팀원 버전은 스키마를 확인만 한다(문서 규칙: 운영에서 크롤러는 DDL 금지). **RDS로 돌리기 전에 팀원 버전을 기준으로 맞춘다** |
| 야간 배치 | 매일 23:00 로컬에서 돈다. 9/23 밤은 DB가 꺼져 있어 파일로만 남았고, 9/24 17시에 손으로 적재 · 묶기 · 색인까지 마쳤다 |

---

## 5. `jobs` RDS 적재 계획 (아직 안 함)

1. **팀원에게 알리고** 로컬 덤프(`pg_dump -n jobs --data-only`)를 RDS에 한 트랜잭션으로 넣는다. 실패하면 전부 취소된다.
2. 테이블 7개 건수를 로컬과 비교한다.
3. 크롤러가 RDS에 쓰도록 바꾼다: `JOBS_DATABASE_URL`을 `DATABASE_URL`보다 먼저 보게 한다. `DATABASE_URL`은 로컬 Django가 쓰므로 그대로 둔다.
4. Pinecone은 다시 올리지 않는다. `indexed_embed_hash`가 같이 복사되기 때문이다.

- 적재 전에 야간 배치가 한 번 더 돌면 덤프를 다시 떠야 한다(기준: 로컬 `runs` 7줄 초과).
- **RDS에 쓰는 명령은 로컬 담당자가 직접 실행한다.**

---

## 6. 보안

- **RDS 공개 접근:** 공인 IP로 열려 있고 비밀번호가 약하다. 변경을 권한다.
- **보안 그룹:** `/32` 단위로만 연다. 지금 추가된 것은 `222.108.81.142/32`(크롤러 담당 PC). 이 IP는 인터넷 환경이 바뀌면 달라진다.
- **공개 API:** `GET /api/postings/{job_id}`는 로그인 없이 열려 있다. 공개 채용공고만 돌려준다.
- **LangSmith:** 2-2장의 가리기 참고. 운영은 내용 숨김을 권한다.

---

## 7. 알려진 버그 (`job_matching_bot`, 아직 안 고침)

배치 시간(23:00~아침)을 피해서 고친다.
- `sync --index-only`에 `--dry-run`을 붙여도 무시되고 **실제로 색인을 올린다**.
- `sync --index-only`는 `jobs.runs`에 기록을 남기지 않는다. `sync.py:156`에서 먼저 빠져나가기 때문이다.
- `jobs.runs` 시각이 9시간 밀려 저장된다. 시간대 없는 `datetime.now()`(KST)를 넘겨서 Postgres가 UTC로 받는다. 공고의 `first_seen_at`, `last_seen_at`은 정상이다.
