// 이력서 화면만 찍는다 — 학생(편집·Doc·댓글)과 강사(검토 목록·피드백 사이드탭).
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const out = process.argv[2] ?? 'shots/resume';
fs.mkdirSync(out, { recursive: true });

const server = spawn('npx', ['vite', 'preview', '--port', '5189', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

async function login(role) {
  await page.goto('http://localhost:5189/login');
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: role, exact: true }).click();
  await page.waitForTimeout(700);
  const dismiss = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  if (await dismiss.count()) {
    await dismiss.click();
    await page.waitForTimeout(400);
  }
  const confirm = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
  if (await confirm.count()) {
    await confirm.first().click();
    await page.waitForTimeout(300);
  }
}

const shot = async (name) => {
  await page.screenshot({ path: `${out}/${name}.png`, fullPage: true });
  console.log('shot', name);
};

await login('학생');
await page.goto('http://localhost:5189/resume');
await page.waitForTimeout(700);
await shot('student-list');

await page.getByRole('link', { name: '이어서 작성' }).click();
await page.waitForTimeout(800);
await shot('student-edit');

await page.getByRole('button', { name: 'Doc', exact: true }).click();
await page.waitForTimeout(500);
await shot('student-doc');

await page.getByRole('button', { name: '맞춤 공고 추천' }).click();
await page.waitForTimeout(1500);
await shot('student-jobs-loading');
await page.waitForTimeout(6000);
await shot('student-jobs-done');

await login('강사');
await page.goto('http://localhost:5189/instructor/resumes');
await page.waitForTimeout(800);
await shot('instructor-list');

const review = page.getByRole('button', { name: '검토하기' }).first();
if (await review.count()) {
  await review.click();
  await page.waitForTimeout(900);
  await shot('instructor-review');
}

await browser.close();
server.kill();
process.exit(0);
