# Application Workspace — Phase 3

## A. Changed Files

이번 단계에서 변경한 파일:

- `lms_api/lms/models.py`: Applications managed model 추가. 기존 Experience/Evidence/Binding 모델은 변경하지 않음.
- `lms_api/lms/migrations/0012_application_workspace.py`: additive migration.
- `lms_api/lms/application_workspace.py`: 공통 서비스와 Resume-first / Job-first adapter.
- `lms_api/lms/test_application_workspace.py`: workspace 및 실제 PostgreSQL 테스트.
- `lms_api/lms/test_resume_experience_postgres.py`: 기존 migration 테스트 종료 시 실제 graph leaf 복구. 테스트 schema 격리만 변경.
- 이 보고서.

기존 미커밋 v2/persistence 작업은 보존했다. v1 prompt/Writer/API/React는 변경하지 않았다.

## B. Application Model

`public.applications`:

| Field | Type / 정책 |
|---|---|
| id | UUID PK |
| user | Users FK, PROTECT |
| base_resume | 필수 Resumes FK, PROTECT |
| tailored_resume | nullable Resumes OneToOne, SET_NULL |
| job_id | nullable 외부 stable string, max 255 |
| role_context_id | nullable 외부 stable string, max 255 |
| requirement_profile | nullable JobRequirementProfiles FK, SET_NULL |
| target_snapshot | 크기 제한된 버전/표시명/수동 설명 object |
| entry_source | resume_first / job_first / manual |
| status | draft / in_progress / ready / submitted / archived |
| carried_from | nullable self FK, SET_NULL |
| idempotency_key | 필수 string, max 128 |
| request_hash | SHA256 정규화 요청 identity |
| created_at / updated_at | 자동 timestamps |

DB 제약: user+request UNIQUE, tailored document UNIQUE, 자기 자신 ancestry 금지,
entry/status CHECK, base != tailored CHECK. user+status index 추가.

Job/role은 외부 참조다. jobs는 raw SQL 관리이고 recruit_roles는 확정되지 않았으므로
새 unmanaged Job model/FK를 만들지 않았다. Job 삭제 후 job_id는 과거 대상 locator로 남는다.
Base resume는 workspace의 문서/증거 연결 기준이므로 보호한다. 삭제하려면 연결된 workspace 처리 정책을 먼저 결정해야 한다.

Django SET_NULL은 ORM 삭제 정책이다. 기존 raw SQL DELETE는 자동 SET NULL을 수행하지 않아 FK 오류로 안전하게 실패할 수 있다.

## C. Migration Graph

현재 코드 graph는 단일 leaf 0011이었으며 다음 migration을 추가했다.

```text
0010_submission_task_questions
  → 0011_resume_experience_evidence
  → 0012_application_workspace
```

기존 번호 변경과 merge migration은 없다. Production RDS에는 적용하지 않았다.
격리 PostgreSQL test database에서 apply → rollback to 0011 → reapply를 검증했다.
rollback은 applications 행을 삭제하므로 운영 데이터 무손실 rollback을 의미하지 않는다.

## D. Application Identity

같은 user+idempotency_key는 같은 Application이다. entry_source는 request hash에서 제외했다.
같은 key로 다른 base/target/version/ancestry를 요청하면 ValueError로 차단한다.
explicit application_id reopen은 소유권과 전달된 base/job/role의 일치를 검증한다.

user/job만으로 자동 합류시키지 않는다. 다른 key는 재지원/다른 목적의 별도 workspace가 될 수 있다.
호출자는 UI 작업당 key를 한 번 생성하고 retry와 동일 작업의 다른 entry에서 재사용해야 한다.
key/application_id가 공유되지 않은 두 작업을 임의로 동일 workspace라고 추정하지 않는다.

## E. Resume-first Flow

기존 production: Resume → 추천 → 공고 선택 → v1 tailored API.

추가한 opt-in adapter:

```text
resume_first_application(base, optional job/version, request key or application id)
  → create_or_open_application
  → optional ensure_tailored_resume
  → Application
```

`start_tailoring=True`면 workspace 생성/열기 후 맞춤 사본을 연결한다.
production route는 아직 교체하지 않았다. 서비스 연결 완료이지 React E2E 완료는 아니다.

## F. Job-first Flow

기존 production: Job → Resume 선택 → v1 tailored API.

추가한 `job_first_application`은 E와 동일한 `_enter_application` 및 core service를 호출한다.
entry_source는 최초 생성 시 analytics metadata일 뿐이다. Writer/selection/validation 분기는 없다.

## G. Tailored Resume Reuse

Application 생성 자체는 copy를 만들지 않는다.
`start_tailoring=True` 또는 `ensure_tailored_resume`에서 lazy copy한다.
Application row lock 내에서 기존 FK가 있으면 재사용하므로 동시 호출도 한 사본만 만든다.

기존 stable-item Binding copier와 ResumeTailorings metadata 구조를 재사용한다.
Application별 가변 문서를 분리하기 위해 v1 global base/job/hash cache의 사본을 여러 workspace가 공동 편집하지 않는다.
이를 위한 작은 ORM copy 동작만 추가했으며 새 AI Writer는 없다.

기존 owned copy는 `attach_tailored_resume`로 연결할 수 있다.
base/job/hash 일치와 다른 workspace에 미연결 상태를 검사한다.
실패하면 사본/metadata/Binding/FK 변경을 transaction 전체에서 rollback한다.

## H. Experience/Evidence Sharing

실제 fixture row count:

| 상태 | Resume | Experience | Evidence | Binding |
|---|---:|---:|---:|---:|
| workspace 생성 전 | 1 | 1 | 1 | 1 |
| workspace 생성 후 | 1 | 1 | 1 | 1 |
| 첫 tailoring 후 | 2 | 1 | 1 | 2 |
| 동일 workspace tailoring 재요청 | 2 | 1 | 1 | 2 |

다른 workspace는 별도 tailored document를 갖지만 동일 Experience를 참조한다.
`application_evidence`는 base Binding → 최신 active Evidence만 읽는다.
공유 Experience의 정정은 A/B 양쪽의 다음 조회에 반영된다.
이미 적용된 Resume text는 자동 수정하지 않는다.

## I. Jobless Application

base만으로 create/open/tailor가 가능하다. role도 필수가 아니다.
manual description은 선택 사항이다. questions/answers 컬럼은 추가하지 않았다.

## J. Closed/Deleted Job Behavior

open/reopen은 Job API/loader를 호출하지 않는다.
존재하지 않는 job locator로도 저장된 workspace를 열 수 있음을 검증했다.
마감 상태를 조회하지 않으므로 마감 후에도 동일하다.
실제 crawler/Job 삭제 API는 호출하지 않았다.
requirement profile을 ORM으로 삭제해도 workspace와 compact snapshot이 남음을 검증했다.

## K. Target Snapshot / Version Strategy

job target은 snapshot_hash, role target은 role_version이 필요하다.
기존 `JobRequirementProfiles.key`(job_id + hash prefix + prompt version)를 FK로 참조할 수 있다.
분석 결과를 workspace에 복사하거나 LLM으로 재분석하지 않는다.

허용 snapshot keys:

```text
snapshot_hash / analysis_version / company_name / job_title / role_version / description
```

값은 string이고 각각 최대 2000자다. Job 전체와 분석 결과를 무조건 복제하지 않는다.
hash/version은 당시 대상의 판본 추적용이며 원문 archive는 아니다.
원문을 완전히 복원하려면 외부 snapshot 보존이 필요하다.
profile과 외부 target의 정확한 내용 대응은 호출 adapter의 책임이다.

## L. Ownership / Idempotency

base/tailored/application/carry 소유권을 service에서 확인한다.
create는 User row lock + DB UNIQUE, tailoring은 Application row lock + OneToOne으로 보호한다.
carry는 새 descendant 생성만 허용한다. 기존 ancestry 수정 API가 없으므로 서비스 경로에서 cycle을 만들 수 없다.
raw SQL/admin이 서비스를 우회하는 cross-owner 참조나 여러 행 cycle까지 DB가 모두 막는 것은 아니다.

reopen은 business status를 변경하지 않는다.
과거 문서 열기와 archived 상태 해제를 혼동하지 않는다.

## M. PostgreSQL Tests

격리 환경: PG16 / localhost:55439 / test_resume_review_v2 / resume_v2_test_admin.
production 설정으로 이 테스트를 발견하면 DB 생성 전에 guard가 거부한다.

검증:

- migration apply/rollback/reapply.
- 기존 Resume/Experience/Evidence/Binding JSON row 보존.
- 실제 catalog: FK 5개, UNIQUE 2개, CHECK 4개, PK 1개.
- 병렬 동일 create 2건 → 같은 Application ID.
- 병렬 tailoring 2건 → 같은 Resume ID, Resume 2 / Binding 2.
- 소유권, request retry, copy rollback, 정정 공유, nullable target, 삭제 정책.

최종 workspace suite 19개(기능 16 + PostgreSQL 전용 3)가 통과했다.
테스트용 PostgreSQL 서버는 종료했다.

## N. Existing Regression Tests

- 통합 Django: workspace 18 + 기존 persistence 32 + mocked resume write/delete 5 = 55개 통과.
- 최종 adapter tailoring test 추가 후 workspace 19개 별도 재실행 통과.
- offline v2 core 33 + 기존 tailored service 7 = pytest 40개 통과.
- makemigrations --check --dry-run: No changes detected.
- migrate --plan: 0012 Create model Applications만 표시.
- git diff --check 통과.

LLM 호출 0회. Production RDS 쓰기 0회.
55개 전체 회귀 suite는 마지막 adapter 변경 전에 실행했고, 그 변경 후에는 영향 범위 workspace 19개를 다시 실행했다.

## O. Issues Found / Fixes Made

1. v1 cached copy를 workspace끼리 공유하면 문서 isolation이 깨진다. workspace-scoped copy와 OneToOne attachment로 분리했다.
2. 기존 migration test가 종료 시 schema를 0011로 고정했다. 현재 graph leaf를 복구하도록 변경했다.
3. catalog 테스트가 CHECK 수를 5개로 잘못 예상했다. 실제 정의 4개로 수정하고 재검증했다.
4. source hash serialization을 기존 gateway의 ensure_ascii=False와 일치시켰다.
5. SQLite unit-test settings는 migration을 비활성화하므로 migration 생성은 격리 PostgreSQL settings로 수행했다.

## P. Remaining Risks

1. production API/React 연결은 미실시. 실제 화면 E2E 완료로 표시하면 안 된다.
2. 새 extraction pipeline은 없다. reader는 inactive Evidence를 재생성하지 않는다. 향후 extraction 연결 전 같은 Experience의 전체 이력과 semantic reconciliation이 필수다. 현 테스트는 조회에 따른 resurrection 부재를 검증하며, 임의 LLM paraphrase의 의미 중복 판별을 보장하지 않는다.
3. 기존 raw SQL Resume delete는 Application FK 정책에 대한 명시적 처리가 필요하다. 현재 안전하게 실패하지만 deletion UX까지 개선하지 않았다.
4. Binding이 없는 legacy 항목은 기존 stable identity 초기화가 필요하다. Application 생성은 Experience를 임의 생성하지 않는다.
5. recruit_roles 구체 schema가 확정되면 external reference/version adapter를 정식 매핑해야 한다.
6. 외부 Job snapshot/profile 보존과 내용의 진위는 workspace 서비스 보장 범위 밖이다.
7. application_evidence는 Experience마다 active query하므로 N+1 가능성이 있다. 이번 속도 최적화 범위에는 넣지 않았다.
8. Production RDS에 0011/0012를 적용하지 않았다. 배포 전 graph와 실제 공용 DB 상태를 다시 확인해야 한다.

## Q. Go / No-Go

GO: 검증한 core service를 기준으로 ApplicationQuestion / ApplicationAnswer의 독립 설계·격리 구현으로 진행 가능하다.

NO-GO: production v1 전면 교체, 현 상태를 React E2E 완료로 취급하는 것.

다음 Question Analyzer/Planner에서도 Job/Role requirements를 applicant Evidence로 저장하지 않는다.
