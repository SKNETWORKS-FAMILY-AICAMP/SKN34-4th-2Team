# SKN34-4th-2Team — PLAYDATA LXP

SK네트웍스 Family AI 캠프 34기 4차 프로젝트 2팀.
학생 · 강사 · 관리자가 함께 쓰는 학습 관리 서비스에 AI 기능(챗봇 · 이력서 첨삭 · 채용공고 추천 · 공부방 노트 · 코드 튜터)을 붙였습니다.

> 3차 프로젝트(Flutter + Firebase) 기록은 [README-3rd.md](README-3rd.md) · [SETUP-3rd.md](SETUP-3rd.md)에 남아 있습니다.

## 구성

```
브라우저 ── React (lms_react, :5173)
              │  /api
              ▼
          Django API (lms_api, :8000) ── PostgreSQL (AWS RDS)
              │  로그인 · 권한 확인 뒤 대신 부름        ├ public : LMS 데이터
              ▼                                        └ jobs   : 채용공고
          AI 서버 (cover_letter_rag/app/integrated.py, :8001)
              ├ 학생 챗봇 (chatbot)
              ├ 이력서 첨삭 (cover_letter_rag)
              ├ 채용공고 추천 · 대화 (job_matching_bot) ── Pinecone
              ├ 공부방 노트 (study_notes)
              └ 연습장 튜터

채용공고 크롤러 (job_matching_bot/crawling) ── 매일 23:00, jobs 스키마 · Pinecone 에 적재
```

| 폴더 | 내용 |
| --- | --- |
| `lms_react/` | 웹 화면 (React · TypeScript · Vite) |
| `lms_api/` | LMS API (Django · django-ninja · JWT) |
| `cover_letter_rag/` | 이력서 첨삭 + AI 서버를 하나로 묶는 진입점(`app/integrated.py`) |
| `chatbot/` | 학생 LMS 챗봇 |
| `job_matching_bot/` | 채용공고 크롤링 · 적재 · 추천 · 공고 대화 |
| `study_notes/` | 공부방 AI 수업 노트 · 복습 문제 |
| `practice_verifier/` | 복습 문제 검증기 (브라우저와 같은 Pyodide) |
| `vectordb/` | 학생 챗봇 벡터 DB 적재 |
| `chatbot_lab/` | 챗봇 실험용 (운영과 연결 안 됨) |
| `lms_mobile/` | 모바일 앱 (Expo · React Native, 웹 도메인 코드를 함께 씀) |
| `lms_expo/` | 모바일 앱 시작점 (Expo) |
| `scripts/` | 실행 · 이전 · 적재 스크립트 |
| `deploy/`, `docker-compose*.yml` | 배포 (Nginx · AI 서버 이미지) |
| `docs/` | 설계 · 이전 · 점검 문서 |
| `functions/`, `config/firebase/` | 3차 Firebase 자산 (이전 참고용) |

각 폴더의 README에 자세한 설명이 있습니다.

## 로컬 실행

필요한 것: Python 3.12, Node 20 이상, (로컬 DB를 쓸 때) Docker.

### 1. 환경변수

```bash
cp .env.example .env
```

- **RDS를 쓸 때:** `DB_HOST` · `DB_NAME` · `DB_USER` · `DB_PASSWORD`를 채웁니다. 채우면 `DATABASE_URL`보다 먼저 씁니다. 접속 정보는 팀 채널에서 받습니다.
- **로컬 DB를 쓸 때:** `DB_*`를 비우고 `docker compose up -d db`로 PostgreSQL을 띄웁니다(`DATABASE_URL` 기본값).
- AI 기능을 쓰려면 `CHATBOT_URL` · `JOBS_URL`을 `http://127.0.0.1:8001`로 둡니다. 비우면 그 기능만 「연결되어 있지 않습니다」로 답합니다.
- 값에 따옴표를 붙이지 않습니다.

### 2. Python 패키지

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r lms_api/requirements.txt
```

### 3. 서버 셋 띄우기 (터미널 셋)

```bash
# Django API → http://127.0.0.1:8000
cd lms_api
python manage.py migrate          # 로컬 DB 일 때만. RDS 는 이미 적용돼 있다
python manage.py runserver 127.0.0.1:8000

# AI 서버 → http://127.0.0.1:8001
python -m uvicorn app.integrated:app --app-dir cover_letter_rag --port 8001
#   Windows 는 scripts/start-backend.ps1 -Port 8001 -SkipJobStoreSync 도 된다

# 화면 → http://localhost:5173  (/api 는 8000 으로 넘긴다)
cd lms_react
npm install
npm run dev
```

계정은 팀 채널에서 받습니다(저장소에 비밀번호를 적지 않습니다).

### 4. 휴대폰으로 보기 (웹 · Expo 앱)

PC와 휴대폰이 **같은 와이파이**에 있어야 합니다. 아래 `192.168.0.55`는 예시이니 `ipconfig`의 IPv4 주소로 바꿉니다.

```bash
ipconfig                          # 무선 LAN 의 IPv4 주소 확인 (예: 192.168.0.55)
```

**① 루트 `.env`에 PC 주소 추가** (바꾼 뒤 Django 를 다시 켭니다)

```
ALLOWED_HOSTS=127.0.0.1,localhost,192.168.0.55
CORS_ALLOWED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://192.168.0.55:5173
CSRF_TRUSTED_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://192.168.0.55:5173
```

**② Django 를 외부에서 접속 가능하게 띄우기**

```bash
cd lms_api
python manage.py runserver 0.0.0.0:8000
```

**③-A 웹으로 보기** → 휴대폰 브라우저에서 `http://192.168.0.55:5173`

```bash
cd lms_react
npm run dev -- --host             # --host 가 있어야 휴대폰에서 열린다
```

**③-B Expo 앱으로 보기** → 휴대폰에 **Expo Go** 설치 후 QR 스캔

```bash
cd lms_mobile
# lms_mobile/.env (처음 한 번)
#   EXPO_PUBLIC_API_BASE=http://192.168.0.55:8000/api
#   EXPO_PUBLIC_WEB_URL=http://192.168.0.55:5173
npm install
npx expo start -c                 # -c : 캐시 비우고 시작 (.env · 패키지 바꾼 뒤엔 꼭)
```

- 터미널에서 `r` 은 앱 새로고침, Android 는 Expo Go 로, iPhone 은 기본 카메라로 QR 을 찍습니다.
- 로그인이 안 되면: PC 주소가 바뀌지 않았는지, `.env` 를 바꾼 뒤 Django · Expo 를 다시 켰는지, Windows 방화벽이 8000 · 5173 · 8081 포트를 막지 않는지 확인합니다.
- 같은 와이파이가 아니면 `npx expo start --tunnel` 로 앱은 열리지만, API 주소(`EXPO_PUBLIC_API_BASE`)는 휴대폰이 닿는 주소여야 합니다.

## 테스트

```bash
cd lms_react && npm test && npm run build     # 화면 테스트 · 타입 검사 · 빌드
cd lms_api && python manage.py test lms       # Django
pytest job_matching_bot/tests                 # 크롤러 · 추천 (로컬 DB 필요)
```

## 작업 방식

### 브랜치

| 브랜치 | 용도 |
| --- | --- |
| `main` | 배포 기준. `develop`에서만 머지 |
| `develop` | 통합 개발 브랜치. 모든 작업 브랜치가 여기로 머지 |
| `feature/*` · `fix/*` · `docs/*` · `chore/*` | 작업 브랜치. `develop`에서 분기 |

```bash
git switch develop && git pull origin develop
git switch -c feature/<이슈번호>-<작업명>
# ... 작업 · 커밋 ...
git push -u origin feature/<이슈번호>-<작업명>
# GitHub 에서 develop 으로 Pull Request
```

### 이슈 · 보드

- 할 일은 [Issues](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team/issues)에서, 진행 상황은 [프로젝트 보드](https://github.com/orgs/SKNETWORKS-FAMILY-AICAMP/projects/64)에서 봅니다.
- 칸: 할 일 → 진행 중 → 검토 중(PR) → 완료
- 이슈를 맡으면 Assignees에 이름을 넣고 카드를 「진행 중」으로 옮깁니다.

### 커밋

```
[#이슈번호] <type>: <짧은 제목>
```

- `type`: `feat` · `fix` · `docs` · `refactor` · `test` · `chore`
- 예: `[#7] feat: 자리 배치 저장 RDS 연결`
- PR 설명에 `Closes #7`을 쓰면 머지될 때 이슈가 닫히고 보드에서 「완료」로 갑니다.

## 문서

| 문서 | 내용 |
| --- | --- |
| [docs/target-architecture.md](docs/target-architecture.md) | 목표 구조 |
| [docs/db-schema.md](docs/db-schema.md) · [docs/db-tables.md](docs/db-tables.md) | DB 스키마 · 테이블 |
| [docs/migration-report.md](docs/migration-report.md) | Firestore → PostgreSQL 이전 결과 |
| [docs/backend-changes-for-rds.md](docs/backend-changes-for-rds.md) | RDS 통합 때 바뀐 백엔드 |
| [docs/deploy-checklist.md](docs/deploy-checklist.md) | 배포 점검 |
