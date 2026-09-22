// 「이 문제 이상해요」 신고 흐름 확인 — 학생 신고 → 2명 되면 숨김 → 강사 화면에서 다시 보이기.
//
//   npm run build && node tools/report-flow.mjs
//
// 스크린샷은 tools/shots/ 에 남긴다. 데모 시드에는 다른 학생이 9/14 문제 5를 신고해 둔 상태다.
import { mkdirSync } from 'node:fs';

import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';

const { base, stop } = await startPreview();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
mkdirSync('tools/shots', { recursive: true });
const say = (k, v) => console.log(`${k}: ${typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : JSON.stringify(v)}`);

async function go(path) {
  await page.evaluate((p) => {
    history.pushState({}, '', p);
    dispatchEvent(new PopStateEvent('popstate'));
  }, path);
  await page.waitForTimeout(800);
}

// 메모리 저장소라 새로 고치면 신고가 사라진다. 첫 번만 goto, 그 뒤는 레일의 로그아웃으로 역할을 바꾼다.
let first = true;
async function login(role) {
  if (first) {
    await page.goto(`${base}/login`);
    first = false;
  } else {
    await page.evaluate(() => document.querySelector('.rail__logout').click());
  }
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: role, exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
  await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
  await page.waitForTimeout(400);
}

try {
  await login('학생');
  await go('/study-room/playground?set=ps-mm-0914&focus=5');
  await page.waitForTimeout(1200);
  const q5 = page.locator('.py-nb-cell--problem').nth(4);
  say('학생 문제 5 머리', await q5.locator('.pb__head').innerText());
  say('학생 진행률', await page.locator('.pb-progress span').innerText());
  await q5.locator('.pb__flag').click();
  await page.waitForTimeout(200);
  await q5.locator('.pb__report').screenshot({ path: 'tools/shots/report-form.png' });
  await q5.locator('.pb__report-reason', { hasText: '정답이 이상해요' }).click();
  await q5.locator('.pb__report input[type="text"]').fill('예시와 결과가 다르게 나와요');
  await q5.locator('.pb__report button[type="submit"]').click();
  await page.waitForTimeout(500);
  say('신고 뒤 숨김 자리', await page.locator('.py-nb-cell--hidden').innerText());
  say('신고 뒤 진행률', await page.locator('.pb-progress span').innerText());
  say('숨김 셀 수', await page.locator('.py-nb-cell--hidden').count());
  await page.locator('.py-notebook').screenshot({ path: 'tools/shots/report-hidden.png', clip: undefined }).catch(() => {});
  await page.locator('.py-nb-cell--hidden').screenshot({ path: 'tools/shots/report-hidden-cell.png' });

  // 학습실 · 다시 풀 문제에서도 빠지는지
  await go('/study-room');
  say('학습실 다시 풀 문제', await page.locator('.practice-sets').innerText().then((t) => (t.match(/다시 풀 문제[^\n]*/) ?? [''])[0]));

  await login('강사');
  await go('/instructor/practice');
  say('강사 화면 제목', await page.locator('.practice-mod__head h1').innerText());
  say('강사 통계', await page.locator('.practice-mod__stats').innerText());
  say('첫 행 머리', await page.locator('.flag-row').first().locator('.flag-row__head').innerText());
  say('신고 목록', await page.locator('.flag-row').first().locator('.flag-row__reports').innerText());
  await page.screenshot({ path: 'tools/shots/report-instructor.png', fullPage: true });
  await page.locator('.flag-row').first().getByRole('button', { name: '다시 보이기' }).click();
  await page.waitForTimeout(300);
  say('결정 뒤 머리', await page.locator('.flag-row').first().locator('.flag-row__head').innerText());

  // 다시 학생으로 — 문제가 다시 보이는지
  await login('학생');
  await go('/study-room/playground?set=ps-mm-0914');
  await page.waitForTimeout(1000);
  say('결정 뒤 숨김 셀 수', await page.locator('.py-nb-cell--hidden').count());
  say('결정 뒤 문제 5 머리', await page.locator('.py-nb-cell--problem').nth(4).locator('.pb__head').innerText());

  // 좁은 화면
  await page.setViewportSize({ width: 390, height: 844 });
  await login('강사');
  await go('/instructor/practice');
  say('좁은 화면 가로 넘침', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth));
  await page.screenshot({ path: 'tools/shots/report-instructor-narrow.png', fullPage: true });

  say('페이지 오류', errors);
} finally {
  await browser.close();
  await stop();
}
