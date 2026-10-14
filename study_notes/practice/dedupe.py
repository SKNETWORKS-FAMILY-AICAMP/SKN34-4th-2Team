"""한 세트 안에서 겹치는 문제 찾기 — LLM 없이.

자동 출제 63세트(746문제)를 살펴보니(2026-10-05) 같은 함수를 종류만 바꿔 다시 낸 문제가 많았다.
「오분류 인덱스」를 빈칸 · 버그 고치기 · 출력으로 세 번, 「로그에서 WARN/ERROR 고르기」를 버그 고치기 · 처음부터로 두 번.
같은 날 exercise · question 노트북이 같은 주제를 다루거나, 한 파일을 여러 종류로 나눠 묻다 보니 생긴다.
database 는 「tb○에서 ○가 N인 행 조회」처럼 테이블 이름 · 값만 바꾼 같은 틀이 아홉 번.

겹침은 정답 코드가 거의 같거나, 같은 이름의 함수를 짜게 하거나, 주제가 같고 코드도 꽤 닮은 것.
출력 문제의 「다음 코드가 출력하는 값을 적으세요」처럼 안내 문장만 같은 것은 겹침이 아니다.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from study_notes.practice.models import PracticeProblem, fill_blanks

SAME_CODE = 0.85  # 정답 코드가 이만큼 닮으면 값만 바꾼 같은 문제
NEAR_CODE = 0.45  # 주제가 같은 편이면 이 정도 닮아도 같은 문제(같은 함수를 고치기 · 처음부터로)
SAME_TOPIC = 0.5
MIN_ANSWER = 15  # 답 조각이 이 글자(공백 뺌) 이상일 때만 다른 문제에 그대로 나오는지 본다
# 흔한 함수 이름은 같아도 겹침 근거로 안 쓴다
COMMON_NAMES = {"main", "solution", "solve", "f", "func", "fn", "test", "check", "run", "app", "index", "handler"}

_COMMENT = re.compile(r"(#|//|--)[^\n]*")
# 맨 바깥 함수만 — 메서드(__init__ 등) · 클래스 이름은 상속 문제끼리 늘 같아서 뺀다(python_basic 06-19)
_NAME = re.compile(r"^(?:async\s+)?(?:def|function)\s+([A-Za-z_]\w*)", re.MULTILINE)
_WORD = re.compile(r"[가-힣]+|[A-Za-z_]+|\d+")
# HTML 뼈대가 든 코드는 글자 비교를 안 한다 — CSS 한 줄만 다른 두 문제가 뼈대 때문에 85% 넘게 닮았다(web_client 09-23)
_HTML = re.compile(r"<\s*(!doctype|html|head|body|style|div|span|ul|form)\b", re.IGNORECASE)


def problem_code(p: PracticeProblem) -> str:
    """학생이 쓰거나 읽게 되는 「답이 들어간」 코드(주석 뺌, 줄 유지). 개념 · 웹 문제는 비교하지 않는다(뼈대 HTML 이 늘 닮아서)."""
    if p.kind == "code_blank":
        code = fill_blanks(p.starter_code, p.blank_answers)
    elif p.kind == "code_output":
        code = p.starter_code
    elif p.kind in ("code_fix", "code_write", "code_scratch", "sql_query"):
        code = p.reference_solution or p.starter_code
    else:
        return ""
    return "\n".join(" ".join(line.split()) for line in _COMMENT.sub("", code).splitlines() if line.strip())


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")}


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _names(code: str) -> set[str]:
    return {n for n in _NAME.findall(code) if n.lower() not in COMMON_NAMES and not n.startswith("__")}


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def answer_pieces(p: PracticeProblem) -> list[str]:
    """학생이 써 넣어야 하는 조각 — 빈칸 답, 버그 고치기에서 고친 줄. 짧은 것(x % 2 같은)은 흔해서 뺀다."""
    if p.kind == "code_blank":
        pieces = p.blank_answers
    elif p.kind == "code_fix":
        before = {_compact(line) for line in p.starter_code.splitlines()}
        pieces = [line for line in p.reference_solution.splitlines() if _compact(line) not in before]
    else:
        return []
    return [c for c in (_compact(_COMMENT.sub("", x)) for x in pieces) if len(c) >= MIN_ANSWER]


_SQL_WORDS = {
    "select", "from", "where", "and", "or", "not", "in", "is", "null", "like", "between", "group", "by", "having", "order",
    "asc", "desc", "join", "left", "right", "inner", "outer", "cross", "on", "as", "distinct", "limit", "offset", "union", "all",
    "exists", "case", "when", "then", "else", "end", "with", "count", "sum", "avg", "min", "max", "round", "create", "table",
    "primary", "key", "foreign", "references", "unique", "check", "default", "constraint", "delete", "update", "cascade", "set",
}


def sql_skeleton(sql: str) -> str:
    """테이블 · 열 이름과 값을 지운 SQL 뼈대 — 「tb2에서 fk가 20인 행」 · 「user_check에서 age가 25인 행」 은 같은 뼈대.
    database 06-25 다시 출제에서 이름이 다 달라 글자 비교로는 못 잡았다(2026-10-06)."""
    text = re.sub(r"'(?:[^']|'')*'|\b\d+(\.\d+)?\b", " v ", _COMMENT.sub("", sql)).strip().rstrip(";")
    tokens = re.findall(r"[A-Za-z_]\w*|[^\sA-Za-z_]", text)
    words = [w if w.lower() in _SQL_WORDS or w == "v" or not (w[0].isalpha() or w[0] == "_") else "x" for w in tokens]
    skeleton = " ".join(w.lower() for w in words)
    return re.sub(r"\b(x|v)( , (x|v))+", r"\1", re.sub(r"x \. x", "x", skeleton))


_CONSTRAINTS = {
    "NOT NULL": r"\bNOT\s+NULL\b", "UNIQUE": r"\bUNIQUE\b", "CHECK": r"\bCHECK\s*\(", "DEFAULT": r"\bDEFAULT\b",
    "FOREIGN KEY": r"\bREFERENCES\b", "ON DELETE": r"\bON\s+DELETE\b", "ON UPDATE": r"\bON\s+UPDATE\b",
}


def constraint_set(ddl: str) -> frozenset[str]:
    """CREATE TABLE 이 거는 제약 종류(기본 키는 늘 있어서 뺀다)"""
    return frozenset(name for name, pattern in _CONSTRAINTS.items() if re.search(pattern, ddl, re.I))


def _sql_overlap(a: PracticeProblem, b: PracticeProblem) -> str:
    """SQL 문제끼리 — 글자 비교는 안 맞는다. 테이블 만들기는 짧은 CREATE TABLE 이 늘 닮고 주제에 「제약 조건」이 늘 들어가
    DEFAULT 와 UNIQUE 를 묻는 두 문제를 겹친다고 봤다(database 06-25, 2026-10-06). 그래서 거는 제약 종류로 본다."""
    if bool(a.check_sql) != bool(b.check_sql):
        return ""
    if a.check_sql:
        same = constraint_set(a.reference_solution) == constraint_set(b.reference_solution)
        return "같은 제약 조건을 다시 물음" if same else ""
    return "SQL 뼈대가 같음(테이블 · 값만 바뀜)" if sql_skeleton(a.reference_solution) == sql_skeleton(b.reference_solution) else ""


def overlap_reason(a: PracticeProblem, b: PracticeProblem) -> str:
    """겹치면 그 까닭, 아니면 ''."""
    if " ".join(a.topic.split()) and " ".join(a.topic.split()) == " ".join(b.topic.split()):
        return "주제가 같음"
    if a.kind == b.kind == "sql_query":
        return _sql_overlap(a, b)
    code_a, code_b = problem_code(a), problem_code(b)
    if not (code_a and code_b):
        return ""
    if _names(code_a) & _names(code_b):
        return "같은 함수를 짜게 함"
    # 한 문제의 답이 다른 문제 코드에 그대로 — 출력 문제가 np.where(y_true != y_pred)[0] 를 보여 주고
    # 빈칸 문제가 바로 그걸 채우라 했다(dl 07-31 다시 출제, 2026-10-05)
    if any(piece in _compact(code_b) for piece in answer_pieces(a)) or any(piece in _compact(code_a) for piece in answer_pieces(b)):
        return "답이 다른 문제 코드에 그대로 나옴"
    if _HTML.search(code_a) or _HTML.search(code_b):
        return ""
    ratio = SequenceMatcher(None, code_a, code_b, autojunk=False).ratio()
    if ratio >= SAME_CODE:
        return "정답 코드가 거의 같음"
    if ratio >= NEAR_CODE and _jaccard(_words(a.topic), _words(b.topic)) >= SAME_TOPIC:
        return "주제가 같고 코드도 닮음"
    return ""


def split_overlaps(
    problems: list[PracticeProblem], kept: list[PracticeProblem] | None = None,
) -> tuple[list[PracticeProblem], list[tuple[PracticeProblem, PracticeProblem, str]]]:
    """앞에서부터 남기고, 이미 남긴 문제(kept 포함)와 겹치는 것은 뺀다. (남긴 것, [(뺀 문제, 겹친 문제, 까닭)])"""
    keep: list[PracticeProblem] = []
    pool = list(kept or [])
    dropped: list[tuple[PracticeProblem, PracticeProblem, str]] = []
    for p in problems:
        hit = next(((q, r) for q in pool if (r := overlap_reason(p, q))), None)
        if hit:
            dropped.append((p, hit[0], hit[1]))
            continue
        keep.append(p)
        pool.append(p)
    return keep, dropped
