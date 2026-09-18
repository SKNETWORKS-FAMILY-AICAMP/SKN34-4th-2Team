// PDF 가이드처럼 학생·강사·관리자 전체를 한 편으로 설명하는 내레이션 영상을 만든다.
// 결과: onboarding/output/videos/0_PLAYDATA_LMS_이용_가이드.mp4 (+ 유튜브 챕터 .txt)
// 사용: node guide.mjs                 (녹음 → 녹화 → 합치기)
//       node guide.mjs --reuse        (녹화는 건너뛰고 마지막 녹화로 다시 합치기)
//
// 흐름
// 1) 대본(아래 guide)의 문장을 edge-tts(ko-KR-SunHiNeural)로 읽어 mp3를 만든다. 문장별로 캐시한다.
// 2) 표지·목차·파트 표지는 HTML로 그려 캡처한다.
// 3) 역할마다 데모 앱을 녹화한다. 문장을 읽는 동안 화면 조작을 하고, 다음 문장은 앞 문장이 끝난 뒤 시작한다.
// 4) 구간마다 자막 바·자막·음성을 입혀 mp4로 만들고, 순서대로 이어 붙인다.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';
import { chromium } from 'playwright';
import { serveBuild, waitForApp, go, outRoot, deliverRoot, sleep } from './lib/app.mjs';
import {
  size, installCursor, highlight, highlightRect, railRect, resetMouse, tapAt, tapIf, hover, typeInto,
  btn, btnLike, openMenu, login, themeOption, scrollCoachPanelToTop, todayCell, writeResumeFeedback, showTourStart,
} from './lib/actions.mjs';

const reuse = process.argv.includes('--reuse');
const voice = 'ko-KR-SunHiNeural';
const rate = '+6%';
const barHeight = 100;
const fps = 30;
// 녹화 영상은 실제 화면보다 조금 늦게 찍혀 음성·자막이 앞서 들린다. 그만큼 늦춘다.
const videoLag = 0.6;
const gapAfterLine = 0.45;

const workDir = path.join(outRoot, 'guide');
const ttsDir = path.join(outRoot, 'tts');
const videoDir = path.join(deliverRoot, 'videos');
const outName = '0_PLAYDATA_LMS_이용_가이드';
for (const d of [workDir, ttsDir, videoDir, path.join(workDir, 'fonts')]) fs.mkdirSync(d, { recursive: true });
for (const f of ['malgun.ttf', 'malgunbd.ttf']) {
  const src = path.join(process.env.WINDIR ?? 'C:\\Windows', 'Fonts', f);
  const dst = path.join(workDir, 'fonts', f);
  if (fs.existsSync(src) && !fs.existsSync(dst)) fs.copyFileSync(src, dst);
}

const roleColor = { student: '#1f6feb', instructor: '#0f9d76', admin: '#7c4dff', common: '#0b57d0' };
const roleLabel = { student: '학생', instructor: '강사', admin: '관리자' };

// ── 대본 ────────────────────────────────────────────────────────────
// beat: { label: 자막 바 왼쪽 이름, say: 읽을 문장, text?: 자막(없으면 say), chapter?: 유튜브 챕터로 쓸지, do?: 화면 조작 }
// 음성은 '플레이데이터'로 읽고 자막은 PLAYDATA로 보이도록 text를 따로 둔다.
const BRAND_SAY = '플레이데이터';

const cards = {
  intro: {
    kind: 'intro',
    lines: [
      {
        say: `안녕하세요. ${BRAND_SAY} LMS 이용 가이드입니다.`,
        text: '안녕하세요. PLAYDATA LMS 이용 가이드입니다.',
      },
      { say: '처음 로그인하는 방법부터 학생, 강사, 관리자 화면의 주요 기능까지 차례대로 안내해 드립니다.' },
    ],
  },
  toc: {
    kind: 'toc',
    lines: [
      { say: '영상은 시작하기, 학생 화면, 강사 화면, 관리자 화면 순서로 진행됩니다.' },
      { say: '필요한 부분만 골라 보셔도 됩니다.' },
    ],
  },
  outro: {
    kind: 'outro',
    lines: [
      { say: '마지막으로 자주 묻는 질문입니다.' },
      { say: '로그인이 안 되면 이메일 앞뒤 공백을 확인하고, 계속 안 되면 매니저에게 계정 확인을 요청하세요.' },
      { say: '화면이 계속 로딩 중이면 새로고침하거나 다시 로그인해 보세요. 이용 안내 투어는 마이페이지에서 언제든 다시 볼 수 있습니다.' },
      {
        say: `${BRAND_SAY} LMS 이용 가이드였습니다. 감사합니다.`,
        text: 'PLAYDATA LMS 이용 가이드였습니다. 감사합니다.',
      },
    ],
  },
};

const parts = [
  {
    id: 'part1',
    no: 1,
    role: 'student',
    color: roleColor.common,
    title: '시작하기',
    intro: '로그인과 이용 안내 투어, 화면 구성과 화면 설정을 알아봅니다.',
    cardSay: 'PART 1, 시작하기입니다. 로그인과 이용 안내 투어, 화면 구성과 화면 설정을 알아봅니다.',
    beats: [
      {
        label: '로그인',
        chapter: true,
        say: '매니저에게 안내받은 주소로 접속한 뒤, 발급받은 이메일과 비밀번호를 입력하고 로그인 버튼을 누릅니다.',
        do: async (page) => {
          await highlight(page, page.getByRole('textbox').nth(0), 2200);
          await sleep(900);
          await login(page, 'student');
        },
      },
      {
        label: '비밀번호 변경',
        say: '처음 로그인할 때는 비밀번호 변경 화면이 먼저 나옵니다. 새 비밀번호를 정해야 다음 화면으로 넘어갈 수 있습니다.',
      },
      {
        label: '이용 안내 투어',
        chapter: true,
        say: '로그인하면 이용 안내 투어가 시작됩니다. 투어를 닫아도 마이페이지의 이용 안내 다시보기에서 언제든 다시 볼 수 있습니다.',
        text: '로그인하면 이용 안내 투어가 시작됩니다. 닫아도 「마이페이지 → 이용 안내 다시보기」에서 언제든 다시 볼 수 있습니다.',
        do: async (page) => showTourStart(page, 4200),
      },
      {
        label: '화면 구성',
        chapter: true,
        say: '화면 왼쪽 사이드바에서 메뉴를 고르고, 오른쪽 위에서 내 계정과 기수를 확인합니다. 역할에 따라 보이는 메뉴가 다릅니다.',
        do: async (page) => {
          await go(page, '/', 1200);
          const menu = await railRect(page, '대시보드');
          if (menu) await highlightRect(page, { ...menu, height: menu.height + 10 * 44 }, 2600);
          await sleep(2600);
          await highlight(page, btnLike(page, /^학생 SK네트웍스/), 2600);
        },
      },
      {
        label: '화면 설정',
        chapter: true,
        say: '사이드바 맨 아래 설정에서는 화면 테마와 사이드바 색, 화면 밀도를 고를 수 있습니다.',
        do: async (page) => {
          const settings = await railRect(page, '설정');
          if (settings) await highlightRect(page, settings, 2000);
          await sleep(1400);
          await openMenu(page, '설정', '/settings');
        },
      },
      {
        label: '화면 테마',
        say: '라이트, 사이드바 다크, 전체 다크 중에서 편한 테마를 고르세요. 설정은 지금 사용하는 기기에만 저장됩니다.',
        do: async (page) => {
          await tapIf(page, themeOption(page, '사이드바 다크'), { pause: 1800 });
          await tapIf(page, themeOption(page, '전체 다크'), { pause: 1800 });
          await tapIf(page, themeOption(page, '라이트'), { pause: 1000 });
        },
      },
    ],
  },
  {
    id: 'part2',
    no: 2,
    role: 'student',
    color: roleColor.student,
    title: '학생 화면 안내',
    intro: '출석 확인부터 이력서와 AI 맞춤 공고 추천·첨삭, 기록실, 성취도평가, 마일리지, 학생 챗봇까지 수강 생활에 필요한 기능을 살펴봅니다.',
    cardSay: 'PART 2, 학생 화면입니다. 출석 확인부터 이력서와 AI 맞춤 공고 추천, 첨삭, 기록실, 성취도평가, 마일리지, 학생 챗봇까지 수강 생활에 필요한 기능을 살펴봅니다.',
    beats: [
      {
        label: '대시보드',
        chapter: true,
        say: '대시보드는 로그인하면 가장 먼저 보이는 홈입니다. 출석 캘린더와 시스템 공지, 이번 주 학습 추천, 설문을 한 화면에서 확인합니다.',
        do: async (page) => {
          await openMenu(page, '대시보드', '/');
          await highlight(page, todayCell(page), 2400, 10);
        },
      },
      {
        label: '출결 폼',
        say: '지각이나 조퇴, 외출 같은 예외 출결은 오른쪽 위 출결 폼 버튼으로 제출합니다.',
        do: async (page) => {
          await highlight(page, btn(page, '출결 폼'), 2600);
          await hover(page, btn(page, '출결 폼'), 600);
        },
      },
      {
        label: '이력서 관리',
        chapter: true,
        say: '이력서 관리에서는 이력서를 작성하고, 다 쓰면 강사와 매니저에게 피드백을 요청합니다.',
        do: async (page) => {
          await openMenu(page, '이력서 관리', '/resume');
          await highlight(page, btnLike(page, /^피드백 요청/), 2400);
        },
      },
      {
        label: '이력서 작성',
        say: '편집 화면에서 항목을 채우고 저장합니다. 위쪽 섹션 버튼을 누르면 해당 항목으로 바로 이동합니다.',
        do: async (page) => {
          if (!(await tapIf(page, btn(page, '이어서 작성'), { pause: 2000 }))) await go(page, '/resume/r-demo-1/edit', 2000);
          await typeInto(page, page.getByRole('textbox', { name: '연락처' }), '010-1234-5678');
          await highlight(page, btn(page, '저장'), 1600);
          await tapIf(page, btn(page, '저장'), { pause: 800 });
        },
      },
      {
        label: 'AI 코치',
        say: '오른쪽 AI 코치에서는 작성한 이력서를 바탕으로 맞춤 공고를 추천받고, 이력서 문장 첨삭을 받을 수 있습니다.',
        do: async (page) => {
          await highlight(page, btn(page, '맞춤 공고 추천'), 2400);
          await sleep(2600);
          await highlight(page, btn(page, '이력서 첨삭'), 2200);
        },
      },
      {
        label: '맞춤 공고 추천',
        chapter: true,
        say: '맞춤 공고 추천을 누르면 이력서에서 기술과 직무를 읽고, 열린 공고를 찾아 지원 조건과 근거를 비교해 추천합니다. 화면의 공고는 데모용 예시입니다.',
        do: async (page) => {
          await tapIf(page, btn(page, '맞춤 공고 추천'), { pause: 7000 });
        },
      },
      {
        label: '추천 근거',
        say: '추천 근거 보기를 누르면 내 이력서 문장과 공고 문장을 나란히 놓고 왜 추천했는지 확인할 수 있습니다.',
        do: async (page) => {
          await tapIf(page, btn(page, '추천 근거 보기'), { pause: 1200 });
          await page.mouse.wheel(0, 250);
        },
      },
      {
        label: '공고 맞춤 첨삭',
        chapter: true,
        say: '지원할 공고에서 공고 맞춤 첨삭을 누르면, AI가 공고 요건에 맞춰 이력서 문장을 다듬은 수정안을 제안합니다.',
        do: async (page) => {
          await tapIf(page, btnLike(page, /공고 맞춤 첨삭/), { pause: 1600 });
          await highlight(page, btnLike(page, /첨삭 시작/), 1400);
          await sleep(1000);
          await tapIf(page, btnLike(page, /첨삭 시작/), { pause: 4800 });
        },
      },
      {
        label: '수정안 적용',
        say: '수정안을 확인하고 이 문장으로 바꾸기를 누르면 이력서에 반영되고, 되돌리기로 언제든 되돌릴 수 있습니다. 첨삭 완료를 누르면 공고별 맞춤 이력서로 저장됩니다.',
        do: async (page) => {
          await highlight(page, btn(page, '이 문장으로 바꾸기'), 1600);
          await sleep(1400);
          await tapIf(page, btn(page, '이 문장으로 바꾸기'), { pause: 3000 });
          await highlight(page, btn(page, '되돌리기'), 2000);
          await sleep(2200);
          // 데모 모드는 첨삭 완료(서버 저장)를 지원하지 않아 누르지 않고 가리키기만 한다.
          await highlight(page, btn(page, '첨삭 완료'), 1800);
          await sleep(2000);
          await tapIf(page, btn(page, '닫기'), { pause: 1000 });
        },
      },
      {
        label: '이력서 첨삭',
        say: '특정 공고와 관계없이 문장 표현만 다듬고 싶을 때는 이력서 첨삭 버튼을 누르면 됩니다.',
        do: async (page) => {
          await scrollCoachPanelToTop(page);
          await highlight(page, btn(page, '이력서 첨삭'), 2600);
          await hover(page, btn(page, '이력서 첨삭'), 400);
        },
      },
      {
        label: '피드백 확인',
        say: '강사나 매니저가 피드백을 남기면 위쪽 알림에 표시되고, 항목별로 답글을 달 수 있습니다.',
        do: async (page) => {
          await highlight(page, btn(page, '피드백 열기'), 2400);
        },
      },
      {
        label: '기록실',
        chapter: true,
        say: '기록실에서는 자격증, 스터디, 블로그 같은 활동 기록을 제출합니다. 새로운 기록 추가를 누르고 종류를 고릅니다.',
        do: async (page) => {
          await openMenu(page, '기록실', '/records');
          await highlight(page, btnLike(page, /새로운 기록 추가/), 1600);
          await sleep(1000);
          if (!(await tapIf(page, btnLike(page, /새로운 기록 추가/), { pause: 1400 }))) await go(page, '/records/create', 1400);
        },
      },
      {
        label: '블로그 제출',
        say: '블로그 기록은 주차를 고르고 글 링크를 붙여 넣은 뒤 제출합니다.',
        do: async (page) => {
          await tapIf(page, btnLike(page, /^블로그/), { pause: 1000 });
          await tapIf(page, btnLike(page, /^4주차/), { pause: 600 });
          await typeInto(page, page.getByRole('textbox').first(), 'https://velog.io/@student/week4');
          await tapIf(page, btn(page, '제출'), { pause: 600 });
        },
      },
      {
        label: '승인과 적립',
        say: '제출한 기록은 대기 상태가 되고, 매니저가 승인하면 기수 규칙에 따라 마일리지가 자동으로 적립됩니다.',
      },
      {
        label: '성취도평가',
        chapter: true,
        say: '성취도평가에서는 공개된 평가에 응시하고, 제출한 평가의 점수와 문항별 정답을 확인합니다.',
        do: async (page) => {
          await openMenu(page, '성취도평가', '/assessments');
          if (!(await tapIf(page, btnLike(page, /34기 2차 성취도평가/), { pause: 1800 }))) await go(page, '/assessments/a1/result', 1800);
          await page.mouse.wheel(0, 400);
        },
      },
      {
        label: '게시판',
        chapter: true,
        say: '게시판에서는 공지사항을 확인하고, 소통 피드에 궁금한 점을 올릴 수 있습니다.',
        do: async (page) => {
          await openMenu(page, '게시판', '/board');
          await tapIf(page, btn(page, '소통 피드'), { pause: 1000 });
          const box = page.getByRole('textbox').first();
          if (await box.count()) {
            await typeInto(page, box, '이번 주 SQL 스터디 같이 하실 분 있나요?');
            // 보내기(종이비행기) 버튼은 접근성 라벨이 없어 입력칸 오른쪽 옆을 누른다.
            const b = await box.first().boundingBox();
            if (b) await tapAt(page, b.x + b.width + 28, b.y + b.height / 2, 800);
          }
        },
      },
      {
        label: '학습실',
        chapter: true,
        say: '학습실에서는 배정된 인프런 강의 패키지와 이번 주 커리큘럼에 맞춘 추천 영상을 확인합니다.',
        do: async (page) => {
          await openMenu(page, '학습실', '/study-room');
          await tapIf(page, btnLike(page, /^Python \d+개 강의/), { pause: 800 });
        },
      },
      {
        label: '자리 배치 · 설문',
        say: '자리 배치에서는 매니저가 게시한 내 좌석을, 설문과 제출에서는 진행 중인 설문과 마감일을 확인합니다.',
        do: async (page) => {
          await openMenu(page, '자리 배치', '/seating');
          await sleep(1200);
          await openMenu(page, '설문 · 제출', '/forms');
          await highlight(page, btn(page, '구글폼 작성'), 2000);
        },
      },
      {
        label: '마일리지',
        chapter: true,
        say: '마일리지 메뉴에서는 적립과 사용 내역을 보고, 마일리지 사용하기를 눌러 상점으로 들어갑니다.',
        do: async (page) => {
          await openMenu(page, '마일리지', '/mileage');
          await highlight(page, btnLike(page, /마일리지 사용하기/), 1800);
          await sleep(1400);
          if (!(await tapIf(page, btnLike(page, /마일리지 사용하기/), { pause: 1200 }))) await go(page, '/mileage/shop', 1200);
        },
      },
      {
        label: '마일리지 상점',
        say: '교환할 상품을 골라 장바구니에 담고 구매를 요청합니다. 매니저가 승인하면 포인트가 차감됩니다.',
        do: async (page) => {
          await tapIf(page, btnLike(page, /네이버페이 포인트/), { pause: 1300 });
          await tapIf(page, btn(page, '장바구니에 담기'), { pause: 1000 });
        },
      },
      {
        label: '학생 챗봇',
        chapter: true,
        say: '화면 오른쪽 아래 로봇 아이콘을 누르면 학생 챗봇이 열립니다. LMS 정책과 공지, 출결, 이전 기수 프로젝트에 대해 물어볼 수 있습니다.',
        do: async (page) => {
          await go(page, '/', 1400);
          await highlight(page, btn(page, '학생 챗봇 열기'), 2200, 2);
          await sleep(2000);
          await tapIf(page, btn(page, '학생 챗봇 열기'), { pause: 1200 });
        },
      },
      {
        label: '자주 묻는 질문',
        say: '자주 묻는 질문 버튼을 누르면 출결 기준이나 공가 사용 방법 같은 답을 바로 볼 수 있습니다.',
        do: async (page) => {
          const chip = page.getByRole('checkbox', { name: '공가 사용 방법' });
          await highlight(page, chip, 1800, 3);
          await sleep(1600);
          await tapIf(page, chip, { pause: 800 });
        },
      },
      {
        label: '챗봇에 직접 질문',
        say: '궁금한 내용은 직접 입력해도 됩니다. 기수나 단위기간 같은 조건을 함께 적으면 더 정확하게 답해 줍니다.',
        do: async (page) => {
          await typeInto(page, page.getByRole('textbox', { name: /메시지를 입력하세요/ }), '3단위기간 출석률 85%면 훈련장려금 받을 수 있어?');
          await tapIf(page, btn(page, '질문 보내기'), { pause: 5200 });
        },
      },
      {
        label: '마이페이지',
        chapter: true,
        say: '마이페이지에서는 프로필 사진과 비밀번호를 관리하고, 이용 안내 다시보기로 투어를 다시 볼 수 있습니다.',
        do: async (page) => {
          await tapIf(page, btn(page, '챗봇 닫기'), { pause: 600 });
          await go(page, '/my-page', 1600);
          await highlight(page, btnLike(page, /이용 안내 다시보기/), 2400);
        },
      },
    ],
  },
  {
    id: 'part3',
    no: 3,
    role: 'instructor',
    color: roleColor.instructor,
    title: '강사 화면 안내',
    intro: '자리 확인과 이력서 피드백, 공지 작성, 성취도평가 출제와 채점, 커리큘럼 등록을 알아봅니다.',
    cardSay: 'PART 3, 강사 화면입니다. 자리 확인과 이력서 피드백, 공지 작성, 성취도평가 출제와 채점, 커리큘럼 등록을 알아봅니다.',
    beats: [
      {
        label: '로그인',
        say: '강사는 발급받은 강사 계정으로 로그인합니다.',
        do: async (page) => login(page, 'instructor'),
      },
      {
        label: '이용 안내 투어',
        say: '강사도 처음 로그인하면 이용 안내 투어가 뜹니다. 투어는 마이페이지의 이용 안내 다시보기에서 언제든 다시 볼 수 있으니, 여기서는 닫고 주요 기능을 살펴보겠습니다.',
        text: '처음 로그인하면 이용 안내 투어가 뜹니다. 「마이페이지 → 이용 안내 다시보기」에서 다시 볼 수 있으니 여기서는 닫고 넘어갑니다.',
        do: async (page) => showTourStart(page),
      },
      {
        label: '자리 확인',
        chapter: true,
        say: '자리 확인에서는 날짜와 교시를 고른 뒤, 호명한 학생이 자리에 있으면 확인, 없으면 보류를 누릅니다.',
        do: async (page) => {
          await go(page, '/instructor', 1400);
          await highlight(page, btn(page, '확인'), 1600);
          await sleep(1000);
          for (const action of ['확인', '확인', '보류', '확인']) await tapIf(page, btn(page, action), { pause: 900 });
        },
      },
      {
        label: '확인 · 보류 집계',
        say: '누를 때마다 다음 학생으로 넘어가고 위쪽에 인원이 집계됩니다. 보류한 학생은 오른쪽에 모여 다시 확인할 수 있습니다.',
      },
      {
        label: '이력서 피드백',
        chapter: true,
        say: '이력서관리에서는 학생이 피드백을 요청한 이력서를 검토하기로 열고, 항목을 골라 피드백을 남깁니다. 검토가 끝나면 승인을 누릅니다.',
        do: async (page) => {
          await openMenu(page, '이력서관리', '/instructor/resumes');
          await highlight(page, btn(page, '검토하기'), 1400);
          await sleep(1200);
          if (await writeResumeFeedback(page, '핵심역량/강점', '프로젝트 성과를 수치로 적어 보세요.')) {
            await highlight(page, btn(page, '승인'), 2000);
          }
        },
      },
      {
        label: '공지 작성',
        chapter: true,
        say: '게시물관리에서는 공지 작성 버튼으로 반 전체에 공지를 올리고 수정할 수 있습니다.',
        do: async (page) => {
          // 목록을 먼저 열면 데모 스트림이 갱신되지 않아 작성 화면으로 바로 간다.
          await go(page, '/instructor/board/create', 1400);
          const boxes = page.getByRole('textbox');
          if ((await boxes.count()) >= 2) {
            await typeInto(page, boxes.nth(0), '내일 SQL 실습 준비물 안내');
            await typeInto(page, boxes.nth(1), '노트북 충전기와 DBeaver 설치를 부탁드립니다.');
            await tapIf(page, btnLike(page, /등록/), { pause: 1200 });
          }
        },
      },
      {
        label: '채점 확인',
        chapter: true,
        say: '성취도평가에서 평가를 열면 학생별 제출 결과가 보입니다. 자동 채점된 점수를 확인하고, 필요하면 문항별 점수를 고친 뒤 점수 저장을 누릅니다.',
        do: async (page) => {
          await openMenu(page, '성취도평가', '/instructor/assessments');
          await go(page, '/instructor/assessments/a1', 1600);
          await tapIf(page, btnLike(page, /^학생 \d+점/), { pause: 1400 });
          await highlight(page, btn(page, '점수 저장'), 2600);
        },
      },
      {
        label: '평가 만들기',
        chapter: true,
        say: '평가 만들기에서는 제목과 태그, 응시 기간을 정하고 문항을 추가합니다.',
        do: async (page) => {
          await go(page, '/instructor/assessments/create', 1600);
          await typeInto(page, page.getByRole('textbox').nth(0), '34기 3차 성취도평가');
          await typeInto(page, page.getByRole('textbox').nth(1), 'Python, SQL');
        },
      },
      {
        label: '문제 생성 AI',
        say: '문제 생성 AI를 누르면 등록된 커리큘럼에서 출제 범위와 문항 수를 골라 AI 문항 초안을 만들 수 있습니다. 초안은 강사가 검토하고 수정한 뒤 발행합니다.',
        do: async (page) => {
          if (!(await tapIf(page, btn(page, '문제 생성 AI'), { pause: 1300 }))) return;
          for (const re of [/^D1 /, /^D8 /]) await tapIf(page, btnLike(page, re), { pause: 700 });
          await tapIf(page, page.getByRole('checkbox', { name: '15문항' }), { pause: 700 });
          await highlight(page, btn(page, '초안 만들기'), 2200);
          await sleep(2400);
          await tapIf(page, btn(page, '취소'), { pause: 600 });
        },
      },
      {
        label: '문항 직접 추가',
        say: '직접 문항을 넣을 때는 수동 추가를 눌러 문제와 선택지, 정답을 입력합니다. 저장한 뒤 발행하면 학생에게 공개됩니다.',
        do: async (page) => {
          if (await tapIf(page, btn(page, '수동 추가'), { pause: 1100 })) {
            const q = page.getByRole('textbox');
            await typeInto(page, q.nth(0), 'SQL에서 두 테이블을 합칠 때 쓰는 키워드는?');
            await typeInto(page, q.nth(2), 'JOIN\nGROUP BY\nORDER BY\nLIMIT');
            await tapIf(page, btn(page, '확인'), { pause: 1000 });
          }
          await highlight(page, btn(page, '발행'), 2200);
        },
      },
      {
        label: '커리큘럼',
        chapter: true,
        say: '커리큘럼 메뉴에서는 구글 시트를 CSV 파일로 내려받아 올립니다. 등록한 커리큘럼은 학습 추천과 평가 문항 생성에 쓰입니다.',
        do: async (page) => {
          await openMenu(page, '커리큘럼', '/instructor/curriculum');
          await highlight(page, btn(page, 'CSV 교체'), 2000);
          const search = page.getByRole('textbox').first();
          if (await search.count()) await typeInto(page, search, 'Database');
        },
      },
    ],
  },
  {
    id: 'part4',
    no: 4,
    role: 'admin',
    color: roleColor.admin,
    title: '관리자 화면 안내',
    intro: '기수 운영에 필요한 승인과 피드백, 공지, 출석, 설문, 마일리지, AI 기능을 점검하는 LLMOps, 기수 관리를 살펴봅니다.',
    cardSay: 'PART 4, 관리자 화면입니다. 기수 운영에 필요한 승인과 피드백, 공지, 출석, 설문, 마일리지, AI 기능을 점검하는 LLMOps, 기수 관리를 살펴봅니다.',
    beats: [
      {
        label: '로그인',
        say: '관리자 계정으로 로그인합니다.',
        do: async (page) => login(page, 'admin'),
      },
      {
        label: '이용 안내 투어',
        say: '관리자도 처음 로그인하면 이용 안내 투어가 뜹니다. 투어는 마이페이지의 이용 안내 다시보기에서 언제든 다시 볼 수 있으니, 여기서는 닫고 주요 기능을 살펴보겠습니다.',
        text: '처음 로그인하면 이용 안내 투어가 뜹니다. 「마이페이지 → 이용 안내 다시보기」에서 다시 볼 수 있으니 여기서는 닫고 넘어갑니다.',
        do: async (page) => showTourStart(page),
      },
      {
        label: '대시보드',
        chapter: true,
        say: '관리자 대시보드에는 기록실 승인 대기와 이력서 검토 대기처럼 오늘 처리할 일이 모입니다. 카드를 누르면 해당 화면으로 바로 이동합니다.',
        do: async (page) => {
          await go(page, '/admin', 1200);
          await highlight(page, btnLike(page, /^기록실 승인 대기/), 2400);
          await sleep(2600);
          await highlight(page, btnLike(page, /^이력서 검토 대기/), 2400);
        },
      },
      {
        label: '기록실 승인',
        chapter: true,
        say: '기록실에서는 학생이 올린 기록의 상세 내용을 확인하고 승인하거나 반려합니다. 승인하면 설정한 규칙대로 마일리지가 적립됩니다.',
        do: async (page) => {
          if (!(await tapIf(page, btnLike(page, /^기록실 승인 대기/), { pause: 1600 }))) await go(page, '/admin/records', 1600);
          await tapIf(page, btn(page, '상세 보기'), { pause: 1400 });
          await highlight(page, btn(page, '승인'), 1400);
          await sleep(900);
          await tapIf(page, btn(page, '승인'), { pause: 1400 });
          await highlight(page, btn(page, '반려'), 1800);
        },
      },
      {
        label: '이력서 피드백',
        chapter: true,
        say: '이력서 메뉴에서는 피드백 요청이 들어온 이력서를 검토하기로 열어 항목별 피드백을 남기고, 검토가 끝나면 승인합니다.',
        do: async (page) => {
          await openMenu(page, '이력서', '/admin/resumes');
          if (await writeResumeFeedback(page, '기본정보', '연락처 형식을 통일해 주세요.')) {
            await highlight(page, btn(page, '승인'), 2000);
          }
        },
      },
      {
        label: '공지 작성',
        chapter: true,
        say: '게시판에서는 공지와 예약 공지, 로그인 알림 팝업을 관리합니다. 등록한 공지는 학생 대시보드와 게시판에 바로 보입니다.',
        do: async (page) => {
          await go(page, '/admin/board/create', 1400);
          await typeInto(page, page.getByRole('textbox').nth(0), '금요일 팀 프로젝트 발표 안내');
          await typeInto(page, page.getByRole('textbox').nth(1), '오후 2시부터 팀별 10분씩 발표합니다.');
          await tapIf(page, btn(page, '공지 등록'), { pause: 1200 });
        },
      },
      {
        label: '출석 관리',
        chapter: true,
        say: '출석 관리에서는 기수별 당일 출석을 조회하고 수정합니다. 고용24 입퇴실 기록과 출결 폼 반영 여부를 한 표에서 확인합니다.',
        do: async (page) => {
          await go(page, '/admin/attendance', 1800);
          await highlight(page, btnLike(page, /^김하늘 /), 2200);
        },
      },
      {
        label: '출결 공지',
        say: '매일 8시 30분 공지 등록 버튼으로 출결 폼 안내 공지를 매일 아침 자동으로 올릴 수 있습니다.',
        text: '「매일 08:30 공지 등록」으로 출결 폼 안내 공지를 매일 아침 자동으로 올릴 수 있습니다.',
        do: async (page) => {
          await highlight(page, btnLike(page, /08:30 공지 등록/), 2600);
          await hover(page, btnLike(page, /08:30 공지 등록/), 400);
        },
      },
      {
        label: '자리 확인 · 좌석 배치',
        say: '자리 확인과 좌석 배치에서는 오늘 좌석 현황을 확인하고, 강의실 좌석 틀을 만들어 학생을 배정한 뒤 게시합니다.',
        do: async (page) => {
          await go(page, '/admin/seat-presence', 2000);
          await go(page, '/admin/seating', 1400);
          await highlight(page, btn(page, '배치 편집'), 2000);
        },
      },
      {
        label: '설문 · 제출',
        chapter: true,
        say: '설문과 제출에서는 구글 폼 설문을 등록하고, 마감 일시와 학생 제출 현황을 관리합니다.',
        do: async (page) => {
          await go(page, '/admin/form-tasks', 1600);
          await highlight(page, btn(page, '설문 등록'), 2200);
        },
      },
      {
        label: '마일리지 관리',
        chapter: true,
        say: '마일리지 관리에서는 교환 상품과 구매 요청 승인, 수동 지급과 차감, 기수별 적립 규칙을 관리합니다.',
        do: async (page) => {
          await go(page, '/admin/mileage', 1400);
          await highlight(page, btnLike(page, /^구매 요청 처리/), 2000);
          await sleep(2200);
          await tapIf(page, btnLike(page, /^상품 관리/), { pause: 800 });
        },
      },
      {
        label: 'LLMOps',
        chapter: true,
        say: '시스템 메뉴의 LLMOps에서는 문제 생성, 공고 챗봇, 추천, 첨삭, 학생 챗봇 같은 AI 기능의 요청 수와 성공률, 응답 시간, 토큰 사용량을 한눈에 봅니다. 화면의 숫자는 예시입니다.',
        text: '「시스템 → LLMOps」에서 AI 기능의 요청 수 · 성공률 · 응답 시간 · 토큰 사용량을 봅니다. 화면의 숫자는 예시입니다.',
        do: async (page) => {
          await go(page, '/admin/ai-quality', 1600);
          await highlight(page, page.getByRole('checkbox', { name: '전체', exact: true }), 2200);
        },
      },
      {
        label: 'LLMOps 로그',
        say: '위쪽 필터로 기능을 골라 좁혀 보고, 아래에서 최근 평가 결과와 프롬프트 버전별 채택률, 오류가 난 요청까지 확인할 수 있습니다.',
        do: async (page) => {
          await tapIf(page, page.getByRole('checkbox', { name: '문제생성', exact: true }), { pause: 2000 });
          await tapIf(page, page.getByRole('checkbox', { name: '전체', exact: true }), { pause: 800 });
          await page.mouse.move(size.width / 2, size.height / 2, { steps: 10 });
          await page.mouse.wheel(0, 700);
        },
      },
      {
        label: '기수 · 계정 관리',
        chapter: true,
        say: '기수 관리에서는 기수를 만들고 교육 기간을 관리합니다. 학생 관리와 강사 관리에서는 계정을 등록하고 비밀번호를 재발급합니다.',
        do: async (page) => {
          await go(page, '/admin/cohorts', 1600);
          await highlight(page, btn(page, '기수 생성'), 2400);
        },
      },
    ],
  },
];

// ── 음성 ────────────────────────────────────────────────────────────
const probeDuration = (file) =>
  Number(execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', file]).toString().trim());

function speech(say) {
  const hash = crypto.createHash('sha1').update(`${voice}|${rate}|${say}`).digest('hex').slice(0, 16);
  const file = path.join(ttsDir, `${hash}.mp3`);
  if (!fs.existsSync(file)) {
    execFileSync('python', ['-m', 'edge_tts', '--voice', voice, `--rate=${rate}`, '--text', say, '--write-media', file], {
      stdio: ['ignore', 'ignore', 'inherit'],
    });
  }
  return { file, dur: probeDuration(file) };
}

function prepareSpeech() {
  const all = [
    ...Object.values(cards).flatMap((c) => c.lines),
    ...parts.map((p) => ({ say: p.cardSay })),
    ...parts.flatMap((p) => p.beats),
  ];
  let n = 0;
  for (const line of all) {
    line.speech = speech(line.say);
    n += 1;
  }
  const total = all.reduce((s, l) => s + l.speech.dur, 0);
  console.log(`음성 ${n}문장 · ${(total / 60).toFixed(1)}분`);
}

// ── 표지 카드 ───────────────────────────────────────────────────────
const esc = (s) => String(s).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');

function cardHtml(kind, part) {
  const shot = path.join(outRoot, 'shots', 'student', 'dashboard.png');
  const shotUrl = fs.existsSync(shot) ? pathToFileURL(shot).href : '';
  const today = new Date();
  const dateLabel = `${today.getFullYear()}.${String(today.getMonth() + 1).padStart(2, '0')}`;
  const base = `
    * { box-sizing: border-box; margin: 0; }
    html, body { width: 1440px; height: 900px; overflow: hidden; }
    body { font-family: 'Noto Sans KR', 'Malgun Gothic', sans-serif; color: #fff; word-break: keep-all;
      background: radial-gradient(1200px 700px at 85% 10%, #1e3a8a 0%, transparent 60%), linear-gradient(160deg, #0b1220 0%, #0f172a 55%, #111c35 100%); }
    .brand { position: absolute; left: 96px; top: 72px; font-weight: 900; letter-spacing: .12em; font-size: 22px; color: #93c5fd; }
    .foot { position: absolute; left: 96px; bottom: 60px; right: 96px; display: flex; justify-content: space-between; color: #64748b; font-size: 18px; }
  `;
  let body = '';
  let css = '';
  if (kind === 'intro') {
    css = `
      .title { position: absolute; left: 96px; top: 250px; width: 640px; }
      h1 { font-size: 76px; font-weight: 900; letter-spacing: -.02em; line-height: 1.15; }
      .sub { margin-top: 26px; font-size: 26px; color: #cbd5e1; line-height: 1.5; }
      .chips { margin-top: 44px; display: flex; gap: 14px; }
      .chips span { padding: 10px 26px; border-radius: 99px; font-weight: 700; font-size: 22px; }
      .shot { position: absolute; right: -40px; top: 190px; width: 760px; border-radius: 18px; border: 1px solid #334155;
        box-shadow: 0 40px 80px rgba(0,0,0,.5); transform: perspective(1600px) rotateY(-14deg) rotateX(4deg); }
    `;
    body = `
      <div class="brand">PLAYDATA</div>
      <div class="title">
        <h1>LMS<br>이용 가이드</h1>
        <p class="sub">처음 로그인부터<br>학생 · 강사 · 관리자 주요 기능까지</p>
        <div class="chips">
          <span style="background:${roleColor.student}">학생</span>
          <span style="background:${roleColor.instructor}">강사</span>
          <span style="background:${roleColor.admin}">관리자</span>
        </div>
      </div>
      ${shotUrl ? `<img class="shot" src="${shotUrl}">` : ''}
      <div class="foot"><span>SK네트웍스 Family AI 캠프</span><span>${dateLabel} 기준 · 데모 화면</span></div>`;
  } else if (kind === 'toc') {
    css = `
      h2 { position: absolute; left: 96px; top: 150px; font-size: 56px; font-weight: 900; }
      ol { position: absolute; left: 96px; right: 96px; top: 270px; list-style: none; padding: 0; }
      li { display: grid; grid-template-columns: 150px 300px 1fr; align-items: baseline; padding: 26px 0; border-bottom: 1px solid #1e293b; }
      .no { font-weight: 900; font-size: 20px; letter-spacing: .08em; }
      .name { font-size: 32px; font-weight: 700; }
      .items { color: #94a3b8; font-size: 20px; }
    `;
    const rows = [
      ...parts.map((p) => ({ no: `PART ${p.no}`, color: p.color, name: p.title.replace(' 안내', ''), items: [...new Set(p.beats.filter((b) => b.chapter).map((b) => b.label))].join(' · ') })),
      { no: '마무리', color: '#94a3b8', name: '자주 묻는 질문', items: '로그인이 안 될 때 · 로딩이 계속될 때 · 투어 다시 보기' },
    ];
    body = `
      <div class="brand">PLAYDATA LMS 이용 가이드</div>
      <h2>목차</h2>
      <ol>${rows.map((r) => `<li><span class="no" style="color:${r.color}">${esc(r.no)}</span><span class="name">${esc(r.name)}</span><span class="items">${esc(r.items)}</span></li>`).join('')}</ol>`;
  } else if (kind === 'part') {
    css = `
      .accent { position: absolute; left: 0; top: 0; bottom: 0; width: 14px; background: ${part.color}; }
      .part { position: absolute; left: 96px; top: 220px; color: ${part.color}; font-weight: 900; letter-spacing: .14em; font-size: 26px; filter: brightness(1.35); }
      h2 { position: absolute; left: 96px; top: 270px; font-size: 80px; font-weight: 900; letter-spacing: -.02em; }
      .intro { position: absolute; left: 96px; top: 400px; width: 1000px; font-size: 26px; color: #cbd5e1; line-height: 1.55; }
      .grid { position: absolute; left: 96px; right: 96px; top: 540px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }
      .grid div { border: 1px solid #334155; background: rgba(15,23,42,.6); border-radius: 12px; padding: 16px 20px; font-size: 21px; font-weight: 500; }
      .grid b { color: ${part.color}; filter: brightness(1.35); margin-right: 10px; }
    `;
    const items = [...new Set(part.beats.filter((b) => b.chapter).map((b) => b.label))];
    body = `
      <div class="accent"></div>
      <div class="brand">PLAYDATA LMS 이용 가이드</div>
      <div class="part">PART ${part.no}</div>
      <h2>${esc(part.title)}</h2>
      <p class="intro">${esc(part.intro)}</p>
      <div class="grid">${items.map((t, i) => `<div><b>${i + 1}</b>${esc(t)}</div>`).join('')}</div>`;
  } else if (kind === 'outro') {
    css = `
      h2 { position: absolute; left: 96px; top: 150px; font-size: 56px; font-weight: 900; }
      dl { position: absolute; left: 96px; right: 96px; top: 270px; }
      dt { font-size: 28px; font-weight: 700; margin-top: 34px; }
      dt::before { content: 'Q'; color: #60a5fa; font-weight: 900; margin-right: 16px; }
      dd { margin: 10px 0 0 42px; font-size: 22px; color: #94a3b8; line-height: 1.5; }
      .thanks { position: absolute; right: 96px; bottom: 120px; font-size: 30px; font-weight: 700; color: #e2e8f0; }
    `;
    body = `
      <div class="brand">PLAYDATA LMS 이용 가이드</div>
      <h2>자주 묻는 질문</h2>
      <dl>
        <dt>로그인이 안 됩니다.</dt><dd>이메일 앞뒤 공백과 대소문자를 확인하세요. 계속 안 되면 매니저에게 계정 확인·비밀번호 재설정을 요청합니다.</dd>
        <dt>화면이 계속 로딩 중이에요.</dt><dd>새로고침(F5) 후에도 같으면 로그아웃했다가 다시 로그인하세요.</dd>
        <dt>이용 안내 투어를 다시 보고 싶어요.</dt><dd>마이페이지 → 「이용 안내 다시보기」를 누르면 처음부터 다시 볼 수 있습니다.</dd>
      </dl>
      <div class="thanks">궁금한 점은 담당 매니저에게 문의해 주세요.</div>
      <div class="foot"><span>PLAYDATA</span><span>SK네트웍스 Family AI 캠프</span></div>`;
  }
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>${base}${css}</style></head><body>${body}</body></html>`;
}

async function renderCard(browser, name, kind, part) {
  const htmlFile = path.join(workDir, `${name}.html`);
  const png = path.join(workDir, `${name}.png`);
  fs.writeFileSync(htmlFile, cardHtml(kind, part));
  const page = await browser.newPage({ viewport: size });
  await page.goto(pathToFileURL(htmlFile).href, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: png });
  await page.close();
  return png;
}

/// 카드 구간: 문장을 이어 읽고, 앞뒤로 숨 쉴 틈을 둔다.
function cardSegment(png, lines, label, partLabel) {
  let t = 0.8;
  const cues = lines.map((l) => {
    const cue = { t, text: l.text ?? l.say, label, audio: l.speech.file };
    t += l.speech.dur + gapAfterLine;
    return cue;
  });
  return { kind: 'card', png, cues, duration: t + 0.9, partLabel };
}

// ── 녹화 ────────────────────────────────────────────────────────────
async function recordRole(browser, server, role, roleParts) {
  const rawDir = path.join(workDir, 'raw', role);
  fs.rmSync(rawDir, { recursive: true, force: true });
  fs.mkdirSync(rawDir, { recursive: true });
  const ctx = await browser.newContext({ viewport: size, locale: 'ko-KR', recordVideo: { dir: rawDir, size } });
  const page = await ctx.newPage();
  const startedAt = Date.now();
  const now = () => (Date.now() - startedAt) / 1000;
  resetMouse();
  await page.goto(server.url);
  await waitForApp(page);
  await installCursor(page);
  await sleep(600);

  let freeAt = 0;
  const waitFree = async () => {
    const wait = freeAt - now();
    if (wait > 0) await sleep(wait * 1000);
  };
  const marks = [];
  for (const part of roleParts) {
    await waitFree();
    const mark = { part, start: now(), cues: [] };
    marks.push(mark);
    await sleep(500);
    for (const beat of part.beats) {
      await waitFree();
      mark.cues.push({ t: now(), text: beat.text ?? beat.say, label: beat.label, audio: beat.speech.file, chapter: beat.chapter });
      freeAt = now() + beat.speech.dur + gapAfterLine;
      console.log(`  [${role}] ${beat.label}`);
      if (beat.do) {
        try {
          await beat.do(page);
        } catch (e) {
          console.error(`  [${role}] ${beat.label} 조작 실패:`, e.message);
        }
      }
    }
    await waitFree();
    await sleep(800);
    mark.end = now();
  }
  const video = page.video();
  await ctx.close();
  const raw = await video.path();
  fs.writeFileSync(path.join(rawDir, 'marks.json'), JSON.stringify({ raw, marks: marks.map((m) => ({ ...m, part: m.part.id })) }, null, 2));
  return { raw, marks };
}

function loadRecording(role) {
  const file = path.join(workDir, 'raw', role, 'marks.json');
  if (!fs.existsSync(file)) throw new Error(`이전 녹화가 없습니다: ${file}`);
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  return { raw: data.raw, marks: data.marks.map((m) => ({ ...m, part: parts.find((p) => p.id === m.part) })) };
}

// ── 구간 인코딩 ─────────────────────────────────────────────────────
const assTime = (sec) => {
  const cs = Math.round(Math.max(0, sec) * 100);
  const h = Math.floor(cs / 360000);
  const m = Math.floor((cs % 360000) / 6000);
  const s = Math.floor((cs % 6000) / 100);
  return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${String(cs % 100).padStart(2, '0')}`;
};
const assText = (s) => String(s).replaceAll('\\', '＼').replaceAll('{', '（').replaceAll('}', '）');

/// 자막 바 가운데 폭에 맞춰 두 줄로 나눈다. 가운데에 가까우면서 쉼표·마침표 뒤를 먼저 고른다.
function wrap(text, max = 40) {
  if (text.length <= max) return assText(text);
  const mid = text.length / 2;
  let best = -1;
  let bestScore = Infinity;
  for (let i = 1; i < text.length - 1; i++) {
    if (text[i] !== ' ') continue;
    const punct = /[,.。]/.test(text[i - 1]) ? 10 : 0;
    const score = Math.abs(i - mid) - punct;
    // 한 줄이 너무 길어지면 쓰지 않는다.
    if (Math.max(i, text.length - i - 1) > max + 6) continue;
    if (score < bestScore) {
      bestScore = score;
      best = i;
    }
  }
  if (best < 0) return assText(text);
  return `${assText(text.slice(0, best))}\\N${assText(text.slice(best + 1))}`;
}

function writeAss(file, cues, duration, partLabel, accent) {
  const W = size.width;
  const mid = size.height + barHeight / 2;
  const hex = accent.replace('#', '');
  const assColor = `&H00${hex.slice(4, 6)}${hex.slice(2, 4)}${hex.slice(0, 2)}`;
  const lines = [];
  cues.forEach((c, i) => {
    const start = assTime(c.at);
    const end = assTime(i + 1 < cues.length ? cues[i + 1].at : duration);
    lines.push(`Dialogue: 1,${start},${end},Text,,0,0,0,,{\\an5\\pos(${W / 2},${mid})}${wrap(c.text)}`);
    if (c.label) lines.push(`Dialogue: 1,${start},${end},Label,,0,0,0,,{\\an4\\pos(36,${mid})\\c${assColor}}${assText(c.label)}`);
  });
  if (partLabel) lines.push(`Dialogue: 0,${assTime(0)},${assTime(duration)},Part,,0,0,0,,{\\an6\\pos(${W - 36},${mid})}${assText(partLabel)}`);
  const ass = `[Script Info]
ScriptType: v4.00+
PlayResX: ${W}
PlayResY: ${size.height + barHeight}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Text,Malgun Gothic,27,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,1
Style: Label,Malgun Gothic,20,&H00FAA560,&H00FAA560,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,4,0,0,0,1
Style: Part,Malgun Gothic,18,&H00B8A394,&H00B8A394,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,0,0,6,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${lines.join('\n')}
`;
  fs.writeFileSync(file, ass, 'utf8');
}

function encodeSegment(seg, index) {
  const name = `seg_${String(index).padStart(2, '0')}`;
  const out = path.join(workDir, `${name}.mp4`);
  const cues = seg.cues.map((c) => ({ ...c, at: seg.kind === 'clip' ? c.t - seg.from + videoLag : c.t }));
  writeAss(path.join(workDir, `${name}.ass`), cues, seg.duration, seg.partLabel, seg.accent ?? '#60a5fa');

  const args = ['-hide_banner', '-loglevel', 'error', '-y'];
  if (seg.kind === 'card') {
    args.push('-loop', '1', '-framerate', String(fps), '-t', seg.duration.toFixed(3), '-i', seg.png);
  } else {
    args.push('-ss', seg.from.toFixed(3), '-t', seg.duration.toFixed(3), '-i', seg.raw);
  }
  cues.forEach((c) => args.push('-i', c.audio));

  const fade = seg.kind === 'card' ? `,fade=t=in:st=0:d=0.4,fade=t=out:st=${(seg.duration - 0.4).toFixed(3)}:d=0.4` : '';
  const filters = [
    `[0:v]fps=${fps},scale=${size.width}:${size.height},setsar=1${fade},pad=${size.width}:${size.height + barHeight}:0:0:color=0x0F172A,` +
      `drawbox=x=0:y=${size.height}:w=${size.width}:h=3:color=0x0B57D0:t=fill,subtitles=${name}.ass:fontsdir=fonts,format=yuv420p[v]`,
  ];
  if (cues.length) {
    cues.forEach((c, i) => {
      const ms = Math.max(0, Math.round(c.at * 1000));
      filters.push(`[${i + 1}:a]aresample=48000,aformat=channel_layouts=stereo,adelay=${ms}:all=1[a${i}]`);
    });
    filters.push(`${cues.map((_, i) => `[a${i}]`).join('')}amix=inputs=${cues.length}:normalize=0:dropout_transition=0,apad,atrim=0:${seg.duration.toFixed(3)}[a]`);
  } else {
    filters.push(`anullsrc=r=48000:cl=stereo,atrim=0:${seg.duration.toFixed(3)}[a]`);
  }
  const scriptFile = path.join(workDir, `${name}.filter`);
  fs.writeFileSync(scriptFile, filters.join(';\n'));
  args.push(
    '-/filter_complex', `${name}.filter`,
    '-map', '[v]', '-map', '[a]', '-t', seg.duration.toFixed(3),
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-r', String(fps),
    '-c:a', 'aac', '-b:a', '160k', '-ar', '48000', '-ac', '2',
    out,
  );
  execFileSync('ffmpeg', args, { cwd: workDir, stdio: ['ignore', 'ignore', 'pipe'] });
  return out;
}

const clock = (sec) => {
  const s = Math.floor(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, '0');
  return h ? `${h}:${String(m).padStart(2, '0')}:${r}` : `${m}:${r}`;
};

// ── 실행 ────────────────────────────────────────────────────────────
prepareSpeech();
const browser = await chromium.launch();
const server = await serveBuild(5182);
try {
  const recordings = {};
  for (const role of ['student', 'instructor', 'admin']) {
    const roleParts = parts.filter((p) => p.role === role);
    if (reuse) {
      recordings[role] = loadRecording(role);
    } else {
      console.log(`녹화: ${roleLabel[role]}`);
      recordings[role] = await recordRole(browser, server, role, roleParts);
    }
  }

  console.log('표지 카드');
  const segments = [];
  segments.push({ ...cardSegment(await renderCard(browser, 'card_intro', 'intro'), cards.intro.lines, '', ''), chapter: '인트로', accent: '#60a5fa' });
  segments.push({ ...cardSegment(await renderCard(browser, 'card_toc', 'toc'), cards.toc.lines, '목차', ''), chapter: '목차', accent: '#60a5fa' });
  for (const part of parts) {
    const png = await renderCard(browser, `card_${part.id}`, 'part', part);
    const partLabel = `PART ${part.no} · ${part.title.replace(' 안내', '')}`;
    segments.push({
      ...cardSegment(png, [{ say: part.cardSay, speech: part.speech ?? speech(part.cardSay) }], `PART ${part.no}`, partLabel),
      chapter: `PART ${part.no} ${part.title.replace(' 안내', '')}`,
      accent: part.color,
    });
    const rec = recordings[part.role];
    const mark = rec.marks.find((m) => m.part.id === part.id);
    segments.push({
      kind: 'clip',
      raw: rec.raw,
      from: mark.start,
      duration: mark.end - mark.start,
      cues: mark.cues,
      partLabel,
      accent: part.color,
    });
  }
  segments.push({ ...cardSegment(await renderCard(browser, 'card_outro', 'outro'), cards.outro.lines, '마무리', ''), chapter: '자주 묻는 질문', accent: '#60a5fa' });

  console.log(`구간 ${segments.length}개 인코딩`);
  const files = [];
  const chapters = [];
  let offset = 0;
  for (const [i, seg] of segments.entries()) {
    const file = encodeSegment(seg, i);
    files.push(file);
    if (seg.chapter) chapters.push({ t: offset, title: seg.chapter, major: true });
    if (seg.kind === 'clip') {
      for (const c of seg.cues.filter((c) => c.chapter)) {
        chapters.push({ t: offset + Math.max(0, c.t - seg.from + videoLag), title: `${seg.partLabel.split(' · ')[1]} · ${c.label}` });
      }
    }
    offset += probeDuration(file);
    console.log(`  ${path.basename(file)}  ${clock(offset)}`);
  }

  const listFile = path.join(workDir, 'concat.txt');
  fs.writeFileSync(listFile, files.map((f) => `file '${path.basename(f)}'`).join('\n'));
  const mp4 = path.join(videoDir, `${outName}.mp4`);
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', mp4], {
    cwd: workDir,
  });

  // 유튜브 챕터는 10초 이상 간격이어야 한다. 표지(PART) 챕터는 항상 남기고,
  // 너무 붙은 세부 챕터를 뺀다.
  const kept = [];
  for (const [i, c] of chapters.entries()) {
    const prev = kept[kept.length - 1];
    const next = chapters[i + 1];
    if (c.major) {
      if (prev && !prev.major && c.t - prev.t < 10) kept.pop();
      kept.push(c);
    } else if ((!prev || c.t - prev.t >= 10) && (!next || !next.major || next.t - c.t >= 10)) {
      kept.push(c);
    }
  }
  const chapterFile = path.join(videoDir, `${outName}_챕터.txt`);
  fs.writeFileSync(chapterFile, kept.map((c) => `${clock(c.t)} ${c.title}`).join('\n') + '\n', 'utf8');
  console.log(mp4);
  console.log(chapterFile);
} finally {
  await browser.close();
  server.close();
}
