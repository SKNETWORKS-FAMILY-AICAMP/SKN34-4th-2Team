"""연습장 튜터 — 학생 · 문제를 확인하고, 힌트 단계와 대화를 기억하며 AI 서버(/proxy/tutor)에 묻는다.

- 문제 셀(mode=problem): 세트 · 문제 번호로 문제를 읽어 모범답안 · 숨긴 테스트 · 시도 수를 붙인다(브라우저로는 안 간다).
  힌트 단계는 여기서 정한다 — 「힌트 더」를 눌러야 오른다. 학생이 글로 졸라도 안 오른다.
  「정답 알려 줘」는 LLM 없이 지금 규칙대로 답한다(통과했거나 2번 틀리면 문제 아래 「모범답안 보기」).
- 일반 셀(mode=cell): 코드 · 오류 설명. 대화는 셀 하나로 이어진다.
- 횟수 한도는 없다. 쓸데없는 질문만 거른다 — 잡담은 AI 서버가 LLM 없이 돌려보내고,
  돌려보낸 답(offtopic)이 최근 OFFTOPIC_WINDOW 안에 OFFTOPIC_STREAK 번 이어지면 여기서 LLM 을 부르지 않는다.
- 대화는 study_tutor_turns — 튜터 창을 다시 열면 이어 보이고, 나중에 한도가 필요한지 볼 근거가 된다.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta

from django.db import connection, transaction

from lms.practice_service import stored_kind
from lms.study_note_service import StudyNoteError, _call, _dicts, _one
from lms.study_source_service import StudySourceError

TIMEOUT = 90
HISTORY = 6
REVEAL_AFTER_TRIES = 2  # 화면(ProblemCell)의 REVEAL_AFTER_TRIES 와 같다
OFFTOPIC_STREAK = 3
OFFTOPIC_WINDOW = timedelta(minutes=10)
STREAK_REPLY = "이 창은 문제와 코드에 대한 질문만 받아요. 막힌 줄이나 오류를 물어봐 주세요."
ACTIONS = ("ask", "more", "answer")
# 잡담이 이어져 LLM 을 멈춘 동안에도 이런 질문은 받는다 — 막는 건 잡담이지 공부가 아니다
ON_TOPIC = re.compile(
    r"오류|에러|코드|줄|함수|변수|리스트|딕셔너리|반복|조건|클래스|모듈|설명|힌트|정답|채점|테스트|문제|왜|어떻게|무슨 뜻|뭐가 틀|"
    # 웹 실습 · JS · SQL 문제도 연습장에 있다
    r"태그|속성|선택자|요소|이벤트|스타일|배열|객체|쿼리|테이블|"
    r"html|css|javascript|js|dom|sql|select|const|let|function|console|"
    r"error|exception|def |return|import|print|python|[()\[\]=:.<>{}]",
    re.IGNORECASE,
)
# 답을 한 번 내면 정답 · 해설이 바로 보이는 문제 — 「모범답안 보기」 단추가 없다(ProblemCell 의 canReveal 은 모범답안이 있을 때만)
ANSWER_ON_SUBMIT = {
    "concept": "보기를 골라 「정답 확인」을 누르면 정답과 해설이 바로 나와요. 먼저 보기마다 맞는지 하나씩 따져 볼까요?",
    "code_output": "답을 적어 「제출」하면 실제 출력과 해설이 나와요. 제출 뒤에는 「실행해서 확인」으로 직접 돌려 볼 수도 있어요.",
}


def locked_reply(problem: dict, level: int | None) -> str:
    """「정답 알려 줘」 — 튜터는 정답을 주지 않고, 문제 셀에서 정답을 보는 길을 알려 준다"""
    kind = stored_kind(problem)
    if kind in ANSWER_ON_SUBMIT:
        if answer_revealed(problem):
            return "정답과 해설은 문제 아래에 이미 나와 있어요. 헷갈리는 부분을 물어보면 왜 그런지 해설해 줄게요."
        return ANSWER_ON_SUBMIT[kind]
    if problem["passed"] or problem["tries"] >= REVEAL_AFTER_TRIES:
        return "모범답안은 문제 아래 「모범답안 보기」에서 볼 수 있어요. 보기 전에 한 번만 더 고쳐 채점해 보는 건 어때요?"
    return (f"모범답안은 {REVEAL_AFTER_TRIES}번 채점해 본 뒤에 열려요(지금 {problem['tries']}번). "
            f"힌트 {level}단계까지 봤으니 고쳐서 한 번 더 채점해 볼까요?")


def _ready(cur) -> None:
    cur.execute("SELECT to_regclass('study_tutor_turns') IS NOT NULL")
    if not cur.fetchone()[0]:
        raise StudySourceError(503, "튜터 기록을 넣을 곳이 없습니다. manage.py migrate 로 lms.0006 까지 적용하세요.")


def _problem(cur, user: dict, set_key: str, index: int) -> dict:
    """내가 볼 수 있는 세트의 문제 — 내 기수(관리자는 모두), 학생이 만든 세트면 만든 학생만"""
    cur.execute(
        """SELECT p.*, s.cohort_id, s.owner_id FROM practice_problems p JOIN practice_sets s ON s.id = p.problem_set_id
           WHERE s.legacy_id = %s AND p.position = %s""",
        [set_key, index],
    )
    row = _one(cur)
    if not row or (row["owner_id"] is not None and row["owner_id"] != user.get("id")):
        raise StudySourceError(404, "문제를 찾을 수 없습니다.")
    if user.get("role") != "admin" and row["cohort_id"] != user.get("cohort_id"):
        raise StudySourceError(403, "해당 기수의 문제가 아닙니다.")
    cur.execute("SELECT passed, tries FROM practice_attempts WHERE user_id = %s AND problem_id = %s", [user.get("id"), row["id"]])
    attempt = cur.fetchone()
    row["passed"], row["tries"] = (bool(attempt[0]), int(attempt[1])) if attempt else (False, 0)
    return row


def _j(value):
    return json.loads(value) if isinstance(value, str) else value


def _problem_payload(p: dict) -> dict:
    # SQL 조회 · 웹 실습은 code_write 로 저장돼 있다(practice_service.stored_kind) — 튜터에는 원래 모양으로 넘긴다
    kind = stored_kind(p)
    sql = kind == "sql_query"
    return {
        "kind": kind, "topic": p["topic"], "prompt": p["prompt"], "choices": _j(p["choices"]) or [],
        "answerIndex": p["answer_index"], "expectedStdout": p["expected_stdout"], "starterCode": p["starter_code"],
        "referenceSolution": p["reference_solution"],
        "hiddenTests": "" if sql else p["hidden_tests"],
        "setupSql": p["hidden_tests"] if sql else "",
        # 언어를 가리는 표시(["js"] · ["web"] · ["web-js"]) — 튜터가 JS · 웹 문제를 파이썬으로 읽지 않게
        "packages": _j(p["packages"]) or [],
        "tries": p["tries"], "passed": p["passed"],
        # 화면에 정답 · 해설이 이미 보이면 튜터도 해설한다 — 통과했거나, 개념 · 출력 예상을 한 번 낸 뒤
        "revealed": answer_revealed(p), "explanation": p.get("explanation") or "",
    }


def answer_revealed(p: dict) -> bool:
    """학생 화면에 정답과 해설이 이미 떠 있는지(ProblemCell — 개념 · 출력 예상은 내면 바로, 코드는 통과해야 해설)"""
    return bool(p["passed"]) or (stored_kind(p) in ANSWER_ON_SUBMIT and p["tries"] >= 1)


def _turns(cur, user_id: int, key: str, limit: int) -> list[dict]:
    cur.execute(
        """SELECT role, text, kind, hint_level, lines, created_at FROM study_tutor_turns
           WHERE user_id = %s AND thread_key = %s ORDER BY id DESC LIMIT %s""",
        [user_id, key, limit],
    )
    rows = _dicts(cur)[::-1]
    return [
        {"role": r["role"], "text": r["text"], "kind": r["kind"], "hintLevel": r["hint_level"],
         "lines": _j(r["lines"]) or [], "at": r["created_at"].isoformat()}
        for r in rows
    ]


# 오답노트에서 연 문제의 대화 — 'retry:2026-09-30'. 복습 때 대화(set:…)와 따로 두고, 날마다 새로 시작한다.
# 복습 때 받은 3단계 힌트가 떠 있으면 다시 풀어 보는 뜻이 없다. 복습 때 대화는 지우지 않는다(복습 탭에서는 그대로 보인다)
RETRY_THREAD = re.compile(r"^retry:\d{4}-\d{2}-\d{2}$")


def _thread_key(mode: str, set_key: str | None, index: int | None, thread: str | None = None) -> str:
    if mode != "problem":
        return "cell"
    key = f"set:{set_key}:{index}"
    return f"{thread}:{key}" if thread and RETRY_THREAD.match(thread) else key


def is_retry_thread(thread: str | None) -> bool:
    return bool(thread and RETRY_THREAD.match(thread))


def thread(user: dict, mode: str, set_key: str | None = None, index: int | None = None, thread: str | None = None) -> dict:
    """튜터 창을 다시 열 때 — 지난 대화와 지금 힌트 단계"""
    with connection.cursor() as cur:
        _ready(cur)
        if mode == "problem":
            _problem(cur, user, str(set_key), int(index or 0))
        turns = _turns(cur, user["id"], _thread_key(mode, set_key, index, thread), 30)
    level = max([t["hintLevel"] or 0 for t in turns] or [0])
    return {"turns": turns, "hintLevel": level}


def reset(user: dict, mode: str, set_key: str | None = None, index: int | None = None, thread: str | None = None) -> dict:
    """「새 대화」 — 이 문제(또는 일반 셀)의 내 대화를 지운다. 힌트 단계도 처음부터 다시 오른다.
    모범답안은 힌트 단계가 아니라 채점 횟수로 열리므로(REVEAL_AFTER_TRIES) 지워도 답이 먼저 열리지 않는다."""
    key = _thread_key(mode, set_key, index, thread)
    with transaction.atomic(), connection.cursor() as cur:
        _ready(cur)
        if mode == "problem":
            _problem(cur, user, str(set_key), int(index or 0))
        cur.execute("DELETE FROM study_tutor_turns WHERE user_id = %s AND thread_key = %s", [user["id"], key])
        removed = cur.rowcount
    return {"turns": [], "hintLevel": 0, "removed": removed}


def _offtopic_streak(cur, user_id: int) -> bool:
    cur.execute(
        """SELECT kind FROM study_tutor_turns WHERE user_id = %s AND role = 'assistant' AND created_at > now() - %s
           ORDER BY id DESC LIMIT %s""",
        [user_id, OFFTOPIC_WINDOW, OFFTOPIC_STREAK],
    )
    kinds = [r[0] for r in cur.fetchall()]
    return len(kinds) == OFFTOPIC_STREAK and all(k == "offtopic" for k in kinds)


def _save(cur, user_id: int, problem_id: int | None, key: str, question: str, answer: dict, level: int | None) -> None:
    cur.execute(
        """INSERT INTO study_tutor_turns (user_id, problem_id, thread_key, role, text, kind, hint_level, lines, llm, created_at)
           VALUES (%s, %s, %s, 'user', %s, '', %s, '[]'::jsonb, false, now())""",
        [user_id, problem_id, key, question, level],
    )
    cur.execute(
        """INSERT INTO study_tutor_turns (user_id, problem_id, thread_key, role, text, kind, hint_level, lines, llm, created_at)
           VALUES (%s, %s, %s, 'assistant', %s, %s, %s, %s::jsonb, %s, now())""",
        [user_id, problem_id, key, answer["reply"], answer["type"] or "", level,
         json.dumps(answer.get("lines") or []), bool(answer.get("llm"))],
    )


def ask(user: dict, body: dict) -> dict:
    """{reply, kind, lines, hintLevel, llm}"""
    mode = "problem" if body.get("mode") == "problem" else "cell"
    action = body.get("action") if body.get("action") in ACTIONS else "ask"
    question = str(body.get("question") or "").strip()[:1000]
    if action == "more" and not question:
        question = "힌트 더 주세요"
    if action == "answer" and not question:
        question = "정답 알려 주세요"
    if not question:
        raise StudySourceError(422, "질문을 적어 주세요.")
    set_key = str(body.get("setId") or "")
    index = int(body.get("index") or 0)
    retry = mode == "problem" and is_retry_thread(body.get("thread"))
    key = _thread_key(mode, set_key, index, body.get("thread"))

    with connection.cursor() as cur:
        _ready(cur)
        problem = _problem(cur, user, set_key, index) if mode == "problem" else None
        history = _turns(cur, user["id"], key, HISTORY)
        current = max([t["hintLevel"] or 0 for t in history] or [0])
        level = None
        if problem:
            level = min(3, current + 1) if action == "more" else max(1, current)

        answer: dict | None = None
        if problem and action == "answer":
            # 모범답안은 튜터가 주지 않는다 — 문제 셀의 「모범답안 보기」 규칙 그대로
            answer = {"type": "locked", "reply": locked_reply(problem, level), "lines": [], "llm": False}
        elif not ON_TOPIC.search(question) and _offtopic_streak(cur, user["id"]):
            answer = {"type": "offtopic", "reply": STREAK_REPLY, "lines": [], "llm": False}

    if answer is None:
        payload = {
            # action — 「다음 힌트」 단추(more)면 튜터가 앞 대화보다 한 걸음 더 나간다
            "mode": mode, "action": action, "question": question, "hintLevel": level or 1,
            "code": str(body.get("code") or "")[:20000], "run": str(body.get("run") or "")[:4000],
            "grade": str(body.get("grade") or "")[:4000],
            # 오답노트면 튜터가 「전에 틀린 문제를 다시 푸는 중」인 줄 안다
            "problem": {**_problem_payload(problem), "retry": retry} if problem else None,
            "history": [{"role": t["role"], "text": t["text"]} for t in history],
        }
        try:
            answer = _call("/proxy/tutor", payload, TIMEOUT)
        except StudyNoteError as exc:
            raise StudySourceError(exc.status, exc.detail) from exc

    with transaction.atomic(), connection.cursor() as cur:
        _save(cur, user["id"], problem["id"] if problem else None, key, question, answer, level)
    return {"reply": answer["reply"], "kind": answer["type"], "lines": answer.get("lines") or [],
            "hintLevel": level, "llm": bool(answer.get("llm"))}
