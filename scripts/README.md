# scripts

개발 환경 준비, Firebase 초기 데이터, 서버 실행을 돕는 스크립트 모음이다. 모두 **레포 루트에서** 실행한다.
Node 스크립트는 처음 한 번 `cd scripts; npm install`이 필요하다.

## 서버·환경

| 스크립트 | 하는 일 |
|---|---|
| `start-backend.ps1` | 통합 백엔드(포트 8000)를 켠다. 켜기 전에 Firebase Storage의 팀 공유 공고 DB가 새로 올라왔는지 보고, 새 파일이면 임시로 받아 무결성·필수 컬럼을 검사한 뒤 교체한다. 크롤링·임베딩·Pinecone 적재는 하지 않는다 |
| `sync-functions-env.ps1` | 루트 `.env`를 `functions/.env`로 복사한다. Firebase CLI가 거부하는 `X_GOOGLE_`·`FIREBASE_`·`EXT_`·`KIT_`로 시작하는 키는 뺀다. Functions 배포 전에 실행 |
| `migrate-env-to-root.ps1` | 예전에 모듈마다 있던 `.env`(`cover_letter_rag/.env`, `functions/.env`)를 루트 `.env` 하나로 합친다. 비밀값은 출력하지 않는다 |

```powershell
.\scripts\start-backend.ps1                    # 공유 DB 확인 후 서버 시작(--reload)
.\scripts\start-backend.ps1 -SkipJobStoreSync  # 공유 DB 확인 건너뛰기
.\scripts\start-backend.ps1 -Port 8010 -NoReload
powershell -ExecutionPolicy Bypass -File scripts\sync-functions-env.ps1
```

`start-backend.ps1`은 `playdata_venv` 가상환경이 있어야 하고, 포트가 이미 쓰이고 있으면 멈춘다.
서버는 `0.0.0.0`에 열리므로 같은 네트워크의 다른 기기에서도 접속할 수 있다.

## Firebase 초기 데이터

| 스크립트 | npm 명령 | 하는 일 |
|---|---|---|
| `run-seed.ps1` | — | **처음 한 번 실행하는 기본 스크립트.** 임시 Firestore 규칙 배포 → 관리자·강사·학생 테스트 계정과 기수 생성 → 운영 규칙 복원·재배포 |
| `seed-via-client.mjs` | `npm run seed` | Client SDK로 계정 + 기수만 생성(샘플 데이터 없음). `run-seed.ps1`이 부른다 |
| `setup-production.mjs` | `npm run setup:production` | Admin SDK로 운영 프로젝트에 계정 + 기수 생성 |
| `seed-instructor.mjs` | `npm run seed:instructor` | 관리자로 로그인해 `createInstructorAccount`로 강사 테스트 계정 생성 |
| `seed-students-bulk.mjs` | `npm run seed:students` | 관리자로 로그인해 `createStudentAccount`로 무작위 학생 N명 생성(`--count=25`) |
| `seed-test-users.mjs` | `npm run seed:users` | Firebase **에뮬레이터**에 테스트 계정 생성 |
| `seed-resume-mocks.mjs` | `npm run seed:resumes` / `clear:resumes` | 가상 이력서(`resume_mocks.json`)를 특정 계정 아래 넣거나 지운다. 비밀번호는 환경변수로만 받는다 |
| `clear-sample-data.mjs` | `npm run clear:sample` | 넣었던 샘플 데이터 삭제, 프로필 초기화 |
| `sync-qual-exam-cache.mjs` | — | 공공데이터포털 자격시험 일정을 로컬 PC에서 받아 Firestore 캐시에 넣는다. Functions에서 포털 연결이 시간 초과될 때 쓰는 대체 경로 |

```powershell
cd scripts; npm install; cd ..
.\scripts\run-seed.ps1

$env:SEED_EMAIL="student@playdata.co.kr"; $env:SEED_PASSWORD="<비밀번호>"
node scripts/seed-resume-mocks.mjs
```

사전 조건(Authentication 이메일/비밀번호 켜기 등)과 생성되는 계정은 [SETUP-3rd.md](../SETUP-3rd.md#계정-시드-최초-1회)에 있다.

## 데이터 파일

| 파일 | 내용 |
|---|---|
| `resume_mocks.json` | 앱 목업 메뉴·시드용 가상 이력서 5종. 키가 `job_matching_bot/schemas/resume.py`의 목업과 1:1이다 |
| `resume_mocks_eval.json` | **평가 전용** 가상 이력서 5종. 프롬프트를 고칠 때 보지 않은 이력서로 추천 품질을 재기 위해 따로 둔다. 앱 메뉴에는 넣지 않는다 |

실제 인물 데이터가 아니다.

## 기타

| 스크립트 | 하는 일 |
|---|---|
| `fetch_holidays.py` | 공공데이터포털 특일 정보로 `lib/core/constants/korean_holidays.dart`를 다시 만든다. 앱은 실행 중에 이 API를 부르지 않고 만들어진 표만 읽는다 |
| `google-form-webhook.gs` | 구글폼에 붙이는 Apps Script. 제출을 Functions `googleFormWebhook`으로 보낸다. 설정 방법은 [SETUP-3rd.md](../SETUP-3rd.md)의 구글폼 설문 연동 |
| `fix-cursor-update-lock.bat` | Cursor 에디터 업데이트 잠금 해제 도우미(개발 도구용, 프로젝트 기능과 무관) |
