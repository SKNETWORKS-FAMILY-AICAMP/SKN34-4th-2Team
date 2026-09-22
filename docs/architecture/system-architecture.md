# PLAYDATA LMS / LXP - Target Architecture

## 역할
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

## 마일리지 처리
- mileage_transactions가 마일리지 원장이다.
- 구매 요청 승인/환급/소멸은 Django DB transaction으로 처리한다.
- users.mileage_balance를 캐시로 유지할 경우 원장 거래와 동일 transaction에서 갱신한다.
- 종강 2주 후 소멸은 Celery 예약 작업으로 처리할 수 있다.
