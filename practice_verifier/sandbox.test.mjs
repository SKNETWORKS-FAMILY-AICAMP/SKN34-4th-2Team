import assert from 'node:assert/strict';
import { after, test } from 'node:test';

import { Sandbox } from './sandbox.mjs';

const sandbox = new Sandbox();
after(() => sandbox.close());

test('print 출력을 그대로 모은다', async () => {
  const r = await sandbox.run({ id: 'a', steps: ['print("hi", end="!")\nprint({"a": 1})'] });
  assert.equal(r.ok, true);
  assert.equal(r.stdout, "hi!{'a': 1}\n");
});

test('steps 는 같은 변수 공간에서 이어서 돈다', async () => {
  const r = await sandbox.run({ id: 'b', steps: ['def add(a, b):\n    return a + b', 'assert add(2, 3) == 5\nprint("pass")'] });
  assert.equal(r.ok, true);
  assert.equal(r.stdout, 'pass\n');
});

test('작업마다 변수 공간이 새로 생긴다', async () => {
  await sandbox.run({ id: 'c1', steps: ['leftover = 1'] });
  const r = await sandbox.run({ id: 'c2', steps: ['print(leftover)'] });
  assert.equal(r.ok, false);
  assert.equal(r.error.type, 'NameError');
});

test('실패한 단계와 예외 이름을 알려 준다', async () => {
  const r = await sandbox.run({ id: 'd', steps: ['x = 1', 'assert x == 2, "x는 2여야 한다"'] });
  assert.equal(r.ok, false);
  assert.deepEqual(r.error, { type: 'AssertionError', message: 'x는 2여야 한다', step: 1 });
});

test('무한 루프는 시간 제한에 걸리고, 다음 작업은 새 워커로 돈다', async () => {
  const r = await sandbox.run({ id: 'e', steps: ['while True:\n    pass'], timeoutMs: 500 });
  assert.equal(r.timedOut, true);
  const next = await sandbox.run({ id: 'f', steps: ['print(1 + 1)'] });
  assert.equal(next.stdout, '2\n');
});

test('js·pyodide 모듈과 input()은 막는다', async () => {
  for (const code of ['import js', 'from pyodide.code import run_js', 'import pyodide_js']) {
    const r = await sandbox.run({ id: code, steps: [code] });
    assert.equal(r.error?.type, 'ImportError', code);
  }
  const r = await sandbox.run({ id: 'input', steps: ['input()'] });
  assert.equal(r.ok, false);
});

test('numpy 는 불러서 쓸 수 있다', async () => {
  const r = await sandbox.run({ id: 'np', steps: ['import numpy as np\nprint(np.arange(4).sum())'] });
  assert.equal(r.ok, true);
  assert.equal(r.stdout, '6\n');
});
