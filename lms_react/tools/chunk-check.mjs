// 청크 나누기 확인 — 역할별로 어떤 JS 를 받는지, 연습장을 열 때 CodeMirror 가 오는지,
// 첫 로그인 이용 안내 투어가 지연 로드된 화면의 타깃을 비추는지.
//
//   npm run build && node tools/chunk-check.mjs
//
// 네트워크를 느리게(Fast 3G 비슷하게) 걸어 청크가 늦게 오는 경우도 본다.
import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';

const { base, stop } = await startPreview();
const browser = await chromium.launch();
const say = (k, v) => console.log(`${k}: ${typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : JSON.stringify(v)}`);

async function session(role, { slow = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1360, height: 900 } });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  if (slow) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send('Network.emulateNetworkConditions', { offline: false, latency: 400, downloadThroughput: 200 * 1024, uploadThroughput: 100 * 1024 });
  }
  const js = [];
  page.on('request', (r) => {
    const u = new URL(r.url());
    if (u.origin === base && u.pathname.endsWith('.js')) js.push(u.pathname.split('/').pop().replace(/-[\w-]{8}\.js$/, ''));
  });
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.getByRole('button', { name: role, exact: true }).click();
  return { ctx, page, js, errors };
}

/** 투어 첫 몇 단계가 타깃을 비추는지(구멍이 있는지) */
async function tourSteps(page, n) {
  const out = [];
  for (let i = 0; i < n; i++) {
    const card = page.locator('.tour-card');
    if (!(await card.count())) break;
    // 화면 청크를 받는 동안은 자리 표시가 뜨고 투어가 기다린다. 끝난 뒤 구멍이 생기는지 본다
    const t0 = Date.now();
    await page.waitForFunction(() => !document.querySelector('[data-screen-loading]'), null, { timeout: 30000 });
    await page.locator('.tour-hole').waitFor({ timeout: 3000 }).catch(() => {});
    const waited = Date.now() - t0;
    const title = await page.locator('.tour-card__title').innerText();
    const hole = await page.locator('.tour-hole').count();
    out.push(`${title}${hole ? '' : '(구멍 없음)'}${waited > 1000 ? ` · ${(waited / 1000).toFixed(1)}초 기다림` : ''}`);
    const next = card.getByRole('button', { name: /다음|완료|시작/ });
    if (!(await next.count())) break;
    await next.first().click();
    await page.waitForTimeout(1200);
  }
  return out;
}

try {
  // 학생: 대시보드 → 연습장
  {
    const { ctx, page, js, errors } = await session('학생');
    const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
    await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
    await page.waitForTimeout(800);
    say('학생 첫 화면 JS', [...js]);
    const before = js.length;
    await page.evaluate(() => {
      history.pushState({}, '', '/study-room/playground');
      dispatchEvent(new PopStateEvent('popstate'));
    });
    await page.locator('.py-nb-cell').first().waitFor();
    say('연습장 열 때 더 받은 JS', js.slice(before));
    say('학생 오류', errors);
    await ctx.close();
  }
  // 강사 · 관리자: 느린 네트워크에서 첫 로그인 투어
  for (const role of ['강사', '관리자']) {
    const { ctx, page, js, errors } = await session(role, { slow: true });
    await page.locator('.tour-card').waitFor({ timeout: 30000 });
    say(`${role} 투어 단계`, await tourSteps(page, 5));
    say(`${role} 받은 JS`, [...new Set(js)]);
    say(`${role} 오류`, errors);
    await ctx.close();
  }
} finally {
  await browser.close();
  await stop();
}
