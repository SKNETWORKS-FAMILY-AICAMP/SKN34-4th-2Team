# Firebase 잔여 정리와 main 반영 전 기준

기준: develop `4e6b827` (2026-10-14). 현재 배포본 `77f32ae`와 구분한다.
이 변경은 저장소 정리이며 AWS 서버 설정·운영 DB·배포본을 변경하지 않는다.

## 이번 정리

- Django 프록시에서 쓰지 않는 Firebase Admin import를 구형 직접 인증/Firestore 기능 안으로 이동했다. API 주소, 요청·응답, 인증 검사와 DB SQL은 유지했다.
- `.env.example`의 “아무 Firebase 프로젝트 이름이나 필요하다”는 설명을 바로잡았다. 기본 v2/PostgreSQL 경로는 필요 없으며, 구형 직접 토큰 인증은 실제 Firebase 설정이 필요하다.
- 중복 psycopg 요구사항을 제거하고 SDK를 유지하는 이유를 명시했다.
- Firebase/Flutter 설정을 Docker 빌드 입력에서 제외했다. 런타임이 쓰는 SQL과 CI 테스트 파일은 남겼다.
- React 초기 목업 설명과 Firebase Functions·시드 문서에 현재 운영 경로와 다른 보관 자료임을 표시했다.
- Firebase SDK import 금지 상태의 통합 앱/공부방 프록시 검사와 구형 토큰 검증 회귀 테스트를 추가했다. CI에도 Firebase 경계 및 첨삭 적용/되돌리기 테스트를 포함했다.

## 바로 삭제하면 안 되는 이름과 파일

| 잔여 | 실제 역할 / 유지 이유 |
| --- | --- |
| `users.firebase_uid`, React `firebase_uid` 매핑 | PostgreSQL의 사용자 식별자. 이력서 소유권·기수 접근·학습 기록 연결에서 사용한다. 컬럼/응답 이름 변경은 별도 데이터 및 API 마이그레이션이 필요하다. |
| `chatbot/firebase_student_context.py` | 실제 내용은 PostgreSQL/Redis/S3 조회이며 챗봇과 warmup, 테스트에서 import한다. 파일명은 오래됐지만 삭제 대상이 아니다. |
| `app/firebase_gateway.py`, `FirestoreResumeReviewRequest` | PostgreSQL 첨삭에서도 공유 메서드와 요청 모델을 사용한다. 상속·import·OpenAPI 스키마까지 확인한 뒤 별도 이름 정리를 해야 한다. |
| `scripts/firestore_to_postgres/` | 이주 이력과 SQL. `jobs_schema.sql`은 AI Dockerfile이 복사하고 공고 저장소가 실제로 사용한다. |
| `firebase-admin`, Google 라이브러리 | 직접 Firebase 토큰 인증, v1/Firestore 적용·되돌리기, 구형 공부방, 공유 도구가 아직 사용한다. 공부방은 구형 서비스의 공통 함수도 재사용하므로 패키지 전체를 제거하면 안 된다. |
| Firebase를 언급하는 기술 스택·과거 평가 결과 | 실제 과거 프로젝트나 테스트 자료의 내용일 수 있으므로 문자열 일괄 치환 대상이 아니다. |

## 이후 별도 변경으로 다룰 부분

1. 구형 Flutter·직접 Firebase 인증·v1·Firebase 시드 도구를 실제로 폐기할지 결정한다. 현재 React가 사용하지 않는다고 해서 모든 외부 소비자가 없다는 근거는 되지 않는다.
2. 폐기 범위를 정하면 라우트/서비스와 Google 의존성을 제거한다. PostgreSQL 서비스가 가져오는 공통 공부방 함수부터 분리해야 한다.
3. 파일/클래스명 정리는 import 및 mock patch 경로와 함께 바꾸되, DB 사용자 ID와 API 필드 변경을 같은 변경에 섞지 않는다.

테스트·설계 문서는 main에 유지한다. Git 저장소에 있는 파일과 실제 Docker/S3 배포 산출물은 다르다. 기능에 필요한 파일만 빌드에서 선택하고, 비밀값·로컬 로그·평가 산출물은 제외한다.

## main 전 확인

정리 브랜치의 CI를 통과시킨 뒤 develop에 반영하고, 그 정확한 커밋을 검증 환경에 배포한다. 로그인, 챗봇, 공부방, 첨삭 생성·이어하기·적용·되돌리기, 공고 맞춤 지원을 확인한 동일 버전을 main으로 승격한다. 이번 모의 회귀 테스트는 실제 계정/실제 LLM의 종단 간 시연 검증을 대신하지 않는다.

## 이번 변경의 검증 결과

로컬 모의 회귀 테스트 148개 통과(통합 앱 Firebase import 차단, 인증 경계, 구형 토큰 검증, 첨삭 엔진·문항 생성·적용/되돌리기, 공부방 서비스 포함). actionlint 및 git diff --check 통과. 운영 DB/외부 LLM을 사용하지 않았다. 전체 Docker 이미지 재빌드와 배포 환경의 실제 계정 확인은 PR CI/후속 develop 배포에서 확인한다.
