# 3차 AI 기능 → React/Django/PostgreSQL/S3 이주 추적

2026-09-23 기준. 기능을 제외하기 위한 목록이 아니라, 3차 기능 전체를 빠짐없이
이주하고 실제 동작까지 검증하기 위한 목록이다. "코드 존재", "DB 연결", "동작 검증",
"배포"를 별도로 판단한다.

| 기능/경로 | 현재 코드 상태 | TO-BE 작업 | 완료 판정 |
|---|---|---|---|
| 학생 챗봇 (`chatbot/`) | 학생 문맥 SQL은 TO-BE 테이블·`DB_*` 우선 연결로 수정. Django 프록시 내부 토큰 단위 테스트와 검증 DB 읽기 전용 SQL 확인 완료. 직접 `/init`·`/stream`은 Firebase ID 토큰. | Django 인증으로 직접 경로 대체, 실제 학생 데이터·Pinecone·S3 문맥 답변 검증 | React→Django→AI→RDS/S3/Pinecone 종단 간 테스트 |
| 공부방 수업 노트 (`study_notes/`) | React 화면의 저장소 조회·노트 생성 호출을 Django 프록시에 연결했고 AI 내부 경로는 PostgreSQL 소스/노트를 사용한다. `0005` migration은 개발 DB에 적용, Django 테스트 22개 통과. 3차 직접 API/`service.py`의 Firestore 경로는 아직 남음. | AI 런타임 의존성 설치, `CHATBOT_URL`·공유 토큰 설정, 실제 소스/학생으로 생성·동시성 시험 | 동시 생성·재조회·실패 복구·권한·React 종단 간 테스트 |
| 이력서 첨삭 (`cover_letter_rag/`) | 이력서 관련 SQL은 있으나 `firebase_gateway.py`의 인증·일부 상태는 Firebase. PostgreSQL 연결은 `DB_*` 우선으로 수정. | Firebase 토큰·잔여 Firestore 읽기/쓰기 제거, Django 인증·TO-BE 이력서/첨삭 테이블 연동 | 원본→첨삭→피드백 저장/적용 및 권한 테스트 |
| 채용 매칭·공고 (`job_matching_bot/`) | `jobs` PostgreSQL 스키마 사용. 운영 저장소의 연결을 `DB_*` 우선으로 수정; 테스트 격리 스키마는 로컬 URL 유지. 야간 배치의 옛 Firebase Storage 공유 업로드를 생략하는 **미커밋 초안**이 있으나 크롤링 담당자 확인 전이며 운영 확정 아님. 수동 공유 도구는 그대로 남음. | 담당자가 공유 파일의 소비자·필요성을 확인한 뒤 크롤링→jobs upsert→임베딩 projection→추천 운영 경로 확정 | 신규·수정·마감 공고의 재수집 및 추천 응답 테스트 |
| 정책·공지·프로젝트 검색 (`vectordb/`, `functions/`) | Pinecone 검색 코드는 존재. 공지 자동 동기화는 Firestore Cloud Function 경로를 전제로 함. | PostgreSQL 원본 변경을 이벤트/작업으로 Pinecone에 투영, 재색인·삭제·재시도 | RDS 원본과 검색 결과의 동기화 검증 |
| 연습·복습 문제 | Django practice 테이블은 존재. 3차의 풀이·생성 API 이주 상태는 별도 확인 필요. | 문제 생성/풀이/신고/검토 경로를 Django 인증과 managed tables에 연결 | 생성→풀이→재시도→신고 테스트 |

공통 원칙: PostgreSQL이 원본, S3는 파일, Redis는 캐시/작업 큐, Pinecone은
재생성 가능한 검색 projection이다. 이전 Firebase/Flutter 계약을 참고하되 신규
React/Django 인증과 스키마가 실제 실행 경로를 소유한다. 운영 RDS에 바로
migration/import를 실행하지 않고 검증 DB에서 먼저 재현한다.
