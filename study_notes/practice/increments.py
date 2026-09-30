"""파일 단위 출제 — 지난번 뒤로 새로 생긴 수업 내용만 골라낸다.

수업이 중간에 끝나면 다음 날 같은 노트북에 셀을 이어 붙인다. 34기 multimodal 의
02_video_rag_frame_extraction.ipynb 는 9/14 에 셀 11개, 9/15 에 21개였고 앞 10개가
똑같았다. 날짜마다 파일 전체로 출제하면 같은 내용으로 문제가 두 번 나온다.

그래서 파일마다 「이미 출제한 셀」의 지문을 기억해 두고, 새 셀로만 출제한다.

- 셀: 노트북은 셀 그대로, .py · .md 는 빈 줄로 나눈 덩어리. 빈 셀은 버린다
- 새 셀: 지문이 처음 보는 것. 다만 이미 본 셀과 90% 넘게 같으면(오타 수정 등) 본 것으로 친다
- 새 내용이 너무 적으면 그날 그 파일은 건너뛴다
- 저장은 하지 않는다. FileCoverage 를 받고 돌려줄 뿐이다(지금은 JSON, 나중에 DB)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from study_notes.git_tools import is_web_file
from study_notes.pipeline import MAX_CHARS_PER_FILE, Material

SIMILAR_RATIO = 0.9
MIN_NEW_CHARS = 200
MIN_PER_FILE = 1
# 그날 수업 파일이 하나뿐이어도 8문제는 낸다
MAX_PER_FILE = 8
# 코드 셀이 없는 파일(설명만 있는 노트북 · .md)이 받을 수 있는 문제 수 — 모두 개념 문제
MAX_CONCEPT_ONLY = 2
SUMMARY_CHARS = 600

# 하루 문제 구성 — 연습장에서 돌려 보는 코드 문제를 중심으로(개념 확인은 성취도평가도 한다)
KIND_MIX: dict[str, int] = {
    "concept": 2, "code_output": 3, "code_blank": 2, "code_fix": 2, "code_write": 2, "code_scratch": 1,
}
DAY_QUOTA = sum(KIND_MIX.values())  # 12
# 남은 개수가 12보다 적을 때(파일이 하나뿐이거나 같은 날 늦은 커밋 추가분) 이 순서로 채운다 — 가벼운 코드 문제부터.
# 처음부터 문제는 7번째 — 파일 하나짜리 날(8문제)에도 하나는 들어간다
_FILL_ORDER = [
    "code_output", "code_blank", "concept", "code_fix", "code_write", "code_output",
    "code_scratch", "code_blank", "concept", "code_fix", "code_write", "code_output",
]


def is_js_file(path: str) -> bool:
    return path.lower().endswith(".js")


def kind_mix(total: int, *, sql: bool = False, web: bool = False, js: bool = False) -> dict[str, int]:
    """문제 total 개의 종류별 개수. total 이 하루 구성(12)이면 KIND_MIX 그대로.

    sql — 그날 자료가 SQL(.sql)이면 코드 문제 대신 SQL 조회 문제를 낸다. 파이썬 코드 문제는 수업과 상관없어진다.
    web — 웹 수업(.html · .css)이면 1/3 개념 + 웹 실습(web_task). 태그 · 속성 · 선택자처럼 외워 둘 개념이 많다.
    js — JS 수업(.js)이면 1/3 개념 + JS 코드 문제(종류는 파이썬 코드 문제와 같다, js_problem.py).
    """
    if web:
        concept = round(total / 3)
        return {"concept": concept, "web_task": total - concept}
    if js:
        concept = round(total / 3)
        mix = {"concept": concept}
        for kind in [k for k in _FILL_ORDER if k != "concept"][:max(0, total - concept)]:
            mix[kind] = mix.get(kind, 0) + 1
        return mix
    if sql:
        concept = min(2, total // 4)
        return {"concept": concept, "sql_query": total - concept}
    if total >= DAY_QUOTA:
        return dict(KIND_MIX)
    mix: dict[str, int] = {}
    for kind in _FILL_ORDER[:max(0, total)]:
        mix[kind] = mix.get(kind, 0) + 1
    return mix


def is_sql_file(path: str) -> bool:
    return path.lower().endswith(".sql")


def kind_counts_text(mix: dict[str, int]) -> str:
    """'concept 2개, code_output 2개, …' — 출제 지시에 넣는 글"""
    return ", ".join(f"{k} {n}개" for k, n in mix.items() if n)


@dataclass(frozen=True)
class Cell:
    kind: str  # 'code' | 'markdown' | 'text'
    text: str

    @property
    def fingerprint(self) -> str:
        return hashlib.sha1(_normalize(self.text).encode("utf-8")).hexdigest()[:16]


@dataclass
class FileCoverage:
    """한 파일에서 이미 출제에 쓴 셀. 비슷한 셀을 찾으려고 글자도 짧게 남긴다."""

    path: str
    fingerprints: list[str] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)
    last_commit: str = ""
    last_date: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "fingerprints": self.fingerprints,
            "samples": self.samples,
            "lastCommit": self.last_commit,
            "lastDate": self.last_date,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "FileCoverage":
        return cls(
            path=data["path"],
            fingerprints=list(data.get("fingerprints", [])),
            samples=list(data.get("samples", [])),
            last_commit=data.get("lastCommit", ""),
            last_date=data.get("lastDate", ""),
        )


@dataclass
class FileIncrement:
    path: str
    commit: str
    new_cells: list[Cell]
    seen_cells: list[Cell]
    new_chars: int
    skipped: str = ""  # 건너뛴 이유. 비어 있으면 출제 대상
    quota: int = 0

    @property
    def has_code(self) -> bool:
        """새 부분에 코드 셀이 있는지 — 없으면(설명만 있는 노트북 · .md) 개념 문제만 낸다"""
        return any(c.kind == "code" for c in self.new_cells)

    @property
    def continues(self) -> bool:
        """앞서 출제한 부분이 있는 파일 — 수업이 이어진 것"""
        return bool(self.seen_cells)


@dataclass
class DayPlan:
    date: str
    files: list[FileIncrement]

    @property
    def targets(self) -> list[FileIncrement]:
        return [f for f in self.files if not f.skipped]

    @property
    def total(self) -> int:
        """이번에 낼 문제 수. 파일이 적어 파일당 상한에 걸리면 하루 몫보다 적을 수 있다."""
        return sum(f.quota for f in self.targets)

    def kind_counts(self) -> str:
        """종류별 개수 — 'concept 2개, code_output 2개, …'. SQL 조회 문제는 SQL 수업 파일에 나눈 몫만큼.

        예전엔 .sql 이 하나라도 있으면 코드 문제를 모두 SQL 로 냈다. 파이썬 파일 7개 + .sql 1개인 날(web_crawling 07-01)
        LLM 이 「SQL 자료는 파일 하나라 SQL 10문제는 못 낸다」며 빈 결과를 돌려줬다(2026-09-29)."""
        sql = sum(f.quota for f in self.targets if is_sql_file(f.path))
        js = sum(f.quota for f in self.targets if is_js_file(f.path))
        web = sum(f.quota for f in self.targets if is_web_file(f.path) and not is_js_file(f.path))
        if sql and sql >= self.total:
            return kind_counts_text(kind_mix(self.total, sql=True))
        mix = kind_mix(self.total - sql - web - js)
        # 코드가 없는 파일의 몫은 개념 문제로 — 그만큼 코드 문제를 뒤(채우는 순서의 끝)부터 뺀다(LLM파트 09-07)
        concept_only = sum(f.quota for f in self.targets if not f.has_code and not is_sql_file(f.path))
        extra = max(0, concept_only - mix.get("concept", 0))
        for kind in reversed(_FILL_ORDER):
            if extra == 0:
                break
            if kind != "concept" and mix.get(kind, 0) > 0:
                mix[kind] -= 1
                mix["concept"] = mix.get("concept", 0) + 1
                extra -= 1
        if sql:
            mix["sql_query"] = sql
        if web:
            # 웹 파일 몫은 따로 — 1/3 개념 + 웹 실습
            for kind, n in kind_mix(web, web=True).items():
                mix[kind] = mix.get(kind, 0) + n
        if not js:
            return kind_counts_text(mix)
        # .js 몫 — 코드 문제 종류는 파이썬과 같은 이름이라 JavaScript 로 낼 것을 따로 적는다
        js_mix = kind_mix(js, js=True)
        for kind, n in js_mix.items():
            mix[kind] = mix.get(kind, 0) + n
        js_code = {k: n for k, n in js_mix.items() if k != "concept"}
        return f'{kind_counts_text(mix)} — 그중 JavaScript 코드 문제("language": "javascript"): {kind_counts_text(js_code)}'

    def materials(self) -> list[Material]:
        """LLM 에 넘길 자료 — 파일마다 「앞부분 요약 + 새 부분」"""
        out: list[Material] = []
        for f in self.targets:
            body = _material_text(f)
            out.append({
                "path": f.path,
                "commit": f.commit[:8],
                "content": body[:MAX_CHARS_PER_FILE],
                "truncated": len(body) > MAX_CHARS_PER_FILE,
            })
        return out

    def focus_note(self) -> str:
        """출제 지시에 덧붙일 말 — 새 부분에서만, 파일별 개수"""
        if not self.targets:
            return ""
        lines = [
            "각 파일의 [새로 진행한 부분]에서만 출제하세요. [앞서 배운 부분]은 문맥으로만 참고하고 다시 묻지 마세요.",
            "파일별 문제 수(합이 전체 개수):",
            *[f"- {f.path}: {f.quota}개{_file_tag(f)}" for f in self.targets],
        ]
        return "\n".join(lines)

    def coverage_after(self, previous: dict[str, FileCoverage]) -> dict[str, FileCoverage]:
        """출제에 쓴 파일의 새 셀을 「이미 출제함」으로 더한 새 기록. 건너뛴 파일은 그대로 둔다."""
        result = {k: FileCoverage.from_json(v.to_json()) for k, v in previous.items()}
        for f in self.targets:
            cov = result.setdefault(f.path, FileCoverage(path=f.path))
            for cell in f.new_cells:
                if cell.fingerprint not in cov.fingerprints:
                    cov.fingerprints.append(cell.fingerprint)
                    cov.samples.append(_normalize(cell.text)[:400])
            cov.last_commit = f.commit
            cov.last_date = self.date
        return result


# ── 셀로 나누기 ──────────────────────────────────────────


def split_cells(path: str, raw: str) -> list[Cell]:
    if path.lower().endswith(".ipynb"):
        try:
            nb = json.loads(raw)
        except json.JSONDecodeError:
            return _split_blocks(raw, "text")
        cells = []
        for c in nb.get("cells", []):
            source = c.get("source", "")
            text = "".join(source) if isinstance(source, list) else str(source)
            if text.strip():
                cells.append(Cell(kind="markdown" if c.get("cell_type") == "markdown" else "code", text=text.strip("\n")))
        return cells
    # 웹 파일(.html · .css · .js)도 코드다 — 설명만 있는 파일로 보면 개념 문제 2개로 묶인다(has_code)
    kind = "code" if path.lower().endswith((".py", ".sql")) or is_web_file(path) else "text"
    return _split_blocks(raw, kind)


def _split_blocks(raw: str, kind: str) -> list[Cell]:
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    return [Cell(kind=kind, text=b.strip("\n")) for b in blocks if b.strip()]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


# ── 새 셀 찾기 ───────────────────────────────────────────


def diff_file(path: str, commit: str, raw: str, coverage: FileCoverage | None) -> FileIncrement:
    cells = split_cells(path, raw)
    seen_fp = set(coverage.fingerprints) if coverage else set()
    samples = coverage.samples if coverage else []
    new_cells: list[Cell] = []
    seen_cells: list[Cell] = []
    for cell in cells:
        if cell.fingerprint in seen_fp or _similar_to_any(cell.text, samples):
            seen_cells.append(cell)
        else:
            new_cells.append(cell)
    new_chars = sum(len(_normalize(c.text)) for c in new_cells)
    skipped = ""
    if not new_cells:
        skipped = "새로 생긴 셀 없음"
    elif new_chars < MIN_NEW_CHARS:
        skipped = f"새 내용이 {new_chars}자로 적음"
    return FileIncrement(path=path, commit=commit, new_cells=new_cells, seen_cells=seen_cells, new_chars=new_chars, skipped=skipped)


def _similar_to_any(text: str, samples: list[str]) -> bool:
    norm = _normalize(text)[:400]
    if len(norm) < 20:
        # 짧은 셀(import 한 줄 등)은 비슷함으로 판단하지 않는다 — 지문이 같을 때만 본 것
        return False
    return any(SequenceMatcher(None, norm, s).ratio() >= SIMILAR_RATIO for s in samples if abs(len(s) - len(norm)) < len(norm) * 0.3)


# ── 하루 계획 ────────────────────────────────────────────


def plan_day(
    date: str,
    files: list[tuple[str, str, str]],
    coverage: dict[str, FileCoverage],
    quota: int = DAY_QUOTA,
) -> DayPlan:
    """files: [(경로, 커밋, 원문)]. 새 내용이 많은 파일에 문제를 더 나눈다.
    quota — 이번에 낼 수 있는 문제 수. 같은 날 늦은 커밋으로 다시 돌 때는 하루 몫에서 이미 낸 만큼 뺀다."""
    increments = [diff_file(p, c, raw, coverage.get(p)) for p, c, raw in files]
    targets = [f for f in increments if not f.skipped]
    # 파일이 너무 많으면 새 내용이 많은 순으로 quota 개까지만
    targets.sort(key=lambda f: -f.new_chars)
    for f in targets[max(0, quota):]:
        f.skipped = "하루 몫을 다 냄" if quota <= 0 else "그날 출제 파일 수를 넘음"
    targets = targets[:quota]
    _distribute(targets, quota)
    return DayPlan(date=date, files=increments)


def _distribute(targets: list[FileIncrement], quota: int) -> None:
    """파일마다 1개씩 주고, 남은 개수는 한 개씩 「새 내용 ÷ (받은 수 + 1)」이 가장 큰 파일에 준다.
    합이 정확히 quota 이고(파일당 최대치가 허락하는 한) 새 내용이 많은 파일이 더 받는다.
    코드가 없는 파일은 MAX_CONCEPT_ONLY 까지만 — 설명 글이 길어 5문제를 받았다가 코드 문제를 못 낸 날이 있었다."""
    for f in targets:
        f.quota = MIN_PER_FILE
    for _ in range(quota - MIN_PER_FILE * len(targets)):
        open_ = [f for f in targets if f.quota < (MAX_PER_FILE if f.has_code or is_sql_file(f.path) else MAX_CONCEPT_ONLY)]
        if not open_:
            break
        best = max(open_, key=lambda f: f.new_chars / (f.quota + 1))
        best.quota += 1


def _material_text(f: FileIncrement) -> str:
    parts = []
    if f.seen_cells:
        parts.append("[앞서 배운 부분 — 요약, 다시 묻지 않음]\n" + _summary(f.seen_cells))
    parts.append(("[새로 진행한 부분]\n" if f.seen_cells else "") + "\n\n".join(_cell_text(c, _fence(f.path)) for c in f.new_cells))
    return "\n\n".join(parts)


def _summary(cells: list[Cell]) -> str:
    """앞부분은 제목과 정의 이름만 — 문맥은 주되 길게 넘기지 않는다"""
    heads: list[str] = []
    for c in cells:
        if c.kind == "markdown":
            heads += [l.strip() for l in c.text.splitlines() if l.strip().startswith("#")]
        else:
            heads += [l.strip() for l in c.text.splitlines() if re.match(r"\s*(def|class)\s+\w+", l)]
    text = "\n".join(dict.fromkeys(heads))
    return text[:SUMMARY_CHARS] or "(요약할 제목 없음)"


def _file_tag(f: FileIncrement) -> str:
    """파일별 지시에 붙이는 말 — 그 파일 몫을 어떤 문제로 낼지"""
    if is_js_file(f.path):
        return ' (JavaScript — 코드 문제는 JavaScript 로, "language": "javascript")'
    if is_web_file(f.path) and any("<script" in c.text.lower() for c in f.new_cells):
        return " (HTML + JavaScript — web_task 에 <script> 를 써서 페이지를 다루는 문제로)"
    if not f.has_code and not is_sql_file(f.path):
        return " (코드 없음 — concept 문제만)"
    return ""


def _fence(path: str) -> str:
    """코드 블록 언어 — 웹 파일은 확장자대로"""
    ext = path.lower().rsplit(".", 1)[-1]
    return {"html": "html", "css": "css", "js": "javascript", "sql": "sql"}.get(ext, "python")


def _cell_text(c: Cell, lang: str = "python") -> str:
    return c.text if c.kind != "code" else f"```{lang}\n{c.text}\n```"
