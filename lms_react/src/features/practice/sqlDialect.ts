/**
 * SQL 셀 — 수업(MySQL) 문법을 연습장의 SQLite 에 맞춘다.
 *
 * 연습장의 SQL 은 파이썬 워커 안 SQLite(sqlite3)로 돈다(pythonWorker.ts 의 run_sql). 수업 database 과목은
 * MySQL 로 가르치므로, 수업 파일을 그대로 붙여도 돌게 실행 전에 문장을 고친다. 2026-09-28 수업 파일로
 * 잰 것: 2일차 조회 파일 84문장 중 고치지 않으면 테이블부터 못 만들고, 고치면 대부분 돈다.
 *
 * - 데이터베이스 · 권한 문장(USE · CREATE DATABASE · GRANT …)은 건너뛴다 — 연습장에는 DB 가 하나뿐이다.
 * - `INT AUTO_INCREMENT` 는 SQLite 자동 번호(`INTEGER PRIMARY KEY AUTOINCREMENT`)로. 그냥 두면 번호가 비어
 *   JOIN 이 0행이 된다. 따로 적은 `PRIMARY KEY (열)` 제약은 뺀다.
 * - `COMMENT '…'` · `ENGINE=…` 같은 테이블 옵션 · `UNSIGNED` · `DROP … CASCADE` 는 뺀다.
 * - `DESC 표` → `PRAGMA table_info(표)`, `SHOW TABLES` → sqlite_master 조회, `START TRANSACTION` → `BEGIN`.
 * - NOW() · CURDATE() · CONCAT() · FIELD() 는 워커가 함수로 채운다(여기서는 그대로 둔다).
 */

export interface SqlPlan {
  /** 실행할 문장(주석을 뺀 것) */
  statements: string[];
  /** 무엇을 고쳤는지 — 셀 아래에 한 줄로 알린다 */
  notes: string[];
}

/** 주석을 빼고 `;` 로 문장을 가른다. 따옴표 안의 ; · -- · # 은 글자로 둔다 */
export function splitSql(sql: string): string[] {
  const out: string[] = [];
  let cur = '';
  let quote: string | null = null;
  for (let i = 0; i < sql.length; i++) {
    const ch = sql[i];
    const next = sql[i + 1];
    if (quote) {
      cur += ch;
      if (ch === quote) {
        if (next === quote) {
          cur += next;
          i += 1;
        } else quote = null;
      } else if (ch === '\\' && quote !== '`' && next !== undefined) {
        cur += next;
        i += 1;
      }
      continue;
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      quote = ch;
      cur += ch;
    } else if ((ch === '-' && next === '-') || ch === '#') {
      while (i < sql.length && sql[i] !== '\n') i += 1;
      cur += '\n';
    } else if (ch === '/' && next === '*') {
      const end = sql.indexOf('*/', i + 2);
      i = end < 0 ? sql.length : end + 1;
      cur += ' ';
    } else if (ch === ';') {
      if (cur.trim()) out.push(cur.trim());
      cur = '';
    } else cur += ch;
  }
  if (cur.trim()) out.push(cur.trim());
  return out;
}

const SKIP = /^(USE|CREATE\s+(DATABASE|SCHEMA|USER)|DROP\s+(DATABASE|SCHEMA|USER)|GRANT|REVOKE|FLUSH|SET\s+(NAMES|FOREIGN_KEY_CHECKS|SQL_MODE|GLOBAL|SESSION|@@))\b/i;

/** 한 문장을 SQLite 에 맞춘다. 건너뛸 문장이면 null. 고친 것은 notes 에 이름으로 모은다 */
export function mysqlToSqlite(statement: string, notes: Set<string>): string | null {
  let s = statement.trim();
  if (SKIP.test(s)) {
    notes.add(`${s.split(/\s+/).slice(0, 2).join(' ').toUpperCase()} 같은 데이터베이스·권한 문장은 건너뜀`);
    return null;
  }
  const desc = /^(DESC|DESCRIBE)\s+`?(\w+)`?$/i.exec(s);
  if (desc) {
    notes.add('DESC → PRAGMA table_info');
    return `PRAGMA table_info(${desc[2]})`;
  }
  if (/^SHOW\s+TABLES$/i.test(s)) {
    notes.add('SHOW TABLES → sqlite_master');
    return "SELECT name AS table_name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name";
  }
  if (/^START\s+TRANSACTION$/i.test(s)) return 'BEGIN';

  const replace = (pattern: RegExp, to: string, note: string) => {
    const next = s.replace(pattern, to);
    if (next !== s) notes.add(note);
    s = next;
  };
  if (/^CREATE\s+TABLE/i.test(s)) {
    // 자동 번호 열 — 열 이름을 모아 따로 적은 PRIMARY KEY 제약을 뺀다
    const auto = [...s.matchAll(/`?(\w+)`?\s+(?:BIG|SMALL|TINY|MEDIUM)?INT(?:EGER)?(?:\(\d+\))?(?:\s+UNSIGNED)?(?:\s+NOT\s+NULL)?\s+AUTO_INCREMENT/gi)].map((m) => m[1]);
    for (const col of auto) {
      s = s.replace(
        new RegExp(`(\`?${col}\`?)\\s+(?:BIG|SMALL|TINY|MEDIUM)?INT(?:EGER)?(?:\\(\\d+\\))?(?:\\s+UNSIGNED)?(?:\\s+NOT\\s+NULL)?\\s+AUTO_INCREMENT(?:\\s+PRIMARY\\s+KEY)?`, 'i'),
        '$1 INTEGER PRIMARY KEY AUTOINCREMENT',
      );
      s = s.replace(new RegExp(`,\\s*(?:CONSTRAINT\\s+\`?\\w+\`?\\s+)?PRIMARY\\s+KEY\\s*\\(\\s*\`?${col}\`?\\s*\\)`, 'i'), '');
    }
    if (auto.length) notes.add('AUTO_INCREMENT → SQLite 자동 번호');
    // 닫는 괄호 뒤 테이블 옵션(ENGINE · CHARSET · COMMENT …)
    replace(/\)\s*(?:(?:ENGINE|DEFAULT|CHARSET|CHARACTER\s+SET|COLLATE|COMMENT|AUTO_INCREMENT|ROW_FORMAT)\b[^)]*)$/i, ')', 'ENGINE 같은 테이블 옵션 뺌');
  }
  replace(/\s+COMMENT\s+'(?:[^']|'')*'/gi, '', "COMMENT '…' 뺌");
  replace(/\s+UNSIGNED\b/gi, '', 'UNSIGNED 뺌');
  replace(/\s+ON\s+UPDATE\s+CURRENT_TIMESTAMP/gi, '', 'ON UPDATE 뺌');
  replace(/\s+AUTO_INCREMENT\b/gi, '', 'AUTO_INCREMENT 뺌');
  if (/^DROP\s+TABLE/i.test(s)) replace(/\s+(CASCADE|RESTRICT)\s*$/i, '', 'DROP … CASCADE 뺌');
  return s;
}

/** SQL 셀의 글을 실행할 문장으로 */
export function planSql(source: string): SqlPlan {
  const notes = new Set<string>();
  const statements = splitSql(source)
    .map((s) => mysqlToSqlite(s, notes))
    .filter((s): s is string => s !== null && s.trim() !== '');
  return { statements, notes: [...notes] };
}

const NOT_COLUMN = /^(CONSTRAINT|PRIMARY|FOREIGN|UNIQUE|KEY|INDEX|CHECK|FULLTEXT)\b/i;

/**
 * 자동완성에 쓸 테이블 → 열 이름 — 노트북 SQL 셀들의 CREATE TABLE 을 읽는다(실행하지 않아도 된다).
 * 같은 테이블을 다시 만들면 뒤의 것을 쓴다.
 */
export function sqlSchema(sources: string[]): Record<string, string[]> {
  const schema: Record<string, string[]> = {};
  for (const statement of sources.flatMap(splitSql)) {
    const head = /^CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)`?\s*\(/i.exec(statement);
    if (!head) continue;
    // 바깥 괄호 안을 맨 위 쉼표로만 가른다 — VARCHAR(30) · DECIMAL(10, 2) 안의 쉼표는 두고
    const body = statement.slice(head[0].length);
    const parts: string[] = [];
    let depth = 0;
    let cur = '';
    for (const ch of body) {
      if (ch === '(') depth += 1;
      if (ch === ')') {
        if (depth === 0) break;
        depth -= 1;
      }
      if (ch === ',' && depth === 0) {
        parts.push(cur);
        cur = '';
      } else cur += ch;
    }
    parts.push(cur);
    schema[head[1]] = parts
      .map((p) => p.trim())
      .filter((p) => p !== '' && !NOT_COLUMN.test(p))
      .map((p) => /^`?(\w+)`?/.exec(p)?.[1])
      .filter((c): c is string => Boolean(c));
  }
  return schema;
}
