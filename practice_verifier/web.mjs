/**
 * 웹 실습(web_task) — 학생 HTML 을 jsdom 으로 읽고 검사문(check(…) 한 줄씩)을 돌린다.
 *
 * 작업: { id, kind: 'web', steps: [html, checks], timeoutMs }
 * 결과: { id, ok, stdout: JSON [{message, ok}], stdoutTruncated, error, timedOut, ms }
 *   ok — 검사가 하나 이상이고 모두 통과
 *
 * - HTML 안의 <script> 는 돌리지 않는다(runScripts: 'outside-only'). 검사문만 바깥에서 돈다.
 * - 검사문은 DB 에 있던 것(출제 때 우리가 검증한 것)만 온다 — 브라우저가 보낸 JS 가 아니다(lms/practice_web.py).
 *   그래도 한 줄마다 vm 시간 제한을 둔다.
 * - 한 줄이 던지면 그 검사만 실패로 적고 다음 줄로 간다. 메시지는 그 줄 끝의 글자열.
 * - 상속값(글자 크기)과 줄임 속성(list-style)은 jsdom 이 비워 둔다 — 출제 규칙(generate.py)이 그런 검사를 막는다.
 */
import vm from 'node:vm';
import { JSDOM, VirtualConsole } from 'jsdom';

const LINE_TIMEOUT_MS = 500;

// 검사문이 쓰는 도우미 — 이름 · 모양은 generate.py 의 web_task 안내와 같다
const HELPERS = `
var __checks = [];
function $(s) { return document.querySelector(s); }
function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function has(s) { return $(s) !== null; }
function count(s) { return $$(s).length; }
function text(s) { var el = $(s); return el ? el.textContent.replace(/\\s+/g, ' ').trim() : null; }
function attr(s, name) { var el = $(s); return el ? el.getAttribute(name) : null; }
function css(s, prop) { var el = $(s); return el ? getComputedStyle(el).getPropertyValue(prop).trim() : null; }
function check(cond, message) { __checks.push({ message: String(message), ok: Boolean(cond) }); }
`;

/** 검사 한 줄 끝의 글자열 — 던졌을 때 무엇을 보던 검사인지 보여 준다 */
function messageOf(line) {
  const m = line.match(/(['"`])((?:\\.|(?!\1).)*)\1\s*\)\s*;?\s*$/);
  return m ? m[2] : line.slice(0, 80);
}

export function runWeb(job) {
  const started = Date.now();
  const [html = '', checks = ''] = job.steps ?? [];
  const base = { id: job.id, stdoutTruncated: false, timedOut: false };
  let dom;
  try {
    dom = new JSDOM(html, { runScripts: 'outside-only', virtualConsole: new VirtualConsole() });
  } catch (err) {
    return { ...base, ok: false, stdout: '[]', error: { type: 'HTMLError', message: String(err?.message ?? err), step: 0 }, ms: Date.now() - started };
  }
  const context = dom.getInternalVMContext();
  vm.runInContext(HELPERS, context);
  const results = [];
  let timedOut = false;
  for (const raw of checks.split('\n')) {
    const line = raw.trim();
    if (!line || line.startsWith('//')) continue;
    const before = vm.runInContext('__checks.length', context);
    try {
      vm.runInContext(line, context, { timeout: job.timeoutMs ? Math.min(job.timeoutMs, LINE_TIMEOUT_MS) : LINE_TIMEOUT_MS });
    } catch (err) {
      if (String(err?.code ?? err?.message).includes('ERR_SCRIPT_EXECUTION_TIMEOUT')) timedOut = true;
      if (line.startsWith('check(')) results.push({ message: messageOf(line), ok: false });
      continue;
    }
    const added = JSON.parse(vm.runInContext('JSON.stringify(__checks.slice(' + before + '))', context));
    results.push(...added);
  }
  dom.window.close();
  const ok = results.length > 0 && results.every((r) => r.ok);
  return { ...base, ok, timedOut, stdout: JSON.stringify(results), error: ok ? null : { type: 'CheckFailed', message: `${results.filter((r) => !r.ok).length}개 검사 실패`, step: 1 }, ms: Date.now() - started };
}
