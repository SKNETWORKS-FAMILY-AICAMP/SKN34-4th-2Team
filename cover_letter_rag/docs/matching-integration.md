# 매칭 봇 ↔ 이력서 첨삭 통합

## 구현 범위

추천 API와 기존 응답 스키마를 유지하고, 추천 카드에서 공고를 선택해 첨삭을 실행한다. 저장된 이력서와 화면 초안이 다르면 실행하지 않는다. 수정안은 사용자가 체크한 항목만 저장하며, 적용 후 서버 원문을 다시 읽어 화면에 반영한다. 같은 창에서 적용 되돌리기도 제공한다.

흐름: 추천 → 공고 맞춤 첨삭 → Firebase 본인 확인 → 이력서/공고 버전 확인 → 공고 원문 전체로 첨삭 → 선택 적용 → 원문 재조회 → 필요 시 되돌리기.

확인 질문은 현재 화면에 표시하며, 답변 입력 및 재첨삭 UI는 아직 연결하지 않았다. 기존 재첨삭 백엔드 API는 유지한다. 일반 공고 검색 카드가 아니라 서버 추천 카드에만 첨삭 버튼이 있다.

## 서버 실행

저장소 루트에서:

```powershell
.\scripts\start-backend.ps1
```

이 스크립트는 Firebase Storage의 팀 공유 공고 DB가 갱신된 경우에만 임시 다운로드,
SQLite 무결성·필수 컬럼 검증, 원자 교체를 마친 뒤 8000번 통합 서버를 실행한다.
공유본 확인을 생략해야 할 때만 `-SkipJobStoreSync`를 사용한다.

- 추천 문서: `http://127.0.0.1:8000/docs`
- 첨삭 문서: `http://127.0.0.1:8000/resume-review/docs`
- 추천: `POST /api/v1/jobs/recommend` (팀원 API 유지)
- 첨삭 문맥: `GET /resume-review/api/v1/resumes/review-context`
- 첨삭: `POST /resume-review/api/v1/resumes/reviews`
- 적용/복원: 위 첨삭 경로 뒤에 `/apply`, `/undo`
- 학생 챗봇: `POST /api/v1/student-chatbot/init`, `POST /api/v1/student-chatbot/stream` (`chatbot/api.py`)
- 공부방 노트: `POST /api/v1/study-notes/tree`, `/generate`, `/get` (`study_notes/api.py`). GitHub REST API가 아니라 `git clone`으로 관리자가 등록한 공개 저장소를 읽는다. 서버 PC에 Git이 설치되어 있어야 한다.

두 모듈의 기존 `/api/v1/jobs/recommend`는 서로 다른 스키마이므로 그대로 한 라우터에 합치지 않는다. 통합 진입점만 별도로 두어 기존 단독 실행 방식도 유지한다.

Flutter 기본 추천 주소는 `http://127.0.0.1:8000`, 첨삭 기본 주소는 추천 주소 뒤에 `/resume-review`를 붙인다. 별도 서버라면 `--dart-define=RESUME_REVIEW_API_URL=http://127.0.0.1:8001`로 지정한다. 학생 챗봇 기본 주소도 추천 주소와 같으며, 챗봇만 따로 띄웠다면 `--dart-define=STUDENT_CHATBOT_API_URL=...`로 바꾼다. URL만 설정하고 키는 Flutter에 넣지 않는다.

## 필요한 로컬 설정/데이터

- 매칭과 첨삭은 모두 저장소 루트 `.env`를 읽는다. Firebase Functions 배포에 필요한 `functions/.env`는 `scripts/sync-functions-env.ps1`가 루트 파일에서 생성하므로 직접 수정하지 않는다.
- Firebase 프로젝트 ID와 서버용 Application Default Credentials, 실제 Firebase 로그인이 필요하다.
- `MATCHING_JOB_STORE_PATH`에는 팀원이 만든 **공고 원문 SQLite**의 절대 경로를 지정한다. 생략 시 `job_matching_bot/artifacts/job_store.sqlite`.
- Pinecone의 요건 발췌(최대 1,200자)를 원문으로 대체하지 않는다. SQLite가 없으면 503, 공고가 없거나 본문이 비었으면 422, 마감됐거나 버전이 바뀌었으면 409다.
- SQLite WAL 모드의 실행 중 DB 파일만 복사하지 말고 팀원에게 SQLite backup 방식의 일관된 스냅샷을 요청한다.
- 로컬 CORS는 루트 `.env`의 `CORS_ALLOW_ORIGINS` 또는 `CORS_ALLOW_ORIGIN_REGEX`로 허용한다. 운영에서는 실제 프론트엔드 출처만 허용한다.
- Pinecone 의존성 범위를 두 백엔드 모두 `>=9,<11`로 통일했다. 오프라인 회귀 테스트는 설치된 10.0.0에서 실행했다. 실제 Pinecone 통신은 별도 검증 대상이다.

## 보호 장치

- 공고 원문은 클라이언트가 보내지 않고 서버가 `job_id`로 읽는다. SQLite는 읽기 전용 연결과 파라미터 쿼리를 사용한다.
- 이력서 원문은 Firebase 인증 후 소유권/기수를 확인하고 서버가 조회한다. 문맥 응답은 `Cache-Control: no-store`.
- 추천 중 초안이 바뀌면 이전 추천 결과를 버린다. 첨삭 요청에는 서버 이력서 해시와 공고 스냅샷 해시를 넣어 조회 이후 변경도 확인한다.
- 적용·복원은 기존 Firestore 트랜잭션과 버전 검증을 그대로 사용한다. 응답이 불확실하면 같은 요청 ID를 재사용한다.
- 이력서 내용이나 API 키는 진단 로그에 출력하지 않는다.

## 검증 구분과 남은 사항

Python 테스트는 임시 SQLite·가짜 Firebase·가짜 LLM으로 실행한다. Flutter 테스트는 가짜 HTTP와 위젯으로 추천 요청, 초안 비교, 선택 적용 및 복원을 검증한다. 실제 Firebase/OpenAI/Pinecone 통합 성공을 의미하지 않는다.

실제 실행에는 원문 DB 제공이 필요하다. 이후 테스트 계정의 이력서로 추천→첨삭→선택 저장→복원까지 검증해야 한다. 원문 적용은 실제 쓰기이므로 사용자와 대상 이력서를 확인하고 진행한다.

팀원의 추천 API 자체에는 Firebase 인증 검증이 아직 없으므로 통합 서버를 그대로 공개 배포하지 않는다. 본인 인증 보호는 이번에 연결한 첨삭 경로에 적용된다. 또한 새로고침/창 강제 종료를 넘는 요청 ID 복구 UI는 아직 없으며, 응답 불명확 시에는 서버 aiReviews/aiApplications 상태를 확인해야 한다.
