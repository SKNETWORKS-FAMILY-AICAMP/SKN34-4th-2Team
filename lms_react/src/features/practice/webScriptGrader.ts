import type { WebGrade } from '../../data/repository';

/**
 * 스크립트가 있는 웹 실습(packages ["web-js"]) 채점 — 학생 문서를 격리된 iframe 에서 돌리고 검사문을 돌린다.
 *
 * 학생 스크립트는 서버에서 돌리지 않는다(Node vm 은 완전한 격리가 아니다). 출제 검증은 서버 jsdom 이 같은 검사문으로 했다
 * (practice_verifier/web.mjs, kind 'web-js'). 검사 도우미(HELPERS)는 web.mjs 와 같은 글이다 — 고치면 둘 다.
 *
 * - iframe 은 sandbox="allow-scripts" 만 — 이 페이지(부모)의 쿠키 · 저장소 · DOM 에 닿지 못한다.
 * - load 뒤에 검사한다(서버 검증과 같은 때). 한 줄이 던지면 그 검사만 실패.
 * - timeoutMs 안에 답이 없으면(끝나지 않는 스크립트 등) 채점하지 못했다고 돌려준다.
 */
export const HELPERS = `
var __checks = [];
function $(s) { return document.querySelector(s); }
function $$(s) { return Array.prototype.slice.call(document.querySelectorAll(s)); }
function has(s) { return $(s) !== null; }
function count(s) { return $$(s).length; }
function text(s) { var el = $(s); return el ? el.textContent.replace(/\\s+/g, ' ').trim() : null; }
function attr(s, name) { var el = $(s); return el ? el.getAttribute(name) : null; }
function css(s, prop) { var el = $(s); return el ? getComputedStyle(el).getPropertyValue(prop).trim() : null; }
function check(cond, message) { __checks.push({ message: String(message), ok: Boolean(cond) }); }
function value(s) { var el = $(s); return el ? el.value : null; }
function style(s, prop) { var el = $(s); return el ? el.style.getPropertyValue(prop).trim() : null; }
function hasClass(s, name) { var el = $(s); return el ? el.classList.contains(name) : false; }
function click(s) { var el = $(s); if (el) el.click(); return true; }
function type(s, text) {
  var el = $(s); if (!el) return true;
  el.value = text;
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
}
`;

/** 검사 한 줄 끝의 글자열 — web.mjs 의 messageOf 와 같다 */
export function messageOf(line: string): string {
  const m = line.match(/(['"`])((?:\\.|(?!\1).)*)\1\s*\)\s*;?\s*$/);
  return m ? m[2] : line.slice(0, 80);
}

export function checkLines(checks: string): string[] {
  return checks
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('//'));
}

/** iframe 에 넣을 문서 — 학생 문서 뒤에 검사 스크립트를 붙인다 */
export function gradingDocument(html: string, checks: string, token: string): string {
  // </script> 가 검사문 글 안에서 스크립트를 닫지 않게
  const lines = JSON.stringify(checkLines(checks)).replace(/</g, '\\u003c');
  const messages = JSON.stringify(checkLines(checks).map(messageOf)).replace(/</g, '\\u003c');
  const runner = `
${HELPERS}
window.addEventListener('load', function () {
  setTimeout(function () {
    var lines = ${lines}, messages = ${messages};
    for (var i = 0; i < lines.length; i++) {
      var before = __checks.length;
      try { (0, eval)(lines[i]); } catch (e) { if (__checks.length === before) __checks.push({ message: messages[i], ok: false }); }
    }
    parent.postMessage({ webGrade: ${JSON.stringify(token)}, checks: __checks }, '*');
  }, 0);
});`;
  return `${html}\n<script>${runner}</script>`;
}

export function gradeWebScript(html: string, checks: string, timeoutMs = 4000): Promise<WebGrade> {
  return new Promise((resolve) => {
    const token = Math.random().toString(36).slice(2);
    const frame = document.createElement('iframe');
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:absolute;width:800px;height:600px;left:-10000px;top:0;border:0;';
    const finish = (grade: WebGrade) => {
      window.clearTimeout(timer);
      window.removeEventListener('message', onMessage);
      frame.remove();
      resolve(grade);
    };
    const onMessage = (e: MessageEvent) => {
      if (e.source !== frame.contentWindow || e.data?.webGrade !== token) return;
      const list = Array.isArray(e.data.checks) ? (e.data.checks as { message: string; ok: boolean }[]) : [];
      const checksOut = list.map((c) => ({ message: String(c.message), ok: Boolean(c.ok) }));
      finish({ passed: checksOut.length > 0 && checksOut.every((c) => c.ok), checks: checksOut, error: checksOut.length ? '' : '검사를 돌리지 못했어요.' });
    };
    const timer = window.setTimeout(
      () => finish({ passed: false, checks: [], error: '시간 안에 끝나지 않았어요. 끝나지 않는 반복문이 있는지 확인해 보세요.' }),
      timeoutMs,
    );
    window.addEventListener('message', onMessage);
    frame.srcdoc = gradingDocument(html, checks, token);
    document.body.appendChild(frame);
  });
}
