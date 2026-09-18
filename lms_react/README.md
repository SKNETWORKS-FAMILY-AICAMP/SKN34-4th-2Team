# PLAYDATA LXP — React 프로토타입

Flutter 앱(`lib/`)을 React + TypeScript + Vite로 옮긴 프로토타입입니다. 학생·강사·관리자
세 역할의 화면 전부가 들어 있고, 데이터는 Flutter의 데모 저장소(`lib/shared/demo/`)를
옮긴 메모리 목업입니다. Firebase는 쓰지 않습니다.

```bash
npm install
npm run dev      # http://localhost:5173
npm test         # vitest 43개
npm run build
```

## 로그인

로그인 화면의 버튼으로 바로 들어갈 수 있습니다. 비밀번호는 셋 다 `Playdata123!`.

| 역할 | 계정 |
| --- | --- |
| 학생 | student@playdata.co.kr |
| 강사 | instructor@playdata.co.kr |
| 관리자 | admin@playdata.co.kr |

## 무엇이 들어 있나

**학생** — 대시보드(프로필·공지·출석 캘린더·미션·내 자리·오늘 커리큘럼·자격시험·주간 학습
추천·설문·승인 현황), 이력서 관리와 편집(AI 코치·피드백 패널), 학습실(인프런 패키지·YouTube
추천·학습 노트), 게시판(공지·소통 피드), 자리 배치, 설문·제출, 자격 시험 일정, 기록실(5종 제출
폼), 마일리지(내역·상점·장바구니), 성취도평가(목록·응시·결과), 마이페이지, 설정, 챗봇.

**강사** — 자리 확인(날짜·교시·확인/보류·좌석도), 이력서 검토, 게시물관리(공지 CRUD),
성취도평가(목록·상세·만들기·채점), 커리큘럼(CSV 등록/교체), 마이페이지, 설정.

**관리자** — 대시보드, 기수 관리, 학생 관리(목록·상세·등록/수정), 강사 관리, 출석 관리,
자리 확인, 좌석 배치(배정·게시), 성취도 평가, 기록실 승인, 이력서 승인, 설문·제출,
학습실, 게시판(공지·예약 공지·알림 팝업), 마일리지(상품·구매 요청·수동 조정·설정), LLMOps.

**이용 안내 투어** — 역할별 14 / 12 / 17스텝. 첫 로그인에 자동으로 뜨고, 스텝이 요구하는
화면으로 옮겨 다니며 메뉴를 비춥니다. 「다시 보지 않기」는 localStorage에 남고, 마이페이지에서
되살릴 수 있습니다.

## 겉모습을 원본에 맞춘 방법

Flutter 앱의 실제 화면은 `onboarding/output/pdf/*.pdf`(역할별 가이드)에 캡처로 남아 있습니다.
그 PDF에서 원해상도 스크린샷을 뽑아 옆에 놓고 맞췄습니다.

- **글꼴**: 앱이 쓰는 Paperlogy를 `assets/fonts/`에서 가져와 `public/fonts/`에 넣고 `@font-face`로 씁니다.
- **아이콘**: `Icons.*`와 같은 Material Symbols Rounded 폰트(`material-symbols` 패키지)를 그대로 씁니다.
- **사이드바**: 흰 바탕 + 선택 항목만 옅은 파랑 알약, 위에 로고, 아래에 프로필·로그아웃. 관리자는 그룹을 접었다 폅니다.
- **색·모서리**: `app_colors.dart`의 값을 CSS 변수로 옮겼고, 카드는 흰 바탕 + 1px 테두리 + 14px 모서리입니다.
- **사이드바 색 6종**: `kSideRailDarkPalettes` 그대로입니다. 고른 색이 사이드바 바탕뿐 아니라 버튼·링크(`action`)와
  마일리지 카드 그라데이션(`primaryDark` → 사이드바 색)까지 정합니다. 전체 다크에서는 `AppColors._balanced`와 같은
  방식(상대 휘도 0.18)으로 밝기를 맞춥니다.
- **움직임**: 원본의 움직임을 값까지 그대로 옮겼습니다.
  - 로그인 브랜드 카드 — 28초 타원 궤도 + 8초 맥박 + 마우스 시차 (`login_brand_stage.dart`)
  - 챗봇 로봇 머리 — 답이 올 때마다 늘어남 곡선(0→1.33→1→-0.33→0.17→0)으로 한 번 튐 (`robot_head_icon.dart`)
  - 마일리지 카드 — 포인터를 따라 최대 0.14rad 3D 기울임, 광택이 함께 흐르고 놓으면 easeOutCubic으로 복귀 (`mileage_credit_card.dart`)
  - 공고 추천 — 매달린 로봇이 3.1초로 흔들리다 끝나면 줄을 놓고 떨어짐(1.3초), 위아래로만 잘림 (`job_recommendation_loading.dart`)
  - 이력서 첨삭 — 네 단계 진행 표시 후 대화 (`job_resume_review_dialog.dart`)

- **이력서 Doc / Edit**: Doc은 입력창 없이 값만 읽는 문서 보기(빈 칸은 「미작성」)이고, 그 상태에서 PDF 버튼을
  누르면 인쇄 미리보기가 열립니다 — 원본 가이드의 "PDF 내보내기: 인쇄 미리보기에서 PDF로 저장합니다" 그대로입니다.
  인쇄에는 사이드바·상단 바·코치 패널이 빠지고 이력서만 남습니다.

  `prefers-reduced-motion`을 켠 사람에게는 모두 멈춰 보입니다.

화면을 고친 뒤에는 직접 찍어서 확인합니다.

```bash
node shot.mjs out-dir   # 빌드된 앱을 띄워 역할별 주요 화면을 캡처
```

## 구조

```
src/
  app/        라우터·셸·테마·네비게이션 정의
  domain/     모델 타입과 라벨 상수 (lib/shared/models, lib/core/constants)
  data/       시드 데이터와 메모리 저장소 (lib/shared/demo)
  features/   화면 — auth, dashboard, board, records, forms, qual, seating,
              study, mileage, assessments, resume, mypage, settings,
              instructor, admin, chatbot, notices
  tour/       이용 안내 투어 (lib/features/onboarding)
  ui/         공통 위젯 (버튼·카드·표·대화상자 등)
  utils/      날짜·숫자 표기
```

### Flutter와의 대응

| Flutter | React |
| --- | --- |
| `core/routing/app_router.dart` (go_router) | `app/routes.tsx` + `app/App.tsx` (react-router) |
| `core/theme/app_colors.dart` | `app/theme.css` (CSS 변수, 다크 포함) |
| `shared/models/*.dart` | `domain/types.ts` |
| `shared/demo/demo_lms_repository.dart` | `data/seed.ts` + `data/store.ts` |
| `shared/providers/*` (Riverpod) | `data/repository.ts` (useSyncExternalStore 훅) |
| `features/auth` (Firebase Auth) | `features/auth/session.tsx` (데모 계정) |
| `features/*/presentation/*_screen.dart` | `features/*/…Screen.tsx` |
| `features/onboarding` | `tour/` |

## 프로토타입이라 다른 점

- **저장소가 메모리입니다.** 새로고침하면 시드 상태로 돌아갑니다. 설정 화면에서 바로 되돌릴
  수도 있습니다. 대신 한 세션 안에서는 진짜로 흐릅니다 — 학생이 올린 기록은 관리자 승인
  대기에 뜨고, 구매를 승인하면 학생 잔액이 깎입니다.
- **AI가 규칙으로 대체됐습니다.** 이력서 AI 코치와 챗봇은 실제로는 LLM을 부릅니다. 여기서는
  같은 자리·같은 모양으로 규칙 기반 답을 보여 줍니다. LLMOps 지표도 시드 로그를 집계합니다.
- **파일 업로드가 없습니다.** 증빙 파일 칸은 자리만 있습니다.
- **비밀번호는 바뀌지 않습니다.** 변경 화면과 첫 로그인 강제 변경 흐름은 있지만 값은
  저장되지 않습니다.

## 테스트

```
src/__tests__/app.test.tsx        앱 전체 — 로그인, 역할 가드, 데이터 흐름, 투어
src/tour/__tests__/               투어 상태·배치 계산·dismiss 저장
```

`npm test`로 43개가 모두 돕니다.
