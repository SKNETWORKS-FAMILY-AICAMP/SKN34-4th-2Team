"""SQL 문제(sql_query) — 예제 테이블을 만들고 조회문 결과를 비교한다.

문제 하나는 「준비 스크립트(setup_sql) + 문제 문장 + 모범 조회문(reference_solution)」이다. 검증기(Pyodide)에서
준비 스크립트를 돌리고 모범 조회문을 실행해 결과 표를 얻는다. 그 표가 기대 결과(expected_stdout, JSON)다.

학생 브라우저는 연습장 SQL 셀과 같은 길로 채점한다 — 워커의 run_sql 로 [준비, 학생 조회문] 을 새 DB 에서
돌리고 결과 표를 기대 결과와 비교한다(lms_react/src/features/practice/sqlGrading.ts). 그래서 여기 값 표기
(`_cell`)와 MySQL 함수 보충(NOW · CONCAT · FIELD)은 워커(pythonWorker.ts 의 HELPER)와 같아야 한다.

DB 에는 새 종류를 넣을 수 없어서(practice_problems 의 kind CHECK 제약 — 스키마는 바꾸지 않는다)
code_write + packages ["sqlite3"] 로 저장하고 준비 스크립트는 hidden_tests 칸에 둔다(lms_api practice_service).

테이블 만들기 문제(check_sql 이 있는 것) — 학생이 CREATE TABLE 을 쓴다. [준비, 학생 CREATE TABLE, 확인 문장] 을
돌리고 확인 문장 끝 SELECT 의 표를 견준다. 확인 문장은 INSERT OR IGNORE 로 제약을 어기는 행을 넣어 본다 — 어긴 행은
조용히 빠지므로(NOT NULL · CHECK · UNIQUE · PRIMARY KEY) 표에 제약이 드러난다. DEFAULT 는 값을 빼고 넣어서,
외래 키는 부모 행을 지워 ON DELETE 로 본다(외래 키를 어기는 INSERT 는 OR IGNORE 로도 실행이 멈춘다).
확인 문장은 기대 결과 JSON 의 after 로 학생 화면에 간다(DB 칸을 늘리지 않는다). database 06-25(제약 조건 수업)에
「수업 테이블에서 조회」만 일곱 문제 나와 제약 조건을 하나도 묻지 못해서 생겼다(2026-10-06).
"""

from __future__ import annotations

import json
import re

# 결과 표가 이보다 크면 학생이 비교해 보기 어렵다
MAX_RESULT_ROWS = 20
MAX_SETUP_CHARS = 4000
# 실행할 때마다 결과가 달라진다
NONDETERMINISTIC = re.compile(r"\b(NOW|CURDATE|CURRENT_DATE|CURRENT_TIME|CURRENT_TIMESTAMP|RANDOM|RAND|SYSDATE|UUID)\b", re.I)
QUERY_HEAD = re.compile(r"^\s*(SELECT|WITH)\b", re.I)
ORDERED = re.compile(r"\bORDER\s+BY\b", re.I)

HARNESS = '''
import datetime as _dt, json as _json, math as _math, sqlite3 as _sqlite3

def _cell(v):
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return "NaN" if _math.isnan(v) else format(v, ".6g")
    return str(v)

def _connect():
    conn = _sqlite3.connect(":memory:", isolation_level=None)
    conn.create_function("NOW", 0, lambda: _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    conn.create_function("CURDATE", 0, lambda: _dt.date.today().isoformat())
    conn.create_function("CONCAT", -1, lambda *a: None if any(v is None for v in a) else "".join(str(v) for v in a))
    conn.create_function("FIELD", -1, lambda v, *a: next((i + 1 for i, x in enumerate(a) if x == v), 0))
    return conn

def _split(script):
    out, buf = [], ""
    for line in script.splitlines(keepends=True):
        buf += line
        if _sqlite3.complete_statement(buf):
            if buf.strip().rstrip(";").strip():
                out.append(buf.strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return out

def _run(setup, query, after=""):
    conn = _connect()
    if after:
        conn.execute("PRAGMA foreign_keys = ON")
    for stmt in _split(setup):
        conn.execute(stmt)
    statements = _split(query)
    if after:
        for stmt in statements:
            conn.execute(stmt)
        statements = _split(after)
        for stmt in statements[:-1]:
            conn.execute(stmt)
    elif len(statements) != 1:
        raise ValueError(f"조회문이 {len(statements)}개 (하나여야 함)")
    cur = conn.execute(statements[-1])
    if not cur.description:
        raise ValueError("조회 결과가 없는 문장")
    rows = cur.fetchall()
    print(_json.dumps({"columns": [d[0] for d in cur.description], "rows": [[_cell(v) for v in r] for r in rows]}, ensure_ascii=False))
'''


def harness_code(setup: str, query: str, after: str = "") -> str:
    """검증기에서 돌릴 파이썬 — 준비 스크립트 다음 조회문 하나를 돌려 결과 표를 JSON 한 줄로 찍는다.
    after 가 있으면 테이블 만들기 문제 — query(CREATE TABLE …)를 모두 돌린 뒤 확인 문장을 돌려 끝 SELECT 의 표를 찍는다."""
    return f"{HARNESS}\n_run({json.dumps(setup)}, {json.dumps(query)}, {json.dumps(after)})\n"


CREATE_TABLE = re.compile(r"\bCREATE\s+TABLE\b", re.I)


def _statements(script: str) -> list[str]:
    """문장 목록(주석 뺌). 문자열 안의 「;」 은 드물어서 줄 끝 「;」 으로만 나눈다."""
    plain = "\n".join(re.sub(r"--.*$", "", line) for line in script.splitlines())
    return [s.strip() for s in re.split(r";\s*(?:\n|$)", plain) if s.strip()]


def static_check(setup: str, query: str, after: str = "") -> str:
    """돌려 보기 전에 거를 이유. 비어 있으면 통과."""
    if len(setup) > MAX_SETUP_CHARS:
        return f"준비 스크립트가 {MAX_SETUP_CHARS}자를 넘음"
    if NONDETERMINISTIC.search(query) or NONDETERMINISTIC.search(setup) or NONDETERMINISTIC.search(after):
        return "실행할 때마다 결과가 달라지는 함수(NOW · RAND …)"
    if after:
        # 테이블 만들기 — 준비는 없어도 된다(외래 키가 가리킬 부모 테이블 정도)
        if not CREATE_TABLE.search(query):
            return "모범답안에 CREATE TABLE 이 없음"
        # 문장 머리로 본다 — ON DELETE SET NULL 의 DELETE 는 문장이 아니다
        if any(not re.match(r"CREATE\s+(TABLE|INDEX|UNIQUE\s+INDEX)\b", s, re.I) for s in _statements(query)):
            return "모범답안에 CREATE TABLE 말고 다른 문장이 있음(행 넣기는 확인 문장에서)"
        checks = _statements(after)
        if not checks or not QUERY_HEAD.match(checks[-1]):
            return "확인 문장의 마지막이 SELECT 조회문이 아님"
        if not any(re.match(r"INSERT\b", s, re.I) for s in checks):
            return "확인 문장에 INSERT 가 없음"
        if CREATE_TABLE.search(after):
            return "확인 문장에 CREATE TABLE 이 있음(학생이 만들 몫)"
        return ""
    if not setup.strip():
        return "준비 스크립트가 비어 있음"
    if not CREATE_TABLE.search(setup) or not re.search(r"\bINSERT\s+INTO\b", setup, re.I):
        return "준비 스크립트에 CREATE TABLE · INSERT 가 없음"
    if not QUERY_HEAD.match(query):
        return "모범답안이 SELECT 조회문이 아님"
    return ""


def _top_level_split(body: str) -> list[str]:
    """괄호 밖 쉼표로 나눈다 — CREATE TABLE ( … ) 안의 열 · 테이블 제약 하나씩."""
    parts, depth, buf = [], 0, ""
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(buf)
            buf = ""
        else:
            buf += ch
    parts.append(buf)
    return [p for p in parts if p.strip()]


def _drop_balanced(text: str, head: re.Pattern[str]) -> str:
    """head( … ) 를 괄호 짝을 맞춰 지운다 — CHECK (age >= 0 AND (age < 200))"""
    while (m := head.search(text)) is not None:
        depth, end = 0, len(text)
        for i in range(m.end() - 1, len(text)):
            depth += text[i] == "("
            depth -= text[i] == ")"
            if depth == 0:
                end = i + 1
                break
        text = text[: m.start()] + text[end:]
    return text


def loosened(ddl: str) -> str:
    """제약 조건(NOT NULL · UNIQUE · CHECK · DEFAULT · ON DELETE/UPDATE)을 뺀 CREATE TABLE.
    기본 키 · 외래 키 연결은 남긴다. 이걸로 돌려도 같은 표가 나오면 확인 문장이 제약을 시험하지 않는 것."""
    out = []
    for stmt in _statements(ddl):
        m = re.match(r"(CREATE\s+TABLE\s+[^(]+)\((.*)\)\s*$", stmt, re.I | re.S)
        if not m:
            out.append(stmt)
            continue
        cols = []
        for part in _top_level_split(m.group(2)):
            if re.match(r"\s*(CONSTRAINT\s+\w+\s+)?(UNIQUE|CHECK)\b", part, re.I):
                continue
            part = re.sub(r"\bCONSTRAINT\s+\w+\s+(?=CHECK|UNIQUE|DEFAULT|NOT)", "", part, flags=re.I)
            part = _drop_balanced(part, re.compile(r"\bCHECK\s*\(", re.I))
            part = re.sub(r"\bNOT\s+NULL\b|\bUNIQUE\b", "", part, flags=re.I)
            part = re.sub(r"\bDEFAULT\s+('(?:[^']|'')*'|\([^)]*\)|[^\s,]+)", "", part, flags=re.I)
            part = re.sub(r"\bON\s+(DELETE|UPDATE)\s+(SET\s+NULL|SET\s+DEFAULT|CASCADE|RESTRICT|NO\s+ACTION)", "", part, flags=re.I)
            cols.append(part)
        out.append(f"{m.group(1)}({','.join(cols)})")
    return ";\n".join(out) + ";"


def expected_table(stdout: str) -> dict | None:
    """검증기가 찍은 결과 표. 모양이 틀리면 None."""
    try:
        data = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("columns"), list) or not isinstance(data.get("rows"), list):
        return None
    return data


def judge_result(
    query: str, reference_stdout: str, starter_stdout: str | None, *, after: str = "", loose_stdout: str | None = None,
) -> tuple[str, str]:
    """(기대 결과 JSON, 떨어진 이유). 이유가 비어 있으면 통과.
    테이블 만들기(after 있음)는 loose_stdout — 제약을 뺀 CREATE TABLE 로 돌린 표 — 가 기대 결과와 달라야 한다."""
    table = expected_table(reference_stdout)
    if table is None:
        return "", "모범답안 결과를 읽지 못함"
    rows = table["rows"]
    if not rows:
        return "", "모범답안 결과가 0행 (준비 데이터와 조건이 맞지 않음)"
    if len(rows) > MAX_RESULT_ROWS:
        return "", f"모범답안 결과가 {len(rows)}행 — {MAX_RESULT_ROWS}행 이하로"
    if starter_stdout is not None and expected_table(starter_stdout) == table:
        return "", "시작 코드만으로 같은 결과가 나옴 (풀 거리가 없음)"
    if after and loose_stdout is not None and expected_table(loose_stdout) == table:
        return "", ("제약 조건을 모두 빼고 만든 테이블로도 같은 결과가 나옴 — 확인 문장이 제약을 시험하지 않음. "
                    "제약을 어기는 행을 INSERT OR IGNORE 로 넣어 빠지는 것이 결과에 보이게")
    table["ordered"] = bool(ORDERED.search(_statements(after)[-1] if after else query))
    if after:
        table["after"] = after.strip()
    return json.dumps(table, ensure_ascii=False), ""
