// 연습장 파일 불러오기·내려받기 확인 — 샘플 .ipynb 를 올려 모두 실행하고, .ipynb·.py 로 내려받아 본다.
//
//   npm run build && node tools/notebook-file.mjs
//
// 첫 실행은 Pyodide·pandas·matplotlib 를 CDN 에서 받아 1분쯤 걸린다.
import { readFileSync } from 'node:fs';

import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';

const { base, stop } = await startPreview();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1360, height: 1000 }, acceptDownloads: true });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const say = (k, v) => console.log(`${k}: ${typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : JSON.stringify(v)}`);

async function go(path) {
  await page.evaluate((p) => {
    history.pushState({}, '', p);
    dispatchEvent(new PopStateEvent('popstate'));
  }, path);
  await page.waitForTimeout(800);
}

try {
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.getByRole('button', { name: '학생', exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
  await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});

  // ── 자유 연습장: 바꾸기 ──
  await go('/study-room/playground');
  await page.locator('input[type="file"]').setInputFiles('tools/fixtures/lesson-sample.ipynb');
  await page.waitForTimeout(300);
  say('안내 줄', await page.locator('.py-import').innerText());
  await page.screenshot({ path: 'tools/shots/nbfile-import.png', clip: { x: 200, y: 0, width: 1160, height: 330 } });
  await page.getByRole('button', { name: '이 파일로 바꾸기' }).click();
  await page.waitForTimeout(400);
  say('바꾼 뒤 셀 수', await page.locator('.py-nb-cell').count());
  say('매직 주석', await page.locator('.py-nb-cell').nth(1).locator('.cm-content').innerText());
  await page.getByRole('button', { name: '모두 실행' }).click();
  await page.locator('.py-nb-cell').nth(3).locator('img').first().waitFor({ timeout: 180000 });
  say('표 출력', await page.locator('.py-nb-cell').nth(2).locator('table').count());
  say('평균 출력', await page.locator('.py-nb-cell').nth(3).locator('.py-line--out').first().innerText());

  // 내려받기 .ipynb
  await page.getByRole('button', { name: '내려받기' }).click();
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: /ipynb/ }).click()]);
  const path = await dl.path();
  const nb = JSON.parse(readFileSync(path, 'utf-8'));
  say('내려받은 이름', dl.suggestedFilename());
  say('셀 종류', nb.cells.map((c) => c.cell_type));
  say('출력 종류', nb.cells.map((c) => (c.outputs ?? []).map((o) => o.output_type)));
  await page.getByRole('button', { name: '내려받기' }).click();
  const [dl2] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: /\.py/ }).click()]);
  say('.py 앞부분', readFileSync(await dl2.path(), 'utf-8').slice(0, 80));

  // ── 복습 세트: 붙이기만 ──
  await go('/study-room/playground?set=ps-mm-0915');
  await page.waitForTimeout(800);
  const before = await page.locator('.py-nb-cell').count();
  await page.locator('input[type="file"]').setInputFiles('tools/fixtures/lesson-sample.py');
  await page.waitForTimeout(300);
  say('세트에서 바꾸기 버튼', await page.getByRole('button', { name: '이 파일로 바꾸기' }).count());
  await page.getByRole('button', { name: '끝에 붙이기' }).click();
  await page.waitForTimeout(400);
  say('붙인 셀 수', (await page.locator('.py-nb-cell').count()) - before);
  say('세트 내려받기 이름', await (async () => {
    await page.getByRole('button', { name: '내려받기' }).click();
    const [d] = await Promise.all([page.waitForEvent('download'), page.getByRole('menuitem', { name: /ipynb/ }).click()]);
    const text = readFileSync(await d.path(), 'utf-8');
    return `${d.suggestedFilename()} · 숨긴테스트 포함=${/assert /.test(text)}`;
  })());

  // 잘못된 파일
  await page.locator('input[type="file"]').setInputFiles({ name: 'broken.ipynb', mimeType: 'application/json', buffer: Buffer.from('{nope') });
  await page.waitForTimeout(300);
  say('깨진 파일', await page.locator('.py-import').innerText());

  say('페이지 오류', errors);
} finally {
  await browser.close();
  await stop();
}
