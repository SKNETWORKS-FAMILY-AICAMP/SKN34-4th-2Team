import { describe, expect, it } from 'vitest';

import { planSql, splitSql, sqlSchema } from '../sqlDialect';

// 수업 database 2일차 「2_2 실습용 Script.sql」 앞부분 그대로
const LESSON = `use menudb;

-- 테이블 삭제
DROP TABLE IF EXISTS tbl_menu CASCADE;

CREATE TABLE IF NOT EXISTS tbl_menu
(
    menu_code    INT AUTO_INCREMENT COMMENT '메뉴코드',
    menu_name    VARCHAR(30) NOT NULL COMMENT '메뉴명',
    menu_price    INT NOT NULL COMMENT '메뉴가격',
    CONSTRAINT pk_menu_code PRIMARY KEY (menu_code)
) ENGINE=INNODB COMMENT '메뉴';

INSERT INTO tbl_menu VALUES (null, '열무김치라떼', 4500);
COMMIT;`;

describe('SQL 셀 — MySQL 문법을 SQLite 에 맞춘다', () => {
  it('주석을 빼고 ; 로 가르되 따옴표 안의 ; · -- · # 은 둔다', () => {
    expect(splitSql("select 'a;b' as x; -- 설명\n# 옛 주석\nselect \"--\" /* 막 */ ;")).toEqual(["select 'a;b' as x", 'select "--"']);
    expect(splitSql("select 'it''s; ok'")).toEqual(["select 'it''s; ok'"]);
  });

  it('수업 실습용 스크립트가 SQLite 문장이 된다', () => {
    const plan = planSql(LESSON);
    expect(plan.statements).toEqual([
      'DROP TABLE IF EXISTS tbl_menu',
      'CREATE TABLE IF NOT EXISTS tbl_menu\n(\n    menu_code INTEGER PRIMARY KEY AUTOINCREMENT,\n    menu_name    VARCHAR(30) NOT NULL,\n    menu_price    INT NOT NULL\n)',
      "INSERT INTO tbl_menu VALUES (null, '열무김치라떼', 4500)",
      'COMMIT',
    ]);
    expect(plan.notes).toContain('AUTO_INCREMENT → SQLite 자동 번호');
    expect(plan.notes.some((n) => n.startsWith('USE MENUDB'))).toBe(true);
  });

  it('열에 붙여 적은 PRIMARY KEY 도 자동 번호로', () => {
    const plan = planSql('CREATE TABLE t (id INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY, name VARCHAR(10)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
    expect(plan.statements).toEqual(['CREATE TABLE t (id INTEGER PRIMARY KEY AUTOINCREMENT, name VARCHAR(10))']);
  });

  it('DESC · SHOW TABLES · START TRANSACTION 을 SQLite 말로', () => {
    expect(planSql('desc tbl_menu; show tables; start transaction').statements).toEqual([
      'PRAGMA table_info(tbl_menu)',
      "SELECT name AS table_name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
      'BEGIN',
    ]);
  });

  it('고칠 것이 없으면 그대로 · 알림도 없다', () => {
    const sql = 'SELECT a.menu_name, b.category_name FROM tbl_menu a JOIN tbl_category b USING (category_code) ORDER BY 1 LIMIT 3';
    expect(planSql(sql)).toEqual({ statements: [sql], notes: [] });
  });
});

describe('SQL 자동완성 — 노트북에서 만든 테이블 · 열', () => {
  it('CREATE TABLE 에서 열 이름만 모은다(제약 · 괄호 안 쉼표는 빼고)', () => {
    expect(sqlSchema([LESSON, 'CREATE TABLE t (id INT, price DECIMAL(10, 2), PRIMARY KEY (id));', 'SELECT 1'])).toEqual({
      tbl_menu: ['menu_code', 'menu_name', 'menu_price'],
      t: ['id', 'price'],
    });
  });
});
