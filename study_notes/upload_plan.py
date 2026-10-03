"""폴더 올리기 계획 — 올리기 전에 「이 파일들을 어느 과목에, 어느 수업 날짜로 넣을지」를 정해 확인 화면에 보여 준다.

화면은 파일 내용을 아직 보내지 않고 목록만 보낸다: 경로 · 크기 · 내용 지문(git blob id) · 수정 시각 · 앞부분 글(노트북은 셀).
지문은 git 과 같은 방식이라 브라우저에서도 계산된다 — 지난번과 같은 파일은 계획에서 「같음」으로 빠지고 올리지 않는다.

날짜 근거는 시안(폴더 올리기 8판)에서 실제 폴더로 검증한 순서 그대로다.
① 이름의 날짜(0923 · 2026-09-30 · 9월23일) ② 회차(3일차 · day3) ③ 파일 안에 「수업」과 함께 적힌 날짜
④ 수정 시각 — 과목에서 거의 다 같으면 복사 · 압축 풀기로 바뀐 것이라 믿지 않고 날짜 없이(지난 자료) 둔다.

커리큘럼 · 공휴일은 **힌트일 뿐 정답이 아니다**(둘 다 틀릴 수 있다 — 대체 · 임시 공휴일이 늦게 정해지거나, 공휴일에 보강을 하거나,
일정이 밀렸는데 커리큘럼은 예전 것). 그래서
- 날짜를 모르는 자료(지난 자료 · 회차 폴더)에만 쓰고, 추정한 날짜는 강사가 확인한 뒤에 커밋한다.
- 공휴일 · 주말 · 커리큘럼에 없는 날 · 다른 과목 날에 올려도 막지 않고 묻는다(warnings).
- 실제로 올린 날짜가 생기면 그 과목은 실제 날짜를 따른다(schedule_check 가 어긋남을 알린다).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from study_notes.git_tools import SEOUL, is_learning_file

NUMBERED = re.compile(r"^\d{1,2}[_\-. ]")
MAX_HEAD = 8_000
MAX_CELLS = 400
MAX_CELL_TEXT = 2_000
# 「오늘 수업 올리기」 새 파일 넣을 곳 — 코드 키워드가 겹치는 큰 주제(시안 그대로)
KEYWORDS = (
    "lambda", "zip", "map", "filter", "sorted", "args", "kwargs", "class", "self", "super", "Enum", "__name__", "import",
    "module", "pip", "open", "with", "csv", "json", "try", "except", "finally", "raise", "streamlit", "st.", "while",
    "range", "append", "def ", "for",
)
WEAK_KEYWORDS = {"def ", "for", "import", "with"}
_KEYWORD_RES = {
    k: re.compile(rf"(?<!\w){re.escape(k.strip())}" + (r"(?!\w)" if k.strip()[-1].isalnum() or k.strip()[-1] == "_" else ""))
    for k in KEYWORDS
}
# 폴더 이름 ↔ 커리큘럼 과목 — 이름만으로는 못 맞추는 흔한 줄임말
ALIASES = {"dl": "딥러닝", "ml": "머신러닝", "db": "database", "데이터베이스": "database", "nlp": "자연어"}
WEEKDAY_OFF = {5: "토요일", 6: "일요일"}


def is_hidden(path: str) -> bool:
    """.ipynb_checkpoints · .git · __pycache__ 처럼 숨김 폴더 · 파일 — 수업 자료가 아니다(화면 folderFiles.isHiddenPath 와 같다)"""
    return any(part.startswith(".") or part in ("__pycache__", "node_modules") for part in path.split("/"))


def blob_id(body: bytes) -> str:
    """git 의 내용 지문(blob id) — 브라우저도 같은 식으로 계산한다: sha1("blob <길이>\\0" + 내용)"""
    return hashlib.sha1(b"blob %d\0" % len(body) + body).hexdigest()


# ── 수업 달력 ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CurriculumDay:
    date: str
    topic: str
    unit: str = ""

    @property
    def key(self) -> str:
        # 「단위 프로젝트」처럼 같은 이름이 단원마다 있다 — 단원까지 붙여 가른다
        return f"{self.unit}|{self.topic}"


@dataclass
class Calendar:
    today: str
    start: str = ""
    end: str = ""
    holidays: dict[str, str] = field(default_factory=dict)
    curriculum: list[CurriculumDay] = field(default_factory=list)
    unreadable: int = 0  # 커리큘럼에서 날짜를 못 읽은 줄
    extra_days: set[str] = field(default_factory=set)  # 강사가 「수업 있었음」 한 날(공휴일 보강 · 커리큘럼에 없는 날)

    def __post_init__(self) -> None:
        if not self.start:
            self.start = (date.fromisoformat(self.today) - timedelta(days=365)).isoformat()
        if not self.end:
            self.end = (date.fromisoformat(self.today) + timedelta(days=365)).isoformat()

    @property
    def years(self) -> list[int]:
        return sorted({int(self.start[:4]), int(self.end[:4])})

    def off_day(self, day: str) -> str:
        """수업 없는 날이면 그 이름(공휴일 · 토요일 · 일요일), 아니면 빈 글"""
        if day in self.holidays:
            return self.holidays[day]
        return WEEKDAY_OFF.get(date.fromisoformat(day).weekday(), "")

    def valid(self, y: int, m: int, d: int) -> str | None:
        try:
            value = date(y, m, d).isoformat()
        except ValueError:
            return None
        return value if self.start <= value <= self.end else None

    def topics(self) -> list[dict[str, Any]]:
        """커리큘럼 과목 — 처음 나온 순서, 과목마다 기간 · 수업일 수"""
        out: dict[str, dict[str, Any]] = {}
        for day in self.curriculum:
            item = out.setdefault(day.key, {"id": day.key, "topic": day.topic, "unit": day.unit, "days": []})
            item["days"].append(day.date)
        return [
            {**t, "first": min(t["days"]), "last": max(t["days"]), "count": len(self.class_days(t["id"]))}
            for t in out.values()
        ]

    def class_days(self, topic: str | None = None) -> list[str]:
        """수업일 — 커리큘럼이 있으면 그 날들(과목을 주면 그 과목만)에서 공휴일을 뺀다. 없으면 기수 기간의 평일에서 공휴일을 뺀다.
        강사가 「수업 있었음」 한 날은 공휴일이어도 넣는다."""
        if self.curriculum:
            days = {c.date for c in self.curriculum if topic is None or c.key == topic}
            kept = {d for d in days if d not in self.holidays or d in self.extra_days}
            # 커리큘럼 밖 「수업 있었음」은 과목을 모르면 그 과목 기간 안일 때만 넣는다
            if days:
                lo, hi = min(days), max(days)
                kept |= {d for d in self.extra_days if topic is None or lo <= d <= hi}
            return sorted(kept)
        out: list[str] = []
        day = date.fromisoformat(self.start)
        last = date.fromisoformat(self.end)
        while day <= last:
            value = day.isoformat()
            if not self.off_day(value) or value in self.extra_days:
                out.append(value)
            day += timedelta(days=1)
        return out

    def topic_on(self, day: str) -> CurriculumDay | None:
        return next((c for c in self.curriculum if c.date == day), None)

    def warnings(self) -> list[dict[str, Any]]:
        """커리큘럼 자체가 이상한 곳 — 공휴일 · 주말에 수업이 잡힘, 날짜를 못 읽은 줄"""
        out: list[dict[str, Any]] = []
        for c in self.curriculum:
            if c.date in self.extra_days:
                continue
            if c.date in self.holidays:
                out.append({"kind": "holiday_in_curriculum", "date": c.date, "name": self.holidays[c.date], "topic": c.topic,
                            "text": f"커리큘럼 {_short(c.date)}({self.holidays[c.date]})에 「{c.topic}」 수업이 잡혀 있어요. 수업일에서 뺐어요 — 수업이 있었다면 되돌려 주세요."})
            elif date.fromisoformat(c.date).weekday() in WEEKDAY_OFF:
                name = WEEKDAY_OFF[date.fromisoformat(c.date).weekday()]
                out.append({"kind": "weekend_in_curriculum", "date": c.date, "name": name, "topic": c.topic,
                            "text": f"커리큘럼 {_short(c.date)}({name})에 「{c.topic}」 수업이 있어요. 보강인가요?"})
        if self.unreadable:
            out.append({"kind": "curriculum_unreadable", "count": self.unreadable,
                        "text": f"커리큘럼에서 날짜를 읽지 못한 줄이 {self.unreadable}개 있어요. 그 줄은 빼고 봤어요."})
        return out


def calendar_view(cal: Calendar) -> dict[str, Any]:
    """화면에 주는 달력 — 공휴일(기간 안), 기간, 오늘, 커리큘럼 수업일(공휴일은 뺀 것), 강사가 「수업 있었음」 한 날"""
    return {
        "today": cal.today,
        "start": cal.start,
        "end": cal.end,
        "holidays": {d: n for d, n in cal.holidays.items() if cal.start <= d <= cal.end},
        "classDays": cal.class_days() if cal.curriculum else [],
        "extraDays": sorted(cal.extra_days),
    }


def calendar_from(raw: dict[str, Any]) -> Calendar:
    curriculum = [
        CurriculumDay(str(r["date"]), str(r.get("topic") or r.get("unit") or "").strip(), str(r.get("unit") or "").strip())
        for r in raw.get("curriculum") or []
        if _iso(r.get("date"))
    ]
    return Calendar(
        today=str(raw["today"]),
        start=str(raw.get("start") or ""),
        end=str(raw.get("end") or ""),
        holidays={str(k): str(v) for k, v in (raw.get("holidays") or {}).items() if _iso(k)},
        curriculum=[c for c in curriculum if c.topic],
        unreadable=int(raw.get("unreadable") or 0),
        extra_days={str(d) for d in raw.get("extraDays") or [] if _iso(d)},
    )


def _iso(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def _short(day: str | None) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}" if day else "-"


# ── 날짜 찾기(시안 규칙) ────────────────────────────────────────────

_FULL = re.compile(r"(20\d{2})[-_.]?(\d{2})[-_.]?(\d{2})")
_KOREAN = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DOTTED = re.compile(r"(?:^|[^\d.])(\d{1,2})[./](\d{1,2})(?=[^\d.]|$)")
_MMDD = re.compile(r"(?:^|[^\d])(\d{2})(\d{2})(?=[^\d]|$)")
# 파일 안의 날짜는 「수업 · 강의」와 함께 적힌 것만 — 예제 데이터(2024-01-15 회의) · 셀 id · 소수 · 가격이 날짜로 잡혔다(python_basic 실측)
_LESSON_DATE = re.compile(
    r"(?:수업|강의)[^\n]{0,20}?(20\d{2})[-./](\d{1,2})[-./](\d{1,2})|(20\d{2})[-./](\d{1,2})[-./](\d{1,2})[^\n]{0,20}?(?:수업|강의)"
)
_HEADING = re.compile(r"^#{1,3}\s+\S")


def dates_all(text: str, cal: Calendar) -> list[str]:
    """글 안의 서로 다른 날짜 — 나온 순서대로. 연도가 없으면 기수 기간 안에 드는 해로"""
    found: list[tuple[int, str]] = []

    def add(index: int, value: str | None) -> None:
        if value and all(v != value for _, v in found):
            found.append((index, value))

    for m in _FULL.finditer(text):
        add(m.start(), cal.valid(int(m[1]), int(m[2]), int(m[3])))
    for pattern in (_KOREAN, _DOTTED, _MMDD):
        for m in pattern.finditer(text):
            add(m.start(), next((v for y in cal.years if (v := cal.valid(y, int(m[1]), int(m[2])))), None))
    return [v for _, v in sorted(found)]


def date_in(text: str, cal: Calendar) -> str | None:
    found = dates_all(text, cal)
    return found[0] if found else None


def round_in(text: str) -> int | None:
    if m := re.search(r"(\d+)\s*주\s*차[\s_-]*(\d+)\s*일", text):
        return (int(m[1]) - 1) * 5 + int(m[2])
    if m := re.search(r"(\d+)\s*일\s*차", text):
        return int(m[1])
    if m := re.search(r"day[\s_-]*(\d+)", text, re.I):
        return int(m[1])
    return None


@dataclass
class UpFile:
    """화면이 보낸 파일 한 줄 — 내용은 아직 없다"""

    path: str
    blob: str
    size: int = 0
    mtime: int = 0  # 수정 시각(ms)
    head: str = ""  # 앞부분 글(노트북이 아닌 파일)
    cells: list[dict[str, str]] = field(default_factory=list)  # 노트북 셀 [{type, source}] — 실행 결과는 빼고

    @classmethod
    def of(cls, raw: dict[str, Any]) -> UpFile:
        cells = [
            {"type": str(c.get("type") or "code"), "source": str(c.get("source") or "")[:MAX_CELL_TEXT]}
            for c in (raw.get("cells") or [])[:MAX_CELLS]
            if isinstance(c, dict)
        ]
        return cls(
            path=str(raw["path"]).replace("\\", "/").strip("/"),
            blob=str(raw.get("blob") or ""),
            size=int(raw.get("size") or 0),
            mtime=int(raw.get("mtime") or 0),
            head=str(raw.get("head") or "")[:MAX_HEAD],
            cells=cells,
        )

    @property
    def text(self) -> str:
        return "\n".join(c["source"] for c in self.cells) if self.cells else self.head

    def markdown(self) -> list[str]:
        """제목 · 「수업」 날짜를 찾을 글 — 노트북은 설명(markdown) 셀, .md 는 전부"""
        if self.cells:
            return [c["source"] for c in self.cells if c["type"] == "markdown"]
        return [self.head] if self.path.lower().endswith(".md") else []


def headings_of(f: UpFile, cal: Calendar) -> list[dict[str, Any]]:
    lines = [line for block in f.markdown() for line in block.split("\n")]
    titles = [re.sub(r"^#+\s+", "", line).strip() for line in lines if _HEADING.match(line)]
    return [{"title": t, "date": date_in(t, cal)} for t in titles]


def lesson_date_in(f: UpFile, cal: Calendar) -> str | None:
    head = "\n".join(f.markdown()) if f.cells else "\n".join(f.head.split("\n")[:30])
    m = _LESSON_DATE.search(head)
    if not m:
        return None
    return cal.valid(int(m[1]), int(m[2]), int(m[3])) if m[1] else cal.valid(int(m[4]), int(m[5]), int(m[6]))


def classify(rest: str, f: UpFile, cal: Calendar) -> dict[str, Any]:
    """파일 하나의 날짜 근거 — split(두 날에 걸침) · name · round · content · time"""
    in_name = dates_all(re.sub(r"\.[^.]+$", "", rest.split("/")[-1]), cal)
    heads = headings_of(f, cal)
    if len(in_name) >= 2:
        i2 = next((i for i, h in enumerate(heads) if h["date"] == in_name[1]), -1)
        cut = i2 if i2 > 0 else max(1, len(heads) // 2)
        return {"basis": "split", "from": "name", "dates": in_name[:2], "heads": heads, "cuts": [0, cut], "date": None}
    dated = [(i, h["date"]) for i, h in enumerate(heads) if h["date"]]
    distinct = [(i, d) for k, (i, d) in enumerate(dated) if all(d != x for _, x in dated[:k])]
    if len(distinct) >= 2:
        return {"basis": "split", "from": "content", "dates": [d for _, d in distinct], "heads": heads,
                "cuts": [i for i, _ in distinct], "date": None}
    for part in reversed(rest.split("/")):
        if day := date_in(part, cal):
            return {"basis": "name", "date": day}
        if n := round_in(part):
            return {"basis": "round", "round": n, "date": None}
    if day := lesson_date_in(f, cal):
        return {"basis": "content", "date": day}
    if f.mtime:
        return {"basis": "time", "date": datetime.fromtimestamp(f.mtime / 1000, SEOUL).date().isoformat()}
    return {"basis": "pick", "date": None}


# ── 과목 나누기 ─────────────────────────────────────────────────────


def detect_what(paths: list[str]) -> str:
    """폴더 하나를 과목 하나로 볼지, 과목 여럿이 든 기수 폴더로 볼지 — 안쪽 폴더가 01_ · 02_ 번호 순서면 과목 하나"""
    first = {p.split("/")[1] for p in paths if len(p.split("/")) > 2}
    if not first:
        return "subject"
    numbered = sum(1 for name in first if NUMBERED.match(name))
    return "subject" if numbered / len(first) >= 0.6 else "cohort"


def group(files: list[UpFile], what: str) -> tuple[str, dict[str, list[tuple[str, UpFile]]], int]:
    """(맨 위 폴더 이름, {과목: [(과목 안 경로, 파일)]}, 뺀 파일 수)"""
    root = files[0].path.split("/")[0] if files else ""
    subjects: dict[str, list[tuple[str, UpFile]]] = {}
    skipped = 0
    for f in files:
        inner = f.path.split("/")[1:]
        if what == "subject":
            name, rest = root, "/".join(inner)
        else:
            if len(inner) < 2:
                skipped += 1
                continue
            name, rest = inner[0], "/".join(inner[1:])
        if not rest or not is_learning_file(rest) or is_hidden(rest) or not f.blob:
            skipped += 1
            continue
        subjects.setdefault(name, []).append((rest, f))
    return root, subjects, skipped


# ── 커리큘럼 과목 맞추기 ────────────────────────────────────────────


def _tokens(name: str) -> set[str]:
    words = {w for w in re.split(r"[^0-9a-z가-힣]+", name.lower()) if w and not w.isdigit()}
    return {ALIASES.get(w, w) for w in words}


def match_topic(name: str, dates: list[str], cal: Calendar) -> dict[str, Any]:
    """올린 과목 ↔ 커리큘럼 과목. ① 날짜가 있으면 날짜가 가장 많이 겹치는 과목(절반 이상) ② 이름이 하나로만 맞으면 그 과목
    ③ 못 맞추면 비워 두고 강사가 고른다(어긋난 이름 web_server ↔ Django Framework 같은 건 날짜로만 맞는다)"""
    topics = cal.topics()
    if not topics:
        return {"id": None, "by": None}
    if dates:
        scored = sorted(((sum(d in set(t["days"]) for d in dates), t) for t in topics), key=lambda x: -x[0])
        if scored[0][0] * 2 >= len(dates) and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            return {"id": scored[0][1]["id"], "by": "dates"}
    mine = _tokens(name)
    hits = [t for t in topics if (theirs := _tokens(t["topic"])) and (theirs <= mine or mine <= theirs)]
    if len({t["topic"] for t in hits}) == 1:
        return {"id": hits[0]["id"], "by": "name"}
    return {"id": None, "by": None}


def nth_class_day(cal: Calendar, n: int, *, topic: str | None, start: str) -> str | None:
    """회차 → 날짜. 커리큘럼 과목을 알면 그 과목의 n 번째 수업일, 모르면 과목 시작일부터 수업일을 센다"""
    if not topic and not start:
        return None
    days = cal.class_days(topic) if topic else cal.class_days()
    if start:
        days = [d for d in days if d >= start]
    if topic and days and n > len(days):
        # 커리큘럼 기간보다 길게 이어진 과목 — 그 뒤는 공휴일 · 주말만 빼고 센다
        days += _weekdays_after(cal, days[-1], n - len(days))
    return days[n - 1] if 0 < n <= len(days) else None


def _weekdays_after(cal: Calendar, last: str, count: int) -> list[str]:
    out: list[str] = []
    day = date.fromisoformat(last)
    while len(out) < max(0, count) and len(out) < 400:
        day += timedelta(days=1)
        if not cal.off_day(day.isoformat()):
            out.append(day.isoformat())
    return out


def estimate_days(items: list[dict[str, Any]], days: list[str]) -> dict[str, str]:
    """「커리큘럼으로 날짜 채우기」 — 날짜 없는 지난 자료의 큰 주제 폴더를 번호 순서대로 그 과목의 수업일에 고르게 나눈다.
    {과목 안 경로: 추정 날짜} — 확인 화면에 노란 줄로만 보이고, 강사가 받아들여야 쓴다.
    파일 수로 몫을 나누면 작은 모듈 파일이 많은 폴더(07_package 15개)가 사흘을 차지해 앞뒤가 비었다(python_basic 실측) — 폴더마다 같은 몫."""
    if not days:
        return {}
    tops: dict[str, list[str]] = {}
    for item in items:
        tops.setdefault(item["path"].split("/")[0], []).append(item["path"])
    order = sorted(tops, key=_natural)
    out: dict[str, str] = {}
    for i, top in enumerate(order):
        # 폴더가 수업일보다 많으면 하루에 여럿, 적으면 띄엄띄엄 — 첫 폴더는 첫날, 마지막 폴더는 마지막 날
        k = 0 if len(order) == 1 else round(i * (len(days) - 1) / (len(order) - 1))
        for path in tops[top]:
            out[path] = days[k]
    return out


def _natural(text: str) -> list[Any]:
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", text.lower())]


# ── 계획: 처음 가져오기(폴더) ───────────────────────────────────────


def plan_import(
    files: list[dict[str, Any]],
    cal: Calendar,
    *,
    what: str | None = None,
    existing: dict[str, dict[str, Any]] | None = None,
    topics: dict[str, str] | None = None,
    starts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """폴더 하나 → 과목마다 파일의 날짜 근거 · 지난번과 견준 상태.

    existing — {과목 이름(소문자): {"kind": "upload"|"github", "id", "tree": {경로: blob}, "dates": [수업 날짜]}}.
    topics / starts — 강사가 고른 커리큘럼 과목 · 과목 시작일(다시 계획할 때).
    """
    ups = [UpFile.of(raw) for raw in files]
    what = what or detect_what([f.path for f in ups])
    root, grouped, skipped = group(ups, what)
    existing = existing or {}
    topics = topics or {}
    starts = starts or {}
    subjects = []
    for name in sorted(grouped):
        items = []
        for rest, f in grouped[name]:
            item = {"path": rest, "blob": f.blob, "size": f.size, **classify(rest, f, cal)}
            if f.cells:
                item["cells"] = [c["source"].strip().split("\n")[0][:60] for c in f.cells]
            items.append(item)
        # 수정 시각이 거의 다 같으면 복사 · 압축 풀기로 바뀐 날짜 — 믿지 않는다
        timed = [x for x in items if x["basis"] == "time"]
        if timed:
            top = max(sum(1 for x in timed if x["date"] == d) for d in {x["date"] for x in timed})
            if len(timed) >= 3 and top / len(timed) >= 0.8:
                for x in timed:
                    x["basis"], x["date"] = "pick", None
        known = sorted(x["date"] for x in items if x["basis"] in ("name", "content"))
        before = existing.get(name.lower()) or {}
        matched = {"id": topics[name], "by": "picked"} if topics.get(name) else match_topic(name, [*known, *before.get("dates", [])], cal)
        topic = matched["id"]
        topic_days = cal.class_days(topic) if topic else []
        start = starts.get(name) or (known[0] if known else topic_days[0] if topic_days else "")
        for x in items:
            if x["basis"] == "round":
                x["date"] = nth_class_day(cal, x["round"], topic=topic, start=start)
        tree = before.get("tree") or {}
        for x in items:
            x["status"] = "same" if tree.get(x["path"]) == x["blob"] else "update" if x["path"] in tree else "new"
        past = [x for x in items if not x["date"] and x["basis"] in ("pick", "round") and x["status"] != "same"]
        estimates = estimate_days(past, topic_days)
        for x in past:
            if x["path"] in estimates:
                x["estimate"] = estimates[x["path"]]
        warnings = _date_warnings(items, cal, topic)
        if before.get("kind") == "github":
            warnings.insert(0, {"kind": "github_same_name", "text": f"「{name}」은 GitHub로 연결된 과목과 이름이 같아요. 확정하면 이 과목은 폴더 올리기로 바뀌고 GitHub에서 더는 받지 않아요."})
        subjects.append({
            "name": name,
            "source": {"id": before.get("id"), "kind": before.get("kind")} if before else None,
            "topic": topic,
            "topicBy": matched["by"],
            "start": start,
            "classDays": topic_days,
            "files": sorted(items, key=lambda x: _natural(x["path"])),
            "counts": _counts(items),
            "warnings": warnings,
        })
    return {
        "what": what,
        "root": root,
        "skipped": skipped,
        "subjects": subjects,
        "topics": cal.topics(),
        "calendarWarnings": cal.warnings(),
        # 확인 화면에서 날짜를 고치면 화면이 바로 「수업 없는 날」을 표시한다 — 공휴일 · 기간 · 커리큘럼 수업일
        "calendar": calendar_view(cal),
    }


def _counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "files": len(items),
        "same": sum(1 for x in items if x["status"] == "same"),
        "dated": sum(1 for x in items if x["date"] or x["basis"] == "split"),
        "past": sum(1 for x in items if not x["date"] and x["basis"] in ("pick", "round")),
        "estimated": sum(1 for x in items if x.get("estimate")),
    }


def _date_warnings(items: list[dict[str, Any]], cal: Calendar, topic: str | None) -> list[dict[str, Any]]:
    """날짜를 찾은 파일 중 수업 없는 날 · 커리큘럼 밖 · 다른 과목 날 — 막지 않고 노란 줄로 묻는다"""
    days = sorted({d for x in items for d in ([x["date"]] if x["date"] else x.get("dates", []))})
    return [w for d in days if (w := day_warning(d, cal, topic))]


def _unit(topic_key: str) -> str:
    """커리큘럼 과목 id(단원|과목) → 단원. 단원 칸이 비었으면 과목 자체"""
    unit, _, topic = topic_key.partition("|")
    return unit or topic


def day_warning(day: str, cal: Calendar, topic: str | None) -> dict[str, Any] | None:
    if day in cal.extra_days:
        return None
    if off := cal.off_day(day):
        return {"kind": "off_day", "date": day, "name": off, "text": f"{_short(day)}({off})에 수업한 게 맞나요?"}
    if not cal.curriculum:
        return None
    on = cal.topic_on(day)
    if on is None:
        return {"kind": "not_in_curriculum", "date": day, "text": f"커리큘럼엔 {_short(day)}에 수업이 없어요. 보강이었나요?"}
    # 단원(큰 묶음)으로 견준다 — 커리큘럼 과목은 저장소와 1:1 이 아니다(34기 「딥러닝」 23일에 저장소 넷, LLM 저장소 하나에 과목 셋)
    if topic and _unit(on.key) != _unit(topic):
        return {"kind": "other_topic", "date": day, "topic": on.topic, "unit": on.unit,
                "text": f"커리큘럼의 {_short(day)} 수업은 다른 단원 「{on.unit or on.topic}」({on.topic})이에요. 이 과목이 맞나요?"}
    return None


# ── 계획: 오늘 수업 올리기 ──────────────────────────────────────────


def plan_daily(
    files: list[dict[str, Any]],
    cal: Calendar,
    *,
    day: str,
    tree: dict[str, str],
    texts: dict[str, str],
    topic: str | None = None,
) -> dict[str, Any]:
    """그날 쓴 파일 몇 개 → 파일마다 같음(건너뜀) · 새 버전 · 어느 파일인지 고르기 · 새 파일(넣을 폴더 추천).

    tree — 이 과목의 지금 파일 {경로: blob}, texts — 그 파일들의 앞부분 글(폴더 추천의 키워드).
    """
    ups = [UpFile.of(raw) for raw in files]
    items = []
    for f in ups:
        if not is_learning_file(f.path) or is_hidden(f.path) or not f.blob:
            continue
        base = f.path.split("/")[-1]
        exact = [p for p in tree if p == f.path or p.endswith(f"/{f.path}")]
        by_name = [p for p in tree if p.split("/")[-1] == base]
        matches = exact if "/" in f.path and exact else exact or by_name
        item: dict[str, Any] = {"path": f.path, "blob": f.blob, "size": f.size}
        if len(matches) == 1:
            item.update(status="same" if tree[matches[0]] == f.blob else "update", target=matches[0])
        elif len(matches) > 1:
            item.update(status="pick", options=sorted(matches, key=_natural), target="")
        else:
            item.update(status="new", **suggest_folder(f, tree, texts, day))
        items.append(item)
    warnings = []
    if day > cal.today:
        warnings.append({"kind": "future", "date": day, "text": "앞으로 올 날짜로는 올릴 수 없어요."})
    elif w := day_warning(day, cal, topic):
        warnings.append(w)
    return {
        "date": day,
        "files": items,
        "folders": _dirs(list(tree)),
        "warnings": warnings,
        "counts": {
            "files": len(items),
            "same": sum(1 for x in items if x["status"] == "same"),
            "pick": sum(1 for x in items if x["status"] == "pick"),
        },
    }


def _dirs(paths: list[str]) -> list[str]:
    out = {"/".join(p.split("/")[:i]) for p in paths for i in range(1, len(p.split("/")))}
    return sorted(out, key=_natural)


def _keyword_counts(text: str) -> Counter[str]:
    """코드 키워드가 몇 번 쓰였나 — 낱말 단위로(list. 안의 st. · ohgiraffers_module 안의 module 은 세지 않는다)"""
    return Counter({k: n for k, pattern in _KEYWORD_RES.items() if (n := len(pattern.findall(text)))})


def suggest_folder(f: UpFile, tree: dict[str, str], texts: dict[str, str], day: str) -> dict[str, str]:
    """새 파일을 넣을 곳 — 같은 안쪽 폴더 → 코드 키워드를 가장 많이 쓴 큰 주제 → 큰 주제 여럿에 비슷하면 날짜 폴더 → 최근 주제.

    키워드가 「있나」만 보면 큰 주제끼리 자주 비긴다 — 실제 02_data-type 도 sorted(key=lambda) · zip 을 써서 04_function 과
    같아졌다. 그래서 키워드마다 「그 키워드를 쓴 횟수 중 이 주제 몫」을 더한다(lambda 는 거의 04_function 몫)."""
    folder = f.path.rsplit("/", 1)[0] if "/" in f.path else ""
    if folder:
        same = [d for d in _dirs(list(tree)) if d == folder or d.endswith(f"/{folder}")]
        if len(same) == 1:
            return {"folder": same[0], "why": "같은 폴더가 있어요"}
    mine = [k for k in _keyword_counts(f.text) if k not in WEAK_KEYWORDS]
    tops = sorted({p.split("/")[0] for p in tree if "/" in p and "_" in p.split("/")[0]}, key=_natural)
    used = {top: sum((_keyword_counts(t) for p, t in texts.items() if p.startswith(f"{top}/")), Counter()) for top in tops}
    total = sum(used.values(), Counter())
    scored = sorted(
        ((sum(used[top][k] / total[k] for k in mine if total[k]), top, [k for k in mine if used[top][k]]) for top in tops),
        key=lambda x: -x[0],
    )
    scored = [x for x in scored if x[0] > 0]
    # 키워드마다 가장 많이 쓴 주제 — 세 주제 넘게 나뉘고 한 주제가 6할도 못 가지면 정리 · 복습 파일(오늘정리.ipynb)
    owners = Counter(max(tops, key=lambda t: used[t][k]) for k in mine if total[k])
    spread = len(owners) >= 3 and owners.most_common(1)[0][1] < 0.6 * sum(owners.values())
    if spread or (len(scored) >= 2 and scored[1][0] >= scored[0][0] * 0.8):
        return {"folder": f"{day}/", "why": f"큰 주제 여러 개에 걸쳐 있어요 ({' · '.join(t for _, t, _ in scored[:3])})"}
    if scored:
        return {"folder": scored[0][1], "why": f"코드가 비슷해요: {', '.join(scored[0][2][:3])}"}
    if tops:
        return {"folder": tops[-1], "why": "최근 수업 주제"}
    return {"folder": f"{day}/", "why": "날짜 폴더"}


# ── 일정 어긋남(강사 · 관리자 수업 저장소 화면) ─────────────────────


def schedule_check(cal: Calendar, subjects: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """실제 수업 날짜 ↔ 커리큘럼. subjects — {과목(저장소) 이름: {"topic": 커리큘럼 과목 id|None, "dates": [실제 수업 날짜]}}.

    커리큘럼 과목은 저장소와 1:1 이 아니다 — 34기 「딥러닝」(7/6~8/6) 한 칸에 저장소 넷(data_analysis · ML · DL ·
    model_validation), LLM 저장소 하나에 과목 셋(LLM · 프롬프트 엔지니어링 · 파인튜닝). 과목 단위로 견주면 다 어긋난 것처럼 나왔다.
    그래서 단원(커리큘럼의 큰 묶음)으로 본다. 알리는 것은 둘이다.
    ① 저장소 수업이 그 저장소의 단원(수업일이 가장 많은 단원)이 아닌 날에 있음 — 다음 단원까지 밀렸거나 당겨짐
    ② 커리큘럼에 수업이 없는 날 수업함(보강 · 휴일 수업)
    단원 안에서 며칠 밀린 것은 알 수 없다(커리큘럼이 그만큼 자세하지 않다). 어느 쪽이 맞는지는 정하지 않는다."""
    out: list[dict[str, Any]] = [*cal.warnings()]
    on_day = {c.date: c for c in cal.curriculum if c.date not in cal.holidays or c.date in cal.extra_days}
    for name, info in sorted(subjects.items()):
        dates = sorted(set(info.get("dates") or []))
        off = [d for d in dates if d not in on_day]
        if off:
            why = [f"{_short(d)}({cal.off_day(d) or '커리큘럼에 없음'})" for d in off[:5]]
            out.append({"kind": "off_curriculum", "subject": name, "dates": off,
                        "text": f"「{name}」 수업 {len(off)}일이 커리큘럼엔 수업이 없는 날이에요: {', '.join(why)}"})
        units = Counter(_unit(on_day[d].key) for d in dates if d in on_day)
        if not units:
            continue
        home = _unit(info["topic"]) if info.get("topic") else units.most_common(1)[0][0]
        away: dict[str, list[str]] = {}
        for d in dates:
            if d in on_day and _unit(on_day[d].key) != home:
                away.setdefault(_unit(on_day[d].key), []).append(d)
        for unit, days in away.items():
            late = days[0] > max(d for d in dates if d in on_day and _unit(on_day[d].key) == home) if units[home] else False
            out.append({
                "kind": "schedule_drift", "subject": name, "unit": unit, "home": home, "dates": days,
                "text": f"「{name}」({home}) 수업 {len(days)}일이 커리큘럼에선 다음 단원 「{unit}」 날이에요: "
                        f"{', '.join(_short(d) for d in days[:5])}. 일정이 밀렸다면 커리큘럼을 다시 올려 주세요." if late else
                        f"「{name}」({home}) 수업 {len(days)}일이 커리큘럼에선 다른 단원 「{unit}」 날이에요: "
                        f"{', '.join(_short(d) for d in days[:5])}. 일정이 바뀌었다면 커리큘럼을 다시 올려 주세요.",
            })
    return out


# ── 서버 안 저장소 읽기(계획에 쓰는 것만) ───────────────────────────


def notebook_cells(raw: str) -> list[dict[str, str]]:
    """서버에 있는 노트북 → 셀(실행 결과 뺌). 화면이 보내는 cells 와 같은 모양 — 시험 · 다시 계획할 때 쓴다"""
    try:
        cells = json.loads(raw).get("cells") or []
    except (ValueError, AttributeError):
        return []
    return [
        {"type": str(c.get("cell_type") or "code"),
         "source": ("".join(c["source"]) if isinstance(c.get("source"), list) else str(c.get("source") or ""))[:MAX_CELL_TEXT]}
        for c in cells[:MAX_CELLS]
        if isinstance(c, dict)
    ]


def file_row(path: str, body: bytes, mtime: int = 0) -> dict[str, Any]:
    """파일 하나 → 계획 요청의 한 줄(화면이 하는 일과 같다). 시험 · 서버 쪽 다시 계획에서 쓴다"""
    text = body.decode("utf-8", errors="replace")
    row: dict[str, Any] = {"path": path, "blob": blob_id(body), "size": len(body), "mtime": mtime}
    if path.lower().endswith(".ipynb"):
        row["cells"] = notebook_cells(text)
    else:
        row["head"] = text[:MAX_HEAD]
    return row


def read_texts(repo: Path, paths: list[str]) -> dict[str, str]:
    """서버 안 저장소의 작업 폴더에서 앞부분 글 — 폴더 추천 키워드용(작업 폴더 = 마지막 커밋 내용)"""
    out: dict[str, str] = {}
    for path in paths:
        target = repo / path
        try:
            raw = target.read_bytes()[:400_000].decode("utf-8", errors="replace")
        except OSError:
            continue
        out[path] = "\n".join(c["source"] for c in notebook_cells(raw)) if path.lower().endswith(".ipynb") else raw[:MAX_HEAD]
    return out
