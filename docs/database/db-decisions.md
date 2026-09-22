# PLAYDATA LMS PostgreSQL Redesign - DB Decision Log

## DEC-001 ~ DEC-014
기존 결정 유지.

## DEC-015 Attendance는 학생/날짜별 최종 일일 출결
- attendances는 학생별 날짜별 최종 업무 상태를 저장한다.
- UNIQUE(user_id, attendance_date)를 기본 제약으로 둔다.
- cohort_id는 과거 출결의 발생 당시 기수를 보존하기 위해 저장한다.

## DEC-016 고용24 원천 출결과 LMS Attendance 분리
- 실제 운영의 입실/퇴실/외출/조퇴 원천은 고용24 비콘 출결이다.
- 현재 프로젝트는 실시간 연동이 어려워 예시 출결 데이터를 사용한다.
- 향후 고용24 연동이 생기더라도 원천 이벤트와 최종 Attendance는 분리한다.
- 현재 단계에서는 원천 이벤트 전용 테이블을 강제하지 않고, 연동 요구가 확정되면 attendance_events/import_batches를 추가 검토한다.

## DEC-017 출결 Google Form은 판단 근거
- 출결 Google Form은 매니저가 이슈와 병가/휴가 등 서류 필요 상황을 파악하기 위한 입력이다.
- Google Form 응답이 최종 Attendance 상태를 자동 결정하지 않는다.
- issue_type과 최종 attendance.status는 독립적으로 유지한다.
