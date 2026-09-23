# 채용공고 일일 수집·저장 운영 계약

> 상태: 검증용 DB에서 스키마 migration과 운영 수집기 연결 확인.
> 운영 배포 및 일일 수집 전체 회귀는 아직 확인하지 않았다.
> 범위: 팀원의 매일 크롤링 작업과 Django/PostgreSQL 물리 설계의 책임 경계.

## 책임 분리

| 주체 | 소유하는 일 | 하지 않는 일 |
|---|---|---|
| Django migration | `jobs` schema의 테이블·view·제약·인덱스 생성/변경 | 매일 공고 수집 |
| 팀원 크롤러와 `job_matching_bot.sync` | 원본 수집, 정규화, PostgreSQL 공고 행 upsert, 수집 결과 기록 | 운영 시점의 `CREATE/ALTER/DROP` DDL |
| Pinecone 동기화 | 검색 벡터 생성·갱신·제거 | 공고 원본 보관 |
| Django API | PostgreSQL의 공고 조회 및 이력서 연결 | 크롤러 스키마 자동 수정 |

스키마 변경이 필요하면 팀원이 migration 변경을 PR로 제출하고 검증 DB에서
적용·호환성 검사를 거친 뒤 배포한다. **migration 배포가 먼저, 새 형식의
일일 수집 실행이 다음**이다. 크롤러가 매일 실행된다는 사실은 DB 스키마를
매일 재생성해야 한다는 뜻이 아니다. 기존 공고를 날리는 `DROP SCHEMA`는 금지한다.

## 하루 실행 흐름

1. 팀원 크롤러가 사이트별 원본 JSONL을 수집한다. 수집 실패와 정상 0건은
   구분하고, 실패한 소스의 공고를 일괄 `REMOVED`로 바꾸지 않는다.
2. `job_matching_bot.sync`가 유효성 검사·중복 제거·정규화 후 `jobs.jobs`에
   upsert한다. 공고의 안정 식별자는 `job_id`; 출처 안의 중복 방지는
   `(source, source_job_id)` UNIQUE를 사용한다. 같은 공고를 재수집해도 새 행을
   만들지 않는다.
3. 새 공고는 `first_seen_at`을 기록한다. 다시 본 공고는 `last_seen_at`을
   갱신하고 `missing_runs`를 0으로 되돌린다. `content_hash`가 달라진 경우에만
   `revisions`를 올린다.
4. 이번에 안 보인 공고는 즉시 삭제하지 않는다. 마감일 경과는 `EXPIRED`,
   출처의 명시적 마감은 `CLOSED`, 마감 전 연속 미관측은 `REMOVED`로 관리한다.
   현재 기본 미관측 기준은 2회(`DEFAULT_MISSING_RUN_LIMIT=2`)이며 정책 변경 시
   수집 코드·테스트·이 문서를 함께 바꾼다. `observed_ids`가 주어진 경우에는
   목록에서 살아 있음을 확인한 공고를 누락으로 세지 않는다.
5. PostgreSQL 저장이 성공한 뒤, `embed_hash`와 `indexed_embed_hash`가 다른
   공고만 Pinecone에 반영한다. 동기화가 실패하면 PostgreSQL 행은 보존하고
   다음 실행에서 재시도한다. Pinecone과 PostgreSQL의 불일치는 재색인으로 복구한다.
6. 실행 결과는 `jobs.runs`와 `artifacts/sync_report.json`의 신규·수정·유지·
   만료·누락·벡터 수·오류를 대조한다. 0건/대량 감소/오류는 운영자가 확인한다.

## 이력서·추천과의 관계

- `resumes.linked_job_id`는 현재 문자열로 보존한다. 공고가 `EXPIRED`, `CLOSED`,
  `REMOVED`가 되어도 기존 이력서와 공고 행을 삭제하지 않는다. 과거 맞춤
  이력서의 근거가 사라지면 안 되기 때문이다.
- 새 매칭/추천은 기본적으로 조회 시점에 유효한 공고를 대상으로 하고,
  과거 이력서 화면에서는 비활성 공고도 당시 연결로 조회할 수 있어야 한다.
- 장기적으로 FK로 바꿀 때는 `jobs.jobs(job_id)`와 모든 `linked_job_id`의
  대응을 먼저 검증한다. 직접 삭제 대신 상태 전이를 기본으로 하므로
  `ON DELETE SET NULL`에 일상 운영을 의존하지 않는다.

## 운영 전 확인

- `lms.0003_jobs_schema`가 검증용 RDS에 7개 테이블과 view를 생성했다.
  `job_matching_bot/ingestion/sqlite_store.py`는 운영 `jobs` schema를 DDL 없이
  확인하고 열며, 테스트 격리 schema만 기존 방식으로 생성한다.
- `scripts/firestore_to_postgres/apply_jobs_schema.py`는 DDL 대신 현재 schema를
  읽기 전용으로 검증한다.
- 운영 DB에는 아직 적용하지 않았다. 기존 데이터가 있는 경우 schema 호환성·
  백업을 먼저 확인한다. 팀원 크롤러의 실제 스케줄, 접속 DB, 전체 증분 수집 및
  Pinecone 연동 테스트는 배포 전 확인한다.

관련 구현: `scripts/firestore_to_postgres/jobs_schema.sql`,
`job_matching_bot/ingestion/sqlite_store.py`, `job_matching_bot/sync.py`,
`job_matching_bot/schemas/job_record.py`.
