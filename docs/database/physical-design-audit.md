# 물리 설계 대조 기록 (2026-09-23)

기준: `requirements.md`, `db-decisions.md`, `schema-draft.md`, `erd.md`,
`migration-plan.md`, `system-architecture.md`. 검증 대상은
`feature/postgresql-integration`의 Django 모델/마이그레이션과
`lms_migration_validation_20260923` 검증용 RDS DB이다. 운영 DB를 검증하거나
변경한 결과로 해석하지 않는다.

| 영역 | 현재 물리 구현 | 판정 / 후속 조치 |
|---|---|---|
| LMS/이력서/Practice | managed models, `lms.0001_initial` | 기본 테이블 생성 확인. 전체 업무 규칙/API 검증은 미완료. |
| Legacy assignments/weekly | unmanaged models 4개, migration이 테이블을 만들지 않음 | 초기 통합 제외와 일치. 신규 API에서 참조하지 않도록 유지. |
| 필수 복합 인덱스 | `lms.0002_physical_indexes` 추가 | 검증 DB에 6개 적용 확인. |
| 핵심 제약 | 출결/제출/복습/이력서 CHECK·UNIQUE | 검증 DB에서 지정 제약 10개 확인. 기본 이력서 단일성은 일반 constraint 행이 아닌 `WHERE is_base_resume` 부분 UNIQUE 인덱스로 확인. |
| 채용공고 원본 | `lms.0003_jobs_schema` migration | 검증 DB에 7개 테이블·view 생성, 운영 schema의 수집기 연결 확인. 실제 일일 수집·Pinecone 전체 회귀는 미검증. |
| 정책/FAQ 원본 | `lms.0004_policy_documents`, 적재 명령, 스테이징 projector | 검증 DB에 로컬 Markdown·CSV 7건 적재, 재실행 시 7건 모두 unchanged. 56개 chunk 미리보기 확인. Notion/PDF/S3/실제 Pinecone 쓰기는 미검증. |
| 삭제 정책 | Django `on_delete`와 PostgreSQL FK | 검증 DB의 public FK 122개가 DB 수준 `NO ACTION`. ORM 정책을 SQL 직접 삭제 정책으로 오인하지 말 것. |
| 실제 공지 | 선별 importer로 검증 DB에 15건 시험 적재 | 작성자 snapshot 보존. 이미지 2건을 Firebase Storage에서 S3로 선별 복사하고 검증 DB의 key로 HEAD/크기 대조 완료. 운영 DB 이전은 미완료. |
| 3차 학생·출결·이력서 등 | 전체 ETL 시험 데이터 | 실제 운영 데이터가 아니므로 운영 초기 적재 대상 제외. |

## 정책 검증 진행 (2026-09-23)

실제 RDS 카탈로그 재대조: 검증 DB는 `public` base table 73개, `jobs` base table
7개이며 `lms.0001`~`0004`가 적용돼 있다. TO-BE 핵심 테이블 15개 모두 존재하고,
Django managed model 63개의 테이블·컬럼과 실제 `public` 스키마를 대조한 결과
누락 테이블 0, 누락 컬럼 0, 여분 컬럼 0이다. `resumes`의 `base_resume_id`,
`linked_job_id`, `content` JSONB와 `cohort_seating.layout` JSONB도 확인했다.
출결·평가응시·기록파일·기본 이력서·사용자 기술·정책 revision의 UNIQUE/CHECK/FK
제약 및 관련 인덱스도 카탈로그에서 확인했다. 이는 구조 일치 검사이며, 업무 흐름
전체의 통과를 뜻하지 않는다.

- 로컬 Markdown·CSV 7개와 검증 DB 문서 7개·revision 7개를 대조했고 현재 본문 hash가 7개 모두 일치한다.
- `policy_postgres` 미리보기는 56 chunk, Pinecone 차원 1536과 일치한다.
- Pinecone 읽기 전용 확인 결과 기존 `policy` namespace는 109 vectors,
  `policy_postgres`는 0 vectors다. 외부 스테이징 적재는 아직 실행하지 않았다.
- 남은 원본은 PDF 1개와 설정된 Notion URL 5개다. 이 환경에는 Notion token이 없고,
  PDF AI 추출용 LangChain 의존성도 없다.
- S3 버킷 접근을 확인했다. 검증 DB의 공지 이미지 key 2건은 처음에는 S3에 없었으나,
  Firebase Storage 원본(97,446/95,892 bytes)을 같은 key로 선별 복사하고 S3 HEAD의
  ContentLength가 각각 일치함을 확인했다. 전체 Storage 이전이나 운영 DB 변경은 하지 않았다.
- 외부 Pinecone 쓰기는 정책 원문·임베딩의 외부 전송이므로 별도 명시적 승인이
  확인될 때만 실행한다. 기존 `policy` 읽기 경로는 전환하지 않는다.

검증 명령 결과: `manage.py check` 정상, `makemigrations --check --dry-run`
변경 없음, `migrate --plan` 미적용 작업 없음. 이 결과는 **스키마/설정 검사**이지
ETL, API, 파일, 검색, 인증의 종단 간 성공을 의미하지 않는다.

S3 선별 복사 후 재확인: 검증 DB 공지 15건, 이미지 참조 2건, 고아 cohort 0건,
중복 legacy ID 0건, 정책 문서/리비전 각 7건. `manage.py check`는 0 issues,
`migrate --plan`은 미적용 작업 0건이다. 로컬 `.env`의 빈 `DJANGO_SECRET_KEY`는
검사 프로세스에서만 임시값을 사용했으며, 배포 전에는 실제 비밀값 설정이 필요하다.

이후 로컬 `.env`에 비밀키가 설정됐음을 값 노출 없이 확인했다. 공지 bootstrap은
`image_storage_key`를 DB에 유지하면서 인증된 요청에만 만료 1시간의 S3 읽기 URL을
`imageUrl`로 제공하고 React 공지 상세가 이를 표시하도록 연결했다. Django check,
서명 URL 단위 검사, React TypeScript/Vite 빌드는 통과했다. 로그인한 실제 화면에서의
이미지 로딩과 운영 IAM role 구성은 아직 종단 간 검증 전이다.
검증 DB의 두 key로 발급한 서명 URL을 통해 S3 GET을 수행했고 각각
97,446/95,892 bytes를 읽어 실제 객체 접근까지 확인했다. 브라우저 UI의 인증된
bootstrap 경로는 별도 확인이 필요하다.

임시 학생·관리자 계정을 검증 DB 트랜잭션 안에서 생성해 API를 검사했다.
익명 bootstrap은 401, 잘못된 비밀번호 로그인은 400, 두 역할의 정상 로그인·
`/api/me`·`/api/bootstrap`은 200이며 공지 15건과 서명 이미지 URL 2건을
응답했다. 학생의 공지 생성은 403이다. 시험 계정은 롤백했고 잔여 0건을 확인했다.
이 과정에서 psycopg가 `cohort_seating.layout` JSONB를 문자열로 반환해
bootstrap이 500을 내는 문제를 수정했다. 브라우저 화면 및 관리자 쓰기 권한은
아직 별도 검증이 필요하다.

관리자 쓰기 API 재검증: 공지 생성·수정·삭제, 예약 공지 생성·수정, 팝업 생성·수정이
검증 DB 트랜잭션에서 통과했고 테스트 행은 롤백했다. 공지 생성의 필수
`vector_chunk_count` 누락과 공통 Django Ninja `LooseBody`가 임의 JSON 필드를
버리던 문제를 수정했다. 일반/명령/예약 공지 INSERT에 필요한 숫자 초기값을
명시했고, JSON body가 OpenAPI의 requestBody로 잡히는 계약 테스트 2개도
통과했다. Pinecone 발행은 공지 CRUD 테스트에서 모의 처리했으며 실제 검색
반영·브라우저 UI·예약 발행 실행은 아직 검증 전이다.

이력서 권한 반례에서 학생 A가 학생 B의 이력서를 수정할 수 있음을 재현했고,
검증 DB의 임시 행을 롤백했다. `upsert`의 이력서 경로에 소유자 검사와
기본 이력서 동일 소유자·기본 여부, 채용공고 stable ID 존재성 검사를 추가했다.
재시험에서 타인 수정/삭제·타인 기본 이력서 연결·없는 공고 연결은 차단되고,
자기 기본 이력서에 연결한 맞춤 이력서 생성은 통과했다. 추가한 단위 계약 테스트
6건과 Django check도 통과했다. 범용 `upsert`의 다른 테이블 권한은 별도
감사가 필요하며, 운영 DB에 적용하지 않았다.

범용 `upsert`의 관리성 테이블에는 최소 역할 제한을 추가했다. 기수 변경은
관리자만, 평가·교재·좌석·마일리지 상품 등 관리성 데이터 변경은 관리자/강사만
가능하도록 막았다. 학생의 기수·상품·평가·좌석 변경과 강사의 기수 변경 거부를
단위 테스트로 확인했다. 학생 개인 기록 테이블의 소유권·기수 범위는 아직
테이블별 보안 감사를 마치지 않았으므로 이 제한만으로 전체 API 권한 검증이
완료됐다고 보지 않는다.

학생 bootstrap에서 같은 기수의 다른 학생 이력서·첨삭·기록실 제출물이
노출될 수 있고 `users` 전체 행에 비밀번호 해시가 실리던 문제를 확인했다.
학생 개인 데이터 조회를 본인 행으로 제한하고, 사용자 응답에서는 모든 역할의
비밀번호를 제거했다. 학생에게 보이는 동료 프로필도 공개 필드만 남겼다.
임시 학생 A/B·강사 계정 테스트에서 A에게 B의 이력서/첨삭/기록이 보이지 않고
강사에게는 기수 자료가 보임을 확인했다. 테스트 행은 롤백했다.

기록실 제출물 쓰기는 학생 본인·해당 기수로 제한하고 학생의 승인 상태 및
검토자 필드 위조를 차단했다. 검증 DB에서 타인 수정·승인 위조 거부와 본인
제출 성공을 확인했다. psycopg raw cursor의 JSONB 문자열 반환도 bootstrap에서
객체로 변환해 이력서 `content`가 React 기대 타입인 객체로 도착함을 확인했다.
단위 테스트 12건과 Django check가 통과했다.

## Freeze 전 필수 게이트

1. `jobs` schema의 migration 편입과 운영 수집기 DDL 제거는 검증 DB에서 확인했다.
   기존 데이터가 있는 운영 DB 적용 전에는 schema 호환성 검사·백업이 필요하다.
   일일 크롤러와 Pinecone 증분 동기화 회귀 테스트도 남아 있다.
2. 정책/FAQ의 원본·revision 모델, 선택적 적재 및 스테이징 projection 명령은
   구현했다. 로컬 Markdown·CSV 7건은 검증했으나 Notion/PDF 경로와 실제
   Pinecone 쓰기, 전체 corpus 건수/검색 품질, S3 원본 key는 검증해야 한다.
3. 공지 이미지 2건의 S3 key·크기 대조는 검증 DB 기준 완료했다. 운영 DB 공지 이전 시
   같은 key 정책과 화면의 이미지 접근 방식을 다시 확인한다.
4. fresh 검증 DB에서 `migrate → 선별 ETL → FK/UNIQUE/건수/S3 검증`을 재현하고
   migration report의 실패 항목을 0으로 만든다.
5. LMS/채용/정책의 핵심 API 및 권한 테스트를 별도로 통과시킨다.

위 항목 완료 전에는 물리 설계 또는 운영 데이터 이전이 끝났다고 표시하지 않는다.
