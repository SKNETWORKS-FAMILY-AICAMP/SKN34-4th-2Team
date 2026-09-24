"""학생이 고른 자료로 복습 문제 — 자기 노트, 또는 연습장에서 연 .py · .ipynb.

수업 세트(auto.py)와 달리 출제 범위를 기억하지 않는다 — 학생이 고른 자료 전체로 한 번 낸다.
저장은 하지 않는다. 만든 문제를 돌려주면 LMS(Django)가 그 학생만 보는 세트로 넣는다.
"""

from __future__ import annotations

import time
from typing import Any

from study_notes.git_tools import notebook_to_text
from study_notes.pipeline import MAX_CHARS_PER_FILE, Material
from study_notes.practice.build import build_practice_set
from study_notes.practice.generate import practice_model_name
from study_notes.practice.increments import kind_counts_text, kind_mix
from study_notes.practice.runner import Runner

MAX_UPLOADS = 3
MAX_UPLOAD_CHARS = 60_000


def upload_materials(uploads: list[dict[str, str]]) -> list[Material]:
    """연습장에서 보낸 파일 — .ipynb 는 셀을 글로 푼다. 너무 길면 앞부분만(노트와 같은 한도)."""
    out: list[Material] = []
    for item in uploads[:MAX_UPLOADS]:
        name = str(item.get("name") or "notebook.py")
        raw = str(item.get("content") or "")[:MAX_UPLOAD_CHARS]
        text = notebook_to_text(raw) if name.lower().endswith(".ipynb") else raw
        if not text.strip():
            continue
        out.append({
            "path": name,
            "commit": "",
            "content": text[:MAX_CHARS_PER_FILE],
            "truncated": len(text) > MAX_CHARS_PER_FILE,
        })
    return out


def make_problems(materials: list[Material], *, scope_label: str, count: int, runner: Runner) -> dict[str, Any]:
    """{problems, model, usage, seconds}. 문제는 검증을 통과한 것만 — count 보다 적을 수 있다."""
    if not materials:
        raise ValueError("문제를 만들 자료가 비어 있어요.")
    started = time.monotonic()
    result = build_practice_set(
        scope_label=scope_label,
        materials=materials,
        runner=runner,
        kind_counts=kind_counts_text(kind_mix(count)),
    )
    return {
        "problems": [p.to_json() for p in result.problems],
        "model": practice_model_name(),
        "usage": vars(result.usage),
        "seconds": round(time.monotonic() - started, 1),
    }
