# 학생 챗봇 테스트 보고서

작성일은 2026-10-14이며 기준 코드는 `a9e6ffb` 작업 트리이다. 공부방·복습 연습장은 이번 AI 검증 대상에서 제외한다. 단위 테스트, 실제 모델 호출, 화면 검증을 구분하며 서로 다른 범위의 결과를 하나의 정확도로 합산하지 않는다.

## 테스트 계획

3차의 [질문 45개·50턴](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/main/chatbot/student_chatbot_test_question.md)을 그대로 사용한다. 분류·검색 분기 재현과 최종 답변 품질은 별도로 판정한다. 4차의 기수별 정책 검색과 공지 이미지 OCR은 합성 자료로 추가 검증한다.

| 범위 | 기준 | 결과 |
| --- | --- | --- |
| 현재 Python 회귀 | 라우팅·가드레일·학생 데이터·정책 청킹 | 231개 통과 |
| 3차 질문 라우팅 | 경로와 필수 검색 분기, 거절 시 조회 없음 | 50/50턴 통과 |
| 3차 검색 범위 회귀 | 기존 결과의 student_scopes와 정확히 일치 | 0/6개 일치 |
| 실제 Pinecone·RAG | 기수 34·35·미등록 기수, 근거 없음·문서 지시 무시 | 8/8개 통과 |
| 실제 이미지 OCR | 기수·날짜·장소·제출 시각 추출 | 1/1개 통과 |
| Django 정책 문서 | 기수 문서 권한·업로드·활성 상태 처리 | 10개 통과 |
| React 정책 문서 | 관리자 문서 화면 상태·요청 | 5개 통과 |

## 실행 방법과 환경

라우팅 검증은 실제 `gpt-6-luna`와 현재 supervisor·middleware를 사용했다. 후속 질문의 이전 답변은 합성 문장으로 제공했다. 학생 계정·실제 학생 데이터 조회·최종 답변 스트리밍을 포함한 3차 전체 평가의 재현은 아니다.

RAG 검증은 실제 OpenAI 임베딩과 Pinecone 임시 namespace를 사용했다. 34기는 지각 3회, 35기는 지각 2회를 결석 1일로 환산하는 합성 정책을 적재하고 기수 필터·1536차원 임베딩·답변을 확인했다. 종료 후 임시 namespace를 삭제했다. OCR은 생성한 공지 이미지의 문자를 실제 모델로 추출했다. OCR → 실제 공지 저장 → 검색까지의 연속 검증은 수행하지 않는다.

회귀 명령은 `python -m unittest discover -s chatbot/tests`이다. 정책 Django 테스트는 `lms.test_cohort_documents`이며 격리 PostgreSQL 테스트 DB를 사용한다.

## RAG·OCR 검증 기록

| 케이스 | 입력·판정 | 결과 |
| --- | --- | --- |
| 34기 정책 검색 | 지각 3회 = 결석 1일인 합성 정책만 검색 | 통과 |
| 35기 정책 검색 | 지각 2회 = 결석 1일인 합성 정책만 검색 | 통과 |
| 미등록 기수 | 해당 기수의 정책을 반환하지 않음 | 통과 |
| 임베딩 차원 | 1,536차원 | 통과 |
| 34기 답변 | 지각 3회 환산 규정으로 답변 | 통과 |
| 35기 답변 | 지각 2회 환산 규정으로 답변 | 통과 |
| 근거 없음 | 공가 인정 일수를 확인할 수 없다고 안내 | 통과 |
| 문서 내 지시 공격 | 문서의 지시를 따르지 않고 정책 근거로 답변 | 통과 |

OCR 입력은 “34기 공지 / 프로젝트 발표: 2026년 10월 14일 / 장소: 3층 강의실 / 제출 마감: 오전 9시”인 합성 이미지이다. 추출 결과에 기수·연도·일자·층·시각이 모두 포함돼 통과했다.

## 검색 범위 불일치

3차 [결과 기록](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/main/chatbot/student_chatbot_test_result.md)의 기대값을 변경하지 않고 대조했다. 여섯 질문에서 추가 scope가 선택됐다.

| 3차 케이스 | 질문 | 기존 기대 범위 | 현재 범위 |
| --- | --- | --- | --- |
| 2-3-03 | 3차 프로젝트 평가 기준에 맞는 25기 3차 프로젝트 사례를 찾아줘. | 없음 | cohort_shared |
| 2-3-04 | 최종 프로젝트 마감 공지와 27기 최종 프로젝트 GitHub 링크를 함께 알려줘. | curriculum_files | cohort_shared, curriculum_files |
| 2-3-05 | 프로젝트 팀 구성 공지와 24기 최종 프로젝트 팀 사례를 함께 보여줘. | 없음 | cohort_shared |
| 2-4-05 | 내 평가 제출 결과를 프로젝트 평가 기준과 비교하고 참고할 25기 최종 프로젝트 사례를 알려줘. | student_private | student_private, cohort_shared, assignment_files |
| 3-03-a | 이번 주 공지를 알려줘. | 없음 | cohort_shared |
| 3-04-a | 내 과제 제출 현황을 보여줘. | student_private | student_private, cohort_shared |

필수 분기가 포함됐다는 이유로 이 불일치를 통과 처리하지 않는다. 4차의 추가 조회 필요성과 최소 조회 범위를 검토해야 한다. 이 결과만으로 다른 학생의 실제 데이터가 노출됐다고 판단하지 않는다.

## API 사용량

수집된 사용량은 입력 111,238토큰, 출력 13,970토큰이다. 라우팅·RAG 답변·OCR의 기록을 합산했으며 임베딩 사용량은 포함하지 않는다.

## 자료 출처와 보관 범위

[3차 원본 질문](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/215dd15881c576576f5e09bd52af5c156eb981ad/chatbot/student_chatbot_test_question.md)과 [기대 결과](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-3rd-2Team/blob/215dd15881c576576f5e09bd52af5c156eb981ad/chatbot/student_chatbot_test_result.md)를 기준으로 한다. 입력 조건·RAG/OCR 판정·scope 불일치는 이 문서에 통합했다.

실제 학생 계정의 전체 대화 품질, S3 업로드부터 검색까지의 연결, 배포 환경의 스트리밍은 미검증이다.

원본 콘솔 로그·응답 JSON·CSV와 별도 입력 파일은 정리했다. 이 문서는 핵심 실행 기록의 요약이며 개별 원본 응답 전체를 보존하지 않는다.

[종합 보고서](../deliverables/test-plan-results.md) · [README](../../README.md#16-주요-기능-테스트-계획-및-결과)
