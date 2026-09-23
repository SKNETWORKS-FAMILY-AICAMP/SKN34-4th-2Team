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
| 정책/FAQ 원본 | `lms.0004_policy_documents`, 적재 명령, 스테이징 projector | 검증 DB에 Markdown 1건 적재·중복 방지, 13개 chunk 미리보기 확인. Notion/PDF/S3/실제 Pinecone 쓰기는 미검증. |
| 삭제 정책 | Django `on_delete`와 PostgreSQL FK | 검증 DB의 FK 121개가 DB 수준 `NO ACTION`. ORM 정책을 SQL 직접 삭제 정책으로 오인하지 말 것. |
| 실제 공지 | 선별 importer로 검증 DB에 15건 시험 적재 | 작성자 snapshot 보존. 이미지 2건은 S3 객체 확인 전이며 운영 이전 미완료. |
| 3차 학생·출결·이력서 등 | 전체 ETL 시험 데이터 | 실제 운영 데이터가 아니므로 운영 초기 적재 대상 제외. |

검증 명령 결과: `manage.py check` 정상, `makemigrations --check --dry-run`
변경 없음, `migrate --plan` 미적용 작업 없음. 이 결과는 **스키마/설정 검사**이지
ETL, API, 파일, 검색, 인증의 종단 간 성공을 의미하지 않는다.

## Freeze 전 필수 게이트

1. `jobs` schema의 migration 편입과 운영 수집기 DDL 제거는 검증 DB에서 확인했다.
   기존 데이터가 있는 운영 DB 적용 전에는 schema 호환성 검사·백업이 필요하다.
   일일 크롤러와 Pinecone 증분 동기화 회귀 테스트도 남아 있다.
2. 정책/FAQ의 원본·revision 모델, 선택적 적재 및 스테이징 projection 명령은
   구현했다. Markdown 1건 외의 파일·Notion/PDF 경로와 실제 Pinecone 쓰기,
   전체 corpus 건수/검색 품질, S3 원본 key는 검증해야 한다.
3. 공지 이미지 2건의 실제 S3 객체와 key를 대조한다. 운영 공지 이전은 그 후 수행한다.
4. fresh 검증 DB에서 `migrate → 선별 ETL → FK/UNIQUE/건수/S3 검증`을 재현하고
   migration report의 실패 항목을 0으로 만든다.
5. LMS/채용/정책의 핵심 API 및 권한 테스트를 별도로 통과시킨다.

위 항목 완료 전에는 물리 설계 또는 운영 데이터 이전이 끝났다고 표시하지 않는다.
