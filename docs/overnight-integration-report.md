# RDS 통합 검증 기록 — 2026-09-24

기준 브랜치: `feature/postgresql-integration`. 기준 DB: AWS RDS
`lms_migration_replay_20260923` (`current_user=project_admin`). DB 변경 전에
`SELECT current_database(), current_user`를 확인했다. `postgres` DB, 새 DB,
ETL 재실행, 초기화 및 AWS 인프라 변경은 하지 않았다.

`VERIFIED`는 실제 요청/연결이 성공한 범위에만 사용한다. Django 테스트나
React 데모 모드 테스트만 통과한 항목은 사용자 E2E가 아니다. 아래의
`CODE EXISTS / NOT VERIFIED`는 기능이 끝났다는 뜻이 아니다.

| # | 기능 | 상태 | 확인한 범위 / 남은 일 |
|---|---|---|---|
| 1 | 로그인 / JWT / 권한 | PARTIAL | 실제 RDS 임시 관리자 계정으로 브라우저 로그인 200, 인증된 bootstrap 200. 일반 학생·강사 및 세부 권한 E2E 미검증. |
| 2 | React bootstrap | VERIFIED | 실제 브라우저 `/api/bootstrap` 200, `/admin` 대시보드 표시. 응답은 기준 RDS의 공지 15건을 포함. |
| 3 | 공지 조회 | PARTIAL | 인증된 Django bootstrap에서 실제 공지 15건 조회. React 공지 목록의 개별 E2E는 별도 미검증. |
| 4 | 공지 생성/수정/삭제 | VERIFIED | 실제 RDS에서 Django API 생성·수정·조회·삭제 200 검증. 임시 행 정리. React 조작은 미검증. |
| 5 | 예약 공지 | VERIFIED | Django API 예약 생성·발행, 재발행 방지, 다른 기수 강사 차단 및 RDS/Pinecone 검증. React 버튼은 미검증. 자세한 내용은 `docs/validation/scheduled-notices-20260924.md`. |
| 6 | 공지 → Pinecone | VERIFIED | 실제 임시 공지 DB commit→벡터 upsert→수정→delete 확인. 임시 벡터 정리. |
| 7 | 공지 이미지/파일 → S3 | PARTIAL | 공지 이미지 key 2개 모두 S3 `HeadObject` 200. 기존 key로 생성한 서명 GET URL에서 `Range: bytes=0-0` 요청 206, `image/png` 확인. 업로드→key 저장→React 표시 E2E는 미검증. |
| 8 | 출결 | PARTIAL | 실제 RDS 임시 관리자·학생으로 같은 학생/날짜 출결을 두 번 저장했을 때 두 번째가 고유 제약으로 500인 것을 재현. 일일 출결 INSERT를 `(user_id, attendance_date)` 충돌 시 UPDATE하도록 최소 수정 후 `[200, 200]`, 한 행·최종 상태 `late`, bootstrap 재조회 확인. 임시 행 롤백. React 관리자 화면 조작과 교시별 착석(`seat_presences`)은 미검증. |
| 9 | TODO 및 기본 학생 기능 | PARTIAL | 임시 학생으로 실제 RDS 로그인→Django `addTodo`→bootstrap 재조회→`toggleTodo`→`deleteTodo` 모두 200. 트랜잭션 롤백 후 잔여 0건. React에는 TODO 함수만 있고 이를 호출하는 화면은 없어 TODO 화면 E2E는 불가. 별도 학생 브라우저 로그인·대시보드 표시 성공. |
| 10 | 과제 / 제출 | CODE EXISTS / NOT VERIFIED | `submission_tasks`, `submission_responses` 테이블은 존재하나 0건. 제출 E2E 미검증. |
| 11 | 프로젝트 관련 | CODE EXISTS / NOT VERIFIED | `project_teams`, `project_team_members` 테이블 존재. 실제 팀 작업 E2E 미검증. |
| 12 | 커리큘럼 / 학습자료 | CODE EXISTS / NOT VERIFIED | `curriculum_sheets/rows/pdfs` 테이블 존재. S3 자료 포함 E2E 미검증. |
| 13 | 공부방 source | PARTIAL | React→Django proxy→AI 경로 코드 및 RDS `study_sources` 테이블 존재(0건). 실제 수업자료 E2E 미검증. |
| 14 | 공부방 AI note | PARTIAL | React·Django proxy·AI PostgreSQL 서비스 코드와 RDS `study_notes` 테이블 존재(0건). 실제 생성/재조회 미검증. |
| 15 | 학생 챗봇 | PARTIAL | Django `/api/chat` proxy 및 AI 서비스 코드. 실제 학생 대화의 React→AI→RDS/S3/Pinecone E2E 미검증. 직접 AI `/init`·`/stream`의 Firebase ID token 경로 잔존. |
| 16 | 이력서 조회/저장 | PARTIAL | 임시 학생으로 Django API 생성·수정→RDS 행·bootstrap 재조회 성공. React가 생성 시 임시 ID 대신 서버 ID를 기다리도록 수정한 뒤 실제 브라우저 생성 200, 편집 화면 조회 성공. 편집 제목과 저장의 비동기 경합을 수정한 뒤 브라우저에서 제목 유지·`저장됨` 표시 및 RDS 제목·수정 횟수 재조회 성공. 테스트 계정·이력서 삭제 후 잔여 0건. 다른 섹션·AI 첨삭은 별도 검증 필요. |
| 17 | AI 이력서 첨삭 | PARTIAL | PostgreSQL 중심 AI 코드 존재. 실제 첨삭 E2E 미검증; 실행 경로의 Firebase 인증/Firestore helper 구분 필요. |
| 18 | 맞춤 이력서 | CODE EXISTS / NOT VERIFIED | DB·화면 코드가 있으나 공고 연결·저장·재조회 E2E 미검증. |
| 19 | 첨삭 적용/undo | CODE EXISTS / NOT VERIFIED | 기존 로직 유지. 실제 적용/되돌리기 E2E 미검증. |
| 20 | 채용공고 PostgreSQL 저장 | PARTIAL | 기준 DB에 `jobs.jobs`를 포함한 `jobs` 스키마 테이블 8개가 있음. `jobs.jobs`·`jobs.runs`는 현재 0건. 스키마 존재만 확인했으며 크롤러 저장·React 조회·추천 E2E는 미검증. |
| 21 | 채용공고 수집 | PARTIAL | 수집 코드 존재. 전체 크롤링은 비용/시간 및 담당자 검토 때문에 실행하지 않음. 공유 파일 라우팅 변경은 미커밋 초안으로 유지. |
| 22 | 채용 추천 | CODE EXISTS / NOT VERIFIED | React `JobRecommendationRun`은 현재 실제 API 대신 고정된 가상 공고 3건을 표시한다. AI `/api/v1/jobs/recommend`는 별도 존재하지만 React→Django 라우트가 없고 기준 DB `jobs.jobs`는 0건. 실제 추천 E2E 미검증이며 현재 화면 결과를 서비스 추천으로 취급하면 안 된다. |
| 23 | 정책/공지/프로젝트 RAG | PARTIAL | Pinecone `smoke_search('cohort_34')` 실제 3개 결과 확인; 공지 projection은 별도 검증. 정책·프로젝트 전체 답변 E2E 미검증. |
| 24 | 연습/복습 문제 | CODE EXISTS / NOT VERIFIED | `practice_*` Django 테이블 존재. 생성→풀이→신고·검토 E2E 미검증. |
| 25 | React 화면과 Django API 실제 연결 | PARTIAL | 실제 Chrome에서 관리자 및 임시 학생 각각 React 로그인→Django API 200→RDS bootstrap 200→역할별 대시보드 표시. 전체 화면 계약은 미검증. |

## 이번 실행에서 완료한 범위

- `feature/test`의 동작을 덮어쓰지 않고 예약 공지 라우트 충돌과 재발행만
  최소 수정했다. 커밋 `e6a877a` (`fix: prevent duplicate scheduled notice publishing`).
- Django 테스트 26개, React/Vitest 테스트 53개, TypeScript 검사 및 Vite 빌드 통과.
  React 테스트는 데모 데이터 기반이므로 실제 RDS E2E로 세지 않는다.
- 브라우저 검증은 임시 관리자 계정 한 개로 수행했다. 로그인/부트스트랩 모두
  200이고 관리자 대시보드가 렌더링됐다. 테스트 계정은 정확한 ID·UID·email로
  삭제한 뒤 잔여 0건 확인. 기준 DB에서 조회한 `users`는 0건, `notices`는 15건.
- 후속 검증에서 임시 학생의 React 로그인/대시보드와 Django TODO 추가·조회·완료·삭제를
  확인했다. 출결 중복 INSERT의 실제 500 오류를 고친 뒤 같은 날짜 재저장이 한 행에
  반영되는 것을 확인했다. 테스트 사용자·TODO·출결은 모두 정리 또는 롤백했다.
- S3는 기존 공지 이미지 2개 `HeadObject` 200 및 서명 GET URL의 실제 읽기 206을
  확인했다. 파일 쓰기/삭제는 하지 않았다. 현재 Django에는 서명 읽기 URL 생성은
  있으나, React 공지 폼에서 S3로 이미지를 업로드하는 경로는 없다.
- 이력서 생성에서 React의 임시 ID와 Django가 발급한 실제 ID가 달랐다. 생성
  요청을 기다려 실제 ID로 이동하도록 최소 수정했다. 실제 RDS 생성과 브라우저
  편집 화면 재조회 확인 후 임시 학생·이력서를 정확한 ID로 삭제했다. React
  TypeScript 검사 및 Vitest 53개 통과.
- 이력서 편집에서는 제목 변경과 저장 요청이 동시에 보내져 화면 제목이 이전
  값으로 돌아가면서 저장 완료를 조기 표시했다. 이력서별 쓰기 순서를 보장하고
  저장 API 응답 뒤에만 완료를 표시하도록 수정했다. 실제 브라우저와 RDS에서
  제목·수정 횟수를 확인했고 임시 데이터는 삭제했다.
- AI 통합 서버는 전용 `.venv-ai`에서 실행해 `/health` 200을 확인했다. 같은
  AI 환경의 PostgreSQL 드라이버로 기준 RDS의 `current_database()`와
  `jobs.jobs` 0건도 읽기 전용으로 확인했다. 헬스·DB 연결만으로 챗봇이나
  채용 추천의 실제 응답을 검증했다고 보지 않는다. 서버는 확인 후 종료했다.
- FastAPI AI 개별 생성·첨삭·추천 요청은 이번 범위에서 실제 성공 확인이 없다.
  이전의 proxy 단위 테스트와 실제 AI E2E를 혼동하지 않는다.

## 계속 확인할 사항

1. 기준 DB에 실제 사용자·학생·학습자료가 없어 역할별 화면과 AI 콘텐츠의
   사용자 E2E는 합성 데이터 또는 실제 데이터 준비 뒤 확인해야 한다.
2. 채용공고 저장소는 별도 `jobs` 스키마에 있으며 기준 DB의 `jobs.jobs`는 0건이다.
   크롤러 적재 경로와 공유 파일 소비자는 크롤링 담당자가 확인해야 한다. 기존
   수집 코드는 되돌리지 않았다.
   React 추천 패널은 고정된 가상 공고 3건을 반환하므로 실서비스 노출 전
   Django proxy→기존 FastAPI 추천 API 연결 및 실공고 적재 검증이 필요하다.
3. 학생 챗봇 직접 AI 경로의 Firebase ID token, 이력서 AI의 실제 실행 경로에
   남은 Firebase Auth/Firestore helper를 구별해 최소 교체해야 한다.
   `users.firebase_uid`는 legacy identifier이므로 제거 대상이 아니다.
4. S3 업로드/다운로드, 공부방 AI 생성, 이력서 첨삭, 채용 추천은 실제 데이터와
   호출 비용을 관리하며 기능별로 한 번씩 E2E 검증해야 한다.

이 보고서는 완료 선언이 아니다. 미검증 기능을 코드 존재만으로 `VERIFIED`로
올리지 않는다. DB 승격·이름 변경·운영 배포는 별도 결정 사항이다.
