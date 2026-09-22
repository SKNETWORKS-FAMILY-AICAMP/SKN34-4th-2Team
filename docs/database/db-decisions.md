# PLAYDATA LMS PostgreSQL Redesign - DB Decision Log

## DEC-001 ~ DEC-023
기존 결정 유지.

## DEC-024 성취도 평가 운영 주체
- 평가 생성/수정/발행/채점은 강사 업무로 정의한다.
- 관리자는 평가 조회 권한을 기본으로 한다.

## DEC-025 평가당 학생 1회 응시
- 한 학생은 동일 assessment에 대해 하나의 assessment_submission만 가진다.
- UNIQUE(assessment_id, user_id)를 둔다.
- 재응시/재시험은 현재 요구사항에 포함하지 않는다.

## DEC-026 문항 유형은 객관식/단답형 우선
- 현재 지원 문항 유형은 multiple_choice / short_answer 두 가지다.
- 서술형, 복수선택은 현재 범위에서 제외한다.

## DEC-027 자동 채점과 최종 채점 분리
- assessment_answers에는 auto_score와 final_score를 분리 저장한다.
- 단답형 표현 차이 등 자동 채점 오판을 강사가 수정할 수 있어야 한다.
- 점수 변경 이력은 assessment_score_adjustments로 보존한다.

## DEC-028 결과는 제출 직후 공개
- 별도의 결과 공개 플래그 없이 학생은 제출 후 즉시 점수/정답/해설을 조회할 수 있다.
- 향후 공개 정책 변경 요구가 생기면 별도 result_visibility 정책을 추가한다.

## DEC-029 AI 문항은 초안
- LLM은 커리큘럼 범위를 기반으로 문항 초안을 생성할 수 있다.
- AI 생성 문항은 강사의 검토/수정을 거쳐 일반 assessment_questions로 저장한 뒤 발행한다.
- origin, prompt_version, source_day/source_topic 등 생성 provenance를 보존할 수 있다.

## DEC-030 평가 삭제 정책
- 응시 기록이 없는 평가는 물리 삭제를 허용할 수 있다.
- 응시 기록이 있는 평가는 submission/answer/score history 보존을 위해 물리 삭제를 기본 금지한다.
- 잘못 출제된 경우 published=false 및 archived/cancelled 상태로 전환하는 방식으로 숨기는 것을 우선한다.
