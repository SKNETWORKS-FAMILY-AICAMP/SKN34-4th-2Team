// 창 크기를 바꿔 가며 카드가 가운데 패널과 겹치지 않는지 본다.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

fs.mkdirSync('shots/login', { recursive: true });
const server = spawn('npx', ['vite', 'preview', '--port', '5194', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const sizes = [
  ['wide', 1600, 900],
  ['user', 1180, 1000],
  ['short', 1440, 700],
];
for (const [name, width, height] of sizes) {
  const page = await browser.newPage({ viewport: { width, height } });
  await page.goto('http://localhost:5194/login');
  await page.waitForTimeout(900);
  // 마우스를 여기저기 옮겨도 무대가 따라오지 않아야 한다.
  await page.mouse.move(width - 200, 150);
  await page.waitForTimeout(250);
  await page.screenshot({ path: `shots/login/size-${name}.png` });
  console.log('shot', name);
  await page.close();
}

await browser.close();
server.kill();
process.exit(0);
