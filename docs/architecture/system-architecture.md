# PLAYDATA LMS / LXP - Target Architecture

- React + Vite: 웹 클라이언트
- Django: LMS 업무 API, 인증/권한, CRUD
- PostgreSQL: 업무 데이터의 canonical source of truth
- S3: 파일 저장소
- Redis: Celery broker/cache
- Celery: 예약/비동기 작업
- Pinecone: semantic retrieval index
- FastAPI: AI orchestration/service layer
- LangGraph: 복합 AI workflow
- Neo4j: Career Knowledge Graph

원칙:
- PostgreSQL이 업무 원본이다.
- S3에는 실제 파일 바이트를 저장하고 PostgreSQL에는 storage key/metadata를 저장한다.
- Pinecone/Neo4j는 PostgreSQL의 업무 데이터를 목적별로 투영한 보조 저장소다.
- 외부 시스템(예: 고용24)의 원천 데이터와 LMS의 확정 업무 데이터를 구분한다.
