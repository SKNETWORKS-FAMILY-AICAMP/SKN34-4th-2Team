// 프로토타입 화면을 찍어 원본 캡처와 나란히 견준다.
// 사용: node shot.mjs [out-dir]
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const out = process.argv[2] ?? 'shots';
fs.mkdirSync(out, { recursive: true });

const server = spawn('npx', ['vite', 'preview', '--port', '5188', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });

async function login(role) {
  await page.goto('http://localhost:5188/login');
  await page.waitForTimeout(400);
  // 데모 계정 버튼은 「빠른 로그인 (데모)」 안에 접혀 있다.
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: role, exact: true }).click();
  await page.waitForTimeout(700);
  // 투어가 화면을 덮고 있으니 투어부터 닫고, 그 뒤에 알림 팝업을 닫는다.
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

async function shot(name, path) {
  if (path) {
    await page.goto(`http://localhost:5188${path}`);
    await page.waitForTimeout(700);
  }
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log('shot', name);
}

await login('학생');
await shot('student-dashboard');
await shot('student-assessments', '/assessments');
await shot('student-board', '/board');
await shot('student-mileage', '/mileage');

await login('강사');
await shot('instructor-attendance');

await login('관리자');
await shot('admin-dashboard');
await shot('admin-students', '/admin/students');

await browser.close();
server.kill();
process.exit(0);
