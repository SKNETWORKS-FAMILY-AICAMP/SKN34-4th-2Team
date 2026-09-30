import type { RunResult } from './pythonProtocol';
import { splitTests } from './practiceGrading';

/**
 * JS 코드 문제(packages ["js"]) — 학생 브라우저에서 돌린다. 학생 코드는 서버에서 돌리지 않는다.
 *
 * 출제 검증(practice_verifier/js.mjs)과 규칙이 같아야 한다 — 출제 때 통과한 문제가 여기서 다르게 나오지 않게.
 *   - 실행 환경(PRELUDE)은 js.mjs 와 같은 글이다. 고치면 둘 다(__tests__/jsRunner.test.ts 가 두 글을 견준다).
 *   - 단계는 한 스크립트로 이어 돈다(코드 + 테스트). 오류 단계는 코드만 먼저 돌려 본다.
 *   - 몇 번째 테스트에서 멈췄는지는 통과한 assert 수(__passed)로 안다.
 * 실행할 때마다 새 Web Worker — 이전 실행의 변수가 남지 않고, 끝나지 않으면 통째로 끝낸다.
 */
export const PRELUDE = `
var __out = [];
var __passed = 0;
function __format(v) {
  if (typeof v === 'string') return v;
  if (v === undefined) return 'undefined';
  if (typeof v === 'function') return '[Function: ' + (v.name || 'anonymous') + ']';
  if (v !== null && typeof v === 'object') { try { return JSON.stringify(v); } catch (e) { return String(v); } }
  return String(v);
}
var console = { log: function () { __out.push(Array.prototype.map.call(arguments, __format).join(' ')); } };
console.info = console.log; console.warn = console.log; console.error = console.log;
class AssertionError extends Error { constructor(m) { super(m); this.name = 'AssertionError'; } }
function assert(cond, message) { if (!cond) throw new AssertionError(message || '테스트가 통과하지 못했어요'); __passed += 1; }
`;

export interface JsOutcome {
  out: string;
  passed: number;
  error: { type: string; message: string } | null;
  timedOut: boolean;
}

/** 워커 안에서 — 받은 글을 전역 스크립트로 돌리고 출력 · 통과 수 · 오류를 돌려준다 */
const WORKER_SOURCE = `
self.onmessage = function (e) {
  var error = null;
  try { (0, eval)(e.data); } catch (err) { error = { type: String((err && err.name) || 'Error'), message: String((err && err.message) || err) }; }
  var out = '', passed = 0;
  try { out = (0, eval)("__out.join('\\\\n')"); passed = (0, eval)('__passed'); } catch (ignore) {}
  self.postMessage({ out: out, passed: passed, error: error });
};
`;

export type JsExecutor = (source: string, timeoutMs: number) => Promise<JsOutcome>;

/** Web Worker 로 한 번 돌린다 — 끝나지 않으면 timeoutMs 뒤에 워커를 끝낸다 */
export const workerExecutor: JsExecutor = (source, timeoutMs) =>
  new Promise((resolve) => {
    const url = URL.createObjectURL(new Blob([WORKER_SOURCE], { type: 'text/javascript' }));
    const worker = new Worker(url);
    const done = (outcome: JsOutcome) => {
      clearTimeout(timer);
      worker.terminate();
      URL.revokeObjectURL(url);
      resolve(outcome);
    };
    const timer = window.setTimeout(() => done({ out: '', passed: 0, error: null, timedOut: true }), timeoutMs);
    worker.onmessage = (e: MessageEvent<Omit<JsOutcome, 'timedOut'>>) => done({ ...e.data, timedOut: false });
    worker.onerror = (e) => {
      e.preventDefault();
      done({ out: '', passed: 0, error: { type: 'SyntaxError', message: e.message || '코드를 읽지 못했어요' }, timedOut: false });
    };
    worker.postMessage(source);
  });

/** steps — [학생 코드] 는 실행, [학생 코드, 숨긴 테스트] 는 채점 */
export async function runJs(steps: string[], timeoutMs = 3000, execute: JsExecutor = workerExecutor): Promise<RunResult> {
  const started = performance.now();
  const base = { value: null, table: null, images: [], stopped: false };
  let firstError: JsOutcome['error'] = null;
  if (steps.length > 1) {
    const alone = await execute(PRELUDE + steps[0], timeoutMs);
    if (alone.timedOut) return { ...base, ok: false, stdout: '', error: null, timedOut: true, ms: performance.now() - started };
    firstError = alone.error;
  }
  const whole = await execute(PRELUDE + steps.join('\n;\n'), timeoutMs);
  const ms = performance.now() - started;
  if (whole.timedOut) return { ...base, ok: false, stdout: '', error: null, timedOut: true, ms };
  const stdout = whole.out ? `${whole.out}\n` : '';
  if (!whole.error) return { ...base, ok: true, stdout, error: null, timedOut: false, ms };
  const step = firstError ? 0 : steps.length > 1 ? 1 : 0;
  // 테스트에서 멈췄으면 — 통과한 assert 다음 줄이 멈춘 테스트다
  const line = step === 1 ? (splitTests(steps[1])[whole.passed]?.line ?? null) : null;
  return { ...base, ok: false, stdout, error: { ...whole.error, step, line }, timedOut: false, ms };
}
