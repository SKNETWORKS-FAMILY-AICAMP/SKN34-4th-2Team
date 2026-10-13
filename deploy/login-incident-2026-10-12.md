> 과거 작업 기록입니다. 아래 상태·검증 결과는 기록 당시 기준이며, 현재 배포 상태를 보장하지 않습니다.

# 사전 배포 사이트 로그인 500 조치 — 2026-10-12

대상: https://d1zqs4mfabqpqs.cloudfront.net

## 관찰과 조치

- 가짜 계정으로 공개 `/api/login`의 HTTP 500을 재현했다. 반복 검사에서 500과 정상 인증 실패 응답 400이 섞여 나왔다.
- API 로그에 psycopg의 `discarding closed connection`이 남아 있었다. 새 Django 프로세스의 동일한 로그인 경로는 400으로 응답했다.
- 운영 DB 설정의 `CONN_HEALTH_CHECKS`가 False였다. `deploy/production_settings.py`에서 True로 설정해 풀에서 꺼낸 연결의 유효성을 먼저 확인하도록 했다.
- 운영 설정을 백업한 뒤 API Gunicorn에 HUP으로 정상 재로딩을 요청했다. 기존 배포 이미지는 유지했다. 사용자 데이터 수정, DB migration, 기능 코드 교체, 브랜치 병합은 하지 않았다.
- 최종 정식 배포는 검증된 develop을 main에 병합한 후 main 확정 커밋에서 진행한다는 기준을 유지한다. 이번 작업은 현재 사전 배포 환경의 설정 복구다.

## 검증

- Django 설정 검사 PASS. 운영 PostgreSQL 풀에 `ConnectionPool.check_connection`이 연결됨을 확인했다.
- 앱과 분리된 진단 프로세스에서 SELECT만 수행하는 전용 풀을 만들고, 그 프로세스 자신의 유휴 연결만 닫아 장애를 재현했다. 검사 OFF에서는 실패, ON에서는 새 연결로 교체 후 SELECT 성공. 기존 앱 연결이나 다른 사용자의 DB 세션은 종료하지 않았다.
- 수정 후 공개 로그인 엔드포인트의 무작위 가짜 계정 요청 6회 모두 400: 500 재발 없음. 실제 사용자 비밀번호를 읽거나 실제 사용자로 로그인하지 않았다.
- 설정 백업: `/opt/skn34-lms/deploy/production_settings.before-db-health-20261012.py`.
- 설정 적용 SSM: `d409f151-eb88-4a3a-a3bb-b9c30f39f3df` Success.
- 회귀 검증 SSM: `bf424aa9-9b5d-4bbb-886a-597511d052b8` Success.

DB 또는 네트워크가 처음 연결을 끊은 원인 자체는 이번 증거만으로 특정하지 않았다. 이번 수정은 닫힌 연결을 재사용해 사용자 요청이 실패하는 경로를 방지한다.

참고: [Django 연결 검사 및 PostgreSQL 풀 문서](https://docs.djangoproject.com/en/5.2/ref/databases/).
