# 2-EC2 배포 구성 (설정 초안)

이 문서는 배포 구조와 필요한 설정을 기록한다. 현재 AWS 리소스 생성, 이미지 push,
실제 EC2 기동, HTTPS 설정 또는 RDS migration을 완료했다는 뜻이 아니다.
기존 루트 `docker-compose.prod.yml`은 단일 호스트 배포 설정으로 남겨 둔다.

## 로컬 개발

### Resume Review v2 실행 선택

통합 진입점 `app.integrated:app`은 `RESUME_REVIEW_ENGINE=v2`를 기본으로 사용한다.
review·context·apply·undo는 공통 PostgreSQL gateway를 사용한다. Django proxy 요청은
기존 사용자/기수/이력서 소유권 검사를 유지하며 Firebase Admin 초기화를 요구하지 않는다.
직접 bearer 요청은 Firebase 인증 설정과 토큰 검증이 계속 필요하다.

- `v2`: 공용 v2 런타임. Analyze/Writer/Verifier checkpoint와 답변 수정·철회 지원.
- `v2-local`: 기존 B 실행용. loopback DB 제한을 유지한다.
- `v1`: 이전 런타임으로 명시적 전환. 진행 중인 v2 review를 v1으로 이어가지 않는다.

이 설정은 서버 프로세스 시작 시 읽는다. 코드 반영 후 AI 프로세스/이미지를 재시작하고
`GET /resume-review/health`의 `review_engine`이 `v2`인지 확인한다.
배포 Compose는 v2를 명시하며, Django/Nginx도 새 timeout 설정을 반영해야 한다.
새 migration은 없다. 기존 v2 저장 테이블 migration이 적용된 DB를 사용한다.

공고 요건은 저장된 profile을 우선 재사용한다. 미생성 profile의 추출은 최대 45초의
호출 timeout을 사용하고, 이 시간을 포함해 review의 165초 예산을 계산한다.
추출 실패를 확인된 요건 없음으로 처리하지 않는다. telemetry의 `v2-local-ui-2`는
기존 checkpoint 호환용 protocol 표식이며 실행 DB가 로컬이라는 뜻은 아니다.

```text
React localhost:5173 → Django localhost:8000 → FastAPI localhost:8001
                                             ↘ RDS / S3 / Pinecone
```

React는 Vite의 `/api` 프록시를 사용한다. 로컬 서버 실행법과 `docker-compose.yml`은
이번 변경의 대상이 아니다. 로컬에서 AI URL은 `http://127.0.0.1:8001`이다.

## 배포 구성

```text
브라우저 → S3 + CloudFront (React 정적 파일)
          └─ HTTPS API 요청 → Django EC2 (nginx → api/Gunicorn)
                                   ├─ redis + Celery worker + Celery beat
                                   ├─ RDS / S3 / Pinecone
                                   └─ VPC private :8001 → FastAPI EC2 (AI 컨테이너)
                                                             └─ RDS / S3 / Pinecone
```

CloudFront의 React에서 Django API에 도달하려면 API 전용 도메인을
`VITE_API_BASE=https://<API_HOST>/api`로 빌드 전에 설정하거나 CloudFront `/api/*`
오리진 라우팅을 별도로 구성해야 한다. 이 연결은 Compose만으로 완성되지 않는다.

| EC2 | Compose 파일 | 서비스 |
|---|---|---|
| Django | `deploy/docker-compose.django.yml` | `redis`, `api`, `worker`, `beat`, `nginx` |
| FastAPI | `deploy/docker-compose.ai.yml` | `ai` |

두 EC2에는 각자의 비공개 `.env`가 필요하다. `env_file: ../.env`는 Compose 파일이
있는 `deploy/`를 기준으로 저장소 루트 `.env`를 가리킨다. 저장소에는 실제 `.env`를
커밋하지 않는다. 두 호스트의 `LMS_AI_SHARED_TOKEN` 값은 같아야 한다.
`deploy/ai.Dockerfile`의 이미지 기본 명령은 컨테이너 내부 `8000`에서 Uvicorn을
실행하고, AI Compose가 호스트 `8001`을 컨테이너 `8000`에 연결한다.

저장소 루트에서 실행하는 명령 예시(각각 해당 EC2에서, 실제 값 준비 후):

```sh
docker compose --env-file .env -f deploy/docker-compose.django.yml config --quiet
docker compose --env-file .env -f deploy/docker-compose.django.yml up -d
```

```sh
docker compose --env-file .env -f deploy/docker-compose.ai.yml config --quiet
docker compose --env-file .env -f deploy/docker-compose.ai.yml up -d
```

`config` 출력을 그대로 공유하지 않는다. 환경변수와 secret이 펼쳐질 수 있다.

## EC2별 런타임 설정

| Django EC2 `.env` | 역할 |
|---|---|
| `ECR_IMAGE` | Django API/worker/beat 이미지 |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | RDS 접속. 운영 대상 DB 이름은 별도로 승인 후 지정 |
| `CHATBOT_URL`, `JOBS_URL`, `STUDY_NOTES_URL`, `RESUME_REVIEW_URL` | 모두 `http://<FASTAPI_PRIVATE_ADDRESS>:8001` 형태. Docker 서비스명 `ai` 사용 금지 |
| `LMS_AI_SHARED_TOKEN` | FastAPI EC2와 동일한 긴 비밀값 |
| `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` | Django 인증·웹 출처 |
| `AWS_REGION`, `AWS_S3_BUCKET` | S3 접근. EC2 IAM role에 최소 권한 부여 |
| `PINECONE_API_KEY2`, `OPENAI_API_KEY` | 공지 벡터 동기화 사용 시 필요 |

`REDIS_URL=redis://redis:6379/0`, `LMS_INLINE_PUBLISH=0`, `DJANGO_DEBUG=0`은
Django Compose가 컨테이너에 명시한다. Redis는 이 Compose 네트워크에서만
접근하며 포트를 EC2 호스트에 공개하지 않는다.

| FastAPI EC2 `.env` | 역할 |
|---|---|
| `ECR_AI_IMAGE` | `deploy/ai.Dockerfile`로 빌드한 통합 AI 이미지 |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_SSLMODE` | Django와 같은 RDS 데이터에 접속 |
| `LMS_AI_SHARED_TOKEN` | Django EC2와 동일한 값 |
| `OPENAI_API_KEY`, `PINECONE_API_KEY1`, `PINECONE_API_KEY2` | 모델과 공고/학생 벡터 검색 |
| `AWS_REGION`, `AWS_S3_BUCKET` | AI 파일·문맥 읽기에 필요한 경우 |
| `GITHUB_TOKEN`, `FIREBASE_PROJECT_ID` | 해당 기존 기능의 실행 경로에서 요구하는 경우만 확인해 제공. 실제 값 커밋 금지 |

AI 챗봇의 YouTube 캐시 조회는 `REDIS_URL`을 사용할 수 있다. 현재 AI Compose에는
Redis를 추가하지 않으며, 미설정 시 AI 컨테이너의 `127.0.0.1`에는 Redis가 없다.
이 경로는 예외를 처리해 캐시를 빈 값으로 반환하지만, 해당 문맥 기능이 필요하면
별도 접근 가능한 Redis 주소와 네트워크 정책을 검토해야 한다. Django Compose의
내부 `redis` 서비스명은 AI EC2에서 해석되지 않는다.

## 네트워크·보안 원칙

- FastAPI EC2 보안그룹의 TCP `8001` 인바운드는 **Django EC2 보안그룹만** 허용한다.
  `8001:8000` 포트 매핑 자체는 외부 접근을 차단하지 않으므로 SG가 필수다.
- RDS TCP `5432`는 Django/AI 등 필요한 SG만 허용한다.
- SSH TCP `22`는 관리자 공인 IP `/32`로만 제한한다.
- `8001`, `5432`, `22`를 `0.0.0.0/0`에 열지 않는다.
- 비밀번호/API 키/공유 토큰은 이미지, Compose, 저장소에 넣지 않는다.
- 현행 `deploy/nginx/nginx.conf`는 HTTP 80의 Django `/api/` 프록시다.
  Compose가 443을 매핑하더라도 TLS 설정은 아직 없으므로 별도 HTTPS/domain
  구성이 필요하다. 이번 변경은 Nginx/Certbot을 재설계하지 않는다.

## 향후 배포 흐름 (미구현)

```text
feature/* → PR → main → GitHub Actions → Docker build → ECR
                                          → EC2 pull → docker compose up -d
```

ECR 저장소/이미지 push, IAM role·OIDC, GitHub Actions CI/CD, CloudFront,
HTTPS/domain, 보안그룹 실제 적용과 양 EC2 간 연결 검증은 이번 변경에 포함하지 않는다.
특히 DB migration, 초기화, 데이터 적재는 이 절차에 자동으로 넣지 않는다.
