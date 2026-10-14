# Existing Requirement Profile Wiring — 2026-10-01

브랜치: `feature/resume-review-quality`. 이번 변경은 backend/domain 연결부에 한정한다. 기존 미커밋 작업은 보존했으며 커밋·푸시는 수행하지 않았다.

## A. Root Cause

기존 공고 분석 캐시는 재사용 가능한 JobRequirement 배열이지만, 새 Application 생성 경로는 명시적으로 받은 profile key만 연결했다. RecruitRole snapshot이 있어도 동일 공고의 기존 profile을 자동 조회하지 않았다. Planner는 profile context를 수용할 수 있었으나 Phase 4B Writer는 별도 ContextMaterial만 받았으므로 상세 요구사항이 마지막 단계까지 전달되지 않았다. 일반 source_path 탐색도 객체 문자열 경로 중심이라 배열 항목을 안정적인 requirement ID로 참조할 수 없었다.

또한 RecruitRole 배열 검증의 import가 잘못되어 있었고 Local E2E 생성 경로는 role content_hash를 posting snapshot_hash로 대체하고 있었다.

```text
기존 job_requirement_profiles.requirements (변경·재분석 없음)
  ↓ 기존 requirement_cache_key(job_id, posting snapshot_hash)
Application.requirement_profile (기존 FK)
  ↓ target_context.requirements + requirement_profile_source
Planner (RecruitRole snapshot도 병렬 유지)
  ↓ 저장된 story_focus / 선택 Evidence / 질문
build_requirement_materials (관련 요구사항 최대 3개/문항)
  ↓ ContextMaterial + RequirementSource (전체 6필드)
Writer sentence.support_refs (type=target_context, id=requirement ID)
  ↓ deterministic source checks + 기존 semantic verifier
ApplicationAnswer draft (기존 저장 계약)
```

## B. Import Fix

`lms_api/lms/recruit_role_store.py`의 배열 검증 import를 실제 정의 위치인 `app.job_requirements.JobRequirement`로 수정했다. `app.models` re-export는 추가하지 않았다. 문자열 배열 fixture 계약과 상세 JobRequirement 배열 계약을 모두 유지한다.

## C. Profile Auto-link

신규 `lms_api/lms/requirement_profile_link.py`는 기존 ORM profile 조회와 검증만 수행한다. `Application` 생성 시 실제 job_id와 target snapshot_hash가 있으면 기존 `requirement_cache_key()`로 찾고 기존 FK에 연결한다. 명시적 profile key도 동일 identity 검증을 거친다.

- 기존 profile 있음: 연결만 수행; 배열 변환·저장·재분석 없음.
- 없음: null 유지; extractor 호출 없음.
- 명시적 profile 없음/다른 snapshot: 입력 오류.
- RecruitRole의 job_id와 Application job_id가 다름: 입력 오류.
- RecruitRole job_id가 있고 실제 posting hash가 제공된 경우: 해당 job_id를 사용할 수 있다.
- role-only이고 posting hash가 없는 경우: profile 연결을 추측하지 않는다.
- 기존 Application에 대한 동일 생성 요청 재시도: 기존 Application을 그대로 반환한다. 나중에 생긴 profile을 자동 backfill하지 않는다.

캐시 identity는 기존 normalized job_id + snapshot_hash 앞 24자리 + req-v1이다. 이 로직을 복제하지 않았다.

## D. Snapshot / Content Hash Separation

profile 조회는 posting snapshot_hash 기준이다. RecruitRole 버전은 기존 content_hash/role_version 기준이며 서로 다를 수 있다. Local E2E의 가짜 job ID 및 content_hash→snapshot_hash 대입을 제거했다. 실제 job ID와 `job_snapshot_hash`가 제공될 때만 profile lookup이 가능하다. RecruitRole snapshot은 유지하며 요구사항으로 덮어쓰지 않는다.

## E. Planner Target Context

`application_question_store._target()`에서 FK profile의 현재 Application identity와 배열을 검증한 후 원래 requirements 전체를 전달한다. `requirement_profile_source`에 profile key, job ID, 전체 snapshot hash, req-v1을 함께 전달한다. RecruitRole requirements는 별도 보조 context로 남는다.

Planner prompt에는 structured requirements가 상세 provenance의 기준이고 role requirements는 보조 context라는 역할만 명시했다. 공고 요구사항은 Applicant Evidence가 아니며 우대를 필수로 확대하지 않도록 했다. 새 Agent/LLM 호출은 없다.

## F. Writer Adapter

신규 `app/application_writing/requirement_context.py`의 pure adapter가 Writer 직전에 ContextMaterial을 만든다. DB/LLM을 호출하지 않는다.

선별에는 질문 원문, 저장된 story_focus, 선택된 core/supporting/result Evidence만 사용한다. label/quote와의 lexical relevance 기준으로 최대 3개를 전달한다. must > preferred 고정 점수는 사용하지 않는다. 전체 요구사항 원본은 Planner target context에 남고 Writer에는 필요한 일부만 전달한다.

eligibility는 해당 자격을 직접 묻는 문항에서만 기본적으로 허용한다. 과거 캐시가 kind=skill 기본값을 담을 가능성에 대비하여 기존 Python `classify_requirement()`를 선택 방어에만 재사용한다. 저장된 kind 및 원본 6필드는 수정하지 않는다.

## G. Provenance Contract

ContextMaterial의 material_id는 requirement ID다. source_type은 target_context로 제한하며 논리 경로는 `['requirements', 'id:req-1', 'posting_quote']`다. 배열 index를 identity로 사용하지 않는다.

추가 optional `RequirementSource` 계약:

```text
application_id
profile_key
snapshot_hash
prompt_version
requirement { id, group, label, posting_quote, kind, kind_basis }
requirement_hash (전체 requirement 필드의 deterministic digest)
```

Writer와 semantic verifier에 원문 quote 및 전체 requirement가 전달된다. 기존 support_ref naming을 유지하여 `type=target_context`, `id=req-1`로 참조한다. 동일 requirement를 여러 문항에서 사용할 수 있지만 같은 문항의 중복 material은 차단한다.

## H. Deterministic Validation

다음을 차단한다.

- 없는/중복 requirement ID, 빈 quote, 비배열 profile.
- Application/job/profile/version/snapshot identity 불일치.
- source_path, 원문 quote, normalized context, requirement 내용 또는 digest 변조.
- Applicant Evidence와 material ID 충돌 및 requirement를 evidence로 참조하는 시도.
- 승인되지 않은 support_ref.
- quote에 근거하지 않은 숫자/기술명: 기존 검사를 유지하되 requirement material의 근거는 label이 아닌 posting_quote로 사용한다.

정상 context가 없는 경우 빈 adapter 결과이며 새 분석을 트리거하지 않는다. 원본 배열 순서가 바뀌어도 ID resolver는 동일 항목을 찾는다. 다만 기존 전체 target hash freshness 계약상 저장된 분석/계획은 stale로 판정될 수 있으며 기존 재분석·재계획 경로를 거쳐야 한다. freshness 검사를 약화시키지 않았다.

## I. Semantic Validation

기존 semantic verifier에 문장/support_ref 및 RequirementSource를 전달한다. group/kind/posting_quote와 대조하여 preferred→must 및 협업→리더십 등 의미 확대를 검사하도록 짧은 계약 지시를 추가했다. 기존 조건부 rewrite 최대 1회 구조를 유지한다.

mock verifier로 우대→필수 실패와 차단 경로를 검증했다. 이는 verifier 연결 계약 검증이며 실제 LLM이 모든 의미 확대를 검출한다는 품질 증명은 아니다. 이번 작업에서는 실제 LLM을 호출하지 않았다.

## J. Tests Added

- `cover_letter_rag/tests/test_requirement_context.py`: import-independent pure adapter, 6필드/quote 보존, identity 변조, 배열 순서, eligibility, 최대 3개, applicant/target 분리, mock semantic 실패, 캐시 hit의 무추출·무저장 등 22개.
- `lms_api/lms/test_requirement_profile_wiring.py`: 배열 RecruitRole import, 기존 profile 자동 FK 연결, no-profile 무호출, S1/R9 분리, role/job mismatch, role-only, stale profile, source adapter, mock Planner→Writer→draft 저장 등 16개.
- `test_application_workspace.py`: 기존 explicit-profile fixture를 실제 cache key 계약에 맞게 수정.

## K. Existing Regression

실제 실행한 결과:

| 검증 | 결과 |
|---|---|
| requirement context + Writer + Planner + Resume Review v2 + tailored resume Python tests | 142 통과 |
| wiring + Writer + Local E2E + Application + Planner + RecruitRole + Experience local Django tests | 140 통과 |
| React 전체 회귀 | 44 files / 269 통과 |
| local `makemigrations --check --dry-run` | No changes detected |
| `git diff --check` | 통과 |

Backend 테스트는 standalone local settings와 격리 PostgreSQL test DB를 사용했다. mock E2E에서 target requirement support와 Applicant Evidence를 분리한 문장 생성 및 draft 저장까지 확인했다. 최신 연결부의 실제 브라우저/HTTP 서버 재시작 후 수동 검증은 수행하지 않았다.

## L. LLM Usage

실제 LLM 호출 0회, API input/output tokens 0. 기존 공고 extraction, 캐시 key, profile format, v1 requirement_map은 변경하지 않았다. 새 분석 pipeline/Agent는 없다.

## M. DB / RDS Usage

이번 구현 검증 중 RDS 연결·INSERT·UPDATE·DELETE·migrate는 없다. DB 검증은 loopback `127.0.0.1:55439`, 격리 local test DB에서만 수행했다. 테스트 fixture/draft 쓰기 및 테스트 DB 생성/삭제는 이 격리 환경에 한정한다. 새 migration 파일은 없으며 기존 0014까지의 모델을 사용한다. AWS 변경, secret 출력, React 변경은 없다.

이전 read-only 조사에서 확인된 RDS의 10 profile/93 requirements를 이번 작업에서 다시 조회하거나 변경하지 않았다.

## N. Remaining Risks

1. 호출자는 실제 posting snapshot_hash를 제공해야 한다. Role hash만 있으면 자동 연결하지 않으며 실제 job 조회/crawl fallback도 추가하지 않았다.
2. lexical relevance는 동의어를 놓칠 수 있다. 최대 3개는 보수적 제한이며 사람/소수 live 검증으로 관련 context 선택을 확인해야 한다.
3. 기존 profile 키는 hash 앞 24자리와 normalized job ID를 사용한다. 전체 snapshot hash를 별도 저장하는 스키마를 추가하지 않았으므로 기존 cache identity 이상의 외부 원본 증명은 아니다.
4. 기존 Application의 null FK는 자동 backfill하지 않는다. 이번 범위는 신규 생성 wiring이다.
5. 배열 재정렬에도 ID provenance는 안정적이나 기존 analysis/plan freshness는 보수적으로 재평가가 필요할 수 있다.
6. 새 의미 검증의 실제 모델 정확도는 미측정이다. 이전 Phase 4B W3 수정 후 live 재검증과 W1 사람 판정도 아직 별도 과제다.
7. 기존 Answer DB 저장 계약은 텍스트/draft 중심이다. 상세 runtime provenance를 별도 영속 audit column으로 저장하는 migration은 추가하지 않았다.
8. 이전 조사에서 RDS RecruitRole 테이블이 없었던 상태에 대해 이번 작업은 migration을 적용하지 않았다. 운영 준비 완료로 해석하면 안 된다.

## O. Go / No-Go

**GO — 별도 승인된 소수 Phase 4B live Writer provenance 검증으로 돌아갈 수 있다.** 연결 및 deterministic/backend 계약은 검증됐다. 실제 모델 문장 품질, 우대→필수 확대 검출, context relevance는 다음 소수 사례에서 사람이 확인해야 한다.

**NO-GO — 운영 전체 전환/실제 모델 품질 검증 완료 선언.** 이번 mock 결과를 실제 LLM 평가 결과로 간주하지 않는다. 기존 live artifact와 사람 판정은 변경하지 않았다.

### 이번 변경 파일 범위

```text
lms_api/lms/recruit_role_store.py
lms_api/lms/requirement_profile_link.py (신규)
lms_api/lms/application_workspace.py
lms_api/lms/application_question_store.py
lms_api/lms/local_resume_e2e_api.py
lms_api/lms/application_answer_writer.py
lms_api/lms/test_application_workspace.py
lms_api/lms/test_requirement_profile_wiring.py (신규)
cover_letter_rag/app/application_writing/models.py
cover_letter_rag/app/application_writing/requirement_context.py (신규)
cover_letter_rag/app/application_writing/engine.py
cover_letter_rag/app/application_writing/prompts.py
cover_letter_rag/app/application_planning/engine.py
cover_letter_rag/tests/test_requirement_context.py (신규)
cover_letter_rag/docs/requirement-profile-wiring-20261001.md (신규)
```

현재 git status의 다른 기존 변경/미추적 파일을 이번 작업에서 새로 작성한 것으로 계산하지 않는다.
