"""웹 실습(web_task) 채점 — 학생이 쓴 HTML 을 AI 서버의 jsdom 에서 그 문제의 검사문으로 본다.

- 검사문(hidden_tests 의 check(…))은 DB 에서 꺼낸다. 브라우저가 보내면 서버에서 남의 JS 를 돌리게 된다.
- 학생 HTML 의 <script> 는 AI 서버가 돌리지 않는다(study_notes/practice/web_problem.py).
- 출제 검증도 같은 jsdom 으로 했다 — 브라우저 계산값(grid 의 fr → px 등)과 어긋나 통과한 문제가 떨어지는 일이 없다.
"""

from __future__ import annotations

from django.db import connection

from lms.practice_service import _problem_id, stored_kind
from lms.study_note_service import StudyNoteError, _call, _one
from lms.study_source_service import StudySourceError

GRADE_TIMEOUT = 30
MAX_HTML_CHARS = 60_000


def grade(user: dict, set_key: str, index: int, html: str) -> dict:
    """{passed, checks: [{message, ok}], error}"""
    if len(html) > MAX_HTML_CHARS:
        raise StudySourceError(413, "코드가 너무 길어요.")
    with connection.cursor() as cur:
        try:
            problem_id = _problem_id(cur, user, set_key, index)
        except KeyError as exc:
            raise StudySourceError(404, "문제를 찾을 수 없습니다.") from exc
        except PermissionError as exc:
            raise StudySourceError(403, "이 문제를 채점할 수 없습니다.") from exc
        except ValueError as exc:
            raise StudySourceError(422, "문제 번호가 올바르지 않습니다.") from exc
        cur.execute("SELECT kind, packages, hidden_tests FROM practice_problems WHERE id = %s", [problem_id])
        row = _one(cur)
    if not row or stored_kind(row) != "web_task":
        raise StudySourceError(422, "웹 실습 문제가 아닙니다.")
    try:
        return _call("/proxy/practice/web-grade", {"html": html, "checks": row["hidden_tests"] or ""}, GRADE_TIMEOUT)
    except StudyNoteError as exc:
        raise StudySourceError(exc.status, exc.detail) from exc
