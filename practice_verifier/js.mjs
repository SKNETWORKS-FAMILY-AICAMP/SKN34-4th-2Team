/**
 * JS 코드 문제(packages ["js"]) — 출제 때 LLM 이 쓴 코드(시작 코드 · 모범답안 · 숨긴 테스트)를 돌려 본다.
 *
 * 작업: { id, kind: 'js', steps: [code, tests?], timeoutMs }
 * 결과: { id, ok, stdout, stdoutTruncated, error: {type, message, step} | null, timedOut, ms }
 *
 * 학생 브라우저(lms_react/src/features/practice/jsRunner.ts)와 규칙이 같아야 한다 — 출제 때 통과한 문제가
 * 학생 채점에서 다르게 나오지 않게.
 *   - console.log 는 인자마다 formatValue 로 바꿔 빈칸으로 잇는다(문자열은 그대로, 배열 · 객체는 JSON).
 *   - 단계는 한 스크립트로 이어 돈다(코드 + 테스트). const/let 으로 만든 함수를 테스트가 볼 수 있다.
 *   - 오류가 어느 단계에서 났는지는 코드만 먼저 돌려 본다(그때 나면 0, 아니면 1).
 *   - assert(조건, 문장) — 거짓이면 AssertionError.
 * 바깥(Node) 객체는 하나도 넘기지 않는다. console · assert 도 안에서 만든다 — 넘긴 함수의 constructor 로
 * process 에 닿는 길을 막는다. setTimeout · require · process 는 없다.
 */
import vm from 'node:vm';

const MAX_STDOUT_CHARS = 20_000;

// 실행 환경 — 브라우저 jsRunner.ts 의 PRELUDE 와 같은 글이다(고치면 둘 다)
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

function runScript(code, timeoutMs) {
  const context = vm.createContext(Object.create(null), { microtaskMode: 'afterEvaluate', codeGeneration: { strings: false, wasm: false } });
  vm.runInContext(PRELUDE, context);
  let error = null;
  let timedOut = false;
  try {
    vm.runInContext(code, context, { timeout: timeoutMs });
  } catch (err) {
    if (err?.code === 'ERR_SCRIPT_EXECUTION_TIMEOUT') timedOut = true;
    else error = { type: String(err?.name ?? 'Error'), message: String(err?.message ?? err) };
  }
  let stdout = '';
  try {
    stdout = vm.runInContext("__out.join('\\n')", context, { timeout: 200 });
  } catch {
    stdout = '';
  }
  if (stdout) stdout += '\n';
  return { error, timedOut, stdout };
}

export function runJs(job) {
  const started = Date.now();
  const steps = job.steps ?? [];
  const timeoutMs = job.timeoutMs ?? 3000;
  let firstStepError = null;
  if (steps.length > 1) {
    const alone = runScript(steps[0], timeoutMs);
    if (alone.timedOut) {
      return { id: job.id, ok: false, stdout: '', stdoutTruncated: false, error: null, timedOut: true, ms: Date.now() - started };
    }
    firstStepError = alone.error;
  }
  const whole = runScript(steps.join('\n;\n'), timeoutMs);
  const truncated = whole.stdout.length > MAX_STDOUT_CHARS;
  const error = whole.error ? { ...whole.error, step: firstStepError ? 0 : steps.length > 1 ? 1 : 0 } : null;
  return {
    id: job.id,
    ok: !whole.error && !whole.timedOut,
    stdout: truncated ? whole.stdout.slice(0, MAX_STDOUT_CHARS) : whole.stdout,
    stdoutTruncated: truncated,
    error,
    timedOut: whole.timedOut,
    ms: Date.now() - started,
  };
}
