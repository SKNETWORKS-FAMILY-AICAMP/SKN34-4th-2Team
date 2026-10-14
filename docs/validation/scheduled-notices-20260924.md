# 예약 공지 검증 — 2026-09-24

기준: `feature/postgresql-integration`, AWS RDS `lms_migration_replay_20260923`.
새 DB·migration·ETL은 만들거나 재실행하지 않았다.

- `feature/test` 이후의 예약 공지 경로 diff를 확인하고 기존 발행 로직을 유지했다.
- 실제 Django API에서 `POST /api/scheduled-notices`는 200이지만
  `POST /api/scheduled-notices/publish`가 동적 `/{pk}` 경로에 가려져 405인 것을 재현했다.
  정적 경로 선언을 앞으로 옮겨 해결했다.
- 한 DB 트랜잭션 안의 임시 데이터로 일회성 예약을 같은 ID로 두 번 발행했을 때
  기존에는 `[1, 1]`(공지 2건), 수정 후 `[1, 0]`(공지 1건)이었다.
  `is_active` 확인과 행 잠금으로 재발행·동시 발행을 막았다.
- 강사의 다른 기수 예약 발행 요청은 0건으로 처리되는 것을 확인했다.
  배치/관리 명령은 기수 제한 없이 기존 역할을 유지한다.
- 별도 임시 예약 1건을 실제 커밋하여 발행 공지와 Pinecone 벡터 1개 생성,
  `vector_chunk_count=1`, 재요청 시 0건을 확인했다. 임시 공지·예약·계정·벡터는 정리했다.
- Django 테스트 26개, React 테스트 53개, TypeScript 검사와 Vite 빌드 통과.

남은 검증: React 관리자 화면에서 실제 로그인→「지금 게시」→공지 조회까지
브라우저 E2E. React 테스트는 데모 데이터 기반이므로 위 서버 검증과 혼동하지 않는다.
