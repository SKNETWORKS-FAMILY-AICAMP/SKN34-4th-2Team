// 화면 캡처를 한자리에 모았다. lms_react 어디에서 불러도 된다.
//
//   node tools/shot.mjs all [폴더]               전 화면 (학생·강사·관리자)
//   node tools/shot.mjs one <역할> <경로> <이름>   한 화면만
//   node tools/shot.mjs resume [폴더]            이력서 흐름 (목록→편집→Doc→추천)
//   node tools/shot.mjs pdf                      PDF 내보내기와 인쇄 화면
//   node tools/shot.mjs login                    로그인 퇴장 연출을 토막으로
//   node tools/shot.mjs stage                    로그인 화면을 창 크기별로
//   node tools/shot.mjs edit [너비]              편집 화면 격자·토글 진단
//
// 찍기 전에 `npm run build` 를 해야 한다. 미리보기는 dist 를 띄운다.
import { chromium } from 'playwright';
import fs from 'node:fs';
import path from 'node:path';
import { startPreview, ROOT } from './preview.mjs';

const ROLE_LABEL = { student: '학생', instructor: '강사', admin: '관리자' };

const ROUTES = {
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

// 출력은 늘 lms_react/shots 아래로 간다. shots/ 는 깃이 무시한다.
function outDir(rel) {
  const dir = path.resolve(ROOT, rel);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// 로그인하고, 화면을 덮는 투어와 알림을 걷어낸다.
async function login(page, base, role) {
  const label = ROLE_LABEL[role] ?? role;
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  // 데모 계정 버튼은 「빠른 로그인 (데모)」 안에 접혀 있다.
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: label, exact: true }).click();
  await page.waitForTimeout(800);
  // 투어가 알림 위에 있으니 투어부터 닫는다.
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  if (await tour.count()) {
    await tour.click();
    await page.waitForTimeout(400);
  }
  const confirm = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
  if (await confirm.count()) {
    await confirm.first().click();
    await page.waitForTimeout(300);
  }
}

const jobs = {
  // 세 역할의 전 화면
  async all({ browser, base, args }) {
    const dir = outDir(args[0] ?? 'shots/all');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    for (const role of ['student', 'instructor', 'admin']) {
      if (role === 'student') {
        await page.goto(`${base}/login`);
        await page.waitForTimeout(500);
        await page.screenshot({ path: `${dir}/00-login.png` });
      }
      await login(page, base, role);
      for (const [name, route] of ROUTES[role]) {
        await page.goto(`${base}${route}`);
        await page.waitForTimeout(650);
        await page.screenshot({ path: `${dir}/${role}-${name}.png` });
        console.log('shot', role, name);
      }
    }
  },

  // 한 화면만 빠르게
  async one({ browser, base, args }) {
    const [role, route, name] = args;
    if (!role || !route || !name) throw new Error('사용: one <역할> <경로> <이름>');
    const dir = outDir('shots/all');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await login(page, base, role);
    await page.goto(`${base}/${route.replace(/^\//, '')}`);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${dir}/${name}.png` });
    console.log('shot', name);
  },

  // 이력서: 학생 목록→편집→Doc→추천, 강사 검토
  async resume({ browser, base, args }) {
    const dir = outDir(args[0] ?? 'shots/resume');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    const shot = async (name) => {
      await page.screenshot({ path: `${dir}/${name}.png`, fullPage: true });
      console.log('shot', name);
    };

    await login(page, base, 'student');
    await page.goto(`${base}/resume`);
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

    await login(page, base, 'instructor');
    await page.goto(`${base}/instructor/resumes`);
    await page.waitForTimeout(800);
    await shot('instructor-list');

    const review = page.getByRole('button', { name: '검토하기' }).first();
    if (await review.count()) {
      await review.click();
      await page.waitForTimeout(900);
      await shot('instructor-review');
    }
  },

  // 내보낸 PDF 에 네모 칸이 없는지 본다
  async pdf({ browser, base }) {
    const dir = outDir('shots/resume');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await login(page, base, 'student');
    await page.goto(`${base}/resume`);
    await page.waitForTimeout(700);
    await page.getByRole('link', { name: '이어서 작성' }).click();
    await page.waitForTimeout(900);

    await page.pdf({ path: `${dir}/export.pdf`, format: 'A4', printBackground: true });
    // 인쇄 상태 그대로 화면으로도 찍어 눈으로 본다.
    await page.emulateMedia({ media: 'print' });
    await page.setViewportSize({ width: 794, height: 1123 });
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${dir}/print-page.png`, fullPage: true });
    console.log('pdf done');
  },

  // 로그인 퇴장 연출을 토막으로
  async login({ browser, base }) {
    const dir = outDir('shots/login');
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
    await page.goto(`${base}/login`);
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${dir}/0-rest.png` });

    // 마우스를 옮겨 시차가 얼마나 움직이는지 본다.
    await page.mouse.move(1100, 200);
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${dir}/1-hover.png` });

    await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
    await page.waitForTimeout(250);
    // 연출 중간을 보려면 클릭을 기다리지 말고 짧게 끊어 찍는다.
    const click = page.getByRole('button', { name: '학생', exact: true }).click();
    for (const [name, wait] of [['2-early', 180], ['3-mid', 200], ['4-late', 220]]) {
      await page.waitForTimeout(wait);
      await page.screenshot({ path: `${dir}/${name}.png` });
    }
    await click;
    await page.waitForTimeout(1200);
    await page.screenshot({ path: `${dir}/5-done.png` });
    console.log('login shots');
  },

  // 창을 줄여도 카드가 가운데 패널과 겹치지 않아야 한다
  async stage({ browser, base }) {
    const dir = outDir('shots/login');
    for (const [name, width, height] of [['wide', 1600, 900], ['user', 1180, 1000], ['short', 1440, 700]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      await page.goto(`${base}/login`);
      await page.waitForTimeout(900);
      // 마우스를 옮겨도 무대가 따라오지 않아야 한다.
      await page.mouse.move(width - 200, 150);
      await page.waitForTimeout(250);
      await page.screenshot({ path: `${dir}/size-${name}.png` });
      console.log('shot', name);
      await page.close();
    }
  },

  // 편집 화면이 좁을 때 격자와 코치 토글이 어떻게 되는지
  async edit({ browser, base, args }) {
    const width = Number(args[0] ?? 1200);
    const dir = outDir('shots/states');
    const page = await browser.newPage({ viewport: { width, height: 940 } });
    await login(page, base, 'student');
    // 편집 화면은 셸 밖 전체화면 라우트다. 세션은 localStorage 에 있어 goto 로도 남는다.
    await page.goto(`${base}/resume/r-demo-1/edit`);
    await page.waitForTimeout(1500);

    const grid = await page
      .locator('.resume-edit__body')
      .evaluate((el) => getComputedStyle(el).gridTemplateColumns)
      .catch(() => '없음');
    const toggle = await page.getByRole('button', { name: /AI 코치 (열기|접기)/ }).count();
    const coach = await page.locator('.resume-coach').count();
    console.log(`너비 ${width} | 토글버튼 ${toggle} | 코치패널 ${coach} | grid ${grid}`);

    if (toggle > 0) {
      await page.getByRole('button', { name: /AI 코치 열기/ }).click();
      await page.waitForTimeout(600);
      console.log(`   → 열고 나서: 코치패널 ${await page.locator('.resume-coach').count()}`);
    }
    await page.screenshot({ path: `${dir}/edit-${width}.png` });
  },
};

const [name, ...args] = process.argv.slice(2);
const job = jobs[name];
if (!job) {
  console.error(`할 일: ${Object.keys(jobs).join(', ')}`);
  console.error('예) node tools/shot.mjs all');
  process.exit(1);
}

const { base, stop } = await startPreview();
const browser = await chromium.launch();
try {
  await job({ browser, base, args });
} finally {
  await browser.close();
  stop();
}
process.exit(0);
