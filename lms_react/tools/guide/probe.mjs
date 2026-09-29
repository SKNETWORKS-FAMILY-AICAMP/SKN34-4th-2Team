// 화면의 버튼·링크·입력칸 이름을 뽑는다. 장면 문구를 쓰기 전에 본다.
//   node probe.mjs <역할> <경로> [클릭할 버튼 이름...] 
import { serve } from './serve.mjs';
import { launch, login, go, sleep } from './lib.mjs';
import { installMocks } from './mocks.mjs';

const [role, route, ...clicks] = process.argv.slice(2);
const out = process.env.PROBE_OUT;
const srv = await serve();
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
  await installMocks(page);
  page.on('pageerror', (e) => console.log('pageerror', e.message));
  await login(page, srv.url, role);
  await go(page, route, 1200);
  for (const c of clicks) {
    const [kind, name] = c.includes('=') ? c.split('=') : ['button', c];
    if (kind === 'wait') { await sleep(Number(name)); continue; }
    if (kind === 'go') { await go(page, name, 1200); continue; }
    const loc = kind === 'text' ? page.getByText(name).first() : kind === 'css' ? page.locator(name).first() : page.getByRole(kind, { name }).first();
    await loc.click();
    await sleep(1500);
  }
  const dump = await page.evaluate(() => {
    const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    const txt = (el) => (el.getAttribute('aria-label') || el.innerText || el.value || el.placeholder || '').trim().replace(/\s+/g, ' ').slice(0, 70);
    const pick = (sel) => [...document.querySelectorAll(sel)].filter(vis).map(txt).filter(Boolean);
    return {
      url: location.pathname,
      headings: pick('h1,h2,h3,h4'),
      buttons: [...new Set(pick('button,[role=button],[role=tab]'))],
      links: pick('a'),
      inputs: [...document.querySelectorAll('input,textarea,select')].filter(vis).map((e) => `${e.tagName}:${e.type}:${e.placeholder || e.getAttribute('aria-label') || e.name || ''}`),
    };
  });
  if (process.env.PROBE_JSON) (await import('node:fs')).writeFileSync(process.env.PROBE_JSON, JSON.stringify(dump, null, 1));
  else console.log(JSON.stringify(dump, null, 1));
  if (out) await page.screenshot({ path: out });
} finally {
  await browser.close();
  srv.close();
}
