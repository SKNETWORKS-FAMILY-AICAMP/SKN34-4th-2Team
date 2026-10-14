// 세 역할의 전 화면을 여러 너비로 열어 레이아웃 문제를 자동으로 찾는다.
//
//   npm run build && node tools/responsive-scan.mjs [이름] [역할,...] [너비,...] [경로,...]
//   예) node tools/responsive-scan.mjs after
//       node tools/responsive-scan.mjs admin admin 390 admin,admin/board
//   ALWAYS=1 을 붙이면 문제가 없어도 캡처한다. 결과는 shots/scan/<이름>/ (깃이 무시한다).
//   Git Bash 에서 경로 인자를 넘길 땐 MSYS_NO_PATHCONV=1 을 앞에 붙인다.
//
// 찾는 것: 가로 스크롤과 그 원인, 화면 밖으로 나간 요소, 형제 카드끼리 겹침,
// 좁은 칸에 눌려 세로로 깨진 글자. 넓은 문단이 몇 줄로 줄바꿈된 것도 걸릴 수 있어 눈으로 한 번 본다.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { startPreview, ROOT } from './preview.mjs';

const prefix = process.argv[2] ?? 'scan';
const roles = (process.argv[3] ?? 'student,instructor,admin').split(',');
const widths = (process.argv[4] ?? '1180,860,560,390').split(',').map(Number);
const only = process.argv[5] ? process.argv[5].split(',') : null;
const ROLE_LABEL = { student: '학생', instructor: '강사', admin: '관리자' };
const ROUTES = {
  student: ['/dashboard', '/resume', '/study-room', '/study-room/notes', '/study-room/playground', '/board', '/seating', '/forms', '/qual-exams', '/records', '/mileage', '/mileage/shop', '/assessments', '/my-page', '/settings'],
  instructor: ['/instructor', '/instructor/resumes', '/instructor/board', '/instructor/assessments', '/instructor/curriculum', '/instructor/my-page', '/instructor/settings'],
  admin: ['/admin', '/admin/cohorts', '/admin/students', '/admin/instructors', '/admin/attendance', '/admin/seat-presence', '/admin/seating', '/admin/assessments', '/admin/records', '/admin/resumes', '/admin/form-tasks', '/admin/study-room', '/admin/board', '/admin/mileage', '/admin/ai-quality', '/admin/my-page'],
};

const dir = path.resolve(ROOT, 'shots/scan', prefix);
fs.mkdirSync(dir, { recursive: true });
const { base, stop } = await startPreview();
const browser = await chromium.launch();
const report = [];

async function login(page, role) {
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: ROLE_LABEL[role], exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  await page.waitForTimeout(300);
  const confirm = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
  if (await confirm.count()) await confirm.first().click();
}

/** 페이지 안에서 돈다. 문제 목록을 돌려준다. */
function inspect() {
  const vw = document.documentElement.clientWidth;
  const out = { hscroll: document.documentElement.scrollWidth - vw, overflow: [], overlap: [], vertical: [] };
  const label = (el) => {
    const cls = typeof el.className === 'string' ? el.className.trim().split(/\s+/).slice(0, 2).join('.') : '';
    const text = (el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 24);
    return `${el.tagName.toLowerCase()}${cls ? '.' + cls : ''}「${text}」`;
  };
  const visible = (el) => {
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || s.position === 'fixed') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const main = document.querySelector('.shell__main, main, #root') || document.body;
  // 좁은 화면에서 화면 밖에 숨겨 둔 메뉴·떠 있는 챗봇은 뺀다
  const all = [...main.querySelectorAll('*')].filter((el) => !el.closest('.rail, .chatbot-fab, .robot-fab, .tour-card') && visible(el));

  // 1) 화면 밖으로 나간 요소 — 가로 스크롤 상자 안에 있는 것은 뺀다
  const inScroller = (el) => {
    for (let p = el.parentElement; p && p !== main; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (/(auto|scroll|hidden)/.test(s.overflowX)) return true;
    }
    return false;
  };
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if ((r.right > vw + 2 || r.left < -2) && !inScroller(el) && el.children.length < 30) out.overflow.push(label(el));
  }

  // 2) 형제 카드끼리 겹침 — 같은 부모 아래 블록 요소만
  const blocks = all.filter((el) => /panel|card|section|tile/.test(el.className) && getComputedStyle(el).position !== 'absolute');
  const byParent = new Map();
  for (const el of blocks) {
    const list = byParent.get(el.parentElement) || [];
    list.push(el);
    byParent.set(el.parentElement, list);
  }
  for (const list of byParent.values()) {
    for (let i = 0; i < list.length; i++)
      for (let j = i + 1; j < list.length; j++) {
        const a = list[i].getBoundingClientRect(), b = list[j].getBoundingClientRect();
        const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (x > 4 && y > 4) out.overlap.push(`${label(list[i])} × ${label(list[j])}`);
      }
  }

  // 3) 세로로 깨진 글자 — 좁은데 여러 줄로 늘어난 글 조각
  for (const el of all) {
    const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    if (own.length < 3) continue;
    const r = el.getBoundingClientRect();
    const lh = parseFloat(getComputedStyle(el).lineHeight) || parseFloat(getComputedStyle(el).fontSize) * 1.4;
    const lines = Math.round(r.height / lh);
    if (lines >= 3 && r.width < own.length * parseFloat(getComputedStyle(el).fontSize) * 0.34) out.vertical.push(`${label(el)} ${Math.round(r.width)}px×${lines}줄`);
  }
  // 가로 스크롤이 있으면 원인 — 부모는 안 넘치는데 자기는 넘치는 첫 요소
  out.cause = [];
  if (out.hscroll > 1) {
    for (const el of document.querySelectorAll('body *')) {
      if (el.closest('.rail')) continue;
      const r = el.getBoundingClientRect();
      if (r.right <= vw + 1 || r.width === 0) continue;
      const pr = el.parentElement.getBoundingClientRect();
      if (pr.right <= vw + 1) {
        const cs = getComputedStyle(el);
        out.cause.push(`${label(el)} w=${Math.round(r.width)} ml=${cs.marginLeft} mr=${cs.marginRight} minW=${cs.minWidth}`);
      }
    }
    out.cause = [...new Set(out.cause)].slice(0, 6);
  }
  out.overflow = [...new Set(out.overflow)].slice(0, 8);
  out.overlap = [...new Set(out.overlap)].slice(0, 8);
  out.vertical = [...new Set(out.vertical)].slice(0, 8);
  return out;
}

try {
  for (const role of roles) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await login(page, role);
    for (const width of widths) {
      await page.setViewportSize({ width, height: 900 });
      for (const route of ROUTES[role].filter((r) => !only || only.includes(r.replace(/^\//, '')))) {
        await page.goto(`${base}${route}`);
        await page.waitForTimeout(700);
        const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
        if (await tour.count()) { await tour.click(); await page.waitForTimeout(250); }
        const res = await page.evaluate(inspect);
        const bad = res.hscroll > 1 || res.overflow.length || res.overlap.length || res.vertical.length;
        const name = `${role}${route.replace(/\//g, '_')}-${width}`;
        if (bad || process.env.ALWAYS) await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true });
        report.push({ role, route, width, ...res, bad: Boolean(bad), shot: bad ? name : null });
        process.stdout.write(bad ? 'x' : '.');
      }
    }
    await page.close();
  }
} finally {
  fs.writeFileSync(`${dir}/report.json`, JSON.stringify(report, null, 1));
  await browser.close();
  await stop();
  const bad = report.filter((r) => r.bad);
  console.log(`\n검사 ${report.length}개 · 문제 ${bad.length}개`);
  for (const r of bad) {
    console.log(`\n■ ${r.role} ${r.route} @${r.width}  가로스크롤 ${r.hscroll}px`);
    for (const k of ['cause', 'overflow', 'overlap', 'vertical']) if (r[k].length) console.log(`  ${k}: ${r[k].join(' | ')}`);
  }
}
