import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runJs } from './js.mjs';
import { runWeb } from './web.mjs';

const js = (steps, timeoutMs = 3000) => runJs({ id: 'j', kind: 'js', steps, timeoutMs });

test('console.log 는 문자열 그대로, 배열 · 객체는 JSON, 여러 인자는 빈칸으로', () => {
  const r = js(['console.log(3 + "3"); console.log(3 - "3"); console.log([1, 2], {a: 1}); console.log(typeof NaN, undefined);']);
  assert.equal(r.ok, true);
  assert.equal(r.stdout, '33\n0\n[1,2] {"a":1}\nnumber undefined\n');
});

test('const 로 만든 함수를 테스트가 본다 — 코드와 테스트는 한 스크립트', () => {
  const r = js(['const add = (a, b) => a + b;', 'assert(add(1, 2) === 3, "더하기");']);
  assert.equal(r.ok, true);
});

test('테스트가 틀리면 AssertionError, 단계 1', () => {
  const r = js(['function add(a, b) { return a - b; }', 'assert(add(1, 2) === 3, "1 + 2 는 3");']);
  assert.equal(r.ok, false);
  assert.deepEqual(r.error, { type: 'AssertionError', message: '1 + 2 는 3', step: 1 });
});

test('코드에서 난 오류는 단계 0', () => {
  const r = js(['undefinedName();', 'assert(true);']);
  assert.equal(r.error.type, 'ReferenceError');
  assert.equal(r.error.step, 0);
});

test('무한 반복은 시간 제한', () => {
  const r = js(['while (true) {}'], 300);
  assert.equal(r.timedOut, true);
  assert.equal(r.ok, false);
});

test('바깥으로 나갈 길이 없다 — process · require · 문자열 eval', () => {
  assert.equal(js(['console.log(typeof process, typeof require)']).stdout, 'undefined undefined\n');
  assert.equal(js(['console.log.constructor("return process")()']).ok, false);
  assert.equal(js(['eval("1 + 1")']).ok, false);
});

test('web-js — 페이지 스크립트가 돈 뒤 click · type 로 검사한다', async () => {
  const html = `<input id="item"><button id="add">추가</button><ul id="list"></ul>
<script>
document.getElementById('add').addEventListener('click', () => {
  const li = document.createElement('li');
  li.textContent = document.getElementById('item').value;
  document.getElementById('list').appendChild(li);
});
</script>`;
  const checks = [
    "check(type('#item', '사과') && click('#add') && count('#list li') === 1, '누르면 항목이 하나 생겨요');",
    "check(text('#list li') === '사과', '입력한 글자가 들어가요');",
  ].join('\n');
  const r = await runWeb({ id: 'w', kind: 'web-js', steps: [html, checks], timeoutMs: 3000 });
  assert.equal(r.ok, true, r.stdout);
  const noScript = await runWeb({ id: 'w', kind: 'web', steps: [html, checks], timeoutMs: 3000 });
  assert.equal(noScript.ok, false, "kind 'web' 은 스크립트를 돌리지 않는다");
});
