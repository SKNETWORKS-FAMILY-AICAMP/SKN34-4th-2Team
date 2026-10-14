// 파이썬 런타임 불러오는 시간 — 처음 · 다시 열기 · 세 번째(같은 브라우저 프로필).
//
//   npm run build && node tools/runtime-cache.mjs
//
// readyAfterOpenMs   연습장을 연 뒤 런타임이 준비되기까지(화면이 열리면 미리 띄운다)
// firstRunAfter3sMs  3초 읽은 뒤 첫 셀을 눌러 결과가 나오기까지 — 학생이 느끼는 기다림
// pandasMs           pandas 를 처음 쓰는 셀(패키지 불러오기 포함)
// files              서비스 워커(public/pyodide-sw.js)가 캐시에 둔 파일
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';

const { base, stop } = await startPreview();
const profile = mkdtempSync(join(tmpdir(), 'lxp-sw-'));
const ctx = await chromium.launchPersistentContext(profile, { viewport: { width: 1280, height: 900 } });
const say = (k, v) => console.log(`${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`);

async function login(page) {
  await page.goto(`${base}/login`);
  await page.waitForTimeout(400);
  const quick = page.getByRole('button', { name: '빠른 로그인 (데모)' });
  if (await quick.count()) {
    await quick.click();
    await page.getByRole('button', { name: '학생', exact: true }).click();
    const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
    await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
    const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
    await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
  }
}

/**
 * 연습장을 열고 → 준비될 때까지(미리 띄우기) · 3초 읽은 뒤 첫 셀 실행 · pandas 셀까지.
 */
async function timeRun(label) {
  const page = await ctx.newPage();
  await login(page);
  const opened = Date.now();
  await page.evaluate(() => {
    history.pushState({}, '', '/study-room/playground');
    dispatchEvent(new PopStateEvent('popstate'));
  });
  const readyMs = await page
    .locator('.py-status--ready')
    .waitFor({ timeout: 240000 })
    .then(() => Date.now() - opened)
    .catch(() => -1);
  await page.waitForTimeout(Math.max(0, 3000 - (Date.now() - opened)));
  const t0 = Date.now();
  await page.locator('.py-nb-cell--code').first().locator('.py-icon-btn--run').click();
  await page.locator('.py-nb-cell--code').first().locator('.py-nb-cell__prompt', { hasText: /\[\d+\]/ }).waitFor({ timeout: 240000 });
  const runtime = Date.now() - t0;
  // pandas 까지
  await page.getByRole('button', { name: 'DataFrame 표' }).click();
  const cell = page.locator('.py-nb-cell--code').last();
  const t1 = Date.now();
  await cell.locator('.py-icon-btn--run').click();
  const got = await cell.locator('table, .py-line--err').first().waitFor({ timeout: 240000 }).then(() => cell.locator('table').count());
  if (!got) say(`${label} 오류`, await cell.locator('.py-nb-out').innerText());
  const pandas = Date.now() - t1;
  const sw = await page.evaluate(async () => {
    const reg = await navigator.serviceWorker?.getRegistration();
    const names = (await caches.keys()).filter((k) => k.startsWith('pyodide'));
    let files = 0;
    const urls = [];
    for (const n of names) for (const r of await (await caches.open(n)).keys()) urls.push(r.url.split('/').pop());
    files = urls;
    return { active: Boolean(reg?.active), controlled: Boolean(navigator.serviceWorker?.controller), caches: names, files };
  });
  say(label, { readyAfterOpenMs: readyMs, firstRunAfter3sMs: runtime, pandasMs: pandas, ...sw });
  await page.close();
}

try {
  await timeRun('처음');
  await timeRun('다시 열기');
  await timeRun('세 번째');
} finally {
  await ctx.close();
  await stop();
  rmSync(profile, { recursive: true, force: true });
}
