import type { RunResult } from './pythonProtocol';

/**
 * 실습 문제 채점 — 화면과 떨어진 순수 함수.
 *
 * 채점은 브라우저 워커에서 [학생 코드, 숨긴 테스트] 를 새 변수 공간에서 이어 돌린 결과로 한다.
 * 서버 검증기(study_notes/practice/verify.py)가 문제를 통과시킨 방식과 같다.
 */

/** 성취도평가 단답과 같은 비교 — 공백은 하나로, 대소문자는 가리지 않는다. */
export function normalizeAnswer(text: string): string {
  return text.replace(/\s+/g, ' ').trim().toLowerCase();
}

/**
 * 출력 예상(code_output) 답의 줄 — 줄 앞뒤 공백과 앞뒤 빈 줄만 뺀다. 눈에 안 보이는 것이라서다.
 * 줄 안의 공백 · 대소문자 · 줄바꿈은 본다. `print("a", "b")` 와 `print("a" + "b")` 의 차이가 문제의 요점일 수 있다.
 * (예전엔 공백 · 줄바꿈 · 대소문자를 모두 무시해서 `.upper()` 문제에 소문자로 적어도 맞았다)
 */
export function outputLines(text: string): string[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n').map((line) => line.trim());
  while (lines.length && lines[lines.length - 1] === '') lines.pop();
  while (lines.length && lines[0] === '') lines.shift();
  return lines;
}

/** 글자 그대로 같은지(outputLines 기준) */
export function outputMatches(answer: string, expected: string): boolean {
  const mine = outputLines(answer);
  return mine.length > 0 && mine.join('\n') === outputLines(expected).join('\n');
}

/**
 * 줄마다 파이썬 값으로 읽어(ast.literal_eval — 실행하지 않고 값 표기만 읽는다) repr 로 견주는 스크립트. 채점 워커에서 돈다.
 * 두 줄이 모두 값이면 표기만 다른 것(`[1,2]` · `[1, 2]`, `{'a':1}` · `{"a": 1}`)을 같게 본다. 3 과 3.0 은 repr 이 달라 다르다.
 * 값이 아닌 줄(`print("a b")` 의 `a b`)은 글자 그대로. 끝에 SAME 또는 DIFF 를 찍는다.
 */
export function literalCompareScript(answer: string, expected: string): string {
  // JSON 문자열 표기는 파이썬 문자열 표기로도 읽힌다
  const lit = (lines: string[]) => JSON.stringify(JSON.stringify(lines));
  return [
    'import ast, json',
    `_mine = json.loads(${lit(outputLines(answer))})`,
    `_want = json.loads(${lit(outputLines(expected))})`,
    'def _value(line):',
    '    try:',
    '        return repr(ast.literal_eval(line))',
    '    except Exception:',
    '        return None',
    'def _same(a, b):',
    '    return a == b or (_value(a) is not None and _value(a) == _value(b))',
    'print("SAME" if _mine and len(_mine) == len(_want) and all(_same(a, b) for a, b in zip(_mine, _want)) else "DIFF")',
  ].join('\n');
}

export type OutputVerdict = 'exact' | 'value' | 'wrong';

/** 출력 예상 채점 — 글자 그대로 같으면 exact, 표기만 다르고 값이 같으면 value, 아니면 wrong. 워커가 안 되면 글자 비교만 */
export async function gradeOutput(
  answer: string,
  expected: string,
  run: (steps: string[]) => Promise<RunResult>,
): Promise<OutputVerdict> {
  if (outputMatches(answer, expected)) return 'exact';
  if (outputLines(answer).length === 0) return 'wrong';
  try {
    const r = await run([literalCompareScript(answer, expected)]);
    return r.ok && r.stdout.trim().endsWith('SAME') ? 'value' : 'wrong';
  } catch {
    return 'wrong';
  }
}

/** 채우지 않은 빈칸 번호 */
export function remainingBlanks(code: string): string[] {
  return [...new Set(code.match(/__\d__/g) ?? [])];
}

export interface TestCase {
  /** 테스트 코드 안에서의 줄 번호(1부터) */
  line: number;
  /** 학생에게 보여 줄 식 — `assert` 뒤 */
  expr: string;
}

/** 숨긴 테스트에서 assert 줄마다 테스트 하나로 본다. 앞의 준비 줄(import, 샘플 데이터)은 세지 않는다. */
export function splitTests(hiddenTests: string): TestCase[] {
  return hiddenTests
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((text, i) => ({ text: text.trim(), line: i + 1 }))
    .filter((l) => l.text.startsWith('assert'))
    .map((l) => ({ line: l.line, expr: l.text.replace(/^assert\s+/, '').replace(/,\s*(['"]).*\1\s*$/, '') }));
}

export type TestStatus = 'pass' | 'fail' | 'skip';

export interface GradeReport {
  passed: boolean;
  statuses: TestStatus[];
  /** 학생에게 보여 줄 한 줄 요약 */
  headline: string;
  /** 오류 내용 (있으면) */
  detail: string;
}

/**
 * 실행 결과를 테스트별 상태로 바꾼다.
 * - 학생 코드(step 0)에서 멈추면 테스트는 하나도 못 돈 것
 * - 테스트(step 1)에서 멈추면 그 줄의 assert 가 실패, 앞은 통과, 뒤는 실행 안 함
 */
export function gradeReport(tests: TestCase[], result: RunResult): GradeReport {
  const skipAll = tests.map((): TestStatus => 'skip');
  if (result.ok) {
    return { passed: true, statuses: tests.map((): TestStatus => 'pass'), headline: `테스트 ${tests.length}개 모두 통과`, detail: '' };
  }
  if (result.timedOut) {
    return { passed: false, statuses: skipAll, headline: '시간 제한에 걸렸어요', detail: '반복문이 끝나는지 확인해 보세요. 끝나지 않는 코드는 채점할 수 없습니다.' };
  }
  if (result.stopped) {
    return { passed: false, statuses: skipAll, headline: '채점을 중단했어요', detail: '' };
  }
  const e = result.error;
  const message = e ? `${e.type}${e.message ? `: ${e.message}` : ''}` : '알 수 없는 오류';
  if (!e || e.step !== 1) {
    const where = e?.line ? `${e.line}번째 줄에서 ` : '';
    return { passed: false, statuses: skipAll, headline: `내 코드가 ${where}멈췄어요`, detail: message };
  }
  const failAt = e.line === null ? -1 : tests.findIndex((t) => t.line >= e.line!);
  const statuses = tests.map((_, i): TestStatus => {
    if (failAt < 0) return 'skip';
    if (i < failAt) return 'pass';
    return i === failAt ? 'fail' : 'skip';
  });
  if (failAt < 0) return { passed: false, statuses, headline: '테스트 준비 중에 멈췄어요', detail: message };
  // 처음부터 문제에서 흔하다 — 함수를 안 만들었거나 이름을 다르게 지었다
  if (e.type === 'NameError') {
    return {
      passed: false,
      statuses,
      headline: `테스트 ${failAt + 1}번이 부르는 이름을 찾지 못했어요`,
      detail: `${message} — 문제에 적힌 이름 그대로 만들었는지 확인하세요.`,
    };
  }
  const assertion = e.type === 'AssertionError';
  return {
    passed: false,
    statuses,
    headline: assertion ? `테스트 ${failAt + 1}번이 맞지 않아요` : `테스트 ${failAt + 1}번에서 오류가 났어요`,
    detail: assertion ? '' : message,
  };
}
