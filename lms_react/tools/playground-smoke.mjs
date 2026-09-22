// 연습장 전체 동작 확인 — 자유 노트북 · 복습 세트 · 다시 풀 문제 · 학습실 진행률.
//
//   npm run build && node tools/playground-smoke.mjs > before.txt
//   (고친 뒤) node tools/playground-smoke.mjs > after.txt && diff before.txt after.txt
//
// 결과를 한 줄씩 찍는다. 고치기 전후로 diff 해서 동작이 바뀌지 않았는지 본다.
// 첫 실행은 Pyodide·pandas 를 CDN 에서 받아 1분쯤 걸린다.
import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';

const { base, stop } = await startPreview();
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1360, height: 1000 } });
const out = [];
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const say = (k, v) => out.push(`${k}: ${typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : JSON.stringify(v)}`);
const cells = () => page.locator('.py-nb-cell');

async function selectWord(cell, text) {
  const box = await cell.locator('.cm-content').evaluate((root, needle) => {
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let n = w.nextNode(); n; n = w.nextNode()) {
      const i = n.textContent.indexOf(needle);
      if (i >= 0) {
        const r = document.createRange();
        r.setStart(n, i + 1);
        r.setEnd(n, i + 2);
        const b = r.getBoundingClientRect();
        return { x: b.left + b.width / 2, y: b.top + b.height / 2 };
      }
    }
    return null;
  }, text);
  await page.mouse.dblclick(box.x, box.y);
}

async function go(path) {
  await page.evaluate((p) => {
    history.pushState({}, '', p);
    dispatchEvent(new PopStateEvent('popstate'));
  }, path);
  await page.waitForTimeout(800);
}

try {
  await page.goto(`${base}/login`);
  await page.waitForTimeout(500);
  await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
  await page.waitForTimeout(250);
  await page.getByRole('button', { name: '학생', exact: true }).click();
  const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
  await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
  // 로그인 뒤 알림 팝업이 뜨면 화면을 덮는다
  const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
  await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
  await page.waitForTimeout(400);

  // ── 자유 연습장 ──
  await go('/study-room/playground');
  say('A 제목', await page.locator('.study-head__title').innerText());
  say('A 셀 수', await cells().count());
  say('A 첫 셀 마크다운', await cells().nth(0).locator('.nb-md').innerText());
  await page.getByRole('button', { name: '모두 실행' }).click();
  await cells().nth(2).getByText('Out[').waitFor({ timeout: 90000 });
  say('A 셀1 출력', await cells().nth(1).locator('.py-nb-out').innerText());
  say('A 셀2 출력', await cells().nth(2).locator('.py-nb-out').innerText());
  say('A 실행 번호', [await cells().nth(1).locator('.py-nb-cell__prompt').innerText(), await cells().nth(2).locator('.py-nb-cell__prompt').innerText()]);

  await page.getByRole('button', { name: 'DataFrame 표' }).click();
  await page.waitForTimeout(300);
  await page.keyboard.press('Shift+Enter');
  await page.locator('.py-nb-table').waitFor({ timeout: 90000 });
  say('A 표', await page.locator('.py-nb-table__shape').innerText());
  say('A Shift+Enter 뒤 셀 수', await cells().count());

  await page.getByRole('button', { name: /입력값/ }).click();
  await page.getByRole('button', { name: 'input() 써 보기' }).click();
  await page.waitForTimeout(300);
  await page.keyboard.press('Control+Enter');
  // COOP/COEP 가 켜진 미리보기에서는 input() 이 셀 아래 입력칸으로 묻는다. 없으면 입력값 칸(민지 · 3)을 읽는다
  const field = page.locator('.py-input__field');
  for (const answer of ['민지', '3']) {
    const asked = await field.waitFor({ timeout: 30000 }).then(() => true).catch(() => false);
    if (!asked) break;
    await field.fill(answer);
    await field.press('Enter');
    await page.waitForTimeout(300);
  }
  await page.getByText('민지 3번째 프레임').waitFor({ timeout: 30000 });
  say('A input', 'ok');

  await page.getByRole('button', { name: '끝나지 않는 반복문' }).click();
  await page.waitForTimeout(300);
  await page.keyboard.press('Control+Enter');
  await page.waitForTimeout(1200);
  await page.locator('.py-toolbar').getByRole('button', { name: '중단' }).click();
  await page.getByText('실행을 중단했습니다').waitFor({ timeout: 5000 });
  say('A 중단 뒤 안내', await page.locator('.py-kernel-note').count() ? 'note' : 'none');

  // 새로고침 없이 다시 열어도 셀이 저장돼 있는지 (다른 화면 갔다 오기)
  const before = await cells().count();
  await go('/study-room');
  await go('/study-room/playground');
  say('A 저장된 셀 수 유지', (await cells().count()) === before);

  // ── 복습 세트 ──
  await go('/study-room/playground?set=ps-mm-0915');
  say('B 제목', await page.locator('.study-head__title').innerText());
  say('B 진행', await page.locator('.pb-progress').innerText());
  const q = (n) => page.locator('.py-nb-cell--problem').nth(n - 1);
  say('B 문제 셀 수', await page.locator('.py-nb-cell--problem').count());
  await q(1).locator('.pb__choice').first().click();
  await q(1).getByRole('button', { name: '정답 확인' }).click();
  say('B Q1', await q(1).locator('.pb__verdict strong').innerText());
  await selectWord(q(4), '__1__');
  await page.keyboard.type("r'_frame(\\d+)\\.jpg'");
  await q(4).getByRole('button', { name: /채점/ }).click();
  await q(4).locator('.pb__verdict--ok').waitFor({ timeout: 60000 });
  say('B Q4', await q(4).locator('.pb__verdict strong').innerText());
  await q(4).getByRole('button', { name: '실행', exact: true }).click();
  await q(4).locator('.py-nb-out').waitFor({ timeout: 30000 });
  const free = page.locator('.py-nb-cell--code').last();
  await free.locator('.cm-content').click();
  await page.keyboard.press('Control+End');
  await page.keyboard.type("extract_frame_no('x_frame00042.jpg')");
  await page.keyboard.press('Control+Enter');
  await free.locator('.py-nb-out__value').waitFor({ timeout: 30000 });
  say('B 자유 셀', await free.locator('.py-nb-out').innerText());
  say('B 진행 뒤', await page.locator('.pb-progress').innerText());

  // ── 다시 풀 문제 ──
  await go('/study-room/playground?set=retry');
  say('C 제목', await page.locator('.study-head__title').innerText());
  say('C 머리', (await page.locator('.pb__head').allInnerTexts()).map((t) => t.replace(/\s+/g, ' ')));
  const r1 = page.locator('.py-nb-cell--problem').first();
  await r1.locator('textarea').fill('1.12');
  await r1.getByRole('button', { name: '제출' }).click();
  say('C 다시 푼 결과', await r1.locator('.pb__verdict strong').innerText());
  say('C 목록 고정', await page.locator('.py-nb-cell--problem').count());

  await go('/study-room/notes');
  say('D 다시 풀 카드', await page.locator('.practice-set--retry .practice-set__title').innerText());
  say('D 9/14', await page.locator('.practice-set', { hasText: 'BLIP' }).locator('.lesson-day__link--main').innerText());
  say('D 9/15', await page.locator('.practice-set', { hasText: '영상 RAG' }).locator('.lesson-day__link--main').innerText());
} catch (e) {
  out.push('실패: ' + e.message.split('\n')[0]);
  await page.screenshot({ path: 'shots/playground-smoke-fail.png', fullPage: true });
} finally {
  if (errors.length) out.push('page errors: ' + errors.join(' | '));
  console.log(out.join('\n'));
  await browser.close();
  await stop();
}
