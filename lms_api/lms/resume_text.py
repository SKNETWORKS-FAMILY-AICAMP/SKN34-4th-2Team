"""이력서를 추천 서버가 받는 평문 · 조건으로 바꾼다.

Flutter 원본의 `resume_text_builder.dart` · `resume_profile.dart` 를 그대로 옮긴 것이다.

**형식을 함부로 다듬으면 안 된다.** 추천 서버는 모델이 돌려준 인용문이 이 평문 안에
**연속해서** 있을 때만 근거로 인정한다(`job_matching_bot`). 사용자가 쓴 문장은 그대로 넣고
라벨만 붙인다.

조건(`education_level` · `career_years` · `majors` · `certifications`)은 추천 서버의 하드 필터가
연차 · 학력 · 전공 · 자격 조건을 거르는 데 쓴다.
"""

from __future__ import annotations

import re
from datetime import date

# 하드 필터의 EDUCATION_RANK 와 같은 순서. 뒤로 갈수록 높다.
EDUCATION_ORDER = ["미기재", "고졸", "초대졸", "대졸", "석사", "박사"]

# 학위를 못 받았을 때 실제로 인정되는 수준. 한 칸씩 내리면 안 된다 — 대학교 중퇴는 초대졸이 아니라 고졸이다.
_BEFORE_DEGREE = {"박사": "석사", "석사": "대졸", "대졸": "고졸", "초대졸": "고졸", "고졸": "미기재"}

SELF_INTRO_KEYS = ["intro", "motivation", "challenge", "growth", "strengthsWeaknesses", "aspiration"]
SELF_INTRO_LABELS = {
    "intro": "자기소개",
    "motivation": "지원동기",
    "challenge": "직무와 관련된 경험 중 어려움을 극복한 사례",
    "growth": "성장과정",
    "strengthsWeaknesses": "직무와 관련된 성격의 장단점",
    "aspiration": "지원한 회사에 대한 포부",
}


def _s(value) -> str:
    return str(value or "").strip()


def _items(content: dict, key: str) -> list[dict]:
    value = content.get(key)
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _period(start, end) -> str:
    s, e = _s(start), _s(end)
    return "" if not s and not e else f" ({s} ~ {e})"


def build_resume_text(content: dict) -> str:
    """이력서 내용 → 추천 서버에 보낼 평문."""
    blocks: list[str] = []

    def section(title: str, lines) -> None:
        body = [line for line in (_s(l) for l in lines) if line]
        if body:
            blocks.append("\n".join([f"[{title}]", *body]))

    section("핵심역량", [(content.get("coreCompetencies") or {}).get("text")])

    section(
        "기술스택",
        [
            _s(t.get("name")) if not _s(t.get("level")) else f"{_s(t.get('name'))} ({_s(t.get('level'))})"
            for t in _items(content, "techStack")
            if _s(t.get("name"))
        ],
    )

    project_lines: list[str] = []
    for p in _items(content, "projects"):
        if not _s(p.get("name")):
            continue
        project_lines.append(f"- {_s(p.get('name'))}{_period(p.get('startDate'), p.get('endDate'))}")
        if _s(p.get("role")):
            project_lines.append(f"  역할: {_s(p.get('role'))}")
        if _s(p.get("techStack")):
            project_lines.append(f"  기술: {_s(p.get('techStack'))}")
        if _s(p.get("description")):
            project_lines.append(f"  {_s(p.get('description'))}")
    section("프로젝트 경험", project_lines)

    experience_lines: list[str] = []
    for e in _items(content, "experience"):
        if not _s(e.get("company")):
            continue
        role = f" / {_s(e.get('role'))}" if _s(e.get("role")) else ""
        end = "재직 중" if e.get("isCurrent") else _s(e.get("endDate"))
        experience_lines.append(f"- {_s(e.get('company'))}{role}{_period(e.get('startDate'), end)}")
        if _s(e.get("description")):
            experience_lines.append(f"  {_s(e.get('description'))}")
    section("경력사항", experience_lines)

    section(
        "학력사항",
        [
            "- "
            + _s(e.get("school"))
            + (f" {_s(e.get('major'))}" if _s(e.get("major")) else "")
            + (f" ({_s(e.get('status'))})" if _s(e.get("status")) else "")
            for e in _items(content, "education")
            if _s(e.get("school"))
        ],
    )

    section(
        "자격사항",
        [
            "- "
            + _s(c.get("name"))
            + (f" / {_s(c.get('issuer'))}" if _s(c.get("issuer")) else "")
            + (f" ({_s(c.get('acquiredDate'))})" if _s(c.get("acquiredDate")) else "")
            for c in _items(content, "certifications")
            if _s(c.get("name"))
        ],
    )

    award_lines: list[str] = []
    for a in _items(content, "awards"):
        if not _s(a.get("name")):
            continue
        org = f" / {_s(a.get('organization'))}" if _s(a.get("organization")) else ""
        when = f" ({_s(a.get('date'))})" if _s(a.get("date")) else ""
        award_lines.append(f"- {_s(a.get('name'))}{org}{when}")
        if _s(a.get("description")):
            award_lines.append(f"  {_s(a.get('description'))}")
    section("수상내역", award_lines)

    training_lines: list[str] = []
    for t in _items(content, "trainingExperience"):
        if not _s(t.get("course")):
            continue
        org = f" / {_s(t.get('organization'))}" if _s(t.get("organization")) else ""
        training_lines.append(f"- {_s(t.get('course'))}{org}{_period(t.get('startDate'), t.get('endDate'))}")
        if _s(t.get("description")):
            training_lines.append(f"  {_s(t.get('description'))}")
    section("교육경험", training_lines)

    other_lines: list[str] = []
    for o in _items(content, "otherActivities"):
        if not _s(o.get("name")):
            continue
        other_lines.append(f"- {_s(o.get('name'))}{_period(o.get('startDate'), o.get('endDate'))}")
        if _s(o.get("description")):
            other_lines.append(f"  {_s(o.get('description'))}")
    section("기타활동", other_lines)

    intro = build_self_introduction_text(content)
    if intro:
        blocks.append("\n".join(["[자기소개서]", intro]))

    return "\n\n".join(blocks).strip()


def build_self_introduction_text(content: dict) -> str:
    """자기소개서 항목만 모아 평문으로. 순서는 원본의 라벨 순서 그대로."""
    intro = content.get("selfIntroduction") or {}
    parts: list[str] = []
    for key in SELF_INTRO_KEYS:
        section = intro.get(key) or {}
        body = _s(section.get("body"))
        if not body:
            continue
        label = SELF_INTRO_LABELS.get(key, key)
        subtitle = _s(section.get("subtitle"))
        head = f"({label})" if not subtitle else f"({label}) {subtitle}"
        parts.append(f"{head}\n{body}")
    return "\n\n".join(parts).strip()


def _degree_of(item: dict) -> str:
    """학교 이름 · 전공에서 학위 수준을 읽는다. 못 읽으면 빈 글자."""
    text = re.sub(r"\s", "", f"{_s(item.get('school'))} {_s(item.get('major'))}")
    if "박사" in text:
        return "박사"
    if "대학원" in text or "석사" in text:
        return "석사"
    # `전문대학` 은 `대학` 을 품고 있다. 반드시 먼저 본다
    if "전문대" in text or re.search(r"\([23]년제\)", text):
        return "초대졸"
    if "대학" in text:
        return "대졸"
    if "고등학교" in text or "고교" in text:
        return "고졸"
    return ""


def _has_degree(status: str) -> bool:
    """학위를 실제로 받았는가. 비워 둔 것은 받은 것으로 본다(학교만 적은 이력서가 흔하다)."""
    s = _s(status)
    return s == "" or "졸업" in s or "학위취득" in s


def education_level_of(education: list[dict]) -> str:
    best = 0
    for item in education:
        degree = _degree_of(item)
        if not degree:
            continue
        level = degree if _has_degree(item.get("status")) else _BEFORE_DEGREE.get(degree, "미기재")
        rank = EDUCATION_ORDER.index(level) if level in EDUCATION_ORDER else 0
        best = max(best, rank)
    return EDUCATION_ORDER[best]


def _parse_month(value) -> date | None:
    v = _s(value)
    if not v:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", v):
        v = f"{v}-01"
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        return None


def estimate_career_years(experience: list[dict]) -> float:
    """재직 기간을 달로 더해 소수 첫째 자리까지. 재직 중은 오늘까지."""
    months = 0
    today = date.today()
    for item in experience:
        start = _parse_month(item.get("startDate"))
        end = today if item.get("isCurrent") else _parse_month(item.get("endDate"))
        if start is None or end is None or end < start:
            continue
        diff = (end.year - start.year) * 12 + end.month - start.month
        months += max(diff, 0)
    return round(months / 12 * 10) / 10


def build_profile(content: dict) -> dict:
    """추천 서버 하드 필터가 쓰는 조건 — 학력 · 연차 · 전공 · 자격."""
    education = [e for e in _items(content, "education") if _s(e.get("school"))]
    experience = [e for e in _items(content, "experience") if _s(e.get("company"))]
    return {
        "education_level": education_level_of(education),
        "career_years": estimate_career_years(experience),
        "majors": [_s(e.get("major")) for e in education if _s(e.get("major"))],
        "certifications": [_s(c.get("name")) for c in _items(content, "certifications") if _s(c.get("name"))],
    }
