// 검증기와 학생 브라우저 워커(lms_react)가 같은 파이썬이어야 한다.
// 한쪽만 바뀌면 「여기서 통과한 문제가 학생 브라우저에서 안 도는」 일이 생긴다.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8');
const pkg = JSON.parse(read('./package.json'));
const verifierWorker = read('./worker.mjs');
const protocol = read('../lms_react/src/features/practice/pythonProtocol.ts');
const browserWorker = read('../lms_react/src/features/practice/pythonWorker.ts');

const blocked = (source) => /BLOCKED = \(([^)]*)\)/.exec(source)?.[1].replace(/\s+/g, '');

test('Pyodide 버전이 같다', () => {
  const browser = /PYODIDE_VERSION = '([^']+)'/.exec(protocol)?.[1];
  assert.equal(browser, pkg.dependencies.pyodide);
});

test('막는 모듈 목록이 같다', () => {
  assert.ok(blocked(verifierWorker));
  assert.equal(blocked(browserWorker), blocked(verifierWorker));
});

test('input() 은 둘 다 막는다 — 검증기는 오류, 브라우저는 입력값 칸이 비면 EOF', () => {
  assert.ok(verifierWorker.includes('setStdin({ error: true })'));
  assert.ok(browserWorker.includes('setStdin({ stdin:'));
});

// JS 코드 문제 · 스크립트 있는 웹 실습 — 출제 검증(여기)과 학생 브라우저 채점(lms_react)이 같은 실행 환경 · 검사 도우미를 쓴다
const templateOf = (source, name) => new RegExp(`const ${name} = \`([\\s\\S]*?)\`;`).exec(source)?.[1];

test('JS 실행 환경(PRELUDE)이 같다', () => {
  const here = templateOf(read('./js.mjs'), 'PRELUDE');
  assert.ok(here);
  assert.equal(templateOf(read('../lms_react/src/features/practice/jsRunner.ts'), 'PRELUDE'), here);
});

test('웹 검사 도우미(HELPERS)가 같다', () => {
  const here = templateOf(read('./web.mjs'), 'HELPERS');
  assert.ok(here);
  assert.equal(templateOf(read('../lms_react/src/features/practice/webScriptGrader.ts'), 'HELPERS'), here);
});
