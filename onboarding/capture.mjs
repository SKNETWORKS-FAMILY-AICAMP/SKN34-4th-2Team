// scenes.mjs의 기능·단계를 차례대로 실행하며 한 장씩 찍는다.
// 결과: build/onboarding/shots/<role>/<feature>-<단계>.png (+ login.png, <role>/_tour.png, themes/*.png)
// 사용: node capture.mjs            (전체)
//       node capture.mjs student    (한 역할만)
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import { serveBuild, waitForApp, login, go, dismissTour, outRoot, sleep } from './lib/app.mjs';
import { ensureVisible, tap, typeInto, btn, btnLike, railRect, todayCell } from './lib/actions.mjs';
import { roles } from './scenes.mjs';

const only = process.argv[2];
const server = await serveBuild();
const browser = await chromium.launch({
  executablePath: process.platform === 'win32'
    ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
    : undefined,
});
const problems = [];

async function waitForSpinners(page, maxMs = 6000) {
  // 로딩 표시(progressbar)가 사라질 때까지 기다리되, 끝없이 도는 것은 maxMs에서 끊는다.
  const end = Date.now() + maxMs;
  while (Date.now() < end) {
    const n = await page.locator('flt-semantics[role="progressbar"]').count();
    if (n === 0) return true;
    await sleep(400);
  }
  return false;
}

/// scenes.mjs가 화면 요소를 찾을 때 쓰는 도구.
function helpers(page) {
  return {
    btn: (name) => btn(page, name),
    btnLike: (re) => btnLike(page, re),
    cb: (name) => page.getByRole('checkbox', { name, exact: true }),
    todayCell: () => todayCell(page),
    /// 사이드바 메뉴 칸. count를 주면 그 칸부터 count개를 묶은 영역.
    rail: async (label, count = 1) => {
      const r = await railRect(page, label);
      return r && { ...r, height: r.height + (count - 1) * 44 };
    },
    /// 글자를 담은 가장 작은 semantics 영역(버튼이 아닌 제목·카드용). nth는 몇 번째 것인지.
    textRect: (text, nth = 0) =>
      page.evaluate(
        ([text, nth]) => {
          const hits = [...document.querySelectorAll('flt-semantics')]
            .map((el) => ({ el, label: (el.getAttribute('aria-label') ?? el.textContent ?? '').trim() }))
            .filter((x) => x.label.includes(text))
            .map((x) => x.el.getBoundingClientRect())
            .filter((r) => r.width > 0 && r.height > 0);
          // 같은 글자로 시작하는 바깥 묶음보다 안쪽의 작은 칸을 고른다. 겹치는 것은 하나로 친다.
          hits.sort((a, b) => a.width * a.height - b.width * b.height);
          const distinct = [];
          for (const r of hits) {
            if (!distinct.some((d) => r.left <= d.left + 2 && r.top <= d.top + 2 && r.right >= d.right - 2 && r.bottom >= d.bottom - 2)) distinct.push(r);
          }
          distinct.sort((a, b) => a.top - b.top || a.left - b.left);
          const r = distinct[nth];
          return r ? { x: r.left, y: r.top, width: r.width, height: r.height } : null;
        },
        [text, nth],
      ),
    tap: (locator, pause = 900) => tap(page, locator, { pause }),
    tapIf: async (locator, pause = 900) => {
      if (!(await locator.count())) return false;
      await tap(page, locator, { pause });
      return true;
    },
    type: (locator, text) => typeInto(page, locator, text),
    scrollTo: (locator) => ensureVisible(page, locator),
  };
}

/// 캡처 위에 번호 상자를 그린다. 못 찾은 번호는 돌려준다.
async function drawMarks(page, h, marks, where) {
  const rects = [];
  const missing = [];
  for (const [i, mark] of marks.entries()) {
    let target = await mark(page, h);
    if (target && typeof target.boundingBox === 'function') {
      target = (await target.count()) ? await target.first().boundingBox() : null;
    }
    if (!target) missing.push(i + 1);
    rects.push(target);
  }
  await page.evaluate((rects) => {
    const layer = document.createElement('div');
    layer.id = 'guide-marks';
    Object.assign(layer.style, { position: 'fixed', inset: '0', zIndex: 2147483646, pointerEvents: 'none' });
    rects.forEach((raw, i) => {
      if (!raw) return;
      const pad = 4;
      // 화면 가장자리에 붙은 요소는 상자가 잘리지 않게 안쪽으로 들인다.
      const edge = pad + 3;
      const left = Math.max(edge, raw.x);
      const top = Math.max(edge, raw.y);
      const right = Math.min(window.innerWidth - edge, raw.x + raw.width);
      const bottom = Math.min(window.innerHeight - edge, raw.y + raw.height);
      const r = { x: left, y: top, width: right - left, height: bottom - top };
      const box = document.createElement('div');
      Object.assign(box.style, {
        position: 'fixed', left: `${r.x - pad}px`, top: `${r.y - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px`,
        border: '3px solid #f97316', borderRadius: '8px', boxShadow: '0 0 0 3px rgba(249,115,22,.18)',
      });
      const badge = document.createElement('div');
      badge.textContent = String(i + 1);
      // 번호는 상자 왼쪽 위 바깥에 둔다. 화면 가장자리에 붙으면 안쪽으로 들인다.
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
  return missing;
}

const clearMarks = (page) => page.evaluate(() => document.getElementById('guide-marks')?.remove());

// 화면 설정에서 테마 항목을 누른다. 항목 전체가 하나의 탭 영역이라 라벨로 시작하는 이름으로 찾는다.
async function pickTheme(page, label) {
  await btnLike(page, new RegExp(`^${label} `)).first().click();
  await sleep(800);
}

// 학생 대시보드를 라이트·사이드바 다크·전체 다크로 한 장씩 찍는다 → shots/themes/<id>.png
async function captureThemes(page) {
  const dir = path.join(outRoot, 'shots', 'themes');
  fs.mkdirSync(dir, { recursive: true });
  const themes = [
    ['light', '라이트'],
    ['railDark', '사이드바 다크'],
    ['dark', '전체 다크'],
  ];
  try {
    for (const [id, label] of themes) {
      await go(page, '/settings', 1500);
      await pickTheme(page, label);
      await go(page, '/', 1800);
      await waitForSpinners(page);
      await sleep(500);
      await page.screenshot({ path: path.join(dir, `${id}.png`) });
      console.log(`themes/${id}`);
    }
  } finally {
    // 다음 캡처가 라이트로 찍히도록 되돌린다.
    await go(page, '/settings', 1200);
    await pickTheme(page, '라이트').catch(() => {});
  }
}

try {
  // 로그인 화면은 역할과 무관하게 한 번만 찍는다.
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
    const page = await ctx.newPage();
    await page.goto(server.url);
    await waitForApp(page);
    fs.mkdirSync(path.join(outRoot, 'shots'), { recursive: true });
    await page.screenshot({ path: path.join(outRoot, 'shots', 'login.png') });
    await ctx.close();
  }

  for (const { role, features } of roles) {
    if (only && only !== role) continue;
    const dir = path.join(outRoot, 'shots', role);
    fs.rmSync(dir, { recursive: true, force: true });
    fs.mkdirSync(dir, { recursive: true });
    // 역할마다 새 컨텍스트: 데모 세션과 온보딩 dismiss 기록이 섞이지 않는다.
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
    const page = await ctx.newPage();
    page.on('pageerror', (e) => console.error(`[${role}] pageerror`, e.message));
    await page.goto(server.url);
    await waitForApp(page);
    await login(page, role);
    await page.screenshot({ path: path.join(dir, '_tour.png') });
    await dismissTour(page);
    const h = helpers(page);

    for (const feature of features) {
      for (const [i, s] of feature.steps.entries()) {
        const where = `${role}/${feature.id}-${i + 1}`;
        try {
          if (s.route) {
            await go(page, s.route, 1800);
            await dismissTour(page);
            await waitForSpinners(page);
          }
          if (s.run) await s.run(page, h);
          await sleep(600);
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
        }
      }
    }
    if (role === 'student') await captureThemes(page);
    await ctx.close();
  }
} finally {
  await browser.close();
  server.close();
  if (problems.length) console.log(`\n확인할 곳 ${problems.length}개\n${problems.join('\n')}`);
}
