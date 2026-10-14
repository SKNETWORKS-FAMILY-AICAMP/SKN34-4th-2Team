// 연습 문제 메뉴와 첫 문제를 찍는다
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { startPreview, ROOT } from './preview.mjs';

const dir = path.resolve(ROOT, 'shots/toolbar');
fs.mkdirSync(dir, { recursive: true });
const { base, stop } = await startPreview();
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 }, deviceScaleFactor: 2 });
  await page.goto(`${base}/login`);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.getByRole('button', { name: '학생', exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
  await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
  await page.goto(`${base}/study-room/playground`);
  await page.locator('.py-toolbar').waitFor({ timeout: 15000 });
  await page.waitForTimeout(500);

  await page.getByRole('button', { name: '연습 문제 풀기' }).click();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: '문제 고르기' }).click();
  await page.waitForTimeout(300);
  const tb = await page.locator('.py-toolbar').boundingBox();
  await page.screenshot({ path: `${dir}/5-problem-menu.png`, clip: { x: tb.x - 8, y: tb.y - 8, width: 720, height: 780 } });
  console.log('shot 5-problem-menu');
  await page.keyboard.press('Escape');
  const last = page.locator('.py-nb-cell').nth(-3);
  await last.scrollIntoViewIfNeeded();
  await page.waitForTimeout(200);
  const b = await last.boundingBox();
  await page.screenshot({ path: `${dir}/6-first-problem.png`, clip: { x: b.x - 8, y: b.y - 8, width: b.width + 16, height: 420 } });
  console.log('shot 6-first-problem');
} finally {
  await browser.close();
  stop();
}
