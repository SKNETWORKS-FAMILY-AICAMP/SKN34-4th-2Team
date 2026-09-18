// 한 화면만 빠르게 찍는다: node shot_one.mjs <role> <path> <name>
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const [role, path, name] = process.argv.slice(2);
fs.mkdirSync('shots/all', { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '5192', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto('http://localhost:5192/login');
await page.waitForTimeout(500);
await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
await page.waitForTimeout(250);
await page.getByRole('button', { name: role, exact: true }).click();
await page.waitForTimeout(800);
const d = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
if (await d.count()) { await d.click(); await page.waitForTimeout(400); }
const c = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
if (await c.count()) { await c.first().click(); await page.waitForTimeout(300); }
await page.goto(`http://localhost:5192/${path.replace(/^\//, '')}`);
await page.waitForTimeout(800);
await page.screenshot({ path: `shots/all/${name}.png` });
console.log('shot', name);
await browser.close();
server.kill();
process.exit(0);
