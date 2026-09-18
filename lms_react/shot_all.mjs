// 프로토타입 전 화면을 참조 캡처와 같은 이름으로 찍는다.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';

const out = process.argv[2] ?? 'shots/all';
fs.mkdirSync(out, { recursive: true });

const server = spawn('npx', ['vite', 'preview', '--port', '5191', '--strictPort'], {
  shell: true,
  stdio: 'ignore',
});
await new Promise((r) => setTimeout(r, 3500));

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

const routes = {
  student: [
    ['dashboard', '/dashboard'],
    ['resume', '/resume'],
    ['study-room', '/study-room'],
    ['board', '/board'],
    ['seating', '/seating'],
    ['forms', '/forms'],
    ['qual-exams', '/qual-exams'],
    ['records', '/records'],
    ['mileage', '/mileage'],
    ['mileage-shop', '/mileage/shop'],
    ['assessments', '/assessments'],
    ['my-page', '/my-page'],
    ['settings', '/settings'],
  ],
  instructor: [
    ['attendance', '/instructor'],
    ['resumes', '/instructor/resumes'],
    ['board', '/instructor/board'],
    ['assessments', '/instructor/assessments'],
    ['curriculum', '/instructor/curriculum'],
    ['my-page', '/instructor/my-page'],
  ],
  admin: [
    ['dashboard', '/admin'],
    ['cohorts', '/admin/cohorts'],
    ['students', '/admin/students'],
    ['instructors', '/admin/instructors'],
    ['attendance', '/admin/attendance'],
    ['seat-presence', '/admin/seat-presence'],
    ['seating', '/admin/seating'],
    ['assessments', '/admin/assessments'],
    ['records', '/admin/records'],
    ['resumes', '/admin/resumes'],
    ['form-tasks', '/admin/form-tasks'],
    ['study-room', '/admin/study-room'],
    ['board', '/admin/board'],
    ['mileage', '/admin/mileage'],
    ['ai-quality', '/admin/ai-quality'],
  ],
};

const base = 'http://localhost:5191';

for (const role of ['student', 'instructor', 'admin']) {
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  if (role === 'student') await page.screenshot({ path: `${out}/00-login.png` });
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  const label = role === 'student' ? '학생' : role === 'instructor' ? '강사' : '관리자';
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.waitForTimeout(800);
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

  for (const [name, path] of routes[role]) {
    await page.goto(`${base}${path}`);
    await page.waitForTimeout(650);
    await page.screenshot({ path: `${out}/${role}-${name}.png` });
    console.log('shot', role, name);
  }
}

await browser.close();
server.kill();
process.exit(0);
