# 역할별 사용 설명서(PDF)

마이페이지 「PDF 매뉴얼 보기」가 여는 `public/manuals/<role>_manual.pdf` 를 만든다.
예전 Flutter 판 `onboarding/` 가이드와 같은 구성이다.

표지 → 목차 → PART 1 시작하기(로그인 · 투어 첫 화면) → 화면 테마 → PART 2 역할 화면 안내 → 자주 묻는 질문

| 파일 | 쪽수 | 챕터 |
|---|---|---|
| `student_manual.pdf` | 31 | 대시보드 · 이력서 · AI 커리어 코치 · 공고 맞춤 지원 · 학습실 · 공부방 · 연습장 · 게시판 · 자리 배치 · 설문/자격 시험 · 기록실 · 마일리지 · 성취도평가 · 학생 챗봇 · 마이페이지/설정 |
| `instructor_manual.pdf` | 18 | 자리 확인 · 이력서 피드백 · 공지 작성 · 성취도평가(만들기 · 채점) · 커리큘럼 · 복습 문제 신고 · 수업 저장소 · 마이페이지 |
| `admin_manual.pdf` | 22 | 대시보드 · 기수 · 학생/강사 계정 · 출석 · 좌석 배치 · 기록실 승인 · 이력서 · 설문 · 학습실 · 게시판 · 마일리지 · LLMOps |

## 개인정보

- 화면은 **데모 빌드**(`vite build --mode test`, 메모리 예시 데이터)로 찍는다. 실서버 · RDS 를 읽지 않는다.
- AI 기능(공고 추천 · 코치에게 묻기 · 첨삭 · 공고 맞춤 지원)이 부르는 `/api` 는 `mocks.mjs` 의 **지어낸 예시 응답**으로 바꾼다.
  모르는 요청은 404 로 막아 밖으로 나가지 않는다.
- 투어는 PART 1 의 첫 화면 한 장에만 넣고, 나머지 캡처는 투어를 닫고 찍는다.

## 다시 만들기

```bash
cd lms_react
npx vite build --mode test --outDir ../build/guide_web --emptyOutDir      # 데모 빌드
npx vite-node tools/guide/dump-seed.ts ../build/guide/demo-resume.json    # 예시 응답이 쓰는 데모 이력서
node tools/guide/capture.mjs            # 캡처 → build/guide/shots/ (역할 하나만: capture.mjs student)
node tools/guide/pdf.mjs                # PDF → public/manuals/
```

Git Bash 에서 경로 인자를 줄 때는 `MSYS_NO_PATHCONV=1` 을 붙인다(`/resume` 이 윈도 경로로 바뀐다).

## 고칠 곳

| 바꾸고 싶은 것 | 파일 |
|---|---|
| 챕터 · 단계 · 설명 문구 · 번호 상자 | `scenes.mjs` |
| 표지 · 시작하기 · 자주 묻는 질문 · 디자인 | `pdf.mjs` |
| AI 화면 예시 응답 | `mocks.mjs` |
| 로그인 · 화면 이동 · 번호 상자 그리기 | `lib.mjs` · `capture.mjs` |

- 설명 문구는 앱 안 이용 안내 투어(`src/tour/steps/*.ts`)와 뜻을 맞춘다.
- 번호 상자 선택자를 고를 때: `node tools/guide/probe.mjs <역할> <경로>` 로 버튼 · 링크 이름을,
  `INSPECT="글자|글자" node tools/guide/inspect.mjs <역할> <경로>` 로 그 글자를 감싼 요소의 클래스를 본다.
- `capture.mjs` 가 끝에 「확인할 곳」을 찍으면 번호 상자를 못 찾은 단계다. 캡처는 남으니 그 단계만 고쳐 다시 찍는다.
- 공고 맞춤 지원 ⑤(문항별 답변 첨삭)는 데모 모드에 공고용 사본 이력서가 없어 로딩에서 멈춘다. ④ 화면에 번호를 달아 글로 설명한다.
