// 로그인 퇴장 연출을 몇 토막으로 나눠 찍는다.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

fs.mkdirSync('shots/login', { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '5193', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:5193/login');
await page.waitForTimeout(800);
await page.screenshot({ path: 'shots/login/0-rest.png' });

// 마우스를 왼쪽 위로 옮겨 시차가 얼마나 움직이는지 본다.
await page.mouse.move(1100, 200);
await page.waitForTimeout(300);
await page.screenshot({ path: 'shots/login/1-hover.png' });

await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
await page.waitForTimeout(250);
// 연출 중간을 찍으려면 클릭 직후 짧게 끊어 찍는다.
const click = page.getByRole('button', { name: '학생', exact: true }).click();
for (const [name, wait] of [['2-early', 180], ['3-mid', 200], ['4-late', 220]]) {
  await page.waitForTimeout(wait);
  await page.screenshot({ path: `shots/login/${name}.png` });
}
await click;
await page.waitForTimeout(1200);
await page.screenshot({ path: 'shots/login/5-done.png' });
console.log('login shots');

await browser.close();
server.kill();
process.exit(0);
