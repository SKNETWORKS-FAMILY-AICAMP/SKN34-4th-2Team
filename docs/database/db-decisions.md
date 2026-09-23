# DB Decision Log

> DEC-001 ~ DEC-039: 기존 결정 유지.

## DEC-040 이력서 본문은 JSONB 유지
- 이력서 각 섹션은 구조가 크고 문서 단위 편집/출력 비중이 높다.
- `resumes.content JSONB`를 유지한다.
- Career AI에 필요한 관계형 축(Skill, Project 등)은 별도 관계 테이블/추출 projection으로 보완한다.

## DEC-041 이력서 revision은 snapshot
- 저장 시점 이력을 보존해야 하는 경우 `resume_revisions.content JSONB`에 snapshot을 저장한다.
- 현재 Resume 레코드를 덮어쓰더라도 revision은 변경하지 않는다.

## DEC-042 표시 이름 중복 제거
- `resumes.user_display_name`, `resume_feedback.author_name` 같은 표시용 값은 TO-BE 원본에서 제거한다.
- `user_id`, `author_id` FK로 조회한다.
- ETL 중 legacy snapshot이 꼭 필요한 경우에만 예외를 둔다.

## DEC-043 Skill은 정규화
- `users.skills text[]`를 최종 Skill 원본으로 사용하지 않는다.
- `skills` + `user_skills`를 Career AI의 관계형 기준으로 사용한다.
- 프로젝트/채용공고 요구 기술 역시 가능한 경우 같은 `skills.id`를 참조한다.

## DEC-044 Job Preference는 JSONB 허용
- 사용자당 현재 설정 하나를 둔다.
- 구조 변경 가능성이 높고 강한 참조 무결성 요구가 낮아 `preferences JSONB`를 사용한다.

## DEC-045 Career Graph는 projection
- Neo4j는 PostgreSQL을 대체하지 않는다.
- PostgreSQL의 Student/Project/Skill/Job/Company 관계를 Neo4j에 projection한다.
- graph rebuild가 가능하도록 PostgreSQL ID를 graph node의 stable source ID로 사용한다.

## DEC-046 기존 공지/커리큘럼/학습실/AI 로그는 재사용 우선
- 실제 운영 프로세스가 기존 구조와 충돌하지 않는 영역은 재설계 비용을 줄이기 위해 `feature/test` 구조를 우선 사용한다.
- 파일 컬럼은 최종적으로 storage key 중심으로 정리한다.

## DEC-047 사용 데이터가 없는 Community/QnA는 우선 제외
- posts/QnA 운영 데이터가 0건인 현재 상태에서는 초기 PostgreSQL 통합 범위에서 제외한다.
- 실제 기능 요구가 확정되면 Django migration으로 추가한다.

## DEC-048 Django migration이 최종 스키마 소유
- `schema.sql` + DROP/CREATE 방식은 초기 ETL 도구로만 본다.
- 통합 이후 스키마 생성/변경의 기준은 Django managed models + migrations다.
- ETL은 스키마를 생성하지 않고 데이터 변환/적재만 담당한다.

## DEC-049 S3는 key 중심 저장
- PostgreSQL에는 가능하면 bucket 포함 전체 URL보다 object `storage_key`를 저장한다.
- 실제 접근 URL은 backend에서 생성한다.

## DEC-050 기본 이력서와 공고 맞춤 이력서의 파생 관계를 보존
- 공고 맞춤 이력서도 `resumes`에 저장하고 `base_resume_id` self FK로 원본 기본 이력서를 참조한다.
- 맞춤 이력서가 대상으로 삼은 채용공고는 `linked_job_id`로 추적한다.
- 기본 이력서가 제거되어도 맞춤 이력서는 보존하고 `base_resume_id` 연결만 해제한다.
- 채용공고는 일일 수집에서 물리 삭제하지 않고 상태를 전이한다. 따라서 과거 맞춤 이력서의 `linked_job_id`는 보존한다. 향후 공고 FK를 도입하고 예외적인 물리 삭제가 필요할 때만 `SET NULL`을 검토한다.
- `base_resume_id`가 자기 자신을 가리키지 못하도록 하고, 기본/맞춤 이력서의 소유자 일치는 Django service validation으로 보장한다.

## DEC-051 Legacy resume sections는 content JSONB로 병합
- Legacy의 `content JSONB`와 `sections JSONB`를 TO-BE에서 중복 원본으로 유지하지 않는다.
- ETL이 `sections`의 섹션 완성 상태를 `content.section_status`로 병합한다.
- 충돌 시 무조건 덮어쓰지 않고 필드별 우선순위를 ETL mapping과 migration report에 기록한다.

## DEC-052 Practice는 Django 관리 도메인으로 통합
- practice 전용 SQL이 아니라 Django managed models + migrations가 테이블과 제약을 소유한다.
- ETL이 `public`을 반복 DROP한다는 전제를 두지 않으며, ETL은 운영 풀이 기록을 삭제하지 않는다.
- 학생과 기수는 `user_uid`, `cohort_code` 문자열이 아니라 `users.id`, `cohorts.id` FK로 참조한다.
- Firebase UID와 기수 코드는 legacy 데이터 이전 시 stable lookup key로만 사용한다.
- 테이블은 기본 PostgreSQL 스키마에 `practice_*` 이름으로 두고, 별도 schema는 권한/운영 요구가 생길 때 다시 검토한다.

## DEC-053 Practice attempt는 현재 상태를 우선 저장
- 초기 범위에서는 학생/문제당 한 행에 `passed`, `tries`, `answered_at`을 저장한다.
- 개별 제출 코드와 채점 결과 전체 이력이 필요해지면 `practice_attempt_events`를 별도 추가한다.
- 문제 신고는 학생/문제당 한 행으로 유지하며 재신고 시 이유와 메모를 갱신한다.

## DEC-054 물리 스키마 소유권은 도메인별로 명시
- LMS/이력서/Practice의 신규 테이블과 인덱스는 Django managed models 및 migration이 소유한다.
- 채용공고 `jobs` schema의 구조는 `lms.0003_jobs_schema` migration이 생성한다. 수집기는 운영 `jobs` schema에서 DDL을 실행하지 않고 구조를 확인한다. 테스트 격리 schema는 테스트 목적으로 자체 생성한다.
- `resumes.linked_job_id`는 현재 stable job ID 문자열로 유지하며 존재성은 서비스에서 검증한다. FK 승격 전에는 서로 다른 스키마의 FK나 job 테이블 재생성에 의존하지 않는다.
- 정책/FAQ의 PostgreSQL 원본·revision 테이블은 `lms.0004_policy_documents`로 생성한다. 다만 현재 저장소 파일 및 외부 문서에서 Pinecone으로 직접 적재하는 경로는 아직 전환되지 않았다. 원본의 식별자·버전/hash·본문 또는 S3 storage key를 이 테이블에 저장하는 ingestion과 Pinecone 재투영을 구현한 뒤 운영 적재한다. Pinecone은 원본이 아니다.

## DEC-055 FK 삭제 정책은 ORM과 DB에서 구분
- `models.PROTECT/CASCADE/SET_NULL`은 Django ORM을 통한 삭제 정책이다.
- 현재 PostgreSQL migration이 생성한 FK는 DB 수준에서 `NO ACTION`이며, 직접 SQL 삭제가 자동 cascade/SET NULL 된다고 가정하지 않는다.
- 운영 데이터 삭제는 우선 soft deactivate를 사용한다. SQL 수준 cascade가 실제로 필요한 관계는 별도 migration과 테스트를 거쳐 명시적으로 변경한다.

## DEC-056 채용공고 수집과 스키마 변경의 책임 분리
- 팀원의 매일 크롤링·정규화·upsert·상태 전이는 유지한다. Django migration은 `jobs` schema 구조만 소유한다.
- 운영 schema의 런타임 DDL은 제거했다. 기존 증분 수집과 Pinecone 변경분 동기화의 전체 회귀 테스트는 별도 완료 조건이다.
- 운영 순서와 장애·이력서 연결 정책은 [채용공고 일일 수집·저장 운영 계약](job-posting-operations.md)을 따른다.
