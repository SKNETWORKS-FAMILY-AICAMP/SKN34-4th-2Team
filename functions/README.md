# Firebase Cloud Functions

LMS 앱이 **클라이언트에서 직접 하면 안 되는 일**을 서버에서 처리한다. 계정 발급, 마일리지 차감,
정답이 있는 평가 채점, 외부 API 키가 필요한 호출, 공지의 벡터 DB 동기화가 여기에 있다.

- 런타임: Node.js 20, TypeScript, `firebase-functions` v2
- 리전: `asia-northeast3`(서울)
- Firestore 규칙은 [config/firebase/](../config/firebase)에 있다. 마일리지·평가 정답·AI 로그처럼 클라이언트 쓰기를 막아 둔 문서는 여기 함수만 Admin SDK로 쓴다.

## 함수 목록

### 계정

| 함수 | 종류 | 설명 |
|---|---|---|
| `createStudentAccount` | callable · 관리자 | 상담 정보로 학생 계정 생성. 로그인 이메일·임시 비밀번호를 무작위로 만들고 `mustChangePassword`를 켠다 |
| `updateStudentAccount` | callable · 관리자 | 학생 상담 정보 수정 |
| `resetStudentPassword` | callable · 관리자 | 임시 비밀번호 재발급 |
| `setStudentActiveStatus` | callable · 관리자 | 퇴소·복학. 기수 학생 수를 함께 맞춘다 |
| `updatePersonalEmail` | callable · 본인 | 구글폼 응답과 학생을 잇는 개인 이메일 등록 |
| `createInstructorAccount` 외 3개 | callable · 관리자 | 강사 계정 생성·수정·비밀번호 재발급·활성 상태 |
| `createAdminAccount` | callable | 최초 셋업용 관리자 생성. `ADMIN_SETUP_KEY`가 맞아야 한다 |

### 공지

| 함수 | 종류 | 설명 |
|---|---|---|
| `syncDiscordNotices` | 스케줄 · 5분 | 디스코드 `#매니저-공지사항`, `#캠퍼스-질문주세요` 글을 기수 공지로 가져온다 |
| `syncDiscordNoticesNow` | callable | 위 동기화를 바로 실행 |
| `publishScheduledNotices` | 스케줄 · 1분 | 예약 공지(`scheduledNotices`) 중 시각이 된 것을 공지로 올린다 |
| `publishScheduledNoticesNow` | callable | 위를 바로 실행 |
| `syncNoticeVector` | Firestore 트리거 | `cohorts/{기수}/notices/{공지}`가 생성·수정·삭제되면 Pinecone `student/notice`에 반영한다. 학생 챗봇이 이 공지를 검색한다 ([상세](../vectordb/README.md#3-공지-notice--자동-동기화)) |

### 출결·설문

| 함수 | 종류 | 설명 |
|---|---|---|
| `googleFormWebhook` | HTTP | 구글폼 Apps Script가 제출을 보내면 설문 응답과 출결(출석 유형·공가 등)로 반영한다. `X-Webhook-Secret` 헤더로 확인하고, 개인 이메일 → 이름 순으로 학생을 찾는다 |

### 마일리지·미션

| 함수 | 종류 | 설명 |
|---|---|---|
| `submitPurchaseRequest` | callable · 학생 | 상품 구매 요청. 카테고리 한도 초과면 거부 |
| `reviewPurchaseRequest` | callable · 관리자 | 승인(잔액 즉시 차감)·반려·수정 요청. 잔액이 모자라면 승인 거부 |
| `cancelPurchaseRequest` | callable · 학생 | 요청 취소 |
| `adjustMileage` | callable · 관리자 | 수동 지급·차감. 트랜잭션으로 잔액과 거래 기록을 같이 쓴다 |
| `reviewSubmission` | callable · 관리자 | 기록실 제출물 승인·반려. 승인하면 미션 규칙(`missions.ts`)에 따라 마일리지를 한 번만 적립한다 |
| `expireMileage` | 스케줄 · 매일 03:00 KST | 종강 14일 뒤 잔액 소멸 |
| `expireMileageNow` | callable · 관리자 | 소멸 배치를 날짜를 지정해 시험 실행 |

### 성취도평가

| 함수 | 종류 | 설명 |
|---|---|---|
| `generateAssessmentQuestions` | callable · 강사·관리자 | 업로드된 커리큘럼 CSV의 일수 구간으로 객관식·단답 초안을 만든다. 마음에 안 드는 문항만 다시 만들 수도 있다 |
| `getAssessmentForTake` | callable · 기수 구성원 | 응시 화면용 문항. **정답을 빼고** 보내며, 학생에게는 공개 여부와 응시 기간을 확인한다 |
| `submitAssessment` | callable · 학생 | 제출과 채점. 단답은 공백·대소문자를 정리한 뒤 허용 답안과 비교한다 |
| `getAssessmentReview` | callable | 결과·해설 조회 |
| `adjustAssessmentScores` | callable · 강사·관리자 | 점수 수동 조정 |
| `recordAiQuestionFeedback` | callable · 강사·관리자 | AI 초안 문항을 채택·수정·폐기했는지 기록 |

AI 출제 프롬프트는 `ai/assessmentPrompt.ts`에 있다. 커리큘럼 행의 교과목·내용 밖에서는 출제하지
않도록 범위를 제한하고, 각 문항에 근거 일수(`sourceDay`)와 주제(`sourceTopic`)를 붙이게 한다.
모델은 `gpt-4o-mini`, 프롬프트 버전은 `ASSESSMENT_PROMPT_VERSION`(기본 `assess_q_v2`)이다.

### LLMOps·외부 데이터

| 함수 | 종류 | 설명 |
|---|---|---|
| `recordAiGenerationLog` | callable | 공고 챗봇·추천·첨삭·출제의 생성 로그(모델·프롬프트 버전·지연 등 메타만). 이력서·대화·공고 원문은 받지 않는다 |
| `recordAiOutcomeFeedback` | callable | 생성 결과를 사용자가 어떻게 썼는지 기록(추천 공고 열기·첨삭으로 넘기기, 수정안 적용·일부 적용·되돌리기 등). 관리자 **AI 품질** 화면이 로그·지연과 함께 읽는다 |
| `getQualExamSchedules` | callable | 공공데이터포털 국가자격 시험일정. 연결이 안 되면 Firestore 캐시를 쓴다 |
| `getCurriculumYoutubeRecommendations` | callable | 커리큘럼 주제로 YouTube Data API를 검색해 공부방 추천 영상을 만든다. 결과는 `youtubeCurriculumCache`에 캐시 |

## 설정

값은 레포 루트 `.env` 한 곳에만 넣고, 배포 전에 `functions/.env`로 복사한다.
`functions/.env`를 직접 고치지 않는다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\sync-functions-env.ps1
```

| 이름 | 방식 | 쓰는 곳 |
|---|---|---|
| `OPENAI_API_KEY` | `.env` + Secret | 성취도평가 출제(`.env`), 공지 임베딩(Secret) |
| `PINECONE_API_KEY2` | Secret | 공지 벡터 동기화 |
| `DISCORD_BOT_TOKEN` | Secret | 디스코드 공지 |
| `GOOGLE_FORM_WEBHOOK_SECRET` | Secret | 구글폼 웹훅 |
| `DISCORD_COHORT_ID` | `.env` | 디스코드 공지를 넣을 기수 |
| `DATA_GO_KR_SERVICE_KEY` | `.env` | 자격시험 일정 |
| `YOUTUBE_API_KEY` | `.env` | 공부방 추천 영상 |
| `ASSESSMENT_PROMPT_VERSION` | `.env` | 출제 프롬프트 버전 기록 |
| `ADMIN_SETUP_KEY` | `.env` | 최초 관리자 생성 |

Secret 등록:

```powershell
firebase functions:secrets:set OPENAI_API_KEY
firebase functions:secrets:set PINECONE_API_KEY2
firebase functions:secrets:set DISCORD_BOT_TOKEN
firebase functions:secrets:set GOOGLE_FORM_WEBHOOK_SECRET
```

## 빌드·배포

Blaze 요금제가 필요하다.

```powershell
cd functions
npm install
npm run build                        # tsc → lib/
npm run serve                        # 에뮬레이터
cd ..
firebase deploy --only functions     # 전체
firebase deploy --only functions:syncNoticeVector    # 하나만
```

평가 관련만 배포할 때는 `npm run deploy:assessments`. 규칙·인덱스는
`firebase deploy --only firestore:rules,firestore:indexes,storage`로 따로 배포한다.

## 파일

| 파일 | 내용 |
|---|---|
| `src/index.ts` | 학생·관리자 계정, 마일리지 수동 조정, 제출물 승인. 나머지 모듈을 다시 내보낸다 |
| `src/firebase.ts` | Admin SDK 지연 초기화(배포 시 탐색 시간 초과 방지) |
| `src/instructors.ts` | 강사 계정 |
| `src/discord.ts`, `src/scheduledNotices.ts`, `src/noticeVectors.ts` | 공지 |
| `src/googleForm.ts`, `src/attendanceForm.ts` | 구글폼 웹훅, 출결 반영 |
| `src/mileage.ts`, `src/missions.ts` | 마일리지 구매·소멸, 미션 적립 규칙 |
| `src/assessments.ts`, `src/ai/assessmentPrompt.ts` | 성취도평가 |
| `src/aiOps.ts` | LLMOps 로그 |
| `src/qualExamSchd.ts`, `src/youtubeRecommendations.ts` | 외부 공공·YouTube API |

## 알려진 한계

- 자동 테스트가 없다.
- 디스코드 공지 동기화는 한 기수(`DISCORD_COHORT_ID`)만 대상으로 한다.
