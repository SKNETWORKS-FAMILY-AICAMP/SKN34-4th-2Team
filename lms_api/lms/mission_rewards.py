"""기록실 마일리지 미션 — 승인할 때 지급할 금액. 규칙은 React domain/missions.ts 의 MissionRules 와 같다.

단계형(학습인증 · 프리코스 퀴즈 · 코딩테스트)은 이번 승인으로 넘어선 단계의 차액을 준다.
블로그 · 팀 스터디는 단위기간(커리큘럼)을 알아야 해서 관리자가 승인 창에서 금액을 확인해 보낸다 — 상한만 서버가 지킨다.
지급액은 record_submissions.details.mileage_amount 에 남기고, 그 합으로 상한을 본다.
"""

from __future__ import annotations

STUDY_CERT_TIERS = ((3, 10000), (5, 30000), (10, 50000))
QUIZ_TIERS = ((1, 10000), (3, 30000), (5, 50000))
QUIZ_PASS_SCORE = 60
BLOG_UNIT_REWARD = 20000
BLOG_MAX_TOTAL = 5 * BLOG_UNIT_REWARD
STUDY_TEAM_REWARD = 50000
CODING_PCCE = 25000
CODING_ADVANCED = 50000

MISSION_LABELS = {
    "studyCert": "학습인증",
    "precourseQuiz": "프리코스 퀴즈",
    "certification": "코딩테스트",
    "blog": "블로그",
    "study": "팀 스터디",
}
MANUAL_DEFAULTS = {"blog": BLOG_UNIT_REWARD, "study": STUDY_TEAM_REWARD}


def _tier(count: int, tiers) -> int:
    target = 0
    for need, amount in tiers:
        if count >= need:
            target = amount
    return target


def _coding_target(cert_types: list[str]) -> int:
    joined = " ".join(cert_types).upper()
    if "PCCP" in joined or "PCSQL" in joined:
        return CODING_ADVANCED
    return CODING_PCCE if "PCCE" in joined else 0


def _score(details: dict) -> float:
    try:
        return float(details.get("quiz_score") or details.get("quizScore") or 0)
    except (TypeError, ValueError):
        return 0


def _approved_others(cur, row: dict) -> list[dict]:
    cur.execute(
        """SELECT details FROM record_submissions
           WHERE user_id = %s AND type = %s AND status = 'approved' AND id <> %s""",
        [row["user_id"], row["type"], row["id"]],
    )
    from lms.content_commands import _as_dict

    return [_as_dict(d) for (d,) in cur.fetchall()]


def mission_reward(cur, row: dict, details: dict, requested) -> int:
    """이 기록을 지금 승인하면 줄 금액. 호출하는 쪽이 같은 학생 기록을 잠근 뒤 부른다."""
    kind = row["type"]
    others = _approved_others(cur, row)
    if kind == "studyCert":
        return _tier(len(others) + 1, STUDY_CERT_TIERS) - _tier(len(others), STUDY_CERT_TIERS)
    if kind == "precourseQuiz":
        if _score(details) < QUIZ_PASS_SCORE:
            return 0
        passed = [d for d in others if _score(d) >= QUIZ_PASS_SCORE]
        return _tier(len(passed) + 1, QUIZ_TIERS) - _tier(len(passed), QUIZ_TIERS)
    if kind == "certification":
        before = [str(d.get("cert_type") or d.get("certType") or "") for d in others]
        mine = str(details.get("cert_type") or details.get("certType") or "")
        return max(0, _coding_target([*before, mine]) - _coding_target(before))
    if kind in MANUAL_DEFAULTS:
        cap = BLOG_MAX_TOTAL if kind == "blog" else STUDY_TEAM_REWARD
        given = sum(int(d.get("mileage_amount") or 0) for d in others)
        try:
            amount = int(requested) if requested not in (None, "") else MANUAL_DEFAULTS[kind]
        except (TypeError, ValueError):
            amount = MANUAL_DEFAULTS[kind]
        return max(0, min(amount, cap - given))
    return 0
