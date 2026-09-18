// PDF 내보내기 결과를 종이 크기로 찍는다 — 네모 칸이 없어야 한다.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

fs.mkdirSync('shots/resume', { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '5190', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:5190/login');
await page.waitForTimeout(400);
await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
await page.waitForTimeout(250);
await page.getByRole('button', { name: '학생', exact: true }).click();
await page.waitForTimeout(700);
const dismiss = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
if (await dismiss.count()) await dismiss.click();
await page.waitForTimeout(400);
const confirm = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
if (await confirm.count()) await confirm.first().click();
await page.goto('http://localhost:5190/resume');
await page.waitForTimeout(700);
await page.getByRole('link', { name: '이어서 작성' }).click();
await page.waitForTimeout(900);

await page.pdf({ path: 'shots/resume/export.pdf', format: 'A4', printBackground: true });
// 인쇄 상태 그대로 화면으로도 찍어 눈으로 본다.
await page.emulateMedia({ media: 'print' });
await page.setViewportSize({ width: 794, height: 1123 });
await page.waitForTimeout(400);
await page.screenshot({ path: 'shots/resume/print-page.png', fullPage: true });
console.log('pdf done');

await browser.close();
server.kill();
process.exit(0);
