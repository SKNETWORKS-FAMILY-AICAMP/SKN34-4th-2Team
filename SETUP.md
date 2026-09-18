# PLAYDATA All-in-One LMS — 팀원 실행 가이드

Flutter + Firebase 기반 LMS입니다.  
**Firebase 설정 파일은 저장소에 포함**되어 있어, 클론 후 바로 앱을 실행할 수 있습니다.

---

## 빠른 시작 (5분)

```powershell
# 1. 저장소 클론 (develop 브랜치)
git clone <저장소 URL>
cd SKN34-3rd-2Team
git checkout develop

# 2. Flutter 패키지 설치
flutter pub get

# 3. Chrome에서 실행
flutter run -d chrome
```

로그인 계정이 없다면 → 아래 [계정 시드](#계정-시드-최초-1회) 참고.

---

## 사전 준비 (설치 목록)

| 도구 | 버전 | 확인 명령 |
|------|------|-----------|
| **Flutter** | SDK `^3.12` | `flutter --version` |
| **Chrome** | 최신 | 웹 실행용 |
| **Git** | 최신 | `git --version` |
| **Node.js** | 20.x | `node --version` (Functions/시드 스크립트용) |
| **Firebase CLI** | 최신 | `firebase --version` (시드·배포용) |

### Flutter 설치가 안 되어 있다면

1. https://docs.flutter.dev/get-started/install/windows
2. 설치 후 `flutter doctor` 실행 → 경고 없는지 확인

### Firebase CLI 설치

```powershell
npm install -g firebase-tools
firebase login
```

> Firebase 프로젝트(`skn34-3rd-2team`)에 **팀원 계정이 초대**되어 있어야 시드·배포가 가능합니다.  
> 초대가 안 되어 있으면 팀 리더에게 요청하세요.

---

## 프로젝트 정보

| 항목 | 값 |
|------|-----|
| Firebase Project ID | `skn34-3rd-2team` |
| 기본 기수 ID | `cohort_34` |
| 지원 플랫폼 | **Web (Chrome)**, Android, Windows |
| 작업 브랜치 | `develop` (`main`은 배포용, 직접 푸시 금지) |

---

## 앱 실행

### Web (권장 — 개발 시)

```powershell
flutter run -d chrome
```

실행 중 단축키:
- `r` — Hot reload
- `R` — Hot restart
- `q` — 종료

### Android

```powershell
flutter devices          # 연결된 기기 확인
flutter run -d <deviceId>
```

### Windows 데스크톱

```powershell
flutter run -d windows
```

---

## 로그인 계정

시드 실행 후 아래 계정으로 로그인합니다.

| 역할 | 이메일 | 비밀번호 |
|------|--------|----------|
| 관리자 | `admin@playdata.co.kr` | `Playdata123!` |
| 강사 | `instructor@playdata.co.kr` | `Playdata123!` |
| 학생 | `student@playdata.co.kr` | `Playdata123!` |

> 최초 로그인 시 비밀번호 변경 화면이 나올 수 있습니다.

---

## 계정 시드 (최초 1회)

Firebase에 테스트 계정이 **아직 없을 때** 한 번만 실행합니다.

### 사전 조건

Firebase Console에서 아래를 먼저 켜야 합니다.

1. **Authentication → 이메일/비밀번호** 사용 설정  
   https://console.firebase.google.com/project/skn34-3rd-2team/authentication/providers

2. **Firestore** 데이터베이스 생성 (이미 되어 있으면 생략)

3. **Storage** 시작하기 (파일 업로드 기능용, 선택)  
   https://console.firebase.google.com/project/skn34-3rd-2team/storage

### 시드 실행

```powershell
cd scripts
npm install
cd ..
.\scripts\run-seed.ps1
```

스크립트가 자동으로:
1. 임시 Firestore Rules 배포
2. 관리자·학생 계정 + 기수 데이터 생성
3. Production Rules 복원·재배포

완료 후 `flutter run -d chrome`으로 로그인하세요.

---

## Functions 로컬 개발 (선택)

Cloud Functions 코드를 수정할 때만 필요합니다.

```powershell
cd functions
npm install
npm run build
cd ..
```

### 환경 변수 설정

```powershell
copy .env.example .env
# 루트 .env에서 DISCORD_COHORT_ID 등 수정
powershell -ExecutionPolicy Bypass -File scripts\sync-functions-env.ps1
```

> 루트 `.env`가 유일한 수동 설정 파일입니다. `functions/.env`는 배포 전 동기화 스크립트가 만드는 복사본이며 직접 수정하지 않습니다. `.env` 파일은 Git에 올라가지 않습니다. 팀 리더에게 값을 받으세요.

학생 챗봇 프롬프트 버전은 `LMS_CHATBOT_PROMPT_VERSION`(기본 `student_chatbot_v2`)입니다. 라우팅 평가 요약을 관리자 LLMOps 화면에 올리려면 명시적으로 `--publish`를 붙입니다.

```powershell
.\playdata_venv\Scripts\python.exe -m chatbot_lab.evaluate_supervisor --production --publish
```

### Functions 배포 (Blaze 플랜 필요)

```powershell
cd functions
npm run build
cd ..
firebase deploy --only functions
```

---

## 자주 겪는 문제

### `flutter pub get` 실패

```powershell
flutter clean
flutter pub get
```

### Chrome 디버그 연결 끊김 (`Cannot find context with specified id`)

1. 터미널에서 `q`로 종료
2. Chrome localhost 탭 전부 닫기
3. `flutter run -d chrome` 다시 실행

### 로그인 안 됨 / `user-not-found`

→ [계정 시드](#계정-시드-최초-1회)를 아직 안 했을 가능성이 큽니다.

### Firebase 권한 오류 (`permission-denied`)

- Firebase Console에서 본인 계정이 프로젝트 멤버인지 확인
- 시드 후에도 안 되면 `firebase login` 다시 실행

### `flutterfire configure` 해야 하나요?

**아니요.** `lib/firebase_options.dart`와 `android/app/google-services.json`이 이미 저장소에 있습니다.  
새 플랫폼(iOS 등)을 추가할 때만 필요합니다.

---

## Git 작업 규칙

| 항목 | 규칙 |
|------|------|
| 작업 브랜치 | `develop` |
| 커밋 메시지 | `S32-XX) 작업 설명` (Jira 이슈 키 + 설명) |
| `main` 브랜치 | 직접 푸시하지 않음 |

```powershell
git checkout develop
git pull origin develop
# 작업 후
git add .
git commit -m "S32-XX) 작업 설명"
git push origin develop
```

---

## 선택 기능 (나중에 필요할 때)

<details>
<summary><b>Discord 공지 연동</b></summary>

디스코드 `#매니저-공지사항`, `#캠퍼스-질문주세요` 채널 글을 5분마다 Firestore `notices`에 동기화합니다.

### 1. Bot Token Secret 등록

```powershell
firebase functions:secrets:set DISCORD_BOT_TOKEN
```

### 2. 기수 ID 설정

루트 `.env.example` → 루트 `.env` 복사 후:

```
DISCORD_COHORT_ID=cohort_34
```

그 다음 Functions 배포 전에 `powershell -ExecutionPolicy Bypass -File scripts\sync-functions-env.ps1`를 실행한다.

### 3. 배포

```powershell
cd functions
npm run build
cd ..
firebase deploy --only functions:syncDiscordNotices,functions:syncDiscordNoticesNow
```

### 채널 매핑

| 채널 | ID | 라벨 |
|------|-----|------|
| #매니저-공지사항 | 1505777394886246501 | 매니저 공지 |
| #캠퍼스-질문주세요 | 1505777394886246502 | 캠퍼스 Q&A |

</details>

<details>
<summary><b>구글폼 설문 연동</b></summary>

구글폼 제출을 LMS에 자동 반영합니다.

### 1. Webhook Secret 등록

```powershell
firebase functions:secrets:set GOOGLE_FORM_WEBHOOK_SECRET
```

### 2. 배포

```powershell
firebase deploy --only functions:googleFormWebhook
```

Webhook URL:
`https://asia-northeast3-skn34-3rd-2team.cloudfunctions.net/googleFormWebhook`

### 3. LMS에서 설문 등록

1. 관리자 로그인 → **설문 · 제출**
2. **설문 등록** → 제목, 구글폼 URL, 마감일 입력
3. 상세 화면에서 `cohortId`, `taskId` 확인 → **Apps Script 코드 복사**

### 4. Google Apps Script 연결

1. 구글폼 → 설정 → 응답 → **이메일 주소 수집: 확인됨**
2. 구글폼 → ⋮ → **스크립트 편집기** (시트가 아니라 폼에서 연다)
3. LMS 설문 상세의 **Apps Script 코드 복사**를 붙여넣는다 (`WEBHOOK_URL`·`COHORT_ID`·`TASK_ID`가 채워져 있다)
4. `WEBHOOK_SECRET`만 Firebase Secret 값으로 바꾼다
5. 왼쪽 시계(트리거) → `onFormSubmit` / **설문지에서** / **양식 제출 시** 를 **하나만** 등록
6. Apps Script의 **배포**는 하지 않는다. 편집기에서 `onFormSubmit`을 직접 실행하면 최신 응답으로 테스트된다

> 학생이 LMS에 등록한 `personalEmail`(Gmail)로 로그인해서 제출해야 매칭됩니다.

</details>

<details>
<summary><b>국가자격 시험일정 API</b></summary>

루트 `.env`에 공공데이터포털 인증키 설정 (Functions 배포 전 동기화):

```
DATA_GO_KR_SERVICE_KEY=발급받은_키
```

</details>

<details>
<summary><b>마일리지 CMS</b></summary>

자체 CMS(Firestore + Cloud Functions)로 마일리지 교환·적립·소멸을 처리합니다. 비즈콘 API는 사용하지 않습니다.

### 관리자 메뉴

Drawer → **마일리지 관리**

| 메뉴 | 경로 | 설명 |
|------|------|------|
| 상품 관리 | `/admin/mileage/products` | 교환 상품 CRUD, 시드 상품 등록 |
| 기수 설정 | `/admin/mileage/settings` | 카테고리 한도·기록실 자동 적립 규칙 |
| 구매 요청 | `/admin/mileage/requests` | 승인/반려/수정요청 (승인 시 즉시 차감) |
| 지급/차감 | `/admin/mileage/adjust` | 수동 마일리지 조정 |

### Functions 배포 (최초 1회)

```powershell
cd functions
npm run build
cd ..
firebase deploy --only functions:submitPurchaseRequest,functions:reviewPurchaseRequest,functions:cancelPurchaseRequest,functions:adjustMileage,functions:reviewSubmission,functions:expireMileage,functions:expireMileageNow
firebase deploy --only firestore:rules,firestore:indexes
```

### E2E 테스트 체크리스트

- [ ] 관리자 **지급/차감**으로 학생에게 마일리지 지급
- [ ] 기록실 블로그/스터디/자격증 **승인** → 자동 적립 (중복 없음)
- [ ] 고정가 상품 구매 요청 → 관리자 **승인** → 잔액 차감
- [ ] 인프런/yes24 커스텀 모달 → 장바구니 → 구매 요청
- [ ] 카테고리 한도 초과 시 구매 요청 **거부**
- [ ] 잔액 부족 시 관리자 **승인 거부**
- [ ] 반려/취소 시 잔액 **변동 없음**
- [ ] 종강+14일 소멸 배치 (관리자 callable 테스트)

### 소멸 배치 수동 테스트

Firebase Console 또는 앱에서 관리자 로그인 후 `expireMileageNow` 호출:

```javascript
// Firebase Console > Functions > expireMileageNow 테스트
{ "mockDate": "2027-01-01" }  // cohort.endDate + 14일 <= mockDate 인 기수 대상
```

기수 `endDate`를 과거로 설정한 테스트 cohort에서 확인하세요. `users.mileageExpiredAt` 플래그로 중복 소멸을 방지합니다.

</details>

---

## 프로젝트 구조 (참고)

```
SKN34-3rd-2Team/
├── lib/              # Flutter 앱 소스
├── functions/        # Firebase Cloud Functions (TypeScript)
├── scripts/          # 시드·설정 스크립트
├── config/firebase/  # Firestore·Storage rules / indexes / CORS
├── android/          # Android 빌드
├── ios/              # iOS 빌드
├── web/              # Web 빌드
└── firebase.json     # Firebase 설정 (rules 경로 포함)
```

---

## 성취도 평가 (CSV 커리큘럼 + AI)

강사가 구글시트를 CSV로 내려받아 업로드하면, 일수 구간을 골라 AI가 객관식/단답 초안을 만듭니다.
Google Sheets API / Notion Integration은 사용하지 않습니다.

### 1) OpenAI API 키 (Secret Manager)

문항 생성은 **배포된 Cloud Functions**가 합니다. Functions는 루트 `.env`를 읽지 않고 Secret Manager 값을 씁니다. 공지 벡터 적재(`syncNoticeVector`)도 같은 Secret을 씁니다.

```powershell
firebase functions:secrets:set OPENAI_API_KEY
firebase deploy --only functions:generateAssessmentQuestions,functions:syncNoticeVector
```

`OPENAI_API_KEY`를 `functions/.env`에 넣지 마세요. Secret과 일반 환경변수에 같은 이름이 있으면 배포가 400으로 실패합니다. `scripts/sync-functions-env.ps1`는 이 키를 자동으로 제외합니다.

Secret 값을 바꿨을 때도 위 배포를 다시 해야 반영됩니다. Flutter `R`만으로는 안 됩니다.

CSV 업로드 permission-denied 가 나면 rules도 배포:

```powershell
firebase deploy --only firestore:rules,storage
```

### 2) 배포

```powershell
cd functions
npm run build
cd ..
firebase deploy --only functions,firestore:rules,storage
```

OPENAI_API_KEY가 없어도 앱은 동작합니다. 커리큘럼 AI 생성만 설정 안내 오류를 반환합니다.
Demo 계정에서는 샘플 커리큘럼으로 AI 다이얼로그가 동작합니다.

### 3) 강사 사용 흐름

1. 구글시트 → 파일 → 다운로드 → CSV
2. 강사 메뉴 **커리큘럼**에서 CSV 업로드
3. 성취도평가 만들기 → **커리큘럼 AI** → 일수 구간 선택 → 초안 생성 → 수정 후 발행

---

<details>
<summary><b>맞춤 공고 추천 — 추천 API 서버 연결 (내 컴퓨터)</b></summary>

이력서 편집 화면의 **AI 코치 → 맞춤 공고 추천**은 `job_matching_bot`의 추천 API
(`POST /api/v1/jobs/recommend`)를 부릅니다. 벡터 검색 → 하드 필터 → LLM 재정렬 → 근거 검증을
거친 공고를 이력서·공고 원문 인용과 함께 보여 줍니다. 서버에 닿지 못하면 추천하지 않고
연결 오류를 그대로 보여 줍니다(앱 안에서 태그만 보고 추측하던 규칙 기반 추천은 없앴습니다).

### 1. 서버 실행 (저장소 루트에서)

```powershell
playdata_venv\Scripts\activate
python -m uvicorn job_matching_bot.api.main:app --host 127.0.0.1 --port 8000
```

이력서 첨삭·학생 챗봇까지 한 번에 띄우려면 통합 진입점을 사용합니다(권장).

```powershell
python -m uvicorn app.integrated:app --app-dir cover_letter_rag --host 127.0.0.1 --port 8000
```

`http://127.0.0.1:8000/health` 가 `{"status":"ok", ...}` 를 주면 됩니다. 로컬 8000 서버는 Pinecone·OpenAI 키를
루트 `.env`에서 읽습니다. Cloud Functions는 `.env`가 아니라 Secret Manager(`OPENAI_API_KEY`, `PINECONE_API_KEY2`)를 읽으므로, 팀원 각자 로컬 `.env`를 채우는 것과 별개로 프로젝트에 Secret이 한 번 등록돼 있어야 합니다.

공부방(수업 노트 생성)도 이 통합 서버가 담당합니다. 관리자가 기수별 GitHub 주소를 등록하면
서버가 `git clone`으로 자료를 읽고 AI 노트를 만듭니다. GitHub 토큰은 공개 저장소에 필요 없습니다.
PC에 Git이 설치되어 있어야 하고, 노트를 **새로 만들 때** 이 서버가 켜져 있어야 합니다. 이미 만든
노트는 Firestore에 있어서 서버가 꺼져 있어도 볼 수 있습니다.

### 2. 앱 실행

앱의 기본 서버 주소가 `http://127.0.0.1:8000` 이라 별도 설정이 없습니다.

```powershell
flutter run -d windows                                  # 데스크톱: 그대로
flutter run -d chrome                                   # 웹: 포트가 매번 달라도 됩니다
```

- Chrome에서 "Failed to fetch"가 나오면 서버가 꺼져 있거나 루트 `.env`에 `CORS_ALLOW_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1)(:\d+)?` 가 없는 경우입니다. 이 값이 로컬호스트의 아무 포트나 허용하므로 `--web-port`를 고정하지 않아도 됩니다.
- 다른 주소를 쓰려면 `--dart-define=JOB_RECOMMEND_API_URL=http://호스트:포트`. 빈 값이면 추천 버튼이 안내 오류를 냅니다.
- 응답은 LLM 재정렬 때문에 평균 30초쯤 걸립니다. 화면의 진행 표시가 그동안 돕니다.
- 지금은 내 컴퓨터에서만 됩니다. 팀원 환경·실제 폰은 서버를 클라우드에 올린 뒤에 됩니다.

</details>

## 도움이 필요할 때

1. 이 문서의 [자주 겪는 문제](#자주-겪는-문제) 확인
2. 팀 Jira 이슈에 `S32-XX` 키로 질문 등록
3. Firebase Console 로그 확인: https://console.firebase.google.com/project/skn34-3rd-2team
