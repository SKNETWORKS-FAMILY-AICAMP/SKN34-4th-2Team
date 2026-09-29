// 캡처·탐색이 같이 쓰는 로그인과 화면 이동.
import { chromium } from 'playwright';

export const ROLE_LABEL = { student: '학생', instructor: '강사', admin: '관리자' };
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function launch() {
  return chromium.launch();
}

/// 투어 말풍선과 로그인 알림 팝업을 닫는다.
export async function closeOverlays(page) {
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  if (await tour.count()) {
    await tour.click();
    await sleep(400);
  }
  const confirm = page.locator('.dialog').getByRole('button', { name: '확인', exact: true });
  if (await confirm.count()) {
    await confirm.first().click();
    await sleep(300);
  }
}

/// 빠른 로그인(데모). tourShot 이 있으면 투어가 뜬 첫 화면을 찍고 나서 닫는다.
export async function login(page, base, role, { tourShot } = {}) {
  await page.goto(`${base}/login`);
  await sleep(600);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await sleep(250);
  await page.getByRole('button', { name: ROLE_LABEL[role], exact: true }).click();
  await sleep(1600);
  if (tourShot) await page.screenshot({ path: tourShot });
  await closeOverlays(page);
}

/// 새로고침 없이 앱 안에서 이동한다(데모 데이터는 메모리에 있어 새로고침하면 처음으로 돌아간다).
export async function go(page, route, settle = 900) {
  await page.evaluate((r) => {
    window.history.pushState({}, '', r);
    window.dispatchEvent(new PopStateEvent('popstate'));
  }, route);
  await sleep(settle);
  await page.evaluate(() => window.scrollTo(0, 0));
}
