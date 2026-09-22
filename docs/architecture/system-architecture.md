# Target System Architecture

```text
React / Clients
      |
      v
Django LMS API
      |
      +-------- PostgreSQL (canonical SoT)
      |             |
      |             +---- Celery / Outbox ----> Pinecone projector
      |             |
      |             +---- Celery / Outbox ----> Neo4j projector
      |
      +-------- S3 (binary objects)
      |
      +-------- Redis (cache / Celery broker)

FastAPI AI Service
      |
      +---- PostgreSQL retrieval
      +---- Pinecone semantic retrieval
      +---- Neo4j relationship retrieval
      +---- LLM / LangGraph
```

## Boundary
- Django: 인증/권한/LMS CRUD/업무 transaction
- FastAPI: AI orchestration
- PostgreSQL: 원본
- S3: 파일
- Redis: 임시 상태/큐/캐시
- Pinecone: 검색 index
- Neo4j: Career 관계 projection
