> 과거 작업 기록입니다. 아래 상태·검증 결과는 기록 당시 기준이며, 현재 배포 상태를 보장하지 않습니다.

# AWS 배포 사전 점검 — 2026-10-09 (한국 시간)

> 후속 인증 보안 릴리스가 운영 반영되었다. 현재 이미지·검증·잔여 위험은 [보안 조치 결과](security-remediation-2026-10-09.md)와 `release-20261009.json`을 참조한다. 아래 배포 절들은 초기 배포 이력이다.

## 최종 공개 상태 — 2026-10-09 저녁

접속 주소: **https://d1zqs4mfabqpqs.cloudfront.net**

사용자가 로컬 `.env` 사용, 도메인 없는 CloudFront 기본 주소 배포를 선택했다.
아래 이전 절들은 단계별 이력이며 이 절이 현재 상태다.

### 구성과 실행 상태

- React: 웹 전용 비공개 S3 `skn34-lxp-web-711425439897-us-east-1`.
  원본 버킷은 공개 차단을 유지하고 OAC로 이 CloudFront 배포에만 GetObject 허용.
  버전 관리 활성화. 기존 문서용 버킷은 웹 파일로 덮어쓰지 않았다.
- CloudFront `E79A6UM0WDCG3`: Deployed. 기본 경로는 웹 S3,
  `/api/*`는 Django VPC origin `vo_GNVnBLHHRLnEbLnbzVwDKD`로 전달.
  API 캐시는 비활성화하고 인증 헤더·쿠키·쿼리를 전달한다.
  기본 경로에만 SPA 재작성 함수를 적용해 API 404가 HTML로 바뀌지 않는다.
- Django EC2: `/opt/skn34-lms`에서 `api`, `nginx`, `redis`, `worker` 실행.
  `deploy/docker-compose.django.yml` + `deploy/docker-compose.cloudfront.yml` 사용.
- AI EC2: 같은 디렉터리에서 `deploy/docker-compose.ai.yml`의 `ai` 실행.
- **사용자 요청으로 정기 작업은 끔:** beat 미실행, `LMS_INLINE_PUBLISH=0`.
  worker는 큐에 들어온 작업을 처리하지만 주기 작업을 새로 예약하지 않는다.
- Django 인바운드 80은 AWS 관리 CloudFront VPC origin SG
  `sg-038dfc9322fca2155`만 추가 허용했다. 인터넷 전체에 API 포트를 열지 않았다.
- 로컬 `.env`의 필요한 값만 서버별 RSA+AES-GCM으로 암호화하여 전달했다.
  AWS 액세스 키는 복사하지 않고 instance role 사용. 런타임 `.env`는 root 전용 0600,
  디렉터리는 0700. 양쪽 임시 암호화 개인키는 전달 완료 후 제거했다.
- HTTPS는 CloudFront에서 처리한다. Django는 CloudFront 전용 Nginx가 덮어쓴
  forwarded-proto를 신뢰한다. secure cookie·clickjacking·HSTS 설정을 배포 overlay에 추가했다.
- 파일용 S3 CORS에는 새 HTTPS 주소의 GET/HEAD만 추가했다. 기존 로컬 규칙 유지.

### 통과한 검사

- CloudFront `/`, `/login`, `/student/home` 및 JavaScript 자산 HTTP 200.
- `/api/bootstrap` 익명 요청 HTTP 401, 없는 API HTTP 404.
- 웹 S3 `index.html` 직접 공개 접근 HTTP 403.
- 독립 Edge 세션에서 로그인 화면 렌더링 확인, JavaScript pageerror 없음.
- 실행 컨테이너에서 Django/AI DB 인증 및 S3 IAM 역할 접근 성공.
  Django 미적용 migration 없음. DB migration/데이터 초기화는 실행하지 않았다.
- Django EC2 → AI private IP `/resume-review/health`: review_engine v2.
- AI 컨테이너에서 설정된 OpenAI 모델 조회, Pinecone 인덱스 2개 조회 성공.
  모델 추론을 호출한 시험은 아니다.
- 운영 React 빌드에서 개발용 데모 로그인 버튼을 제외했다.
  기존 전체 414개 테스트 통과 후 해당 UI 변경의 앱·로그인 테스트 28개와 재빌드 통과.

### 아직 검증 또는 보완할 내용

- 실제 사용자 계정의 로그인 이후 전체 기능·업로드·AI 추론 종단 간 시험은 미완료.
  비밀번호를 채팅에 올리지 않고 사용자가 직접 로그인해 확인할 수 있다.
- **긴 첨삭 요청:** CloudFront origin response timeout은 120초로 설정했다.
  현재 첨삭 코드의 단계 예산은 최대 165초라, 응답 없이 120초를 넘는 요청은 실패할 수 있다.
  비동기 작업+상태 조회 또는 스트리밍 설계를 검토해야 하며 긴 첨삭 정상 완료를 보장하지 않는다.
  [AWS timeout 문서](https://docs.aws.amazon.com/cloudfront/latest/APIReference/API_VpcOriginConfig.html).
- `manage.py check --deploy`의 남은 세 경고는 HSTS includeSubdomains/preload 미사용과
  Django SSL redirect 미사용이다. HTTPS 진입은 CloudFront에서 강제하며 origin은 사설망이다.
  이 경고들을 감추는 설정은 추가하지 않았다.
- 기존 사용자 데이터를 삭제·초기화하거나 데모 계정을 생성하지 않았다.
- GitHub 자동 배포 workflow는 여전히 별도 작업이다. EC2·CloudFront·S3 사용 요금은 발생한다.

### 운영·롤백 메모

- SSH 공개 범위 확대 없이 SSM으로 관리한다. `docker compose config` 전체 출력이나
  `docker inspect`의 env 전체 출력에는 비밀값이 포함되므로 공유하지 않는다.
- 서버 이미지 digest는 `deploy/release-20261009.json`에 고정했다. 이후 배포도 새 태그로
  push하고 확인된 digest를 런타임에 반영한다.
- 웹 버킷의 이전 `index.html` 버전과 해시 자산은 남겨 두었다. 롤백 시 해당 HTML 버전을
  복원하고 CloudFront invalidation을 실행한다. 첫 서버 배포라 이전 운영 서버 버전은 없다.
- 배포 overlay 소스: `deploy/production_settings.py`, `deploy/nginx/cloudfront.conf`,
  `deploy/docker-compose.cloudfront.yml`.

## 최신 AWS 진행 상태: 이미지 업로드·서버 기동 완료

사용자의 진행 승인 후 검증 이미지를 ECR로 push하고 기존 EC2 두 대를 기동했다.
아래 이전 절의 미기동/미업로드 기록은 해당 단계 당시의 상태다.

- ECR의 두 이미지 digest가 로컬 검증 산출물과 일치한다. 주소·태그·digest는
  `deploy/release-20261009.json`에 기록했다.
- Django/AI EC2 모두 running, EC2 system/instance 상태 검사 ok.
  IAM 프로필은 associated, SSM은 Online이다. 인스턴스 실행 요금이 재개된다.
- 두 서버 모두 Ubuntu 24.04, Docker 29.1.3, Compose 2.40.3이며 실행 컨테이너는 없었다.
- 각 서버의 IAM 역할로 자기 ECR 이미지를 digest 고정으로 pull 완료했다.
  ECR 로그인 토큰은 서버에서 직접 발급했고 임시 Docker config는 작업 후 자동 삭제했다.
- 두 서버 모두 IAM 역할을 통한 프로젝트 S3 ListObjectsV2 성공.
  객체 쓰기/삭제나 전체 서비스 업로드 기능 검증은 아직 하지 않았다.
- 두 서버에서 RDS TCP 5432 연결 성공. DB 로그인·쿼리·migration 검증을 의미하지 않는다.
- 기존 `/home/ubuntu/SKN34-4th-2Team`은 존재하지만 `.env`와 분리 배포 Compose는 없었다.
  현재 로컬 소스를 서버의 기존 checkout 위에 덮어쓰지 않았다.
- 서비스 컨테이너는 아직 시작하지 않았다. 런타임 설정의 기준과 웹/API 도메인 선택을
  사용자에게 질문한 상태이며, 운영 비밀값은 SSM 명령 본문이나 출력으로 전달하지 않는다.

다음 단계: 운영 환경변수의 원본·안전한 전달 방식 확정, 런타임 구성 배치,
서비스 기동 및 DB 인증/AI 내부 연결 검증, HTTPS·웹 배포 구성.

## 로컬 빌드 및 기동 검증 완료

사용자가 선택한 현재 작업 내용(미커밋 변경 포함)으로 검증했다. 아래 이미지 ID가
검증한 실제 산출물의 기준이며, 이후 소스 변경은 새 빌드로 검증해야 한다.

- React: 54개 파일 / 414개 테스트 통과, TypeScript 및 Vite 프로덕션 빌드 성공.
  jsdom/React Router 경고와 큰 번들 경고는 남아 있다.
- Django: `lms-api:preflight-20261009`, linux/amd64, 약 470 MB.
  이미지 ID `sha256:e481a956efc89dcb9da76adec8631151056f1d80818d73d6c7f2c679d09c1dcc`.
  컨테이너에서 `manage.py check`, `pip check` 통과.
- AI: `lms-ai:preflight-20261009`, linux/amd64, 약 1.11 GB.
  이미지 ID `sha256:475a6ae2a2d6e2f5060c31e3d0a88ea5a2474d951cc0e74c84f951bf3fb92918`.
  `pip check`, Node 실행, Uvicorn 실제 기동과 `/resume-review/health`의
  `review_engine=v2` 응답 확인. 재검증 스크립트는 `deploy/verify-ai-image.py`.
- 검증 컨테이너는 `--network none`으로 실행했고 운영 `.env`를 전달하지 않았다.
  RDS/S3/LLM/전체 사용자 기능 통합 검증은 아직 수행하지 않았다.
- 두 이미지의 `/app`에 `.env*`, `.pem`, `.key`, Firebase Admin SDK 이름의 파일이
  없는 것을 확인했다. 파일 내용 전체의 비밀 탐지 검사를 의미하지는 않는다.
- `.dockerignore`에 중첩 비밀 파일·로컬 업로드·스케줄러 상태 제외 규칙을 추가했다.
- AI Dockerfile의 Node/Python 베이스를 둘 다 Debian bookworm으로 명시해
  복사한 Node 바이너리의 OS 호환성을 맞췄다.
- 로컬 `.env`의 `DJANGO_SECRET_KEY`는 값 변경 없이 작은따옴표로 감싸서 `$`
  치환을 방지했다. 두 분리 Compose의 `config --quiet`가 경고 없이 통과했다.

### Docker 복구 기록

Docker Desktop의 오래된 AF_UNIX 소켓 처리 실패로 엔진이 시작되지 않았다.
Docker를 종료하고 다음 런타임 디렉터리를 백업 이름으로 보존한 뒤 복구했다.

- `%LOCALAPPDATA%/Docker/run-backup-20261009-deploy`
- `%LOCALAPPDATA%/Docker/run-backup-20261009-deploy2`
- `%LOCALAPPDATA%/docker-secrets-engine-backup-20261009-deploy`

Factory reset, 볼륨 삭제, WSL 초기화는 수행하지 않았다. Docker Engine 29.8.0
응답 및 두 이미지 빌드·컨테이너 실행까지 확인했다.

### 실제 배포 전 남은 항목

1. 검증 이미지의 ECR push, EC2 기동 및 역할 연결 완료/SSM 접속 확인.
2. EC2 런타임 환경 주입과 RDS/S3 접근 확인. 운영 DB migration은 백업·대상 DB 확인 후 별도 수행.
3. 웹/API 도메인 또는 CloudFront 경로 구성, HTTPS 및 Django 보안 설정 확정.
   `check --deploy`에는 clickjacking middleware, HSTS, HTTPS redirect,
   session/CSRF secure cookie 관련 경고 5개가 남아 있다.
4. 실제 로그인·AI 기능·파일 업로드 종단 간 검증과 롤백 검증.

이번 단계에서 ECR push나 EC2 기동은 수행하지 않았다.

## 후속 적용 결과 (사용자 승인 후)

아래 초기 점검 이후 ECR 및 EC2 런타임 역할을 실제 생성했다.

| 대상 | 적용 결과 |
| --- | --- |
| Django ECR | `711425439897.dkr.ecr.us-east-1.amazonaws.com/lms-api` |
| AI ECR | `711425439897.dkr.ecr.us-east-1.amazonaws.com/lms-ai` |
| Django 역할·프로필 | `skn34-django-ec2-runtime` → `i-09af311c959d14cc4` |
| AI 역할·프로필 | `skn34-fastapi-ec2-runtime` → `i-07856cc9d2859e4e8` |

- 두 ECR 모두 immutable 태그, push 시 이미지 스캔 활성화. 아직 이미지는 없다.
- 각 역할은 EC2만 AssumeRole할 수 있고, 자기 서비스의 ECR 이미지 pull만 허용한다.
- S3 조회는 `skn34-4th-2team-lxp` 버킷에 한정한다. Django는 업로드도 허용하며,
  삭제는 `cohorts/*/curriculum/rag/*`, `cohorts/*/policy/rag/*` 객체에만 허용한다.
  AI에는 S3 쓰기·삭제를 허용하지 않았다.
- 사용자 승인 범위에 따라 두 역할에 `AmazonSSMManagedInstanceCore`를 부착했다.
  SSM 에이전트와 네트워크가 정상인지 서버 기동 후 확인해야 한다.
- `describe-instances`에 두 프로필이 표시된다. 마지막 연결 상태 조회는 둘 모두
  `associating`이었다. `associated` 완료 및 실제 런타임 자격 증명 사용은 추가 확인이 필요하다.
- EC2 두 대는 계속 stopped 상태다. 서버 기동, 이미지 push, DB 변경은 수행하지 않았다.
- 두 서버의 기존 IMDSv2 required / hop limit 2 설정을 확인했고 변경하지 않았다.

검증: IAM Access Analyzer에서 두 인라인 정책 모두 findings 없음.
IAM 시뮬레이션에서 AI GetObject 허용·PutObject/DeleteObject 거부,
Django의 기수 문서 DeleteObject 허용·다른 경로 DeleteObject 거부를 확인했다.
시뮬레이션은 실제 서버의 S3 접근 테스트를 대체하지 않는다.

적용 정책 원본: `deploy/iam/ec2-trust.json`, `deploy/iam/django-runtime.json`,
`deploy/iam/fastapi-runtime.json`.

설계 참고: [ECR 권한 범위](https://docs.aws.amazon.com/service-authorization/latest/reference/list_ecr.html),
[컨테이너의 EC2 메타데이터 접근](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/instancedata-data-retrieval.html).

다음 작업은 배포 커밋 확정, Docker 엔진 기동 및 이미지 빌드다. 이후 두 EC2를 기동해
역할 연결 완료와 SSM 접속을 확인하고, 런타임 환경과 HTTPS를 구성한다.

## 확인된 연결

- AWS CLI 2.37.10, `resume-review-rds` 프로필 재로그인 및 STS 인증 성공.
- 실제 프로젝트 리전: `us-east-1`. 로컬 `.env`의 AWS 리전 및 RDS 호스트,
  S3 bucket location과 대조했다. 로그인에 사용한 리전과 리소스 리전은 다를 수 있다.
- 현재 로그인 주체는 root다. 배포 자동화에는 전용 IAM 역할을 준비한다.
- 점검 소스: `refactor/calculation-rules`, HEAD `b07537f` 및 미커밋 변경 포함.
  배포할 커밋은 별도 확정해야 한다.

## AWS 조회 결과

| 대상 | 확인 결과 | 배포 전 할 일 |
| --- | --- | --- |
| Django EC2 `skn34-django-prod` | stopped, t3.small, IAM instance profile 없음 | 런타임 역할, 관리 접속 및 기동 준비 |
| FastAPI EC2 `skn34-fastapi-prod` | stopped, t3.small, IAM instance profile 없음 | 런타임 역할, 관리 접속 및 기동 준비 |
| ECR | us-east-1에 저장소 없음 | Django/AI 각각 저장소 및 이미지 준비 |
| RDS `skn34-4th-2team` | available, PostgreSQL, PubliclyAccessible=true | 배포 대상 DB 이름·백업·migration 상태 확인 |
| S3 `skn34-4th-2team-lxp` | us-east-1, 공개 접근 차단 4개 모두 true | 기존 데이터 버킷 용도 유지, 웹 배포 대상 별도 확정 |
| CloudFront | 배포 없음 | 웹 배포와 API HTTPS 연결 구성 |
| SSM | us-east-1 관리 인스턴스 없음 | EC2 역할·에이전트·네트워크 구성 확인 |
| IAM OIDC | 공급자 없음 | GitHub Actions를 사용할 경우 OIDC 역할 준비 |

네트워크 조회 결과:

- AI TCP 8001은 Django 보안그룹에서만 허용되어 있다.
- RDS TCP 5432는 Django/AI 보안그룹과 지정된 관리자 IP에 허용되어 있다.
- 두 EC2의 SSH는 지정 IP /32에서만 허용되어 있다.
- Django 보안그룹은 현재 SSH만 허용한다. 웹/API ingress 경로는 미구성이다.

## 로컬 및 저장소 상태

- Docker Compose v5.5.1은 사용 가능하지만 Docker Linux 엔진이 실행 중이지 않아
  실제 이미지 빌드와 컨테이너 기동은 검증하지 못했다.
- `deploy/docker-compose.django.yml`, `deploy/docker-compose.ai.yml`의 분리 배포
  구성을 기준으로 준비한다. AI 주소는 배포 시 실제 private IP/DNS를 다시 조회한다.
- `.github/workflows/deploy.yml`의 ECR push와 EC2 배포는 아직 echo placeholder다.
- Nginx 설정은 HTTP 80만 수신한다. Compose의 443 매핑만으로 HTTPS가 제공되지 않는다.
- 로컬 환경의 키/DB 비밀번호를 이미지나 배포 문서에 복사하지 않는다.
- 두 분리 Compose의 `config --quiet`는 임시 이미지·AI URL·토큰을 프로세스에
  주입한 문법 검사에서 종료 코드 0으로 통과했다. 단, 기존 `.env`에서 미정의
  `h` 변수 치환 경고가 발생했다. `$`가 들어간 값을 Compose가 변환할 수 있으므로
  운영 환경 파일 작성 시 해당 리터럴 값을 작은따옴표로 감싸고 경고 없이 재검증해야 한다.
  이 검사는 운영 값의 유효성이나 컨테이너 정상 실행을 보장하지 않는다.
- `aws-preflight.ps1`을 실제 계정으로 실행해 읽기 전용 조회 성공을 확인했다.

## 재점검 명령 (저장소 루트 PowerShell)

```powershell
$awsTool = Join-Path $env:USERPROFILE 'Documents\ChatGPT\SKN-4th Project\aws-cli-tool\Amazon\AWSCLIV2\aws.exe'
& $awsTool sts get-caller-identity --profile resume-review-rds --region us-east-1
# 세션이 만료된 경우에만 실행
& $awsTool login --profile resume-review-rds --region us-east-1
# 읽기 전용 인벤토리. 일부 조회 실패 시 종료 코드 1.
& .\deploy\aws-preflight.ps1 -AwsExecutable $awsTool
```

## 다음 배포 순서

1. 배포 커밋, 웹/API 도메인 또는 CloudFront `/api/*` 라우팅, 배포 대상 DB 확정.
2. ECR 2개와 최소 권한 EC2 역할 준비. GitHub 자동 배포 사용 시 OIDC trust를
   해당 저장소·배포 브랜치로 제한한다.
3. Docker 엔진 실행 후 Django/AI 이미지 빌드 및 React 테스트·배포 빌드 수행.
4. 두 EC2에 각자의 런타임 환경 주입. Django의 4개 AI URL은 AI private 주소로
   설정하고, 공유 토큰은 양쪽에 동일하게 제공한다.
5. HTTPS·웹 배포·API ingress 설정 후 ECR push, EC2 기동 및 Compose 배포.
6. DB 백업과 migration 계획을 확인한 뒤 필요한 migration을 별도로 수행한다.
7. 로그인, 챗봇, 공부방 노트, 채용 추천, 첨삭 v2 및 업로드를 실제 화면에서 검증.

이번 점검은 AWS 리소스를 생성·기동·변경하거나 DB migration을 실행하지 않았다.
AWS 인증 성공과 실제 서비스 배포 완료는 별개의 상태다.
