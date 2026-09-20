import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
const W = Number(process.argv[2] ?? 1200);
fs.mkdirSync('shots/states', { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '5230', '--strictPort'], { shell: true, stdio: 'ignore' });
await new Promise((r) => setTimeout(r, 3500));
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: W, height: 940 } });
await p.goto('http://localhost:5230/login');
await p.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
await p.waitForTimeout(300);
await p.getByRole('button', { name: '학생', exact: true }).click();
const d = p.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
await d.waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
if (await d.count()) await d.click();
await p.waitForTimeout(700);
const ok = p.locator('.dialog').getByRole('button', { name: '확인', exact: true });
if (await ok.count()) { await ok.first().click(); await p.waitForTimeout(400); }
// 편집 화면은 셸 밖 전체화면 라우트다. 세션은 localStorage에 있어 goto로도 유지된다.
await p.goto('http://localhost:5230/resume/r-demo-1/edit');
await p.waitForTimeout(1500);
const grid = await p.locator('.resume-edit__body').evaluate((el) => getComputedStyle(el).gridTemplateColumns).catch(() => '없음');
const toggle = await p.getByRole('button', { name: /AI 코치 (열기|접기)/ }).count();
const coach = await p.locator('.resume-coach').count();
console.log(`width ${W} | 토글버튼 ${toggle} | 코치패널 ${coach} | grid ${grid}`);
if (toggle > 0) {
  await p.getByRole('button', { name: /AI 코치 열기/ }).click();
  await p.waitForTimeout(600);
  console.log(`   → 열고 나서: 코치패널 ${await p.locator('.resume-coach').count()}`);
}
await p.screenshot({ path: `shots/states/edit-${W}.png` });
await b.close(); server.kill(); process.exit(0);
