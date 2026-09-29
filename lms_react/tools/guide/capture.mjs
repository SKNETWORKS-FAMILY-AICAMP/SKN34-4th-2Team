// scenes.mjs 의 기능 · 단계를 차례대로 실행하며 한 장씩 찍는다.
// 결과: build/guide/shots/<role>/<feature>-<단계>.png (+ login.png, <role>/_tour.png, themes/*.png)
//
//   node tools/guide/capture.mjs            전체
//   node tools/guide/capture.mjs student    한 역할만
//
// 데모 빌드(build/guide_web)를 띄우고, AI 서버 요청은 mocks.mjs 의 예시 응답으로 바꿔 찍는다.
import fs from 'node:fs';
import path from 'node:path';
import { serve, outRoot } from './serve.mjs';
import { launch, login, go, sleep } from './lib.mjs';
import { installMocks } from './mocks.mjs';
import { roles } from './scenes.mjs';

const only = process.argv[2];
const shots = path.join(outRoot, 'shots');
const server = await serve();
const browser = await launch();
const problems = [];

/// scenes.mjs 가 화면 요소를 찾을 때 쓰는 도구.
function helpers(page) {
  const main = () => page.locator('main, .shell__main, body').first();
  const h = {
    btn: (name) => page.getByRole('button', { name, exact: typeof name === 'string' }).first(),
    link: (name) => page.getByRole('link', { name, exact: typeof name === 'string' }).first(),
    tab: (name) => page.getByRole('tab', { name }).first(),
    /// 버튼이든 링크든 이름으로
    any: (name) => page.getByRole('button', { name }).or(page.getByRole('link', { name })).first(),
    text: (text) => page.getByText(text, { exact: typeof text === 'string' }).first(),
    css: (sel) => page.locator(sel).first(),
    input: (placeholder) => page.getByPlaceholder(placeholder).first(),
    /// 사이드바 메뉴 칸. count 를 주면 그 칸부터 count 개를 묶은 영역.
    nav: async (label, count = 1) => {
      const items = page.locator('nav.rail a.rail__item');
      const labels = await items.evaluateAll((els) => els.map((e) => e.querySelector('.rail__label')?.textContent?.trim()));
      const i = labels.indexOf(label);
      if (i < 0) return null;
      const first = await items.nth(i).boundingBox();
      const last = await items.nth(Math.min(i + count - 1, labels.length - 1)).boundingBox();
      return first && last && { x: first.x, y: first.y, width: first.width, height: last.y + last.height - first.y };
    },
    /// 두 요소를 함께 두르는 영역
    union: async (a, b) => {
      const ra = await a.boundingBox();
      const rb = await b.boundingBox();
      if (!ra || !rb) return null;
      const x = Math.min(ra.x, rb.x);
      const y = Math.min(ra.y, rb.y);
      return { x, y, width: Math.max(ra.x + ra.width, rb.x + rb.width) - x, height: Math.max(ra.y + ra.height, rb.y + rb.height) - y };
    },
    /// 요소를 감싸는 가까운 조상(selector)
    closest: async (locator, selector) => {
      const handle = await locator.elementHandle({ timeout: 3000 }).catch(() => null);
      if (!handle) return null;
      const r = await handle.evaluate((el, sel) => {
        const box = (el.closest(sel) ?? el).getBoundingClientRect();
        return { x: box.left, y: box.top, width: box.width, height: box.height };
      }, selector);
      return r;
    },
    tap: async (locator, pause = 900) => {
      await locator.scrollIntoViewIfNeeded({ timeout: 5000 }).catch(() => {});
      await locator.click({ timeout: 5000 });
      await sleep(pause);
    },
    tapIf: async (locator, pause = 900) => {
      if (!(await locator.count())) return false;
      await h.tap(locator, pause);
      return true;
    },
    type: async (locator, text) => {
      await locator.click({ timeout: 5000 });
      await locator.fill(text);
      await sleep(300);
    },
    /// 요소가 화면 위쪽(offset px)에 오도록 스크롤한다
    scrollTo: async (locator, offset = 120) => {
      const handle = await locator.elementHandle({ timeout: 5000 });
      await handle.evaluate((el, offset) => {
        let p = el.parentElement;
        while (p && p !== document.body) {
          const s = getComputedStyle(p);
          if (/(auto|scroll)/.test(s.overflowY) && p.scrollHeight > p.clientHeight) break;
          p = p.parentElement;
        }
        const top = el.getBoundingClientRect().top;
        if (p && p !== document.body) p.scrollBy(0, top - p.getBoundingClientRect().top - offset);
        else window.scrollBy(0, top - offset);
      }, offset);
      await sleep(500);
    },
    go: (route, settle = 1200) => go(page, route, settle),
    main,
    page,
  };
  return h;
}

/// 캡처 위에 번호 상자를 그린다. 못 찾은 번호는 problems 에 남긴다.
async function drawMarks(page, h, marks, where) {
  const rects = [];
  const missing = [];
  for (const [i, mark] of marks.entries()) {
    let target = null;
    try {
      target = await mark(page, h);
      if (target && typeof target.boundingBox === 'function') {
        target = (await target.count()) ? await target.boundingBox({ timeout: 3000 }) : null;
      }
    } catch {
      target = null;
    }
    if (!target || target.width === 0) missing.push(i + 1);
    rects.push(target);
  }
  await page.evaluate((rects) => {
    const layer = document.createElement('div');
    layer.id = 'guide-marks';
    Object.assign(layer.style, { position: 'fixed', inset: '0', zIndex: 2147483646, pointerEvents: 'none' });
    rects.forEach((raw, i) => {
      if (!raw || raw.width === 0) return;
      const pad = 4;
      const edge = pad + 3;
      const left = Math.max(edge, raw.x);
      const top = Math.max(edge, raw.y);
      const right = Math.min(window.innerWidth - edge, raw.x + raw.width);
      const bottom = Math.min(window.innerHeight - edge, raw.y + raw.height);
      const r = { x: left, y: top, width: Math.max(8, right - left), height: Math.max(8, bottom - top) };
      const box = document.createElement('div');
      Object.assign(box.style, {
        position: 'fixed', left: `${r.x - pad}px`, top: `${r.y - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
        border: '3px solid #f97316', borderRadius: '8px', boxShadow: '0 0 0 3px rgba(249,115,22,.18)',
      });
      const badge = document.createElement('div');
      badge.textContent = String(i + 1);
      Object.assign(badge.style, {
        position: 'fixed', left: `${Math.max(0, r.x - pad - 12)}px`, top: `${Math.max(0, r.y - pad - 12)}px`,
        width: '24px', height: '24px', borderRadius: '50%', background: '#f97316', color: '#fff',
        font: '700 14px/24px "Malgun Gothic", sans-serif', textAlign: 'center', boxShadow: '0 1px 3px rgba(0,0,0,.3)',
      });
      layer.append(box, badge);
    });
    document.body.appendChild(layer);
  }, rects);
  if (missing.length) problems.push(`${where}: 번호 ${missing.join(', ')} 못 찾음`);
}

const clearMarks = (page) => page.evaluate(() => document.getElementById('guide-marks')?.remove());

async function newPage() {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR', reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await installMocks(page, { delayMs: 200 });
  return { ctx, page };
}

// 학생 대시보드를 라이트 · 사이드바 다크 · 전체 다크로 한 장씩 찍는다 → shots/themes/<id>.png
async function captureThemes(page, h) {
  const dir = path.join(shots, 'themes');
  fs.mkdirSync(dir, { recursive: true });
  const themes = [
    ['light', '라이트'],
    ['railDark', '사이드바 다크'],
    ['dark', '전체 다크'],
  ];
  try {
    for (const [id, label] of themes) {
      await h.go('/settings');
      await h.tap(page.getByText(label, { exact: true }).first(), 600);
      await h.go('/', 1500);
      await page.screenshot({ path: path.join(dir, `${id}.png`) });
      console.log(`themes/${id}`);
    }
  } finally {
    await h.go('/settings');
    await h.tapIf(page.getByText('라이트', { exact: true }).first(), 600);
  }
}

try {
  // 로그인 화면은 역할과 무관하게 한 번만 찍는다.
  {
    const { ctx, page } = await newPage();
    await page.goto(`${server.url}/login`);
    await sleep(1500);
    fs.mkdirSync(shots, { recursive: true });
    await page.screenshot({ path: path.join(shots, 'login.png') });
    await ctx.close();
  }

  for (const { role, features } of roles) {
    if (only && only !== role) continue;
    const dir = path.join(shots, role);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    // 역할마다 새 컨텍스트 — 데모 데이터 · 투어 기록이 섞이지 않는다
    const { ctx, page } = await newPage();
    page.on('pageerror', (e) => console.error(`[${role}] pageerror`, e.message));
    // 투어는 로그인 직후 첫 화면만 찍고 닫는다
    await login(page, server.url, role, { tourShot: path.join(dir, '_tour.png') });
    await sleep(600);
    // 표지에 쓰는 첫 화면(투어 · 팝업을 닫은 뒤)
    await page.screenshot({ path: path.join(dir, '_home.png') });
    const h = helpers(page);

    for (const feature of features) {
      for (const [i, s] of feature.steps.entries()) {
        const where = `${role}/${feature.id}-${i + 1}`;
        try {
          if (s.route) await h.go(s.route, 1400);
          if (s.run) await s.run(page, h);
          await sleep(500);
          if (s.marks?.length) await drawMarks(page, h, s.marks, where);
          await page.screenshot({ path: path.join(dir, `${feature.id}-${i + 1}.png`) });
          await clearMarks(page);
          if (s.after) await s.after(page, h);
          console.log(where);
        } catch (e) {
          problems.push(`${where}: ${e.message.split('\n')[0]}`);
          await clearMarks(page).catch(() => {});
          await page.screenshot({ path: path.join(dir, `${feature.id}-${i + 1}.png`) });
          console.log(`${where}  (실패)`);
          await page.keyboard.press('Escape').catch(() => {});
        }
      }
    }
    if (role === 'student') await captureThemes(page, h);
    await ctx.close();
  }
} finally {
  await browser.close();
  server.close();
  if (problems.length) console.log(`\n확인할 곳 ${problems.length}개\n${problems.join('\n')}`);
}
