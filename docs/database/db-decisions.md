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
