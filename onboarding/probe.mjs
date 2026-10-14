// 한 역할로 로그인해서 화면을 찍고, 화면에 보이는 semantics 라벨을 덤프한다.
// 캡처 시나리오를 짤 때 버튼 이름을 확인하는 용도.
// 사용: node probe.mjs student /board
//       node probe.mjs admin /admin/mileage /admin/mileage/requests   (여러 화면을 차례로)
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';
import { serveBuild, waitForApp, login, go, dismissTour, outRoot, sleep } from './lib/app.mjs';

const role = process.argv[2] ?? 'student';
const routes = process.argv.slice(3);
const dir = path.join(outRoot, 'probe');
fs.mkdirSync(dir, { recursive: true });

const server = await serveBuild(5184);
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, locale: 'ko-KR' });
page.on('pageerror', (e) => console.error('[pageerror]', e.message));

async function dump(name) {
  await page.screenshot({ path: path.join(dir, `${name}.png`) });
  const labels = await page.evaluate(() =>
    [...document.querySelectorAll('flt-semantics')]
      .map((n) => {
        const role = n.getAttribute('role') ?? '';
        const label = (n.getAttribute('aria-label') ?? n.textContent ?? '').trim();
        return label ? `${role}\t${label.replace(/\s+/g, ' ').slice(0, 80)}` : null;
      })
      .filter(Boolean),
  );
  console.log(`\n## ${name}\n${[...new Set(labels)].join('\n')}`);
}

try {
  await page.goto(server.url);
  await waitForApp(page);
  await page.screenshot({ path: path.join(dir, 'login.png') });
  await login(page, role);
  await page.screenshot({ path: path.join(dir, `${role}-after-login.png`) });
  const dismissed = await dismissTour(page);
  console.log('tour dismissed:', dismissed);
  for (const route of routes.length ? routes : [null]) {
    if (route) await go(page, route, 2500);
    await sleep(1000);
    await dump(`${role}${(route ?? '/home').replaceAll('/', '_')}`);
  }
} finally {
  await browser.close();
  server.close();
}
