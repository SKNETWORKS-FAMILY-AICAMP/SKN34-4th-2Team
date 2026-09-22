# PLAYDATA LMS PostgreSQL Redesign - Requirements

> 상태: **통합 직전 Freeze Candidate**
>
> 원칙: 실제 운영 요구사항을 우선하고, `feature/test`의 기존 Firestore → PostgreSQL 구조는 마이그레이션 자산으로 재사용한다.

## 1. 핵심 운영 도메인

### 사용자 / 기수
- 사용자는 현재 역할 하나를 가진다: student / instructor / admin.
- 학생·강사는 현재 기수를 최대 하나 가진다.
- `users.cohort_id`로 현재 기수를 참조한다.
- 역할/기수 변경 이력 테이블은 만들지 않는다.
- 업무 이력에는 필요 시 발생 당시 `cohort_id`를 저장한다.

### 좌석 / 착석 확인
- 현재 좌석 레이아웃은 기수별 JSONB로 저장한다.
- 과거 좌석 레이아웃 이력은 핵심 요구사항이 아니다.
- 교시별 착석 확인은 Attendance와 분리한다.

### 제출 관리
- 행정성 제출은 `submission_tasks` / `submission_responses`로 관리한다.
- 하나의 제출 요청을 여러 기수에 배포할 수 있다.
- Google Form / 내부 Form / 파일 / 링크 제출 확장을 허용한다.
- 제출 상태는 가능한 경우 `due_at`, `submitted_at`으로 파생한다.

### 출결
- 고용24 비콘이 실제 출결 원천이다.
- 프로젝트에서는 실시간 연동 대신 예시 출결 데이터를 사용한다.
- `attendances`는 학생별 일일 최종 출결이다.
- 출결 Google Form은 병가/휴가/지각 등 이슈 파악과 증빙 확인을 위한 별도 입력이다.
- 출결 이슈와 최종 Attendance는 별도 엔터티다.

### 기록실
- 실제 유형: certification / study / blog / study_cert / precourse_quiz.
- 학생이 제출하고 관리자가 승인/반려한다.
- 반려 후 재제출은 새 레코드로 생성한다.
- 증빙 파일은 복수 첨부 가능하며 S3에 저장한다.
- 승인된 기록은 마일리지 자동 적립 규칙의 입력이다.

### 성취도 평가
- 강사가 생성/수정/발행/채점한다.
- 관리자는 조회 중심이다.
- 학생은 평가당 1회 응시한다.
- 문항은 multiple_choice / short_answer.
- 자동 점수와 강사 확정 점수를 분리한다.
- 단답형 표현 차이로 오답 처리된 경우 강사가 정정 가능하다.
- 학생은 제출 직후 결과/정답/해설을 확인한다.
- AI는 커리큘럼 기반 문제 초안을 만들고 강사가 검수 후 발행한다.
- 응시자가 없는 평가는 삭제 가능하며, 응시 이력이 있으면 폐기/비공개를 우선한다.

### 마일리지
- `mileage_transactions`가 원장이다.
- 구매 요청 시에는 차감하지 않고 관리자 승인 시 차감한다.
- 승인 후 환불/회수는 원거래 수정 대신 반대 거래를 생성한다.
- 관리자 수동 지급/차감이 가능하다.
- 상품 분류: gifticon / book / online_course.
- 가격 방식: fixed / variable.
- variable 상품은 실제 가격과 구매 링크를 학생이 입력한다.
- 종강 2주 후 남은 마일리지는 소멸 거래로 처리한다.
- 기수별 카테고리 한도 및 적립 규칙을 관리한다.

## 2. Career / Resume

### 이력서
- 학생은 하나 이상의 이력서를 작성할 수 있다.
- 기본 이력서(`is_base_resume`)를 지정할 수 있다.
- 이력서는 기본정보, 핵심역량, 경력, 학력, 기술스택, 자격증, 수상, 교육, 활동, 프로젝트, 자기소개서 등 구조화된 섹션을 가진다.
- 이력서 화면은 문서 단위 편집 비중이 높으므로 본문은 `content JSONB`를 유지한다.
- 강사/관리자는 학생 이력서를 조회하고 섹션 단위 피드백을 남길 수 있다.
- 저장 시 revision snapshot을 남길 수 있다.
- 표시용 `user_display_name`, `author_name`은 관계형 원본에 중복 저장하지 않는 것을 기본으로 한다.

### Skill
- Career AI와 채용공고 매칭에서 기술은 검색/집계/그래프 연결의 핵심 축이므로 `users.skills text[]`를 최종 구조로 사용하지 않는다.
- `skills` 마스터와 `user_skills` 관계 테이블을 둔다.
- 학생 기술은 출처(source)와 숙련도/근거를 확장할 수 있어야 한다.
- 프로젝트 기술과 채용공고 요구 기술도 동일 Skill ID를 참조할 수 있도록 설계한다.

### Job Preference
- 한 학생당 현재 취업 선호 설정 하나를 둔다.
- 희망 직무/지역/고용형태/기업 조건 등은 변경 가능성이 높으므로 `user_job_preferences.preferences JSONB`를 허용한다.
- 매칭에 자주 쓰이는 핵심 속성이 생기면 이후 컬럼으로 승격한다.

### Career AI
- PostgreSQL이 학생/이력서/프로젝트/Skill/채용공고 분석 결과의 원본이다.
- Pinecone은 의미 검색 후보 추출용이다.
- Neo4j는 Student-Experience-Project-Skill-Job-Company 관계 탐색과 설명 가능한 추천에 사용한다.
- AI가 생성한 문장은 근거가 존재하는 경험만 사용해야 한다.
- 근거가 부족하면 사실을 만들지 않고 확인 질문 또는 gap으로 남긴다.
- `job_requirement_profiles`, `resume_ai_reviews`, `resume_ai_applications`는 PostgreSQL에 유지한다.

## 3. 재사용 우선 도메인
다음은 `feature/test` 관계형 구조를 우선 재사용한다.

- 공지: notices / scheduled_notices / alert_popups / alert_popup_dismissals
- 커리큘럼: schedules / curriculum_pdfs / curriculum_sheets / curriculum_rows / materials
- 프로젝트 팀: project_teams / project_team_members
- 학습실: inflearn_packages / youtube_recommendations / recommendation_events / study_sources / study_notes
- AI 운영 로그: ai_generation_logs / ai_question_feedback / ai_eval_runs
- 사용자 보조: todos / student_intakes / system_cache

### 제외
- posts / post_comments: 현재 운영 데이터 0건이므로 우선 제외
- qna_threads / qna_messages: 현재 운영 데이터 0건이므로 우선 제외
- youtube_curriculum_cache: Redis 사용

## 4. 저장소 역할
- PostgreSQL: canonical source of truth
- S3: 파일 바이트
- Redis: Cache / Celery broker / 임시 데이터
- Pinecone: vector retrieval index
- Neo4j: Career graph projection
