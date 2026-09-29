import { describe, expect, it } from 'vitest';

import type { RunResult, TableData } from '../pythonProtocol';
import { gradeSql, parseExpected, sqlProblemSteps } from '../sqlGrading';

const expected = parseExpected(
  JSON.stringify({ columns: ['menu_name', 'category_name'], rows: [['붕어빵초밥', '일식'], ['민트미역국', '한식']], ordered: true }),
)!;

function ran(rows: string[][], cols = 2): RunResult {
  const table: TableData = { columns: Array.from({ length: cols }, (_, i) => `c${i}`), index: [], indexName: '', rows, shape: [rows.length, cols] };
  return { ok: true, stdout: '', error: null, value: null, table, images: [], timedOut: false, stopped: false, ms: 1 };
}

describe('SQL 조회 문제 채점', () => {
  it('열 이름은 보지 않고 값 · 순서만 본다', () => {
    expect(gradeSql(expected, ran([['붕어빵초밥', '일식'], ['민트미역국', '한식']])).passed).toBe(true);
  });

  it('ORDER BY 가 있는 문제는 순서가 다르면 틀림 — 값은 맞다고 알려 준다', () => {
    const g = gradeSql(expected, ran([['민트미역국', '한식'], ['붕어빵초밥', '일식']]));
    expect(g).toMatchObject({ passed: false, headline: '값은 맞는데 순서가 달라요' });
  });

  it('ORDER BY 가 없는 문제는 순서를 가리지 않는다', () => {
    expect(gradeSql({ ...expected, ordered: false }, ran([['민트미역국', '한식'], ['붕어빵초밥', '일식']])).passed).toBe(true);
  });

  it('열 · 행 개수가 다르면 어디가 다른지 말한다', () => {
    expect(gradeSql(expected, ran([['붕어빵초밥'], ['민트미역국']], 1)).headline).toBe('열이 1개예요 — 2개가 나와야 해요');
    expect(gradeSql(expected, ran([['붕어빵초밥', '일식']])).headline).toBe('행이 1개예요 — 2개가 나와야 해요');
  });

  it('예제 테이블(0단계)과 내 조회문(1단계) 오류를 가른다', () => {
    const err = (step: number): RunResult => ({ ...ran([]), ok: false, table: null, error: { type: 'OperationalError', message: 'no such column: x', step, line: null } });
    expect(gradeSql(expected, err(0)).headline).toBe('예제 테이블을 만들지 못했어요');
    expect(gradeSql(expected, err(1))).toMatchObject({ headline: '내 조회문이 멈췄어요', detail: 'OperationalError: no such column: x' });
  });

  it('실행 단계 — 예제 테이블을 지우고 다시 만든 뒤, MySQL 문법을 고친 학생 조회문', () => {
    const { steps, notes } = sqlProblemSteps('CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT);\nINSERT INTO t VALUES (1, \'a\');', 'desc t;\nselect name from t');
    expect(JSON.parse(steps[0])).toEqual(['DROP TABLE IF EXISTS t', 'CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)', "INSERT INTO t VALUES (1, 'a')"]);
    expect(JSON.parse(steps[1])).toEqual(['PRAGMA table_info(t)', 'select name from t']);
    expect(notes).toEqual(['DESC → PRAGMA table_info']);
  });
});
