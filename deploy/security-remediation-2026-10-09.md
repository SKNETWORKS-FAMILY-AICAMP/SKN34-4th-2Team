> 과거 작업 기록입니다. 아래 상태·검증 결과는 기록 당시 기준이며, 현재 배포 상태를 보장하지 않습니다.

# 보안 조치 결과 — 2026-10-09

## 운영 반영 완료

대상: https://d1zqs4mfabqpqs.cloudfront.net

사용자의 보안 문제 해결 요청에 따라 `Clone SKN34-4th-2Team repository` 채팅이 인증 구현을 맡았고, AWS 배포 채팅이 코드 검토·격리 Redis 통합 검증·운영 반영을 수행했다. 기존 보안 점검 보고서는 조치 전 이력이며 현재 상태는 이 문서를 기준으로 한다.

| 항목 | 결과 |
| --- | --- |
| 프로필 비밀번호 우회 | 일반 프로필에서 password, mustChangePassword, lastLoginAt 변경 차단 |
| 전용 비밀번호 변경 | 현재 비밀번호 필수 확인, 새 비밀번호 8~128자, 변경 후 새 토큰 발급 |
| 기존 세션 무효화 | DB 비밀번호 해시에 대한 HMAC 대조로 비밀번호 변경/관리자 초기화 후 기존 토큰 거부 |
| 갱신 토큰 | Redis Lua 원자적 회전, 이전 토큰 재사용 거부, 지연 재사용 감지 시 세션 폐기 |
| 로그아웃 | 해당 세션의 access/refresh 폐기. 로그아웃 중 갱신이 먼저 완료돼도 같은 세션 폐기 |
| 브라우저 경쟁조건 | 로그아웃·새 로그인·비밀번호 변경 후 오래된 refresh 응답이 토큰을 되살리거나 덮어쓰지 못하도록 revision 확인 |
| 로그인 보호 | 계정별 15분 8회, IP별 15분 300회 제한. 실패 메시지 통일 및 입력 길이 제한 |
| 접속 IP 신뢰 | CloudFront가 viewer.ip로 x-lms-client-ip를 덮어씀. 앱은 명시한 내부 nginx 서브넷에서 온 헤더만 신뢰 |
| 인증 저장소 장애 | Redis 장애 시 인증 503으로 차단, 운영에서 메모리 저장소로 우회하지 않음 |
| API 문서 | 운영 docs와 openapi.json 비활성화, 외부 404 확인 |
| 기록 증빙 파일 | MIME과 파일 시그니처 대조, PDF 파싱 검증 추가. 악성코드 검사나 모든 이미지의 완전한 디코딩 검증은 아님 |
| 실행 권한 | Django API·worker UID 10001, cap_drop ALL, no-new-privileges 적용 |
| 로그 크기 | API·worker Docker 로그 파일당 10MB, 3개 회전 |
| DB 삭제 보호 | ON 적용 완료 |
| DB 네트워크 | 사용처가 RDS 하나인 기본 SG의 자기 참조 전체 프로토콜 허용 규칙 제거. 앱/팀원 5432 규칙 유지 |

동시 갱신은 하나만 성공한다. 직전 토큰의 3초 이내 중복 요청은 거부하되 먼저 성공한 세션은 유지하고, 이후 재사용은 세션을 폐기한다. 이 유예 중에도 이전 토큰으로 새 토큰을 발급하지 않는다. 브라우저 한 탭의 중복 갱신은 단일 요청으로 합친다. 여러 탭 사이의 완전한 갱신 조율까지 제공하는 구현은 아니다.

기존 로그인 세션은 새 검증 정보를 갖고 있지 않아 재로그인이 필요하다. DB migration은 없으며 운영 사용자 데이터 변경, 실제 계정 비밀번호 변경·초기화는 수행하지 않았다. 정기 작업 beat는 계속 OFF다. 인증 Redis가 유실되면 기존 세션도 무효화되어 재로그인이 필요하다.

## 검증

- 최종 배포 이미지 안에서 DB/외부 네트워크 없는 보안 회귀 11개 PASS.
- 외부망 없는 실제 Redis에서 8개 동시 refresh 중 1개 성공, 로그아웃·비밀번호 변경·지연 재사용 후 토큰 거부, 로그인 제한 PASS.
- React refresh 경쟁조건 테스트 3개 및 기존 앱 회귀 28개 PASS. Django 설정 검사, React 타입 검사 및 운영 빌드 PASS.
- 새 이미지의 운영 전 사전 검사: 비특권 UID, JWT 키 길이, Redis 연결, DB SELECT 1 PASS.
- 실제 공개 주소에 무작위 `example.invalid` 가짜 계정으로 9회만 요청: 400 × 8 후 429. 실제 사용자 계정은 시도하지 않음.
- 비인증 bootstrap/me 및 잘못된 Bearer token은 401. docs/openapi.json은 404.
- Edge headless에서 로그인 화면 정상 렌더, 브라우저 오류 0, 운영 HTML과 로컬 보안 빌드 SHA-256 일치.
- CloudFront 캐시 무효화 `IE42205JEYMJHHM4O66NFDMSBX` Completed.
- 최종 API·worker running, RestartCount=0, UID 10001 및 권한 제한 확인. `.env`와 복구용 `.env`는 0600 유지.

모바일·Expo 코드도 새 인증 계약에 맞췄으나 의존성이 설치되지 않아 해당 앱의 타입/실기기 검증은 완료하지 못했다. 이번 배포 대상은 React 웹과 Django다. 실제 사용자 로그인부터 전체 업무 기능까지의 E2E 및 침해 포렌식은 이번 검증 범위가 아니다.

## 릴리스 및 복구

- API/worker 이미지: `lms-api@sha256:0e732660b3438f78212e567ccc6b65f09764ed578678f2ba887d22d0d08fac5a` (레지스트리 `711425439897.dkr.ecr.us-east-1.amazonaws.com`).
- ECR 태그: `security-20261009-0e732660b343`.
- 최종 스캔 플랫폼 digest: `sha256:7c8e5110ba58f01927d23b34c7701fafbb1f407b41224dafb471b51c1d8f5627`.
- 기존 배포 이미지에 검토한 인증 파일만 덧씌운 `deploy/security-overlay.Dockerfile`로 빌드했다. 동시 진행 중인 RAG/계산 규칙 변경은 포함하지 않았다. 파일별 해시는 `security-release-20261009.json` 참조.
- SSM 배포 명령: `9dc9d338-fcf6-4b46-b2ee-1b591ff6c14a` Success. 최종 확인: `580daa84-711a-4962-b48c-34f1d8524092` Success.
- EC2의 `/opt/skn34-lms/security-before-20261009`에 이전 `.env` 및 변경 전 배포 설정을 root 전용으로 보관했다. 배포 중 실패 시 이전 API/worker 이미지와 설정을 복원하도록 준비했고 이번에는 복구 없이 성공했다.
- 웹 S3의 기존 assets는 삭제하지 않았다. 이전 index.html 버전 ID: `SNTSmAIcx5Uta9lKOrHVYrmQ5yjHL3t3`. 이전 웹/API를 함께 복구하면 기존 인증 취약점도 다시 열리므로 긴급 복구 목적 외에는 사용하지 않는다.
- CloudFront API 함수: `skn34-lxp-api-client-ip`. `/api/*` viewer-request에 연결, 위조 헤더 덮어쓰기 AWS 함수 테스트 PASS 및 Deployed 확인.

## 남은 항목 — 해결 완료로 간주하지 않음

1. **OS 패키지 취약점**: API에 사용 가능한 안정판 업데이트(liblzma5)는 적용했으나 재스캔 HIGH 1건(zlib)은 남았다. AI 안정판 업데이트 검사에서는 갱신 가능한 패키지가 없었고 AI는 기존 이미지를 유지했다(HIGH 8/MEDIUM 2/LOW 2). Debian 공지상 [zlib](https://security-tracker.debian.org/tracker/CVE-2026-85091), [util-linux](https://security-tracker.debian.org/tracker/CVE-2026-76642), [gcc](https://security-tracker.debian.org/tracker/CVE-2026-95619)의 해당 안정판 수정 상태를 확인했으며 임의 소스 패치나 불안정 배포판 혼합으로 대체하지 않았다. 패키지 수정 제공 여부와 실제 악용 전제는 계속 별도 검토가 필요하다. 자동 추적 작업을 생성한 것은 아니다.
2. **DB 백업 7일 연장**: AWS가 `FreeTierRestrictionError`로 거부했다. 실제 보관 기간은 **1일 유지**다. 무료 요금제를 유료로 전환하지 않았다. 삭제 보호만 별도 요청으로 적용했다.
3. **추가 운영 보완**: 일상 배포의 root 세션 대체, 지속적 감사/접근 로그 및 알림, 전체 Python/npm/nginx/redis/호스트 취약점 검사, 복구 시험은 아직 완료하지 않았다. AI의 실행 사용자 변경도 이번 릴리스에 포함하지 않았다.

위 잔여 항목 때문에 이 결과를 ‘모든 보안 문제가 해결됨’ 또는 ‘침해가 없음’으로 해석하면 안 된다.
