// 설명서 캡처 — prepare-demo.py 로 만든 데모 웹 앱을 폰 · 태블릿 크기로 띄워 화면마다 찍는다. 사용법은 README.md
import { chromium } from 'playwright-core';
const only = process.argv[2];
import { mkdirSync } from 'fs';
mkdirSync('shots', { recursive: true });
const browser = await chromium.launch(process.env.CHROME ? { executablePath: process.env.CHROME } : {});
const BASE = process.env.DEMO_URL ?? 'http://127.0.0.1:8090/';
const UIDS = { student: 'demo-student-001', student3: 'demo-student-003', instructor: 'demo-instructor-001', admin: 'demo-admin-001' };

async function session(role, { size = [390, 844], tour = true, popups = false, login = true } = {}) {
  const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, deviceScaleFactor: 2, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const uid = UIDS[role];
  await ctx.addInitScript(([uid, tour, popups, login]) => {
    if (login) localStorage.setItem('demoUid', uid);
    if (tour) localStorage.setItem(`lms.tour.${uid}`, '1');
    if (popups) localStorage.setItem('demoPopups', '1');
  }, [uid, tour, popups, login]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log(role, 'pageerror:', e.message.slice(0, 200)));
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(1800);
  const ids = await page.evaluate(() => {
    try {
      const db = globalThis.__db();
      return JSON.parse(JSON.stringify({
        post: db.posts[0]?.id, note: db.studyNotes[0]?.id,
        exams: db.assessments.map((a) => ({ id: a.id, title: a.title, start: a.startDate, end: a.endDate, published: a.isPublished })),
        subs: db.assessmentSubmissions.map((s) => ({ id: s.id, a: s.assessmentId, u: s.userId })),
        form: db.formTasks.find((f) => f.kind !== 'external' && f.isPublished)?.id ?? db.formTasks[0]?.id,
        resume: db.resumes.find((r) => r.userId === 'demo-student-001' && r.isBaseResume)?.id ?? db.resumes[0]?.id,
        student2: 'demo-student-002',
      }));
    } catch (e) { return { err: String(e) }; }
  });
  return { ctx, page, ids };
}
async function go(page, path, wait = 1200) {
  await page.evaluate((p) => globalThis.__router.push(p), path);
  await page.waitForTimeout(wait);
}
async function shot(page, name) {
  await page.screenshot({ path: `shots/${name}.png` });
  console.log('shot', name);
}
async function tap(page, text, wait = 900) {
  await page.getByText(text, { exact: true }).first().click({ timeout: 4000 });
  await page.waitForTimeout(wait);
}

if (!only || only === 'student') {
  // 로그인 · 투어
  { const { ctx, page } = await session('student', { login: false }); await shot(page, 'st-login'); await ctx.close(); }
  { const { ctx, page } = await session('student', { tour: false }); await go(page, '/tour', 1500); await shot(page, 'st-tour'); await ctx.close(); }
  { const { ctx, page } = await session('student3'); await go(page, '/(student)/exams/a1/take', 1800); await shot(page, 'st-exam-take'); try { await tap(page, '다음', 600); } catch {} ; await ctx.close(); }
  { const { ctx, page } = await session('student', { popups: true }); await page.waitForTimeout(1500); await shot(page, 'st-popup'); try { await tap(page, '확인', 800); await tap(page, '확인', 800); } catch {} ; await go(page, '/(student)/alerts', 1200); try { await page.getByText('이력서 클리닉 신청 안내').first().click(); await page.waitForTimeout(800); } catch {} ; await shot(page, 'st-alerts'); await ctx.close(); }
  const { ctx, page, ids } = await session('student');
  console.log(JSON.stringify(ids).slice(0, 800));
  await shot(page, 'st-dashboard');
  
  await go(page, '/(student)/chat'); await shot(page, 'st-chat');
  try { await tap(page, '출결 기준', 4500); await shot(page, 'st-chat-answer'); } catch (e) { console.log('chat tap fail'); }
  await go(page, '/(student)/(tabs)/board'); await shot(page, 'st-board');
  try { await page.getByText(/^자유게시판/).first().click({ timeout: 4000 }); await page.waitForTimeout(1500); await shot(page, 'st-board-free'); } catch (e) { console.log('free tap fail', e.message.slice(0, 100)); }
  if (ids.post) { await go(page, `/(student)/post/${ids.post}`, 1500); await shot(page, 'st-post'); }
  await go(page, '/(student)/(tabs)/study'); await shot(page, 'st-study');
  await go(page, '/(student)/notes'); await shot(page, 'st-notes');
  if (ids.note) { await go(page, `/(student)/notes/${encodeURIComponent(ids.note)}`, 1800); await shot(page, 'st-note'); }
  await go(page, '/(student)/wrong'); await shot(page, 'st-wrong');
  await go(page, '/(student)/exams'); await shot(page, 'st-exams');
  const mineSub = ids.subs?.find((s) => s.u === 'demo-student-001');
  if (mineSub) { await go(page, `/(student)/exams/${mineSub.a}/result`, 1800); await shot(page, 'st-exam-result'); }
  await go(page, '/(student)/attendance', 1500); await shot(page, 'st-attendance');
  await go(page, '/(student)/seating', 1500); await shot(page, 'st-seating');
  await go(page, '/(student)/teams'); await shot(page, 'st-teams');
  await go(page, '/(student)/forms'); await shot(page, 'st-forms');
  if (ids.form) { await go(page, `/(student)/forms/${ids.form}`); await shot(page, 'st-form'); }
  await go(page, '/(student)/records', 1500); await shot(page, 'st-records');
  await go(page, '/(student)/records/new'); await shot(page, 'st-record-new');
  await go(page, '/(student)/records/form/blog'); await shot(page, 'st-record-form');
  await go(page, '/(student)/(tabs)/mileage'); await shot(page, 'st-mileage');
  await go(page, '/(student)/shop', 1500); await shot(page, 'st-shop');
  await go(page, '/(student)/cart'); await shot(page, 'st-cart');
  await go(page, '/(student)/quests'); await shot(page, 'st-quests');
  await go(page, '/(student)/resume'); await shot(page, 'st-resumes');
  if (ids.resume) { await go(page, `/(student)/resume/${ids.resume}`, 1800); await shot(page, 'st-resume-edit'); }
  await go(page, '/(student)/qual'); await shot(page, 'st-qual');
  await go(page, '/(student)/(tabs)/more'); await shot(page, 'st-more');
  await go(page, '/(student)/mypage'); await shot(page, 'st-mypage');
  await go(page, '/(student)/settings'); await shot(page, 'st-settings');
  await ctx.close();
  // 태블릿 대시보드
  { const { ctx, page } = await session('student', { size: [1194, 834] }); await shot(page, 'st-dashboard-pad'); await ctx.close(); }
}

if (!only || only === 'instructor') {
  const { ctx, page, ids } = await session('instructor');
  await shot(page, 'in-presence');
  { const p2 = await session('instructor', { size: [1194, 834] }); await shot(p2.page, 'in-presence-pad'); await p2.ctx.close(); }
  try { await page.getByLabel('메뉴').first().click({ timeout: 3000 }); await page.waitForTimeout(900); await shot(page, 'in-drawer'); await page.keyboard.press('Escape'); } catch (e) { console.log('drawer fail'); }
  await go(page, '/(instructor)/resumes'); await shot(page, 'in-resumes');
  await go(page, '/(instructor)/board'); await shot(page, 'in-board');
  await go(page, '/(instructor)/exams'); await shot(page, 'in-exams');
  const ex = ids.exams?.[0];
  if (ex) { await go(page, `/(instructor)/exams/${ex.id}`, 1500); await shot(page, 'in-exam-detail'); }
  await go(page, '/(instructor)/exams/new'); await shot(page, 'in-exam-new');
  const sub = ids.subs?.[0];
  if (sub) { await go(page, `/(instructor)/exams/${sub.a}/sub/${sub.id}`, 1500); await shot(page, 'in-grade'); }
  await go(page, '/(instructor)/curriculum'); await shot(page, 'in-curriculum');
  await go(page, '/(instructor)/sources', 1500); await shot(page, 'in-sources');
  await go(page, '/(instructor)/settings'); await shot(page, 'in-settings');
  await ctx.close();
}

if (!only || only === 'admin') {
  const { ctx, page, ids } = await session('admin');
  await shot(page, 'ad-dashboard');
  try { await page.getByLabel('메뉴').first().click({ timeout: 3000 }); await page.waitForTimeout(900); await shot(page, 'ad-drawer'); await page.keyboard.press('Escape'); } catch (e) { console.log('drawer fail'); }
  await go(page, '/(admin)/attendance/spot', 1800); await shot(page, 'ad-spot');
  await go(page, '/(admin)/attendance', 1500); await shot(page, 'ad-attendance');
  try { await page.getByText(/^점검 이력/).first().click({ timeout: 4000 }); await page.waitForTimeout(1200); await shot(page, 'ad-spot-history'); } catch (e) { console.log('history tap fail'); }
  await go(page, '/(admin)/cohorts'); await shot(page, 'ad-cohorts');
  await go(page, '/(admin)/students'); await shot(page, 'ad-students');
  await go(page, `/(admin)/people/${ids.student2}`); await shot(page, 'ad-person');
  await go(page, '/(admin)/counsel'); await shot(page, 'ad-counsel');
  await go(page, '/(admin)/rooms'); await shot(page, 'ad-rooms');
  await go(page, '/(admin)/exams'); await shot(page, 'ad-exams');
  await go(page, '/(admin)/records', 1500); await shot(page, 'ad-records');
  await go(page, '/(admin)/resumes'); await shot(page, 'ad-resumes');
  await go(page, '/(admin)/forms'); await shot(page, 'ad-forms');
  await go(page, '/(admin)/study'); await shot(page, 'ad-study');
  await go(page, '/(admin)/board'); await shot(page, 'ad-board');
  try { await page.getByText(/^예약 공지 \d/).first().click({ timeout: 4000 }); await page.waitForTimeout(1000); await shot(page, 'ad-scheduled'); } catch (e) { console.log('sched fail'); }
  await go(page, '/(admin)/alerts'); await shot(page, 'ad-alerts');
  await go(page, '/(admin)/mileage', 1500); await shot(page, 'ad-mileage');
  try { await tap(page, '조정', 1000); await shot(page, 'ad-mileage-adjust'); } catch (e) { console.log('adjust fail'); }
  await go(page, '/(admin)/quests', 1500); await shot(page, 'ad-quests');
  await go(page, '/(admin)/ai'); await shot(page, 'ad-ai');
  await go(page, '/(admin)/assistant'); await shot(page, 'ad-assistant');
  await go(page, '/(admin)/settings'); await shot(page, 'ad-settings');
  await ctx.close();
  { const p2 = await session('admin', { size: [1194, 834] }); await go(p2.page, '/(admin)/attendance/spot', 1800);
    for (const [seat, n] of [['3번', 1], ['7번', 1], ['9번', 1], ['12번', 1], ['21번', 1], ['15번', 2]]) { for (let i = 0; i < n; i++) { try { await p2.page.getByText(seat, { exact: true }).first().click({ timeout: 2000 }); await p2.page.waitForTimeout(250); } catch (e) { console.log('seat fail', seat); } } }
    try { await p2.page.getByText('외출', { exact: true }).first().click({ timeout: 2000 }); } catch (e) { console.log('reason fail'); }
    await p2.page.waitForTimeout(600); await shot(p2.page, 'ad-spot-pad'); await p2.ctx.close(); }
}
await browser.close();
