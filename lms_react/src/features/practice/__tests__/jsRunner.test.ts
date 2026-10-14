import { describe, expect, it } from 'vitest';

import { runJs, type JsExecutor } from '../jsRunner';
import { splitTests } from '../practiceGrading';
import { gradingDocument, messageOf } from '../webScriptGrader';

/** 워커 대신 — 같은 글을 함수 하나로 돌린다(한 스크립트로 이어 도는 규칙은 같다) */
const fnExecutor: JsExecutor = async (source) => {
  const read = '\n;return [__out.join("\\n"), __passed];';
  try {
    const [out, passed] = new Function(source + read)() as [string, number];
    return { out, passed, error: null, timedOut: false };
  } catch (err) {
    const e = err as { name?: string; message?: string };
    return { out: '', passed: 0, error: { type: String(e.name), message: String(e.message) }, timedOut: false };
  }
};

describe('JS 실행 — 출제 검증기와 같은 규칙', () => {
  // 출제 검증기와 같은 글인지는 practice_verifier/sync.test.mjs 가 본다(여기선 앱 밖 파일을 못 읽는다)
  it('출력 모양 — 문자열 그대로, 배열 · 객체는 JSON', async () => {
    const r = await runJs(['console.log(3 + "3"); console.log([1, 2], {a: 1});'], 1000, fnExecutor);
    expect(r.ok).toBe(true);
    expect(r.stdout).toBe('33\n[1,2] {"a":1}\n');
  });

  it('const 로 만든 함수를 테스트가 본다', async () => {
    const r = await runJs(['const add = (a, b) => a + b;', "assert(add(1, 2) === 3, '1 + 2');"], 1000, fnExecutor);
    expect(r.ok).toBe(true);
  });

  it('멈춘 테스트 줄을 통과한 assert 수로 찾는다', async () => {
    const tests = "assert(1 === 1, '하나');\nassert(2 === 3, '둘');";
    const at = (passed: number): JsExecutor => async (source) =>
      source.includes('assert(2') ? { out: '', passed, error: { type: 'AssertionError', message: '둘' }, timedOut: false } : { out: '', passed: 0, error: null, timedOut: false };
    const r = await runJs(['const x = 1;', tests], 1000, at(1));
    expect(r.error).toMatchObject({ type: 'AssertionError', message: '둘', step: 1, line: 2 });
  });

  it('코드에서 난 오류는 단계 0', async () => {
    const r = await runJs(['nope();', "assert(true, 'x');"], 1000, fnExecutor);
    expect(r.error).toMatchObject({ type: 'ReferenceError', step: 0 });
  });

  it('끝나지 않으면 시간 제한으로 돌려준다', async () => {
    const r = await runJs(['while (true) {}'], 200, async () => ({ out: '', passed: 0, error: null, timedOut: true }));
    expect(r.timedOut).toBe(true);
    expect(r.ok).toBe(false);
  });
});

describe('스크립트 있는 웹 실습 채점 문서', () => {
  it('검사문 속 </script> 가 채점 스크립트를 닫지 못한다', () => {
    const doc = gradingDocument('<p>x</p>', "check(text('p') === '</script><b>', '닫는 태그');", 't1');
    expect(doc.match(/<\/script>/g)).toHaveLength(1);
  });

  it('JS assert 줄에서 조건만 보인다', () => {
    expect(splitTests("assert(add(1, 2) === 3, '1 + 2');")[0].expr).toBe('add(1, 2) === 3');
    expect(messageOf("check(has('#a'), '버튼이 있어요');")).toBe('버튼이 있어요');
  });
});
