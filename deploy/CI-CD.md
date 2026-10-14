# main CI/CD 운영

이 설정은 기존 Django EC2·AI EC2·S3·CloudFront를 사용한다. 새 서버는 만들지 않는다.

- develop/main 대상 PR 및 develop push: 배포 스크립트 테스트, React 테스트·빌드, API/AI 이미지 빌드·회귀 테스트.
- main push 및 main에서 수동 실행: 위 검증 산출물을 그대로 ECR에 push하고 digest로 EC2에 배포한다. React는 S3 업로드 후 CloudFront를 갱신한다.
- main 이외의 수동 실행은 검증만 한다. 현재 기본 브랜치가 main이므로 workflow가 main에 들어가기 전에는 UI의 수동 실행이 제공되지 않을 수 있다.
- 원격 GitHub Actions 권한: OIDC, 저장소 `SKNETWORKS-FAMILY-AICAMP/SKN34-4th-2Team`의 `refs/heads/main`만 AWS 역할을 사용할 수 있다. 장기 AWS 키나 EC2 SSH 키를 GitHub에 저장하지 않는다.
- 역할: `arn:aws:iam::711425439897:role/skn34-github-main-deploy`. 정책은 `iam/github-main-*.json`. 기존 ECR 2개, EC2 2대의 SSM 명령, 웹 버킷, CloudFront invalidation에 한정한다.

## 배포 순서

1. 테스트를 통과한 동일 이미지 산출물을 ECR에 push하고 digest를 고정한다.
2. 각 서버의 현재 이미지·환경 파일을 `/opt/skn34-lms/releases/<commit>-<run>-<attempt>/`에 권한 제한 백업한다.
3. 새 이미지를 pull하고 Django `migrate --check`로 DB 스키마가 이미 준비됐는지 확인한다. 자동 migration은 하지 않는다.
4. worker의 새 작업 수신을 잠시 멈추고 처리 중인 작업이 끝나기를 기다린다.
5. AI → API/worker 순서로 교체한다. 준비 응답과 worker 작업 등록 확인 후 Nginx를 갱신하고 worker 수신을 재개한다.
6. React 파일을 올린다. 기존 해시 자산은 삭제하지 않고 index를 마지막에 교체한다.
7. CloudFront 갱신 완료, 공개 index 일치, 익명 API 401 응답을 확인한다.

## 유지되는 운영 설정

서버에 적용된 Compose 오버레이와 production_settings.py를 그대로 사용한다. 이번 파이프라인은 운영 설정 파일 업데이트를 자동 적용하지 않는다. 해당 파일 변경은 별도 검토·반영이 필요하다.
`.env`는 이미지 선택 키만 변경한다. OpenAI/GitHub/DB 비밀값, AI 캐시, 비활성화된 정기 작업을 유지한다. 현재 공부방 GitHub 인증과 자동 출제는 시연 범위에서 제외되어 있다.

## 실패와 복구

- 확인된 배포 실패: 시도한 두 서버 모두 이전 이미지로 복구하고 worker 수신을 재개한다. 업로드 중 덮어쓴 기존 비해시 웹 파일도 복원하고 CDN을 다시 갱신한다. 새로 추가된 파일과 해시 자산은 남겨둔다.
- DB는 자동 변경하지 않아 이전 이미지로 되돌리는 동안 schema undo를 하지 않는다.
- SSM 결과가 장시간 불명확한 경우에는 진행 중인 적용과 복구가 충돌하지 않도록 자동 복구를 시작하지 않는다. `release-result.json` 및 Actions 요약의 명령 ID를 확인한 후 수동 복구한다.
- Actions 강제 종료·러너 유실에서는 자동 복구가 보장되지 않는다. EC2의 위 백업 경로와 SSM 이력으로 확인해야 한다.
- 배포는 순차 교체이므로 잠깐의 요청 실패 가능성이 있으며 무중단 구성이 아니다.
- 커밋의 기능 검증이 끝난 다음 develop→main을 병합한다. 이 CI/CD PR 자체는 main 기능 최종 배포 승인을 의미하지 않는다.

## 검증 범위

PR의 verify job은 AWS 운영 권한 없이 실행된다. main 배포 및 OIDC 실제 인증의 최종 확인은 최초 main 배포 시 수행된다. 부분 회귀 테스트와 상태 확인은 실제 사용자 첨삭 품질·전체 화면 동작 검증을 대체하지 않는다.

## 실제 GitHub OIDC 식별자

이 저장소의 현재 토큰 `sub`에는 이름뿐 아니라 조직/저장소 ID가 포함된다.
`repo:SKNETWORKS-FAMILY-AICAMP@169222902/SKN34-4th-2Team@1373784236:ref:refs/heads/main`

AWS 신뢰 정책은 위 값과 `aud=sts.amazonaws.com`을 정확히 일치시킨다. 이름만 있는 과거 형식으로 되돌리면 `AssumeRoleWithWebIdentity`가 거절된다. 다른 저장소에 적용할 때는 그 저장소의 실제 식별자를 확인하며, 오류를 피하려고 와일드카드로 범위를 넓히지 않는다.
