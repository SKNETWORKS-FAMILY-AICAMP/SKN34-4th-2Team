import type { RunResult, TableData } from './pythonProtocol';
import { planSql, sqlSchema } from './sqlDialect';

/**
 * SQL 조회 문제(sql_query) 채점 — 화면과 떨어진 순수 함수.
 *
 * 문제에는 예제 테이블 스크립트(setupSql)와 기대 결과 표(expectedStdout, JSON)가 있다. 기대 결과는 서버 검증기가
 * 모범 조회문을 실제로 돌려 얻은 것이다(study_notes/practice/sql_problem.py). 브라우저는 워커의 SQL 실행(run_sql)으로
 * [예제 테이블, 학생 조회문] 을 돌려 나온 표를 기대 결과와 견준다. 값 표기는 두 쪽이 같다(NULL · 소수 6자리).
 *
 * - 열 이름은 보지 않는다(별칭은 자유). 열 개수 · 순서와 값만 본다.
 * - 모범 조회문에 ORDER BY 가 있을 때만 행 순서까지 본다.
 */

export interface ExpectedTable {
  columns: string[];
  rows: string[][];
  ordered: boolean;
  /**
   * 테이블 만들기 문제의 확인 문장 — 학생 CREATE TABLE 뒤에 돌린다(INSERT OR IGNORE … · 끝은 SELECT).
   * 제약을 어긴 행은 조용히 빠져 결과 표에 드러난다. 조회 문제는 ''.
   */
  after: string;
}

export function parseExpected(expectedStdout: string): ExpectedTable | null {
  try {
    const data = JSON.parse(expectedStdout) as Partial<ExpectedTable>;
    if (!Array.isArray(data.columns) || !Array.isArray(data.rows)) return null;
    return {
      columns: data.columns.map(String),
      rows: data.rows.map((r) => r.map(String)),
      ordered: Boolean(data.ordered),
      after: typeof data.after === 'string' ? data.after : '',
    };
  } catch {
    return null;
  }
}

/** 기대 결과를 결과 표 모양으로 — 문제에 「이런 결과가 나오게」로 보여 준다 */
export function expectedAsTable(expected: ExpectedTable): TableData {
  return {
    columns: expected.columns,
    index: expected.rows.map((_, i) => String(i)),
    indexName: '',
    rows: expected.rows,
    shape: [expected.rows.length, expected.columns.length],
  };
}

/**
 * 워커에 넘길 단계 — [예제 테이블, 학생 조회문] 각각 문장 목록 JSON.
 * 예제 테이블 앞에 DROP TABLE 을 붙인다: 연습장 세션에서 여러 번 실행해도 「이미 있는 테이블」 오류가 나지 않고,
 * 실행한 뒤에는 아래 SQL 셀에서 그 테이블을 조회해 볼 수 있다.
 */
export function sqlProblemSteps(setupSql: string, studentSql: string, after = ''): { steps: string[]; notes: string[] } {
  const setup = planSql(setupSql);
  const student = planSql(studentSql);
  if (!after) {
    const drops = Object.keys(sqlSchema([setupSql])).map((t) => `DROP TABLE IF EXISTS ${t}`);
    return {
      steps: [JSON.stringify([...drops, ...setup.statements]), JSON.stringify(student.statements)],
      notes: student.notes,
    };
  }
  // 테이블 만들기 — 학생이 만들 테이블도 먼저 지운다(다시 채점할 때 「이미 있는 테이블」이 안 나게).
  // 외래 키는 지울 때만 끄고, 학생 테이블 · 확인 문장은 켠 채로 돈다(ON DELETE 를 확인 문장이 본다)
  const names = new Set([...Object.keys(sqlSchema([setupSql, studentSql])), ...tablesIn(after)]);
  const drops = [...names].map((t) => `DROP TABLE IF EXISTS ${t}`);
  return {
    steps: [
      JSON.stringify(['PRAGMA foreign_keys = OFF', ...drops, 'PRAGMA foreign_keys = ON', ...setup.statements]),
      JSON.stringify(student.statements),
      JSON.stringify(planSql(after).statements),
    ],
    notes: student.notes,
  };
}

/** 확인 문장이 쓰는 테이블 이름 */
function tablesIn(sql: string): string[] {
  return [...sql.matchAll(/\b(?:INTO|FROM|UPDATE)\s+`?(\w+)`?/gi)].map((m) => m[1]);
}

export interface SqlGrade {
  passed: boolean;
  headline: string;
  detail: string;
}

const rowKey = (row: string[]) => JSON.stringify(row);

/** 실행 결과(마지막 단계의 표)를 기대 결과와 견준다 */
export function gradeSql(expected: ExpectedTable, result: RunResult): SqlGrade {
  if (result.timedOut) return { passed: false, headline: '시간 제한에 걸렸어요', detail: '' };
  if (result.stopped) return { passed: false, headline: '채점을 중단했어요', detail: '' };
  const ddl = expected.after !== '';
  const e = result.error;
  if (e) {
    const message = `${e.type}${e.message ? `: ${e.message}` : ''}`;
    if (e.step === 0) {
      return { passed: false, headline: '예제 테이블을 만들지 못했어요', detail: `${message} — 문제가 이상하면 「이상해요」로 알려 주세요.` };
    }
    if (ddl && e.step === 2) {
      // 부모 행을 지우거나 바꾸는 확인 문장이 외래 키에 막혔다 — ON DELETE · ON UPDATE 를 안 걸었을 때 난다
      const hint = /FOREIGN KEY/i.test(e.message)
        ? '부모 행을 지우거나 바꿀 때 자식 행을 어떻게 할지(ON DELETE · ON UPDATE)를 확인하세요.'
        : '테이블 이름 · 열 이름 · 열 순서가 문제와 같은지 확인하세요.';
      return { passed: false, headline: '확인 문장이 멈췄어요', detail: `${message} — ${hint}` };
    }
    return { passed: false, headline: ddl ? '내 CREATE TABLE 문이 멈췄어요' : '내 조회문이 멈췄어요', detail: message };
  }
  const table = result.table;
  if (!table) return { passed: false, headline: '조회 결과가 없어요', detail: '마지막 문장이 SELECT 조회문이어야 채점할 수 있어요.' };
  const [rows, cols] = table.shape;
  if (cols !== expected.columns.length) {
    return {
      passed: false,
      headline: `열이 ${cols}개예요 — ${expected.columns.length}개가 나와야 해요`,
      detail: ddl ? '문제에 적힌 열을 모두, 적힌 순서대로 만들었는지 확인하세요.' : '문제에 적힌 열만, 적힌 순서대로 골랐는지 확인하세요.',
    };
  }
  if (rows !== expected.rows.length) {
    return {
      passed: false,
      headline: `행이 ${rows}개예요 — ${expected.rows.length}개가 나와야 해요`,
      detail: ddl
        ? '확인 문장 중 빠져야 할 행이 들어갔거나, 들어가야 할 행이 빠졌어요. 제약 조건(비울 수 없음 · 범위 · 중복 · 외래 키)을 확인해 보세요.'
        : 'WHERE · JOIN 조건을 확인해 보세요.',
    };
  }
  if (expected.ordered) {
    const at = expected.rows.findIndex((row, i) => rowKey(row) !== rowKey(table.rows[i] ?? []));
    if (at >= 0) {
      const sameSet = [...expected.rows].map(rowKey).sort().join() === [...table.rows].map(rowKey).sort().join();
      return sameSet
        ? { passed: false, headline: '값은 맞는데 순서가 달라요', detail: 'ORDER BY 기준과 방향(ASC · DESC)을 확인해 보세요.' }
        : { passed: false, headline: `${at + 1}번째 행이 달라요`, detail: `기대 ${expected.rows[at].join(' | ')} · 내 결과 ${(table.rows[at] ?? []).join(' | ')}` };
    }
  } else {
    const want = expected.rows.map(rowKey).sort();
    const got = table.rows.map(rowKey).sort();
    if (want.join() !== got.join()) {
      return {
        passed: false,
        headline: '값이 다른 행이 있어요',
        detail: ddl ? '기본값(DEFAULT) · 외래 키의 ON DELETE 동작을 확인해 보세요.' : '조건과 고른 열을 확인해 보세요.',
      };
    }
  }
  return { passed: true, headline: '기대 결과와 같아요', detail: '' };
}
