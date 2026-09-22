# PLAYDATA LMS / LXP - Target Architecture

## 역할
- React + Vite: 웹 클라이언트
- Django: LMS 업무 API, 인증/권한, CRUD
- PostgreSQL: 업무 데이터의 canonical source of truth
- S3: 프로필 사진, 증빙, PDF/CSV, 공지 이미지 등 binary object storage
- Redis: Celery broker/cache
- Celery: 예약 공지, 비동기 작업, 검색 인덱스 동기화
- Pinecone: 공지/정책 등 semantic retrieval index
- FastAPI: AI orchestration/service layer
- LangGraph: 학생 챗봇 및 복합 AI workflow
- Neo4j: Career Knowledge Graph / 관계 탐색

## 원칙
- PostgreSQL이 업무 원본이다.
- S3에는 실제 파일 바이트를 저장하고 PostgreSQL에는 storage key/metadata를 저장한다.
- Pinecone/Neo4j는 PostgreSQL의 업무 데이터를 목적별로 투영한 보조 저장소다.
- Redis는 영속 업무 데이터의 원본으로 사용하지 않는다.
- 외부 시스템(예: 고용24)의 원천 데이터와 LMS의 확정 업무 데이터를 구분한다.
- 기록실 증빙 파일은 S3, 제출/심사/마일리지 거래 정보는 PostgreSQL에 저장한다.
