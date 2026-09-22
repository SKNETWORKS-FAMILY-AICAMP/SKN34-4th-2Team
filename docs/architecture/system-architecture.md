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

성취도 평가:
- 평가/문항/응시/채점 데이터는 PostgreSQL에 저장한다.
- LLM 문항 생성은 FastAPI AI 계층에서 수행할 수 있다.
- 생성 결과는 초안이며 Django LMS에서 강사가 검토 후 확정/발행한다.
