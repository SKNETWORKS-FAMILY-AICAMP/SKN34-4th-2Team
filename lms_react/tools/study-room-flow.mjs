// 공부방 구조 확인 — 학습실 요약 · 공부방 수업 카드(노트 + 복습 문제) · 노트 위 복습 링크 · 날짜 미리 고른 노트 만들기.
//
//   npm run build && node tools/study-room-flow.mjs

import { chromium } from 'playwright';
import { startPreview } from './preview.mjs';
const { base, stop } = await startPreview();
const b = await chromium.launch();
const page = await b.newPage({ viewport: { width: 1360, height: 1000 } });
const errors = []; page.on('pageerror', (e) => errors.push(e.message));
const say = (k, v) => console.log(`${k}: ${typeof v === 'string' ? v.replace(/\s+/g, ' ').trim() : JSON.stringify(v)}`);
const go = async (p) => { await page.evaluate((x) => { history.pushState({}, '', x); dispatchEvent(new PopStateEvent('popstate')); }, p); await page.waitForTimeout(700); };
await page.goto(`${base}/login`); await page.waitForTimeout(500);
await page.getByRole('button', { name: '빠른 로그인 (데모)' }).click();
await page.getByRole('button', { name: '학생', exact: true }).click();
const tour = page.locator('.tour-card').getByRole('button', { name: '다시 보지 않기' });
await tour.waitFor({ timeout: 4000 }).then(() => tour.click()).catch(() => {});
const dlg = page.locator('.dialog').getByRole('button', { name: '확인' });
await dlg.waitFor({ timeout: 1500 }).then(() => dlg.click()).catch(() => {});
await go('/study-room');
say('학습실 공부방 카드', await page.locator('.study-entry').first().innerText());
say('학습실에 복습 문제 영역', await page.locator('.practice-sets').count());
await page.screenshot({ path: 'tools/shots/study-room.png', clip: { x: 200, y: 0, width: 1160, height: 420 } });
await page.locator('.study-entry').first().getByRole('link', { name: '공부방 열기' }).click();
await page.waitForTimeout(700);
say('공부방 제목', await page.locator('.study-head__title').innerText());
say('카드', await page.locator('.practice-set').allInnerTexts().then((a) => a.map((x) => x.replace(/\s+/g, ' '))));
await page.screenshot({ path: 'tools/shots/study-notes.png', fullPage: true });
// 9/15 노트 → 복습 문제 링크
await page.locator('.lesson-day', { hasText: '영상 RAG' }).getByRole('link', { name: /노트/ }).click();
await page.waitForTimeout(700);
say('노트 위 복습 링크', await page.locator('.note-practice').innerText());
await page.screenshot({ path: 'tools/shots/study-note-link.png', clip: { x: 200, y: 0, width: 1160, height: 420 } });
await page.locator('.note-practice').getByRole('link', { name: '복습 문제 풀기' }).click();
await page.waitForTimeout(900);
say('연습장 위치', await page.locator('.py-crumbs').innerText());
// 9/14 노트 만들기 → 날짜 미리 선택
await go('/study-room/notes');
await page.locator('.lesson-day', { hasText: 'BLIP' }).getByRole('link', { name: '노트 만들기' }).click();
await page.waitForTimeout(700);
say('미리 고른 날짜', await page.locator('.study-scope-options .chip--on').innerText());
await page.getByRole('button', { name: '선택한 범위 정리하기' }).click();
await page.waitForTimeout(500);
say('만든 노트 위 복습 링크', await page.locator('.note-practice').innerText());
await go('/study-room/notes');
say('9/14 카드 노트 링크', await page.locator('.lesson-day', { hasText: 'BLIP' }).locator('.lesson-day__link').first().innerText());
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(400);
say('좁은 화면 넘침', await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth));
await page.screenshot({ path: 'tools/shots/study-notes-narrow.png', fullPage: true });
say('오류', errors);
await b.close(); await stop();
