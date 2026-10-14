"""앱이 서버로 보내는 이력서를 그대로 만든다.

## 왜 필요한가

평가는 `fixtures/eval_resumes.json`에 손으로 쓴 이력서 여섯 개를 써 왔다. 그런데
그 글은 앱이 만드는 양식이 아니었다. `[교육]` `[프로젝트 경험]` 두세 구간뿐이고
**자격사항·학력사항·기술스택·핵심역량이 아예 없었다.** 요청 본문의 `certifications`와
`majors`도 빈 채로 나갔다.

앱은 `scripts/resume_mocks.json`의 열한 구간을 `resume_text_builder.dart`로 엮어
보낸다. 평가가 그것과 다른 글을 보내면, 재고 있는 것이 실제로 사용자가 받는 추천이
아니다. 자격증을 요구하는 공고를 걸러내는지, 전공을 보는지도 평가에 안 잡힌다.

그래서 여기서는 `resume_text_builder.dart`와 `resume_profile.dart`를 파이썬으로
옮겨 **같은 원본에서 같은 글을** 만든다. 원본이 하나이므로 앱 목업을 고치면 평가도
따라 바뀐다.

## 옮긴 원본

- `lib/features/resume/ai_coach/data/resume_text_builder.dart` — 구간 순서와 줄 모양
- `lib/features/resume/ai_coach/data/resume_profile.dart` — 학력·연차·전공·자격증
- `lib/shared/models/resume_content.dart` — 어떤 항목을 '채워졌다'고 보는지

Dart 쪽이 바뀌면 여기도 바뀌어야 한다. `tests/test_app_resume.py`가 두 파일이
갈라졌는지 알려 준다.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
MOCKS = REPO_ROOT / "scripts" / "resume_mocks.json"
# 평가 전용 이력서. 구조와 직렬화기는 위와 똑같고 사람만 다르다.
#
# 기존 5종으로 판정 프롬프트와 가중치를 고쳤다. 같은 것으로 다시 재면 자기 데이터에
# 맞춘 셈이 되어 항상 좋아 보인다. 바꾼 것이 진짜 나아진 것인지는 **처음 보는
# 이력서**로만 알 수 있다.
EVAL_MOCKS = REPO_ROOT / "scripts" / "resume_mocks_eval.json"

# 자기소개서 구간의 순서와 이름. `ResumeSelfIntroLabels`와 같아야 한다.
SELF_INTRO_LABELS: list[tuple[str, str]] = [
    ("intro", "자기소개"),
    ("motivation", "지원동기"),
    ("challenge", "직무와 관련된 경험 중 어려움을 극복한 사례"),
    ("growth", "성장과정"),
    ("strengthsWeaknesses", "직무와 관련된 성격의 장단점"),
    ("aspiration", "지원한 회사에 대한 포부"),
]

# 이력서에는 없는 값이다. 앱에서는 사용자가 따로 고른다. 평가용으로 여기 둔다.
EVAL_PREFERENCES: dict[str, dict[str, list[str]]] = {
    "backend_entry": {"regions": ["서울", "경기"], "employment_types": ["정규직"]},
    "frontend_entry": {"regions": ["서울"], "employment_types": ["정규직"]},
    "backend_experienced_3y": {"regions": ["서울"], "employment_types": ["정규직"]},
    "data_entry_junior_college": {"regions": ["서울", "경기"], "employment_types": ["정규직"]},
    "embedded_entry_regional": {"regions": ["대전"], "employment_types": ["정규직"]},
    # 평가 전용 5종
    "qa_entry": {"regions": ["서울", "경기"], "employment_types": ["정규직"]},
    "security_entry": {"regions": ["서울"], "employment_types": ["정규직"]},
    "devops_experienced_2y": {"regions": ["서울"], "employment_types": ["정규직"]},
    "ai_masters": {"regions": ["서울", "경기"], "employment_types": ["정규직"]},
    "frontend_experienced_5y": {"regions": ["서울"], "employment_types": ["정규직"]},
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _period(start: Any, end: Any) -> str:
    """`_period` — 둘 다 비면 아무것도 안 붙는다."""
    s, e = _text(start), _text(end)
    if not s and not e:
        return ""
    return f" ({s} ~ {e})"


def _self_introduction(content: dict) -> str:
    """`buildSelfIntroductionText` — 채워진 구간만 순서대로."""
    intro = content.get("selfIntroduction") or {}
    blocks: list[str] = []
    for key, label in SELF_INTRO_LABELS:
        section = intro.get(key) or {}
        body = _text(section.get("body"))
        if not body:
            continue
        subtitle = _text(section.get("subtitle"))
        head = f"({label})" if not subtitle else f"({label}) {subtitle}"
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def _project_lines(content: dict) -> Iterable[str]:
    for p in content.get("projects") or []:
        if not _text(p.get("name")):
            continue
        yield f"- {_text(p.get('name'))}{_period(p.get('startDate'), p.get('endDate'))}"
        if _text(p.get("role")):
            yield f"  역할: {_text(p.get('role'))}"
        if _text(p.get("techStack")):
            yield f"  기술: {_text(p.get('techStack'))}"
        if _text(p.get("description")):
            yield f"  {_text(p.get('description'))}"


def _experience_lines(content: dict) -> Iterable[str]:
    for e in content.get("experience") or []:
        if not _text(e.get("company")):
            continue
        role = _text(e.get("role"))
        end = "재직 중" if e.get("isCurrent") else e.get("endDate")
        yield (
            f"- {_text(e.get('company'))}"
            f"{'' if not role else f' / {role}'}"
            f"{_period(e.get('startDate'), end)}"
        )
        if _text(e.get("description")):
            yield f"  {_text(e.get('description'))}"


def _dated_lines(items: Iterable[dict], name_key: str, org_key: str, date_key: str) -> Iterable[str]:
    """수상내역·기타활동처럼 `이름 / 소속 (날짜)` + 설명 한 줄인 구간."""
    for item in items or []:
        if not _text(item.get(name_key)):
            continue
        org = _text(item.get(org_key)) if org_key else ""
        when = _text(item.get(date_key)) if date_key else ""
        yield (
            f"- {_text(item.get(name_key))}"
            f"{'' if not org else f' / {org}'}"
            f"{'' if not when else f' ({when})'}"
        )
        if _text(item.get("description")):
            yield f"  {_text(item.get('description'))}"


def _activity_lines(content: dict) -> Iterable[str]:
    for a in content.get("otherActivities") or []:
        name = _text(a.get("name"))
        if not name:
            continue
        yield f"- {name}{_period(a.get('startDate'), a.get('endDate'))}"
        if _text(a.get("description")):
            yield f"  {_text(a.get('description'))}"


def _education_lines(content: dict) -> Iterable[str]:
    for e in content.get("education") or []:
        school = _text(e.get("school"))
        if not school:
            continue
        major = _text(e.get("major"))
        status = _text(e.get("status"))
        tail = "" if not status else f" ({status})"
        yield f"- {school}{'' if not major else ' ' + major}{tail}"


def _certification_lines(content: dict) -> Iterable[str]:
    for c in content.get("certifications") or []:
        name = _text(c.get("name"))
        if not name:
            continue
        issuer = _text(c.get("issuer"))
        when = _text(c.get("acquiredDate"))
        yield f"- {name}{'' if not issuer else ' / ' + issuer}{'' if not when else f' ({when})'}"


def _training_lines(content: dict) -> Iterable[str]:
    for t in content.get("trainingExperience") or []:
        course = _text(t.get("course"))
        if not course:
            continue
        org = _text(t.get("organization"))
        yield f"- {course}{'' if not org else ' / ' + org}{_period(t.get('startDate'), t.get('endDate'))}"
        if _text(t.get("description")):
            yield f"  {_text(t.get('description'))}"


def build_resume_text(content: dict) -> str:
    """`buildResumeText`의 파이썬 판. 구간 순서까지 같아야 한다.

    서버는 모델이 돌려준 인용문이 이 글 안에 **그대로** 있을 때만 근거로 인정한다.
    그래서 원본 문장을 다듬지 않고 라벨만 붙인다.
    """
    parts: list[str] = []

    def section(title: str, lines: Iterable[str]) -> None:
        # Dart 쪽 `section`이 줄마다 trim을 건다. `  역할:` 같은 들여쓰기는
        # 살아남지 못한다. 아쉬워도 앱이 보내는 글과 한 글자라도 달라지면 안 된다.
        body = [s for s in (line.strip() for line in lines) if s]
        if not body:
            return
        parts.append(f"[{title}]\n" + "\n".join(body))

    section("핵심역량", [_text((content.get("coreCompetencies") or {}).get("text"))])
    section(
        "기술스택",
        [
            _text(t.get("name")) if not _text(t.get("level"))
            else f"{_text(t.get('name'))} ({_text(t.get('level'))})"
            for t in content.get("techStack") or []
            if _text(t.get("name"))
        ],
    )
    section("프로젝트 경험", _project_lines(content))
    section("경력사항", _experience_lines(content))
    section("학력사항", _education_lines(content))
    section("자격사항", _certification_lines(content))
    section("수상내역", _dated_lines(content.get("awards"), "name", "organization", "date"))
    section("교육경험", _training_lines(content))
    section("기타활동", _activity_lines(content))

    intro = _self_introduction(content)
    if intro:
        parts.append("[자기소개서]\n" + intro)

    return "\n\n".join(parts).strip()


# 하드 필터의 `EDUCATION_RANK` 와 같은 순서. 뒤로 갈수록 높다.
EDUCATION_ORDER = ["미기재", "고졸", "초대졸", "대졸", "석사", "박사"]

# 학위를 못 받았을 때 실제로 인정되는 수준. 한 칸씩 내리면 안 된다.
# 대학교 중퇴는 초대졸이 아니라 고졸이다.
_BEFORE_DEGREE = {"박사": "석사", "석사": "대졸", "대졸": "고졸", "초대졸": "고졸", "고졸": "미기재"}


def _degree_of(item: dict) -> str:
    """학교 이름·전공에서 학위 수준을 읽는다. 못 읽으면 빈 문자열."""
    text = re.sub(r"\s", "", f"{_text(item.get('school'))} {_text(item.get('major'))}")
    if "박사" in text:
        return "박사"
    if "대학원" in text or "석사" in text:
        return "석사"
    # `전문대학`은 `대학`을 품고 있다. 반드시 먼저 본다.
    if "전문대" in text or re.search(r"\([23]년제\)", text):
        return "초대졸"
    if "대학" in text:
        return "대졸"
    if "고등학교" in text or "고교" in text:
        return "고졸"
    return ""


def _has_degree(status: str) -> str:
    """학위를 실제로 받았는가. 상태 칸은 자유 입력이라 정해진 목록이 없다.

    `졸업예정`도 대졸 공고에 지원할 수 있으니 포함한다. `재학`·`중퇴`·`수료`에는
    `졸업`이 없어 자연히 걸러진다. 비워 둔 것은 받은 것으로 본다 — 학교만 적고
    상태를 안 쓴 이력서가 흔하고, 안 썼다고 깎으면 멀쩡한 공고가 사라진다.
    """
    s = _text(status)
    return not s or "졸업" in s or "학위취득" in s


def education_level_of(education: Iterable[dict]) -> str:
    """학력사항에서 가장 높은 학력을 고른다.

    예전에는 학력 항목이 한 줄이라도 있으면 무조건 `대졸`이었다. 전공을 적었다는 것과
    그 학위를 받았다는 것은 다른 이야기인데 둘을 같이 봤다.
    """
    best = 0
    for item in education or []:
        if not _text(item.get("school")):
            continue
        degree = _degree_of(item)
        if not degree:
            continue
        level = degree if _has_degree(item.get("status")) else _BEFORE_DEGREE.get(degree, "미기재")
        best = max(best, EDUCATION_ORDER.index(level))
    return EDUCATION_ORDER[best]


def _parse_month(value: Any) -> date | None:
    text = _text(value)
    if not text:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", text):
        text = f"{text}-01"
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def estimate_career_years(experience: Iterable[dict], today: date | None = None) -> float:
    """`estimateCareerYears` — 재직 개월을 더해 소수 첫째 자리까지. 재직 중은 오늘까지."""
    now = today or date.today()
    months = 0
    for item in experience or []:
        if not _text(item.get("company")):
            continue
        start = _parse_month(item.get("startDate"))
        end = now if item.get("isCurrent") else _parse_month(item.get("endDate"))
        if start is None or end is None or end < start:
            continue
        diff = (end.year - start.year) * 12 + end.month - start.month
        months += max(diff, 0)
    return round(months / 12 * 10) / 10


def profile_from_content(content: dict, today: date | None = None) -> dict:
    """`RecommendResumeProfile.fromContent` — 학력·연차·전공·자격증."""
    education = [e for e in content.get("education") or [] if _text(e.get("school"))]
    experience = [e for e in content.get("experience") or [] if _text(e.get("company"))]
    return {
        "education_level": education_level_of(education),
        "career_years": estimate_career_years(experience, today),
        "majors": [_text(e.get("major")) for e in education if _text(e.get("major"))],
        "certifications": [
            _text(c.get("name")) for c in content.get("certifications") or [] if _text(c.get("name"))
        ],
    }


def load_personas(path: Path | None = None, today: date | None = None) -> dict[str, dict]:
    """앱 목업을 평가가 그대로 서버에 보낼 수 있는 모양으로 읽는다.

    키는 사람이 읽는 제목이다. `[목업]`·`[평가]` 머리말은 떼어 채점 화면에서 짧게
    보이게 한다.
    """
    mocks = json.loads((path or MOCKS).read_text(encoding="utf-8"))["personas"]
    out: dict[str, dict] = {}
    for key, persona in mocks.items():
        content = persona["content"]
        prefs = EVAL_PREFERENCES.get(key, {"regions": [], "employment_types": []})
        name = _text(persona["title"]).removeprefix("[목업]").removeprefix("[평가]").strip()
        out[name] = {
            "resume_text": build_resume_text(content),
            "preferred_regions": list(prefs["regions"]),
            "preferred_employment_types": list(prefs["employment_types"]),
            **profile_from_content(content, today),
        }
    return out
