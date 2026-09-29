import { describe, expect, it } from 'vitest';

import type { RunResult } from '../pythonProtocol';
import { gradeOutput, gradeReport, literalCompareScript, outputMatches, remainingBlanks, splitTests } from '../practiceGrading';

const TESTS = [
  'import numpy as np',
  "assert extract_frame_no('skiing_frame00030.jpg') == 30",
  "assert extract_frame_no('alpinist_frame00300.jpg') == 300, '세 자리'",
  "assert extract_frame_no('video_frame7.jpg') == 7",
].join('\n');

function result(partial: Partial<RunResult>): RunResult {
  return { ok: false, stdout: '', error: null, value: null, table: null, images: [], timedOut: false, stopped: false, ms: 1, ...partial };
}

describe('실습 채점', () => {
  it('출력 답은 줄 앞뒤 공백 · 앞뒤 빈 줄만 무시하고 나머지는 글자 그대로 본다', () => {
    expect(outputMatches('  4\n9  \n\n', '4\n9')).toBe(true);
    expect(outputMatches('4\n9', '4 9')).toBe(false); // print 두 번과 print(a, b) 는 다르다
    expect(outputMatches('a  b', 'a b')).toBe(false); // 줄 안의 띄어쓰기도 답이다
    expect(outputMatches('ab', 'a b')).toBe(false);
    expect(outputMatches('hello', 'HELLO')).toBe(false); // .upper() 문제
    expect(outputMatches('', '')).toBe(false);
  });

  it('글자가 다르면 워커에서 값으로 견준다', async () => {
    const said = (stdout: string) => async () => result({ ok: true, stdout });
    expect(await gradeOutput('[1,2]', '[1, 2]', said('SAME\n'))).toBe('value');
    expect(await gradeOutput('3', '3.0', said('DIFF\n'))).toBe('wrong');
    expect(await gradeOutput('12', '12', async () => { throw new Error('부르지 않는다'); })).toBe('exact');
    expect(await gradeOutput('[1,2]', '[1, 2]', async () => { throw new Error('워커 없음'); })).toBe('wrong');
    expect(await gradeOutput('[1,2]', '[1, 2]', async () => result({ ok: false, stdout: 'SAME' }))).toBe('wrong');
  });

  it('값 비교 스크립트에 답을 안전하게 넣는다', () => {
    const script = literalCompareScript('print("x")\n\'a\' """', '"b"');
    expect(script).toContain('ast.literal_eval');
    expect(script).not.toContain('exec(');
    expect(script).toContain(JSON.stringify(JSON.stringify(['print("x")', '\'a\' """'])));
  });

  it('남은 빈칸을 찾는다', () => {
    expect(remainingBlanks("re.search(__1__, f)\nint(m.group(__2__)) + __1__")).toEqual(['__1__', '__2__']);
    expect(remainingBlanks("re.search(r'_frame(\\d+)', f)")).toEqual([]);
  });

  it('assert 줄만 테스트로 센다', () => {
    const tests = splitTests(TESTS);
    expect(tests.map((t) => t.line)).toEqual([2, 3, 4]);
    expect(tests[1].expr).toBe("extract_frame_no('alpinist_frame00300.jpg') == 300");
  });

  it('통과하면 모두 pass', () => {
    const r = gradeReport(splitTests(TESTS), result({ ok: true }));
    expect(r.passed).toBe(true);
    expect(r.statuses).toEqual(['pass', 'pass', 'pass']);
  });

  it('두 번째 assert 에서 멈추면 앞은 통과, 뒤는 실행 안 함', () => {
    const r = gradeReport(splitTests(TESTS), result({ error: { type: 'AssertionError', message: '', step: 1, line: 3 } }));
    expect(r.statuses).toEqual(['pass', 'fail', 'skip']);
    expect(r.headline).toBe('테스트 2번이 맞지 않아요');
  });

  it('학생 코드에서 멈추면 테스트는 하나도 안 돈다', () => {
    const r = gradeReport(splitTests(TESTS), result({ error: { type: 'NameError', message: "name 're' is not defined", step: 0, line: 2 } }));
    expect(r.statuses).toEqual(['skip', 'skip', 'skip']);
    expect(r.headline).toBe('내 코드가 2번째 줄에서 멈췄어요');
    expect(r.detail).toContain('NameError');
  });

  it('테스트가 부르는 함수가 없으면 이름을 확인하라고 한다 — 처음부터 문제에서 흔하다', () => {
    const r = gradeReport(
      splitTests(TESTS),
      result({ error: { type: 'NameError', message: "name 'extract_frame_no' is not defined", step: 1, line: 2 } }),
    );
    expect(r.statuses).toEqual(['fail', 'skip', 'skip']);
    expect(r.headline).toBe('테스트 1번이 부르는 이름을 찾지 못했어요');
    expect(r.detail).toContain('문제에 적힌 이름');
  });

  it('시간 제한', () => {
    expect(gradeReport(splitTests(TESTS), result({ timedOut: true })).headline).toBe('시간 제한에 걸렸어요');
  });
});
