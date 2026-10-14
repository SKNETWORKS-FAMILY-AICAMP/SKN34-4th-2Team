# EC2 / 배포 체크리스트 (프론트 API URL · 백엔드)

## 현재 상태 (2026-09-23)

- **개발/검증 연결 완료:** Django는 루트 `.env`의 `DB_HOST`, `DB_NAME`,
  `DB_USER`, `DB_PASSWORD`, `DB_PORT`, `DB_SSLMODE`로 AWS RDS PostgreSQL에
  접속한다. 새 검증 DB `lms_migration_replay_20260923`에서 빈 DB migration,
  실제 공지 15건과 로컬 정책 원본 7건 적재, 인증 HTTP 확인을 마쳤다.
- **S3 일부 연결 완료:** 공지 이미지 2건을 S3에 복사해 객체 크기·읽기를 확인했다.
  DB에는 `image_storage_key`를 두고 인증된 bootstrap 응답에 짧은 수명의
  읽기 URL을 제공한다. 모든 업로드 경로와 운영 IAM 권한 검증은 아직 아니다.
- **운영 배포 미완료:** `.github/workflows/deploy.yml`은 React 테스트/빌드와
  Django 이미지 빌드만 실제로 수행한다. S3 업로드, ECR push, EC2 배포는
  `echo` placeholder다. `docker-compose.prod.yml`은 Django API/worker/beat에
  `ECR_IMAGE` 하나를 쓰며 AI 서비스는 정의하지 않았다.
- **AI 기능 코드 존재, AI 배포 준비는 별개:** 3차의 학생 챗봇·채용 추천·첨삭
  Python 코드는 저장소에 있다. `lms-ai` 이미지 빌드, Compose 서비스,
  실제 `CHATBOT_URL` 설정 및 Firestore 의존 경로의 TO-BE 데이터 연결은
  별도 통합 작업이다. 학생 챗봇의 PostgreSQL 문맥 조회는 Django와 동일하게
  `DB_*`를 우선 사용하도록 수정했고, Django→AI `/chat` 호출은 양쪽에 설정한
  `LMS_AI_SHARED_TOKEN`이 있어야 받는다. 이는 코드·단위 테스트 수준이며
  AI 서버 종단 간 실행 검증은 아직 아니다. 최종 React UI는 `feature/change_react`에서 진행 중이므로
  현재 브랜치 화면을 최종 통합 검증으로 간주하지 않는다.
- **로컬 Compose는 별도:** `docker-compose.yml`의 api/worker/beat는
  `DB_HOST`를 빈 값으로 덮어 로컬 `DATABASE_URL`을 사용한다. 루트 `.env`에
  RDS 값이 있더라도 로컬 컨테이너가 우연히 RDS를 수정하지 않도록 한 설정이다.

## 연결/배포 순서

1. **검증 환경(현재):** RDS 검증 전용 DB에 Django `migrate` → 선별 importer →
   FK/건수/S3 key 검사 → 인증 및 API HTTP 검증. `postgres` 기본 DB나 운영 DB를
   시험 대상으로 사용하지 않는다.
2. **운영 데이터 준비:** 실제 공지·정책·채용공고의 원본 및 정기 갱신 경로를
   확정한다. 이미지와 파일은 S3 object key를 DB에 저장한다. 실제 학생 계정과
   학습 이력은 3차 데모 데이터를 전량 이사하지 않고 새 서비스에서 생성한다.
3. **서비스 통합:** Django API와 별도 AI 서비스를 같은 내부 네트워크에서
   연결하고, 최종 React 브랜치를 합친 뒤 화면→API→RDS/S3 종단 간 시험을 한다.
4. **운영 배포:** 팀 담당자가 AWS OIDC/IAM, ECR 저장소, EC2, 웹 버킷·CloudFront
   정보를 확정한 뒤 placeholder를 실제 배포 명령으로 교체한다. Django와 AI는
   각각 독립 이미지로 빌드/태그/배포한다. 검증 결과와 백업·롤백 절차 없이
   운영 DB에 migration/import를 실행하지 않는다.

웹 빌드 시 Axios baseURL 은 `VITE_API_BASE` 로 고정된다 (`lms_react/src/data/http.ts`).
로컬 기본값은 `/api` 이고, Vite 가 `127.0.0.1:8000` 으로 프록시한다.

## 프론트 API URL

| 환경 | `VITE_API_BASE` | 비고 |
|------|-----------------|------|
| 로컬 `npm run dev` | `/api` | `lms_react/.env.example` 참고 |
| 배포 · 같은 도메인 (Nginx가 `/api` → Django) | `/api` | 추가 설정 거의 없음 |
| 배포 · API 전용 도메인 | `https://api.example.com/api` | **빌드 전에** 환경변수로 넣기 |

```powershell
# 배포 빌드 예 (API 분리 도메인일 때)
cd lms_react
$env:VITE_API_BASE = "https://api.example.com/api"
npm ci
npm run build
# dist/ 를 S3 등 mid
```

GitHub Actions: `VITE_API_BASE` secret/variable 이 있으면 build 단계에 주입한다.
없으면 기본 `/api` 로 빌드한다.

## 백엔드 · EC2 (요약)

- [ ] `DJANGO_SECRET_KEY` 충분히 긴 값 (JWT 서명)
- [ ] `DJANGO_DEBUG=0`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` (웹 도메인)
- [ ] RDS 접속: `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`,
      `DB_SSLMODE=require`를 EC2 런타임에 제공 (`DB_HOST` 설정 시 이 조합이
      `DATABASE_URL`보다 우선한다)
- [ ] `REDIS_URL` → ElastiCache 또는 compose redis
- [ ] `CHATBOT_URL` → 챗봇 서비스 내부 URL (compose에 추가 시)
- [ ] Django와 AI 서비스에 동일한 `LMS_AI_SHARED_TOKEN`을 별도로 주입하고
      AI 서비스 포트는 외부 공개하지 않는다 (미설정 시 Django `/api/chat`은 503)
- [ ] 공부방 노트: Django `/api/study-notes/{tree,generate,get}` → 내부 AI
      `/api/v1/study-notes/internal/{tree,generate,get}` 경로 검증. 기준 DB에는
      `lms.0006`까지 적용했다. 실제 AI 호출과 학습자료 응답은 별도 검증 대상이다.
- [ ] `LMS_INLINE_PUBLISH=0` (Celery worker/beat 사용 시)
- [ ] gunicorn chat 타임아웃 (필요 시 120초)
- [ ] `AWS_S3_BUCKET`, `AWS_REGION` 및 최소 권한 IAM role로 S3 객체 읽기/쓰기 검증
- [ ] HTTPS(Nginx+certbot 또는 선택한 TLS 종단), 웹 버킷·CloudFront 연결
- [ ] `lms-api`/`lms-ai` 이미지의 별도 ECR push와 EC2 pull/up, 실제 헬스체크

관련: `docker-compose.prod.yml`, `deploy/nginx/nginx.conf`, `.github/workflows/deploy.yml`

전체 AI 기능별 남은 이주/검증 항목: `docs/architecture/ai-migration-tracker.md`.
