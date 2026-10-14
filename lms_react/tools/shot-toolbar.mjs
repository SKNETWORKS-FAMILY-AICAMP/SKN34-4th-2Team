// 연습장 도구 줄만 잘라 찍는다 — 닫힘 · 셀 추가 열림 · ··· 열림
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { startPreview, ROOT } from './preview.mjs';

const dir = path.resolve(ROOT, 'shots/toolbar');
fs.mkdirSync(dir, { recursive: true });
const { base, stop } = await startPreview();
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  await page.goto(`${base}/login`);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.getByRole('button', { name: '학생', exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
  await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
  await page.goto(`${base}/study-room/playground`);
  await page.locator('.py-toolbar').waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);

  const head = page.locator('.study-head');
  const shot = async (name) => {
    const a = await head.boundingBox();
    await page.screenshot({ path: `${dir}/${name}.png`, clip: { x: a.x - 8, y: a.y - 8, width: a.width + 16, height: 300 } });
    console.log('shot', name);
  };
  await shot('1-closed');
  await page.locator('.py-toolbar').getByRole('button', { name: '셀 추가' }).click();
  await page.waitForTimeout(200);
  await shot('2-add-menu');
  await page.keyboard.press('Escape');
  await page.locator('.py-toolbar').getByRole('button', { name: '더 보기' }).click();
  await page.waitForTimeout(200);
  await shot('3-more-menu');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '더 보기' }).click();
  await page.getByRole('menuitem', { name: /단축키/ }).click();
  await page.waitForTimeout(200);
  await shot('4-keys');
} finally {
  await browser.close();
  stop();
}
