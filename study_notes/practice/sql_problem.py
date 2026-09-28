"""SQL 문제(sql_query) — 예제 테이블을 만들고 조회문 결과를 비교한다.

문제 하나는 「준비 스크립트(setup_sql) + 문제 문장 + 모범 조회문(reference_solution)」이다. 검증기(Pyodide)에서
준비 스크립트를 돌리고 모범 조회문을 실행해 결과 표를 얻는다. 그 표가 기대 결과(expected_stdout, JSON)다.

학생 브라우저는 연습장 SQL 셀과 같은 길로 채점한다 — 워커의 run_sql 로 [준비, 학생 조회문] 을 새 DB 에서
돌리고 결과 표를 기대 결과와 비교한다(lms_react/src/features/practice/sqlGrading.ts). 그래서 여기 값 표기
(`_cell`)와 MySQL 함수 보충(NOW · CONCAT · FIELD)은 워커(pythonWorker.ts 의 HELPER)와 같아야 한다.

DB 에는 새 종류를 넣을 수 없어서(practice_problems 의 kind CHECK 제약 — 스키마는 바꾸지 않는다)
code_write + packages ["sqlite3"] 로 저장하고 준비 스크립트는 hidden_tests 칸에 둔다(lms_api practice_service).
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

def _run(setup, query):
    conn = _connect()
    for stmt in _split(setup):
        conn.execute(stmt)
    statements = _split(query)
    if len(statements) != 1:
        raise ValueError(f"조회문이 {len(statements)}개 (하나여야 함)")
    cur = conn.execute(statements[0])
    if not cur.description:
        raise ValueError("조회 결과가 없는 문장")
    rows = cur.fetchall()
    print(_json.dumps({"columns": [d[0] for d in cur.description], "rows": [[_cell(v) for v in r] for r in rows]}, ensure_ascii=False))
'''


def harness_code(setup: str, query: str) -> str:
    """검증기에서 돌릴 파이썬 — 준비 스크립트 다음 조회문 하나를 돌려 결과 표를 JSON 한 줄로 찍는다."""
    return f"{HARNESS}\n_run({json.dumps(setup)}, {json.dumps(query)})\n"


def static_check(setup: str, query: str) -> str:
    """돌려 보기 전에 거를 이유. 비어 있으면 통과."""
    if not setup.strip():
        return "준비 스크립트가 비어 있음"
    if len(setup) > MAX_SETUP_CHARS:
        return f"준비 스크립트가 {MAX_SETUP_CHARS}자를 넘음"
    if not re.search(r"\bCREATE\s+TABLE\b", setup, re.I) or not re.search(r"\bINSERT\s+INTO\b", setup, re.I):
        return "준비 스크립트에 CREATE TABLE · INSERT 가 없음"
    if not QUERY_HEAD.match(query):
        return "모범답안이 SELECT 조회문이 아님"
    if NONDETERMINISTIC.search(query) or NONDETERMINISTIC.search(setup):
        return "실행할 때마다 결과가 달라지는 함수(NOW · RAND …)"
    return ""


def expected_table(stdout: str) -> dict | None:
    """검증기가 찍은 결과 표. 모양이 틀리면 None."""
    try:
        data = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("columns"), list) or not isinstance(data.get("rows"), list):
        return None
    return data


def judge_result(query: str, reference_stdout: str, starter_stdout: str | None) -> tuple[str, str]:
    """(기대 결과 JSON, 떨어진 이유). 이유가 비어 있으면 통과."""
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
    table["ordered"] = bool(ORDERED.search(query))
    return json.dumps(table, ensure_ascii=False), ""
