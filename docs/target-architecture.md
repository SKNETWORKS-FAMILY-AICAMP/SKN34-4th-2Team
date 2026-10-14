# LMS 목표 아키텍처

웹/앱은 같은 JWT(Access 15분, Refresh 7일)로 Django Ninja `/api`를 호출한다.

- HTTP: **Django Ninja** (`lms/api.py`). OpenAPI: `/api/docs` (DEBUG)
- 인증 헤더: `Authorization: Bearer <access>`
- 갱신: `POST /api/token/refresh` `{ "refresh" }`
- 로그인: `POST /api/login` `{ email, password }` → `{ access, refresh, uid, role, mustChangePassword, user }`
- 에러 포맷: `{ "detail" }` 또는 `{ "message" }`
- Query 키: `['bootstrap']`, `['me']`, `['qual-exams']`
- 서버 상태: TanStack Query. 클라 상태: Zustand(세션 토큰, 장바구니). 테마/투어는 localStorage.
- Access는 메모리, Refresh는 sessionStorage.
- 계정 소스는 unmanaged `users` 테이블. Django `auth_user` / dj-rest-auth 없음.
- JWT 발급/검증은 SimpleJWT, HTTP 라우팅은 Ninja (DRF APIView 미사용).
- 웹 API base: `VITE_API_BASE` (기본 `/api`). 배포 시 도메인에 맞게 빌드. 자세한 표는 [deploy-checklist.md](deploy-checklist.md).
