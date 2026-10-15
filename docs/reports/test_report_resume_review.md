# 이력서 첨삭 테스트 보고서

작성일은 2026-10-14이며 기준 코드는 `a9e6ffb` 작업 트리이다. 공부방·복습 연습장은 이번 AI 검증 대상에서 제외한다. 단위 테스트, 실제 모델 호출, 화면 검증을 구분하며 서로 다른 범위의 결과를 하나의 정확도로 합산하지 않는다.

## 테스트 계획

3차의 [첨삭 테스트 10개 파일](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/tree/main/cover_letter_rag/tests)을 변경하지 않고 현재 코드에 실행한다. 현재 코드의 회귀 테스트와 추가된 v2 엔진의 실제 모델 호출도 별도 확인한다. 사실 보존, 질문·근거 연결, 선택 적용, 버전 충돌과 저장 권한을 검증한다.

| 범위 | 결과 | 의미 |
| --- | --- | --- |
| 현재 Python 회귀 | 1,006/1,006개 통과 | 모델 응답은 대체하며 일부 공고 저장소는 격리 PostgreSQL을 사용한다. |
| 3차 원본 테스트 | 227개 중 211개 통과·16개 실패 | 이전 계약과의 호환성 실패를 유지한다. |
| 실제 v2 첨삭 | 10개 처리 완료 | READY 6개·UNCHANGED 3개·NEEDS_EVIDENCE 1개이다. |
| Django 경험 저장 | 11개 통과 | 경험 저장·권한·상태 처리를 확인한다. |
| React 첨삭 | 101개 통과 | 공고 코치 21개를 제외한 첨삭 화면 테스트이다. |

3차 README의 127개는 당시 실행 기록이다. 이번에 가져온 main 스냅샷의 동일 테스트 파일들은 227개를 수집하므로 과거 건수와 현재 건수를 혼용하지 않는다. 원본 스냅샷과 파일별 blob 해시는 이 문서의 ‘3차 테스트 원본’에 기록한다.

## 실행과 중복 집계

현재 `cover_letter_rag/tests`를 pytest로 실행했다. 첫 실행에서 DB 접근 오류가 난 공고 연계 테스트를 격리 PostgreSQL로 다시 실행했으며, 동일한 테스트 식별자를 대체해 1,006개로 집계했다. 재실행 63개를 더해 1,069개로 표시하지 않는다.

실제 v2 검증은 기존 `evaluation/v2_cases.json`의 합성 경험·질문·답변 10개를 `ReviewEngineV2`에 전달한다. 모델은 `gpt-6-luna`이며 총 30회 호출했다. 엔진 상태를 기록했으며 학생 저장본을 수정하지 않았다. 결과 상태는 엔진 자체 판정이며 사람이 첨삭 품질을 채점한 합격률은 아니다.

## 실제 모델 케이스

| 케이스 | 확인 목적 | 엔진 상태 |
| --- | --- | --- |
| 01_procedure_dump | 작업 나열을 근거 중심으로 구성 | READY |
| 02_keep_technical_signal | 기술 근거 유지 | READY |
| 03_mostly_duplicate | 중복 정보 구분 | UNCHANGED |
| 04_action_without_result | 결과 없는 수행 사실 처리 | READY |
| 05_confirmed_result | 확인된 결과 반영 | READY |
| 06_team_vs_self | 팀 성과와 개인 역할 구분 | READY |
| 07_no_or_unknown | 부정·모름 답변 처리 | READY |
| 08_uncertain_claim | 불확실한 주장에 추가 근거 요구 | NEEDS_EVIDENCE |
| 09_job_only_technology | 공고에만 있는 기술을 경험으로 추가하지 않기 | UNCHANGED |
| 10_already_good | 충분한 문장에 불필요한 수정 제한 | UNCHANGED |

## 3차 호환성 실패

| 분류 | 건수 | 원인 |
| --- | --- | --- |
| health 모델 기대값 | 1개 | gpt-5.6-luna를 기대하지만 현재 gpt-6-luna를 반환한다. |
| 공고 저장소 fixture | 10개 | 기존 SQLite fixture를 현재 PostgreSQL 저장소로 읽을 수 없어 unavailable·503을 반환한다. |
| FirebaseGateway fixture | 1개 | 읽기 전용 _db 속성에 이전 fixture가 직접 값을 설정한다. |
| 맞춤 이력서 fixture | 4개 | 가짜 Gateway가 추가된 purpose 인자를 받지 못한다. |

이전 테스트가 실패했다는 사실을 보존한다. fixture 불일치만으로 실제 권한 우회·저장 실패가 발생했다고 결론 내리지 않는다. 현재 권한·선택 적용 테스트 통과와 별도로 이전 계약의 변경을 검토해야 한다.

## 실제 입력·판정 예시

`08_uncertain_claim`은 기존 문장의 ‘모델 학습을 직접 수행해 검색 정확도를 높였다’는 주장을 검증한다. 사용자 답변은 ‘정확도는 수치로 비교하지 않아 좋아졌는지 모르며, 모델 학습은 팀원이 했고 본인은 검색 API 연결만 담당했다’는 내용이다. 엔진은 기존 성과·역할 주장을 대체 대상으로 분류하고 `NEEDS_EVIDENCE`를 반환했다. 사람의 문장 품질 평가를 통과한 의미는 아니다.

## 3차 테스트 원본

원본 기준은 [3차 저장소의 고정 스냅샷](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/tree/215dd15881c576576f5e09bd52af5c156eb981ad/cover_letter_rag/tests)이며 커밋은 `215dd15881c576576f5e09bd52af5c156eb981ad`이다.

| 원본 파일 | blob SHA |
| --- | --- |
| `test_api.py` | `64e2a54684fa1088e6159c79f932bac1b43bd6d6` |
| `test_job_requirements.py` | `9aff01d6788a6d829479247cee12405c8da144d5` |
| `test_matching_handoff.py` | `534ceec8bbe9f016f4f417b64fbe35e01694d954` |
| `test_resume_apply.py` | `52d2bf71d0039d9b855c44dfd559df325d00f16c` |
| `test_resume_quality.py` | `cd7118cf48f57f30a69b428e39700b3de0f5f494` |
| `test_resume_review.py` | `95aba0c831792e1c434f1f33e358f02cfd03d9eb` |
| `test_review_workflow.py` | `4c7e5bca020e970727627201814706505cb0f6a4` |
| `test_star_checks.py` | `34adc4190ee2ded4f9c7d3684e53700abd57c389` |
| `test_tailored_resumes.py` | `cc2594c0c4575360fdea66481cf5547cc5170db8` |
| `test_technology.py` | `765c640984f88305c6a2ee6b4121aa19492bd46f` |

## API 사용량

수집된 사용량은 입력 111,147토큰, 출력 43,181토큰이다. 실제 v2 첨삭 10개·모델 호출 30회의 기록이다. 입력 캐시 세부값은 수집하지 않았다.

## 자료 출처와 보관 범위

현재 코드의 [v2 평가기](../../cover_letter_rag/evaluation/v2_eval.py)와 [합성 케이스](../../cover_letter_rag/evaluation/v2_cases.json)를 사용했다. 3차 원본 출처·엔진 상태·대표 판정·실패 유형은 이 문서에 통합했다.

지원서 전체 작성의 실제 모델 호출, 사람 첨삭 품질 채점, 브라우저에서 저장·적용하는 전체 흐름은 미검증이다.

원본 콘솔 로그·응답 JSON·CSV와 별도 입력 파일은 정리했다. 이 문서는 핵심 실행 기록의 요약이며 개별 원본 응답 전체를 보존하지 않는다.

[종합 보고서](../deliverables/test-plan-results.md) · [README](../../README.md#16-주요-기능-테스트-계획-및-결과)
