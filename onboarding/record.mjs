// 역할별 시연 영상을 녹화한다. 결과: onboarding/output/videos/<순번>_<역할>_시연.mp4
// 사용: node record.mjs              (전체)
//       node record.mjs student      (한 역할만)
//
// - Playwright 녹화에는 마우스 커서가 안 찍히므로 가짜 커서를 DOM에 얹는다.
// - 자막은 앱 화면을 가리지 않도록 영상 아래에 붙인 자막 바에 ffmpeg로 입힌다.
//   녹화하면서 자막이 바뀐 시각을 기록해 두고(.ass), 다음 자막이 나올 때까지 계속 보여 준다.
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright';
import { serveBuild, waitForApp, go, outRoot, deliverRoot, sleep } from './lib/app.mjs';
import {
  size, installCursor, resetMouse, moveTo, tap, tapIf, hover, typeInto, btn, btnLike, openMenu, login, showTourStart, themeOption,
  scrollCoachPanelToTop, todayCell, writeResumeFeedback,
} from './lib/actions.mjs';

const only = process.argv[2];
const barHeight = 100;
// 첫 1.5초는 앱 로딩 흰 화면이라 잘라낸다.
const trimSec = 1.5;
const videoDir = path.join(deliverRoot, 'videos');
const rawDir = path.join(outRoot, 'videos-raw');
fs.mkdirSync(videoDir, { recursive: true });
fs.mkdirSync(rawDir, { recursive: true });
// 자막 글꼴(맑은 고딕). 윈도우 글꼴 폴더 전체를 넘기면 libass가 수백 개를 훑느라 느리다.
const fontDir = path.join(rawDir, 'fonts');
fs.mkdirSync(fontDir, { recursive: true });
for (const f of ['malgun.ttf', 'malgunbd.ttf']) {
  const src = path.join(process.env.WINDIR ?? 'C:\\Windows', 'Fonts', f);
  if (fs.existsSync(src) && !fs.existsSync(path.join(fontDir, f))) fs.copyFileSync(src, path.join(fontDir, f));
}

// ── 자막 ────────────────────────────────────────────────────────────
// cue: { t: 녹화 시작 후 초, title, sub, step }. step은 몇 번째 단계인지(0이면 번호 없음).
let cues = [];
let videoStartedAt = 0;
let stepNo = 0;

const now = () => (Date.now() - videoStartedAt) / 1000;

/// 자막을 바꾼다. 다음 자막이 나올 때까지 화면 아래에 계속 남는다. holdMs는 읽을 틈.
async function caption(title, sub = '', holdMs = 1200) {
  cues.push({ t: now(), title, sub, step: stepNo });
  if (process.env.REC_DEBUG) console.log(`${now().toFixed(1)}s  ${title}`);
  await sleep(holdMs);
}

/// 새 단계를 시작하는 자막. 오른쪽에 "3 / 7" 같은 단계 번호가 붙는다.
async function step(title, sub = '', holdMs = 1400) {
  stepNo += 1;
  await caption(title, sub, holdMs);
}

const assTime = (sec) => {
  const s = Math.max(0, sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const cs = Math.round((s - Math.floor(s)) * 100);
  return `${h}:${String(m).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}.${String(cs % 100).padStart(2, '0')}`;
};
const assText = (s) => String(s).replaceAll('\\', '＼').replaceAll('{', '（').replaceAll('}', '）');

function writeAss(file, roleLabel, endSec) {
  const W = size.width;
  const barMid = size.height + barHeight / 2;
  const totalSteps = Math.max(...cues.map((c) => c.step), 0);
  const lines = [];
  // 녹화 영상은 실제 화면보다 조금 늦게 찍혀 자막이 앞서 보인다. 그만큼 늦춘다.
  const at = (c) => c.t - trimSec + 0.6;
  cues.forEach((c, i) => {
    const start = assTime(at(c));
    const end = assTime(i + 1 < cues.length ? at(cues[i + 1]) : endSec);
    if (c.sub) {
      lines.push(`Dialogue: 1,${start},${end},Title,,0,0,0,,{\\an5\\pos(${W / 2},${barMid - 17})}${assText(c.title)}`);
      lines.push(`Dialogue: 1,${start},${end},Sub,,0,0,0,,{\\an5\\pos(${W / 2},${barMid + 20})}${assText(c.sub)}`);
    } else {
      lines.push(`Dialogue: 1,${start},${end},Title,,0,0,0,,{\\an5\\pos(${W / 2},${barMid})}${assText(c.title)}`);
    }
    if (c.step > 0 && totalSteps > 0) {
      lines.push(`Dialogue: 1,${start},${end},Step,,0,0,0,,{\\an6\\pos(${W - 36},${barMid})}${c.step} / ${totalSteps}`);
    }
  });
  lines.push(`Dialogue: 0,${assTime(0)},${assTime(endSec)},Role,,0,0,0,,{\\an4\\pos(36,${barMid})}${assText(roleLabel)} 시연`);

  // 색은 &HAABBGGRR
  const ass = `[Script Info]
ScriptType: v4.00+
PlayResX: ${W}
PlayResY: ${size.height + barHeight}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Malgun Gothic,30,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Sub,Malgun Gothic,21,&H00E1D5CB,&H00E1D5CB,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Role,Malgun Gothic,20,&H00FAA560,&H00FAA560,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Step,Malgun Gothic,20,&H00B8A394,&H00B8A394,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,6,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${lines.join('\n')}
`;
  fs.writeFileSync(file, '﻿' + ass, 'utf8');
}

/// 화면 설정에서 테마를 바꿔 보이고 라이트로 되돌린다.
async function showThemes(page, settingsLabel, settingsRoute) {
  await openMenu(page, settingsLabel, settingsRoute);
  const theme = (label) => themeOption(page, label);
  await tapIf(page, theme('사이드바 다크'), { pause: 600 });
  await caption('사이드바 다크', '본문은 밝게, 사이드바만 어둡게', 1600);
  await tapIf(page, theme('전체 다크'), { pause: 600 });
  await caption('전체 다크', '화면 전체를 어둡게', 1600);
  await tapIf(page, theme('라이트'), { pause: 600 });
  await caption('설정은 지금 쓰는 기기에만 저장됩니다', '사이드바 색과 화면 밀도(자동·보통·좁게)도 여기서 고릅니다', 2000);
}

// ── 시나리오 ────────────────────────────────────────────────────────
const scripts = {
  async student(page) {
    await step('학생으로 로그인', '매니저에게 받은 이메일과 비밀번호를 입력합니다', 900);
    await login(page, 'student');

    await step('이용 안내 투어', '처음 로그인하면 메뉴를 하나씩 짚어 줍니다. 「다음」으로 넘겨 보세요');
    await caption('닫아도 「마이페이지 → 이용 안내 다시보기」에서 다시 볼 수 있습니다', '', 200);
    await showTourStart(page);

    // 대시보드
    await step('대시보드', '출석 캘린더 · 시스템 공지 · 이번 주 학습 추천 · 설문을 한 화면에서 봅니다');
    await go(page, '/', 1200);
    await hover(page, todayCell(page), 1200);
    await caption('지각·조퇴·외출은 오른쪽 위 「출결 폼」으로 냅니다', '구글 폼이 새 창으로 열립니다', 1400);
    await hover(page, btn(page, '출결 폼'), 1200);

    // 이력서
    await step('이력서 작성', '항목을 채우고 「저장」, 다 쓰면 강사·매니저에게 피드백을 요청합니다');
    await openMenu(page, '이력서 관리', '/resume');
    if (!(await tapIf(page, btn(page, '이어서 작성'), { pause: 2200 }))) await go(page, '/resume/r-demo-1/edit', 2200);
    await typeInto(page, page.getByRole('textbox', { name: '연락처' }), '010-1234-5678');
    await tapIf(page, btn(page, '저장'), { pause: 1500 });

    // AI 코치 — 맞춤 공고 추천 · 공고 맞춤 첨삭 (데모에서는 예시 결과)
    await step('AI 맞춤 공고 추천', '이력서의 기술·직무를 읽고 지원 조건과 근거를 비교해 공고를 추천합니다 (화면의 공고는 예시)');
    await tapIf(page, btn(page, '맞춤 공고 추천'), { pause: 6800 });
    await caption('「추천 근거 보기」', '내 이력서 문장과 공고 문장을 나란히 비교합니다', 600);
    await tapIf(page, btn(page, '추천 근거 보기'), { pause: 2000 });
    await step('AI 공고 맞춤 첨삭', '지원할 공고에 맞춰 이력서 문장을 다듬은 수정안을 받습니다');
    await tapIf(page, btnLike(page, /공고 맞춤 첨삭/), { pause: 1600 });
    await tapIf(page, btnLike(page, /첨삭 시작/), { pause: 4800 });
    await caption('「이 문장으로 바꾸기」로 반영, 「되돌리기」로 되돌리기', '이력서에 없는 내용은 지어내지 않습니다', 1200);
    await tapIf(page, btn(page, '이 문장으로 바꾸기'), { pause: 3200 });
    // 데모 모드는 첨삭 완료(서버 저장)를 지원하지 않아 누르지 않고 가리키기만 한다.
    await caption('「첨삭 완료」를 누르면 공고별 맞춤 이력서로 저장됩니다', '', 600);
    await hover(page, btn(page, '첨삭 완료'), 1600);
    await tapIf(page, btn(page, '닫기'), { pause: 1000 });
    await caption('공고와 관계없이 문장만 다듬을 때는 「이력서 첨삭」', '피드백이 오면 위의 종 아이콘에 표시됩니다', 600);
    await scrollCoachPanelToTop(page);
    await hover(page, btn(page, '이력서 첨삭'), 1600);

    // 기록실
    await step('기록실에 기록 제출', '블로그 · 스터디 · 자격증 기록을 올리면 승인 후 마일리지가 적립됩니다');
    await openMenu(page, '기록실', '/records');
    if (!(await tapIf(page, btnLike(page, /새로운 기록 추가/), { pause: 1800 }))) await go(page, '/records/create', 1800);
    await caption('제출할 기록 종류를 고릅니다', '종류마다 적립 규칙이 함께 안내됩니다', 1400);
    await tapIf(page, btnLike(page, /^블로그/), { pause: 1000 });
    await caption('블로그 제출', '주차를 고르고 글 링크를 붙여 넣은 뒤 「제출」', 600);
    await tapIf(page, btnLike(page, /^4주차/), { pause: 700 });
    await typeInto(page, page.getByRole('textbox').first(), 'https://velog.io/@student/week4');
    await tapIf(page, btn(page, '제출'), { pause: 600 });
    await caption('제출하면 「대기」 상태가 됩니다', '매니저가 승인하면 규칙에 따라 마일리지가 적립됩니다', 2400);

    // 성취도평가
    await step('성취도평가 결과 확인', '제출한 평가의 점수와 문항별 정답을 봅니다');
    await openMenu(page, '성취도평가', '/assessments');
    if (!(await tapIf(page, btnLike(page, /34기 2차 성취도평가/), { pause: 2200 }))) await go(page, '/assessments/a1/result', 2200);
    await page.mouse.wheel(0, 400);
    await sleep(1600);

    // 게시판
    await step('게시판', '공지사항을 확인하고, 소통 피드에 궁금한 점을 올립니다');
    await openMenu(page, '게시판', '/board');
    await sleep(800);
    await tapIf(page, btn(page, '소통 피드'), { pause: 1200 });
    const feedBox = page.getByRole('textbox').first();
    if (await feedBox.count()) {
      await typeInto(page, feedBox, '이번 주 SQL 스터디 같이 하실 분 있나요?');
      // 보내기(종이비행기) 버튼은 접근성 라벨이 없어 입력칸 오른쪽 옆을 누른다.
      const box = await feedBox.first().boundingBox();
      if (box) {
        await moveTo(page, box.x + box.width + 28, box.y + box.height / 2);
        await sleep(250);
        await page.mouse.down();
        await page.mouse.up();
      }
      await sleep(1000);
      await caption('올린 글은 같은 기수 학생들이 보고 댓글을 답니다', '', 1800);
    }

    // 학습실
    await step('학습실', '배정된 인프런 강의와 이번 주 커리큘럼에 맞춘 추천 영상을 봅니다');
    await openMenu(page, '학습실', '/study-room');
    await tapIf(page, btnLike(page, /^Python \d+개 강의/), { pause: 1800 });

    // 마일리지
    await step('마일리지 상점', '적립한 마일리지로 교환할 상품을 장바구니에 담습니다');
    await openMenu(page, '마일리지', '/mileage');
    if (!(await tapIf(page, btnLike(page, /마일리지 사용하기/), { pause: 2000 }))) await go(page, '/mileage/shop', 2000);
    await tapIf(page, btnLike(page, /네이버페이 포인트/), { pause: 1400 });
    await tapIf(page, btn(page, '장바구니에 담기'), { pause: 1400 });
    await caption('장바구니에서 구매를 요청하면 매니저가 승인할 때 차감됩니다', '', 2200);

    // 학생 챗봇
    await step('학생 챗봇', '오른쪽 아래 로봇을 누르면 LMS 정책 · 공지 · 출결 · 프로젝트를 물어볼 수 있습니다');
    await go(page, '/', 1400);
    await tapIf(page, btn(page, '학생 챗봇 열기'), { pause: 1400 });
    await caption('「자주 묻는 질문」 버튼으로 바로 답 보기', '출결 기준 · 공가 사용 방법 · 훈련장려금 등', 600);
    await tapIf(page, page.getByRole('checkbox', { name: '공가 사용 방법' }), { pause: 2200 });
    await caption('궁금한 내용은 직접 입력해도 됩니다', '기수 · 단위기간 같은 조건을 함께 적으면 더 정확합니다', 600);
    await typeInto(page, page.getByRole('textbox', { name: /메시지를 입력하세요/ }), '3단위기간 출석률 85%면 훈련장려금 받을 수 있어?');
    await tapIf(page, btn(page, '질문 보내기'), { pause: 5200 });
    await tapIf(page, btn(page, '챗봇 닫기'), { pause: 600 });

    // 마이페이지 · 화면 설정
    await step('마이페이지 · 화면 설정', '프로필과 비밀번호를 관리하고, 이용 안내를 다시 볼 수 있습니다');
    await go(page, '/my-page', 2000);
    await hover(page, btnLike(page, /이용 안내 다시보기/), 1000);
    await caption('사이드바 맨 아래 「설정」', '화면 테마를 바꿔 봅니다', 1000);
    await showThemes(page, '설정', '/settings');

    await caption('학생 시연 끝', 'PLAYDATA LMS', 2200);
  },

  async instructor(page) {
    await step('강사로 로그인', '발급받은 강사 계정으로 로그인합니다', 900);
    await login(page, 'instructor');

    await step('이용 안내 투어', '처음 로그인하면 강사 메뉴를 하나씩 짚어 줍니다');
    await caption('닫아도 「마이페이지 → 이용 안내 다시보기」에서 다시 볼 수 있습니다', '', 200);
    await showTourStart(page);

    // 자리 확인
    await go(page, '/instructor', 1500);
    await step('자리 확인', '교시마다 호명한 학생이 자리에 있으면 「확인」, 없으면 「보류」', 1800);
    for (const action of ['확인', '확인', '보류', '확인']) {
      await tapIf(page, btn(page, action), { pause: 1000 });
    }
    await caption('누를 때마다 다음 학생으로 넘어가고 위에 집계됩니다', '보류한 학생은 오른쪽에 모여 다시 확인할 수 있습니다', 2400);

    // 이력서 피드백
    await step('이력서 피드백', '피드백을 요청한 이력서를 「검토하기」로 열고 항목별 의견을 남깁니다');
    await openMenu(page, '이력서관리', '/instructor/resumes');
    if (await writeResumeFeedback(page, '핵심역량/강점', '프로젝트 성과를 수치로 적어 보세요.')) {
      await caption('검토가 끝나면 오른쪽 위 「승인」', '학생은 알림 종에서 피드백을 받고 답글을 답니다', 600);
      await hover(page, btn(page, '승인'), 1600);
    }

    // 공지 작성 (목록을 먼저 열면 데모 스트림이 갱신되지 않아 작성 화면으로 바로 간다)
    await step('공지 작성', '게시물관리 → 「공지 작성」으로 반 전체에 공지를 올립니다');
    await go(page, '/instructor/board/create', 1500);
    const noticeBoxes = page.getByRole('textbox');
    if ((await noticeBoxes.count()) >= 2) {
      await typeInto(page, noticeBoxes.nth(0), '내일 SQL 실습 준비물 안내');
      await typeInto(page, noticeBoxes.nth(1), '노트북 충전기와 DBeaver 설치를 부탁드립니다.');
      await sleep(600);
      await tapIf(page, btnLike(page, /등록/), { pause: 2200 });
    }

    // 채점
    await step('성취도평가 채점', '제출한 답안의 자동 채점 결과를 확인합니다');
    await openMenu(page, '성취도평가', '/instructor/assessments');
    await go(page, '/instructor/assessments/a1', 1800);
    if (await tapIf(page, btnLike(page, /^학생 \d+점/), { pause: 1600 })) {
      await caption('문항별 점수를 고치고 「점수 저장」', '단답형은 표현이 달라도 강사가 맞게 처리할 수 있습니다', 1200);
      await hover(page, btn(page, '점수 저장'), 1400);
    }

    // 평가 만들기
    await step('평가 만들기', '제목과 기간을 정하고 문항을 넣습니다');
    await go(page, '/instructor/assessments/create', 1800);
    await typeInto(page, page.getByRole('textbox').nth(0), '34기 3차 성취도평가');
    await typeInto(page, page.getByRole('textbox').nth(1), 'Python, SQL');
    if (await btn(page, '문제 생성 AI').count()) {
      await caption('「문제 생성 AI」', '등록된 커리큘럼에서 출제 범위와 문항 수를 고릅니다', 800);
      await tap(page, btn(page, '문제 생성 AI'), { pause: 1500 });
      for (const re of [/^D1 /, /^D8 /]) await tapIf(page, btnLike(page, re), { pause: 800 });
      await tapIf(page, page.getByRole('checkbox', { name: '15문항' }), { pause: 800 });
      await caption('「초안 만들기」를 누르면 AI가 문항 초안을 만듭니다', '초안은 강사가 검토·수정한 뒤 발행합니다', 1000);
      await hover(page, btn(page, '초안 만들기'), 1600);
      await tapIf(page, btn(page, '취소'), { pause: 1000 });
    }
    if (await btn(page, '수동 추가').count()) {
      await caption('「수동 추가」로 직접 문항 넣기', '문제 · 선택지 · 정답을 입력합니다', 800);
      await tap(page, btn(page, '수동 추가'), { pause: 1300 });
      const q = page.getByRole('textbox');
      await typeInto(page, q.nth(0), 'SQL에서 두 테이블을 합칠 때 쓰는 키워드는?');
      await typeInto(page, q.nth(2), 'JOIN\nGROUP BY\nORDER BY\nLIMIT');
      await sleep(400);
      await tapIf(page, btn(page, '확인'), { pause: 1500 });
    }
    await caption('「저장」 후 「발행」하면 학생에게 공개됩니다', '', 1000);
    await hover(page, btn(page, '발행'), 1400);

    // 커리큘럼
    await step('커리큘럼', '구글 시트를 CSV로 내려받아 「CSV 교체」로 올립니다');
    await openMenu(page, '커리큘럼', '/instructor/curriculum');
    const search = page.getByRole('textbox').first();
    if (await search.count()) await typeInto(page, search, 'Database');
    await caption('등록한 커리큘럼은 학습 추천과 평가 문항 생성에 쓰입니다', '', 2400);

    await caption('강사 시연 끝', 'PLAYDATA LMS', 2200);
  },

  async admin(page) {
    await step('관리자로 로그인', '관리자 계정으로 로그인합니다', 900);
    await login(page, 'admin');

    await step('이용 안내 투어', '처음 로그인하면 사이드바 메뉴를 하나씩 짚어 줍니다');
    await caption('닫아도 「마이페이지 → 이용 안내 다시보기」에서 다시 볼 수 있습니다', '', 200);
    await showTourStart(page);

    // 대시보드
    await go(page, '/admin', 1200);
    await step('대시보드', '기록실 승인 대기 · 이력서 검토 대기 등 오늘 처리할 일이 모입니다', 1200);
    const pendingCard = btnLike(page, /^기록실 승인 대기/);
    await hover(page, pendingCard, 1200);

    // 기록실 승인
    await step('기록실 승인', '학생이 올린 자격증 · 스터디 · 블로그 기록을 확인합니다');
    if (!(await tapIf(page, pendingCard, { pause: 2000 }))) await go(page, '/admin/records', 2000);
    await tapIf(page, btn(page, '상세 보기'), { pause: 1400 });
    await caption('제출 내용을 확인하고 「승인」', '승인하면 기수 규칙에 따라 마일리지가 자동 적립됩니다', 1200);
    await tapIf(page, btn(page, '승인'), { pause: 1800 });
    await caption('조건에 맞지 않으면 「반려」', '', 600);
    await hover(page, btn(page, '반려'), 1200);

    // 이력서 피드백
    await step('이력서 피드백', '피드백을 요청한 이력서를 「검토하기」로 열고 항목별 의견을 남깁니다');
    await openMenu(page, '이력서', '/admin/resumes');
    if (await writeResumeFeedback(page, '기본정보', '연락처 형식을 통일해 주세요.')) {
      await caption('검토가 끝나면 오른쪽 위 「승인」', '학생은 알림 종에서 피드백을 받고 답글을 답니다', 600);
      await hover(page, btn(page, '승인'), 1600);
    }

    // 공지 작성 (게시판 목록을 먼저 열어 두면 데모 스트림이 등록 전 값에 머문다)
    await step('공지 작성', '게시판 → 「공지 작성」으로 기수 전체에 공지를 올립니다');
    await go(page, '/admin/board/create', 1500);
    await typeInto(page, page.getByRole('textbox').nth(0), '금요일 팀 프로젝트 발표 안내');
    await typeInto(page, page.getByRole('textbox').nth(1), '오후 2시부터 팀별 10분씩 발표합니다.');
    await sleep(600);
    await tapIf(page, btn(page, '공지 등록'), { pause: 1600 });
    await caption('등록한 공지는 학생 대시보드와 게시판에 바로 보입니다', '예약 공지 · 로그인 알림 팝업도 여기서 관리합니다', 2400);

    // 출석 관리
    await step('출석 관리', '고용24 입퇴실 기록과 출결 폼을 한 표에서 확인합니다');
    await go(page, '/admin/attendance', 2000);
    await hover(page, btnLike(page, /^김하늘 /), 1000);
    await caption('「매일 08:30 공지 등록」', '출결 폼 안내 공지를 매일 아침 자동으로 올립니다', 600);
    await hover(page, btnLike(page, /08:30 공지 등록/), 1600);

    // 설문 · 마일리지 · 기수
    await step('설문 · 제출', '구글 폼 설문을 등록하고 학생 제출 현황을 봅니다');
    await go(page, '/admin/form-tasks', 2200);

    await step('마일리지 관리', '상품 · 구매 요청 승인 · 수동 지급 · 적립 규칙을 관리합니다');
    await go(page, '/admin/mileage', 1500);
    await tapIf(page, btnLike(page, /^상품 관리/), { pause: 2400 });

    await step('LLMOps (AI 품질)', '문제 생성 · 공고 챗봇 · 추천 · 첨삭 · 학생 챗봇의 요청 수, 성공률, 지연, 토큰을 봅니다 (화면의 숫자는 예시)');
    await go(page, '/admin/ai-quality', 2000);
    await hover(page, page.getByRole('checkbox', { name: '전체', exact: true }), 1200);
    await caption('기능별로 좁혀 보기', '위쪽 필터에서 문제생성 · 공고챗봇 · 추천 · 첨삭 · 학생챗봇을 고릅니다', 400);
    await tapIf(page, page.getByRole('checkbox', { name: '문제생성', exact: true }), { pause: 1800 });
    await caption('문제 생성은 채택률 · 수정률로 강사가 AI 초안을 얼마나 썼는지 봅니다', '', 1600);
    await tapIf(page, page.getByRole('checkbox', { name: '전체', exact: true }), { pause: 800 });
    await caption('최근 평가 실행 · 프롬프트 버전별 · 최근 생성 로그', '오류가 난 요청은 로그 카드에 사유가 표시됩니다', 400);
    await moveTo(page, size.width / 2, size.height / 2);
    await page.mouse.wheel(0, 700);
    await sleep(2600);

    await step('기수 관리', '진행 중 · 예정 기수와 교육 기간을 관리합니다');
    await go(page, '/admin/cohorts', 2200);

    await caption('관리자 시연 끝', 'PLAYDATA LMS', 2200);
  },
};

// ── 녹화 ────────────────────────────────────────────────────────────
const order = ['student', 'instructor', 'admin'];
const labels = { student: '학생', instructor: '강사', admin: '관리자' };
const server = await serveBuild(5180);
const browser = await chromium.launch();

try {
  for (const [i, role] of order.entries()) {
    if (only && only !== role) continue;
    const ctx = await browser.newContext({
      viewport: size,
      locale: 'ko-KR',
      recordVideo: { dir: rawDir, size },
    });
    const page = await ctx.newPage();
    videoStartedAt = Date.now();
    cues = [];
    stepNo = 0;
    resetMouse();
    await page.goto(server.url);
    await waitForApp(page);
    await installCursor(page);
    await sleep(800);
    try {
      await scripts[role](page);
    } catch (e) {
      console.error(`[${role}] 시나리오 중단:`, e.message);
    }
    const endSec = now() - trimSec + 0.5;
    const video = page.video();
    await ctx.close();
    const raw = await video.path();

    const assName = `${role}.ass`;
    writeAss(path.join(rawDir, assName), labels[role], endSec);
    const mp4 = path.join(videoDir, `${i + 1}_${labels[role]}_시연.mp4`);
    // 영상 아래에 자막 바를 붙이고(pad) 윗선을 긋고(drawbox) 자막을 입힌다.
    // 필터 안의 경로는 콜론 문제를 피하려고 rawDir 기준 상대 경로로 넘긴다.
    const vf = [
      `pad=${size.width}:${size.height + barHeight}:0:0:color=0x0F172A`,
      `drawbox=x=0:y=${size.height}:w=${size.width}:h=3:color=0x0B57D0:t=fill`,
      `subtitles=${assName}:fontsdir=fonts`,
    ].join(',');
    execFileSync(
      'ffmpeg',
      [
        '-hide_banner', '-loglevel', 'error', '-y',
        '-ss', String(trimSec), '-i', raw,
        '-vf', vf,
        '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', mp4,
      ],
      { cwd: rawDir },
    );
    console.log(mp4);
  }
} finally {
  await browser.close();
  server.close();
}
