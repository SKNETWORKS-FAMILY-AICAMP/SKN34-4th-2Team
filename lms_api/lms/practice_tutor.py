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
    r"error|exception|def |return|import|print|python|[()\[\]=:.]",
    re.IGNORECASE,
)


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
    return {
        "kind": p["kind"], "topic": p["topic"], "prompt": p["prompt"], "choices": _j(p["choices"]) or [],
        "answerIndex": p["answer_index"], "expectedStdout": p["expected_stdout"], "starterCode": p["starter_code"],
        "referenceSolution": p["reference_solution"], "hiddenTests": p["hidden_tests"],
        "tries": p["tries"], "passed": p["passed"],
    }


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


def _thread_key(mode: str, set_key: str | None, index: int | None) -> str:
    return f"set:{set_key}:{index}" if mode == "problem" else "cell"


def thread(user: dict, mode: str, set_key: str | None = None, index: int | None = None) -> dict:
    """튜터 창을 다시 열 때 — 지난 대화와 지금 힌트 단계"""
    with connection.cursor() as cur:
        _ready(cur)
        if mode == "problem":
            _problem(cur, user, str(set_key), int(index or 0))
        turns = _turns(cur, user["id"], _thread_key(mode, set_key, index), 30)
    level = max([t["hintLevel"] or 0 for t in turns] or [0])
    return {"turns": turns, "hintLevel": level}


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
    key = _thread_key(mode, set_key, index)

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
            if problem["passed"] or problem["tries"] >= REVEAL_AFTER_TRIES:
                reply = "모범답안은 문제 아래 「모범답안 보기」에서 볼 수 있어요. 보기 전에 한 번만 더 고쳐 채점해 보는 건 어때요?"
            else:
                reply = (f"모범답안은 {REVEAL_AFTER_TRIES}번 채점해 본 뒤에 열려요(지금 {problem['tries']}번). "
                         f"힌트 {level}단계까지 봤으니 고쳐서 한 번 더 채점해 볼까요?")
            answer = {"type": "locked", "reply": reply, "lines": [], "llm": False}
        elif not ON_TOPIC.search(question) and _offtopic_streak(cur, user["id"]):
            answer = {"type": "offtopic", "reply": STREAK_REPLY, "lines": [], "llm": False}

    if answer is None:
        payload = {
            "mode": mode, "question": question, "hintLevel": level or 1,
            "code": str(body.get("code") or "")[:20000], "run": str(body.get("run") or "")[:4000],
            "grade": str(body.get("grade") or "")[:4000],
            "problem": _problem_payload(problem) if problem else None,
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
