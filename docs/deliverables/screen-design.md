# LXP 2.0 화면설계서

작성 기준일: 2026-10-13. 가이드의 화면별 시각 자료 형식을 따라 주요 화면을 정리한다. PDF의 화면은 구현 코드·이용 안내 정의를 기반으로 단순화한 와이어프레임이며 실제 서비스 캡처가 아니다.

[화면설계서 PDF](screen-design.pdf) · [화면 경로](../../lms_react/src/app/routePaths.ts) · [역할별 라우트](../../lms_react/src/app/routes.tsx) · [상세 이용 안내 정의](../../lms_react/tools/guide/scenes.mjs)

## UI-01 학생 대시보드

- 경로: `/`
- 사용자: 학생
- 요구사항: AUTH-01, LMS-01
- 구현 근거: [lms_react/src/features/dashboard/DashboardScreen.tsx](../../lms_react/src/features/dashboard/DashboardScreen.tsx)

1. 로그인 역할에 맞는 홈을 표시한다.
2. 오늘 복습 카드에서 풀이 화면으로 이동한다.
3. 출결 신청과 학생 챗봇을 공통 진입점으로 제공한다.

## UI-02 학생 챗봇

- 경로: `학생 화면 공통 패널`
- 사용자: 학생
- 요구사항: CHAT-01, DATA-02
- 구현 근거: [docs/features/student-chatbot.md](../../docs/features/student-chatbot.md)

1. 로그인 학생의 기수·본인 데이터를 사용한다.
2. 정책·이미지 공지·프로젝트 근거를 검색한다.
3. 문서에 근거가 없는 내용과 권한 밖 자료를 구분한다.

## UI-03 공부방·수업 노트

- 경로: `/study-room`
- 사용자: 학생
- 요구사항: STUDY-01, STUDY-02
- 구현 근거: [lms_react/src/features/study/StudyRoomScreen.tsx](../../lms_react/src/features/study/StudyRoomScreen.tsx)

1. 선택한 수업 자료로 노트를 생성·조회한다.
2. 동일 자료의 저장된 노트를 재사용한다.
3. 날짜별 복습 문제와 오답을 연결한다.

## UI-04 복습 연습장·코드 튜터

- 경로: `/study-room/playground`
- 사용자: 학생
- 요구사항: STUDY-02, TUTOR-01
- 구현 근거: [lms_react/src/features/practice/PythonPlaygroundScreen.tsx](../../lms_react/src/features/practice/PythonPlaygroundScreen.tsx)

1. 코드를 실행하고 결과를 확인한다.
2. 본인 코드·오류를 바탕으로 단계별 힌트를 요청한다.
3. 풀이 기록을 보존하고 복습 완료 후 공부방으로 돌아간다.

## UI-05 이력서 편집·AI 첨삭

- 경로: `/resume/:resumeId/edit`
- 사용자: 학생
- 요구사항: RESUME-01, RESUME-02
- 구현 근거: [lms_react/src/features/resume/ResumeEditScreen.tsx](../../lms_react/src/features/resume/ResumeEditScreen.tsx)

1. 저장한 이력서를 기준으로 수정안을 제시한다.
2. 원문·수정안·근거를 대조하고 선택한 문장만 반영한다.
3. 버전 충돌·실패 상태를 표시하며 저장한 단계부터 재개한다.

## UI-06 공고 추천·공고 맞춤 지원

- 경로: `/job-apply`
- 사용자: 학생
- 요구사항: JOB-01, JOB-02, APPLY-01
- 구현 근거: [lms_react/src/features/jobApply/JobApplyScreen.tsx](../../lms_react/src/features/jobApply/JobApplyScreen.tsx)

1. 코치 추천·검색에서 고른 공고로 진입할 수 있다.
2. 추출한 지원 문항을 확인한 뒤 초안을 작성한다.
3. 기본 이력서와 공고별 맞춤 사본을 구분한다.

## UI-07 관리자 AI·출결 아카이빙

- 경로: `/admin/attendance`
- 사용자: 관리자
- 요구사항: ADMIN-01, ADMIN-02, ARCHIVE-01
- 구현 근거: [lms_react/src/features/admin/AdminAttendanceScreens.tsx](../../lms_react/src/features/admin/AdminAttendanceScreens.tsx)

1. 운영 자료를 자연어로 조회한다.
2. 알림·공지 제안은 대상과 문구를 확인한 뒤 실행한다.
3. 선택한 기록을 Excel·CSV·Word 또는 인쇄 PDF로 보관한다.

## UI-08 기수·정책 문서 관리

- 경로: `/admin/cohorts/:id/edit`
- 사용자: 관리자
- 요구사항: DATA-01, NFR-04
- 구현 근거: [lms_react/src/features/admin/AdminPeopleScreens.tsx](../../lms_react/src/features/admin/AdminPeopleScreens.tsx)

1. 기수와 문서 종류를 지정해 업로드한다.
2. 청킹·임베딩 검증이 성공한 문서만 활성화한다.
3. 실패한 업로드가 기존 정책 검색을 대체하지 않도록 한다.

## UI-09 강사 수업·평가 관리

- 경로: `/instructor/study-sources`
- 사용자: 강사·관리자
- 요구사항: LMS-02, STUDY-02
- 구현 근거: [lms_react/src/features/instructor/InstructorStudySourcesScreen.tsx](../../lms_react/src/features/instructor/InstructorStudySourcesScreen.tsx)

1. 담당 기수의 수업 자료를 관리한다.
2. 문제 관리·평가 기능은 역할별 메뉴에서 연결한다.
3. 학생 응답과 강사용 정답·채점 자료의 공개 범위를 분리한다.

## UI-10 Expo 모바일 로그인·공지

- 경로: `lms_expo/src/main.tsx`
- 사용자: 인증 사용자
- 요구사항: AUTH-01, NFR-07
- 구현 근거: [lms_expo/src/main.tsx](../../lms_expo/src/main.tsx)

1. Django 로그인 API로 토큰을 발급받는다.
2. 비밀번호 변경 요구를 처리하고 홈을 표시한다.
3. bootstrap 응답의 사용자 정보와 공지를 조회한다. 현재 폴더의 구현 범위를 기준으로 한다.

## 공통 상태·반응형 기준

인증 만료는 로그인 흐름으로 연결한다. 요청 중에는 진행 상태를 표시하고 실패 시 재시도 경로를 제공한다. 권한·기수·소유권은 서버가 확인한다. 좁은 화면에서는 열을 재배치하고 표·긴 콘텐츠는 스크롤로 확인한다. 실제 기기 검증은 별도 테스트 대상으로 남긴다.

## 참고 양식

[프로젝트 가이드 화면설계서 예시](https://drive.google.com/file/d/1Wer24krs72fsBsghcVwCsd86fiEye5GT/view)
