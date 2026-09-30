import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runWeb } from './web.mjs';

const PAGE = `<!doctype html><html><head><style>
  .menu { display: flex; justify-content: center; }
  #hero { position: absolute; }
</style></head><body>
  <ul class="menu"><li>홈</li><li>소개</li></ul>
  <a href="#top" target="_blank">링크</a>
  <div id="hero">히어로</div>
</body></html>`;

const CHECKS = [
  "check(css('.menu', 'display') === 'flex', '메뉴가 flex 컨테이너예요');",
  "check(css('.menu', 'justify-content') === 'center', '항목이 가운데 정렬돼야 해요');",
  "check(count('.menu li') === 2, '항목이 두 개 있어요');",
  "check(attr('a', 'target') === '_blank', '링크가 새 탭에서 열려요');",
].join('\n');

const job = (html, checks = CHECKS) => ({ id: 'w', kind: 'web', steps: [html, checks], timeoutMs: 3000 });
const checksOf = (r) => JSON.parse(r.stdout);

test('모든 검사를 통과하면 ok', () => {
  const r = runWeb(job(PAGE));
  assert.equal(r.ok, true);
  assert.deepEqual(checksOf(r).map((c) => c.ok), [true, true, true, true]);
});

test('하나라도 틀리면 ok 아님 — 검사마다 결과가 남는다', () => {
  const r = runWeb(job(PAGE.replace('justify-content: center', 'justify-content: left')));
  assert.equal(r.ok, false);
  assert.deepEqual(checksOf(r).map((c) => c.ok), [true, false, true, true]);
  assert.equal(checksOf(r)[1].message, '항목이 가운데 정렬돼야 해요');
});

test('던지는 줄은 그 검사만 실패하고 다음 줄로 간다', () => {
  const r = runWeb(job(PAGE, "check($('#없음').textContent === 'x', '없는 요소');\ncheck(has('#hero'), '히어로가 있어요');"));
  assert.deepEqual(checksOf(r), [{ message: '없는 요소', ok: false }, { message: '히어로가 있어요', ok: true }]);
});

test('HTML 안의 script 는 돌지 않는다', () => {
  const r = runWeb(job('<body><script>document.body.innerHTML = "<p id=hacked></p>"</script></body>', "check(!has('#hacked'), '스크립트가 안 돌았어요');"));
  assert.equal(r.ok, true);
});

test('끝나지 않는 검사는 시간 제한에 걸린다', () => {
  const r = runWeb(job(PAGE, "check((() => { while (true) {} })(), '무한 반복');"));
  assert.equal(r.ok, false);
  assert.equal(r.timedOut, true);
});

test('검사가 하나도 없으면 ok 아님', () => {
  assert.equal(runWeb(job(PAGE, '// 설명만')).ok, false);
});
