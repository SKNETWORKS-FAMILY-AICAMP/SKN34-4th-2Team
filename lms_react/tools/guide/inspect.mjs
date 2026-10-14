// 글자를 담은 요소의 조상 사슬(태그.클래스 크기)을 뽑는다 — scenes.mjs 의 번호 상자 선택자를 고를 때 본다.
//   INSPECT="오늘 복습|시스템 공지" node inspect.mjs <역할> <경로> [클릭...]
import fs from 'node:fs';
import { serve } from './serve.mjs';
import { launch, login, go, sleep } from './lib.mjs';
import { installMocks } from './mocks.mjs';

const [role, route, ...clicks] = process.argv.slice(2);
const texts = (process.env.INSPECT ?? '').split('|').filter(Boolean);
const srv = await serve();
const browser = await launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
  await installMocks(page);
  await login(page, srv.url, role);
  await go(page, route, 1200);
  for (const c of clicks) {
    const [kind, name] = c.includes('=') ? c.split('=') : ['button', c];
    if (kind === 'wait') { await sleep(Number(name)); continue; }
    const loc = kind === 'text' ? page.getByText(name).first() : kind === 'css' ? page.locator(name).first() : page.getByRole(kind, { name: new RegExp(name) }).first();
    await loc.click();
    await sleep(1500);
  }
  const out = await page.evaluate((texts) => texts.map((t) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) if (node.textContent.includes(t)) break;
    if (!node) return `${t}: 없음`;
    const chain = [];
    let el = node.parentElement;
    for (let i = 0; el && el !== document.body && i < 9; i++, el = el.parentElement) {
      const r = el.getBoundingClientRect();
      chain.push(`${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).join('.') : ''}[${Math.round(r.width)}x${Math.round(r.height)}]`);
    }
    return `${t}:\n   ${chain.join('\n   ')}`;
  }), texts);
  fs.writeFileSync(process.env.INSPECT_OUT ?? 'inspect.out.txt', out.join('\n'));
} finally {
  await browser.close();
  srv.close();
}
