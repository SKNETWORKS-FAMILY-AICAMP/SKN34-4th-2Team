# 채용공고 검색·추천 테스트 보고서

작성일은 2026-10-14이며 기준 코드는 `a9e6ffb` 작업 트리이다. 공부방·복습 연습장은 이번 AI 검증 대상에서 제외한다. 단위 테스트, 실제 모델 호출, 화면 검증을 구분하며 서로 다른 범위의 결과를 하나의 정확도로 합산하지 않는다.

## 테스트 계획

3차의 [검색 대화 48개 케이스·62턴](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/main/job_matching_bot/fixtures/chat_cases.json)과 앱·평가용 이력서 10종을 그대로 사용한다. 라우터를 3회 반복하고 실제 검색·추천에서 조건 유지, 원문 인용, 마감 상태를 검사한다. 사람의 추천 적합성 평가는 자동 규칙 검사와 구분한다.

| 범위 | 결과 | 판정 범위 |
| --- | --- | --- |
| 현재 Python 회귀 | 874개 중 856개 통과·5개 실패·2개 오류·11개 건너뜀 | 전체 통과 상태가 아니다. |
| 3차 라우터 3회 | 매회 48/48개 케이스 통과 | 매회 62턴의 조건·모드·후속 맥락을 확인한다. |
| 실제 검색 API | 48/48개 케이스·62/62턴 통과 | FastAPI TestClient, 실제 모델·Pinecone·공고 DB 복사본이다. |
| 실제 추천 | 이력서 10종·추천 120건, 규칙 결함 0건 | 원문 대조와 조건 검사를 수행한다. |
| 검사기 회귀 | 27개 통과 | 기존 25개와 PostgreSQL 조회 추가 2개이다. 기존 874개와 중복 집계하지 않는다. |
| React 공고 코치 | 21개 통과 | 참조·스트림·질문 화면 테스트이다. |

## 데이터와 실행 방법

운영 PostgreSQL 공고 데이터를 읽기 전용 트랜잭션으로 복사했다. 복사본은 `127.0.0.1:55440/lxp_validation`에 있으며 공고 92,597건과 관련 테이블 6개를 포함한다. 검색·추천의 상태 갱신은 복사본에만 적용했다. Pinecone 공고 인덱스는 조회에 사용하며 벡터를 적재하지 않는다.

기존 라우터 케이스를 3회 실행하고 실제 검색 API를 확인했다. 추천은 기존 이력서당 최대 12건을 요청했다. 추천 검사기가 SQLite를 직접 열어 중단돼 검증 중에만 `SqliteJobStore`의 PostgreSQL 접근으로 임시 수정한 뒤 저장된 결과를 검사했다. 재검사에는 추가 모델 호출을 사용하지 않았다. 임시 실행 코드 정리 시 검사기도 검증 전 코드로 되돌렸다.

추천의 8개 검사 항목은 신입에게 경력 공고, 희망 지역, 고용형태, 근거 없는 높음, 원문에 없는 인용, 마감·삭제 상태, 저장소 누락, 회사당 상한이다. 120건에서 모두 결함 0건이다. 마감 상태는 복사 당시 DB 기준이며 각 공고 사이트의 현재 상태를 보장하지 않는다.

## 실패·오류 분석

| 대상 | 건수 | 확인 내용 |
| --- | --- | --- |
| AdviceTest | 실패 2개·오류 2개 | 집계 답변을 서버가 조립하면서 기존 가짜 adviser의 답변·후속 제안·stats 호출 기대와 달라졌다. |
| ServiceStreamTest | 실패 2개 | 이벤트에 think가 추가됐으며 가짜 adviser 문장 대신 실제 집계 문장을 반환한다. |
| ObservedSemanticsTest | 실패 1개 | 같은 시각의 +09:00와 UTC +00:00 문자열을 다르게 비교한다. |

기대 계약의 변경과 실제 회귀를 구분해 확인해야 한다. 11개 건너뜀은 통과에 포함하지 않는다. 검사를 통과시키기 위해 제품 답변·이벤트를 이전 형식으로 되돌리지 않았다.

## 시간 측정과 사람 평가

실제 검색 62턴의 응답 시간 중앙값은 약 5.8초, 최대는 약 15.9초이다. 추천 10회는 중앙값 31.35초이며 범위는 27.80~37.80초이다. 순차 실행·로컬 복사본 환경의 관측값이며 부하 테스트나 운영 SLA가 아니다. 모델·데이터·환경이 달라 3차 수치와 성능 개선율을 계산하지 않는다.

추천의 사람 정답 라벨링은 수행하지 않아 Precision·Recall·F1과 사람 기준 적합도는 산출하지 않는다.

## 추천 입력과 결과

모두 합성 이력서이며 희망 고용형태는 정규직이다. 경력은 실제 요청에 전달한 값이다.

| 이력서 | 경력(년) | 희망 지역 | 추천 건수 | 총 시간(초) |
| --- | --- | --- | --- | --- |
| 백엔드 신입 · Python/Django | 0 | 서울·경기 | 12 | 33.18 |
| 프론트엔드 신입 · React/TypeScript | 0 | 서울 | 12 | 37.80 |
| 백엔드 경력 3년 · Java/Spring Boot | 3 | 서울 | 12 | 27.82 |
| 데이터 신입 · Python/SQL (전문학사) | 0 | 서울·경기 | 12 | 27.80 |
| 임베디드 신입 · C/C++/Linux (대전) | 0 | 대전 | 12 | 28.93 |
| QA 엔지니어 신입 · 자동화 테스트 | 0 | 서울·경기 | 12 | 31.76 |
| 정보보안 신입 · 네트워크·관제 | 0 | 서울 | 12 | 29.16 |
| DevOps 경력 2년 · Kubernetes/AWS | 2 | 서울 | 12 | 35.83 |
| AI 연구 석사 · 컴퓨터비전 | 0 | 서울·경기 | 12 | 30.93 |
| 프론트엔드 경력 5년 · Vue/Nuxt | 4.9 | 서울 | 12 | 32.70 |

프론트엔드 경력 5년 프로필의 직렬화된 경력 값은 4.9년이다. 추천 120건에서 신입·지역·고용형태·근거·원문 인용·마감 상태·저장소 존재·회사당 상한의 8개 규칙 항목 모두 결함 0건이다.

## 실패 상세

| 테스트 | 실제 결과 |
| --- | --- |
| AdviceTest.test_a_countable_question_with_no_conditions_counts_everything | 가짜 adviser의 stats 기록이 없어 KeyError가 발생했다. |
| AdviceTest.test_the_table_says_what_it_counted | 가짜 adviser의 stats 기록이 없어 KeyError가 발생했다. |
| AdviceTest.test_followups_become_suggestions | 가짜 후속 질문 대신 서버가 조립한 제안을 반환했다. |
| AdviceTest.test_question_is_answered_with_counted_jobs | 가짜 문장 대신 실제 집계에 따른 문장을 반환했다. |
| ServiceStreamTest.test_a_broken_listener_does_not_stop_the_answer | 기대 문장 ‘끝까지 씁니다.’ 대신 집계 답변을 반환했다. |
| ServiceStreamTest.test_a_question_announces_its_stages_and_streams_the_answer | route → stats → answer를 기대했으나 think가 추가됐다. |
| ObservedSemanticsTest.test_observed_but_not_collected_stays_open | 2026-09-03T12:00:00+09:00와 2026-09-03T03:00:00+00:00를 문자열로 다르게 판정했다. |

## API 사용량

수집된 사용량은 입력 1,975,531토큰, 출력 50,134토큰이다. 라우터 3회와 실제 검색 API의 기록이다. 추천 호출의 토큰은 검사 중단 전에 저장되지 않아 누락됐다.

## 자료 출처와 보관 범위

[3차 대화 48개](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/215dd15881c576576f5e09bd52af5c156eb981ad/job_matching_bot/fixtures/chat_cases.json), [앱 이력서 5종](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/215dd15881c576576f5e09bd52af5c156eb981ad/scripts/resume_mocks.json), [평가 이력서 5종](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/215dd15881c576576f5e09bd52af5c156eb981ad/scripts/resume_mocks_eval.json)을 사용했다. 개별 프로필 조건·추천 건수·시간·실패 상세는 이 문서에 통합했다.

Django 로그인부터 브라우저까지의 전체 흐름, 사이트별 최신 마감 확인, 사람 추천 평가는 미검증이다.

원본 콘솔 로그·응답 JSON·CSV와 별도 입력 파일은 정리했다. 이 문서는 핵심 실행 기록의 요약이며 개별 원본 응답 전체를 보존하지 않는다.

[종합 보고서](../deliverables/test-plan-results.md) · [README](../../README.md#16-주요-기능-테스트-계획-및-결과)
