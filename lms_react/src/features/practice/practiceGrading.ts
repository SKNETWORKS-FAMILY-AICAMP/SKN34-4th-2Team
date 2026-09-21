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

export function outputMatches(answer: string, expected: string): boolean {
  return normalizeAnswer(answer) !== '' && normalizeAnswer(answer) === normalizeAnswer(expected);
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
  const assertion = e.type === 'AssertionError';
  return {
    passed: false,
    statuses,
    headline: assertion ? `테스트 ${failAt + 1}번이 맞지 않아요` : `테스트 ${failAt + 1}번에서 오류가 났어요`,
    detail: assertion ? '' : message,
  };
}
