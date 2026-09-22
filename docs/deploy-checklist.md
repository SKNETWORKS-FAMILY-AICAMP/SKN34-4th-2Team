# EC2 / 배포 체크리스트 (프론트 API URL · 백엔드)

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
- [ ] `DATABASE_URL` → 보통 RDS
- [ ] `REDIS_URL` → ElastiCache 또는 compose redis
- [ ] `CHATBOT_URL` → 챗봇 서비스 내부 URL (compose에 추가 시)
- [ ] `LMS_INLINE_PUBLISH=0` (Celery worker/beat 사용 시)
- [ ] gunicorn chat 타임아웃 (필요 시 120초)
- [ ] S3/IAM, HTTPS(Nginx+certbot)

관련: `docker-compose.prod.yml`, `deploy/nginx/nginx.conf`, `.github/workflows/deploy.yml`
