"""실습 문제 시험 생성 — 몇 개 날짜로 돌려 검증 통과율을 잰다.

Firestore·로그인 없이 돈다. 결과는 JSON 파일과 요약 표로 남기고 어디에도 저장하지 않는다.

    # 수업 저장소의 특정 날짜
    python -m study_notes.practice.trial --repo https://github.com/ORG/REPO --date 2026-09-15

    # 폴더 / 파일 지정
    python -m study_notes.practice.trial --repo ... --prefix day15/
    python -m study_notes.practice.trial --repo ... --files day15/a.ipynb day15/b.py

    # 로컬 파일
    python -m study_notes.practice.trial --local path/to/lesson.ipynb other.py

루트 .env의 OPENAI_API_KEY, PRACTICE_MODEL(비우면 gpt-5.6-luna)을 쓴다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from study_notes.git_tools import RepoCache, cache_root, is_learning_file, notebook_to_text, parse_repo_url
from study_notes.pipeline import MAX_CHARS_PER_FILE, Material
from study_notes.practice.build import BuildResult, build_practice_set
from study_notes.practice.generate import practice_model_name
from study_notes.practice.runner import REPO_ROOT, PyodideRunner

MAX_FILES = 8


def _material(path: str, commit: str, raw: str) -> Material:
    text = notebook_to_text(raw) if path.lower().endswith(".ipynb") else raw
    return {
        "path": path,
        "commit": commit[:8],
        "content": text[:MAX_CHARS_PER_FILE],
        "truncated": len(text) > MAX_CHARS_PER_FILE,
    }


def _from_repo(args: argparse.Namespace) -> tuple[str, list[Material]]:
    cache = RepoCache("trial", "practice", parse_repo_url(args.repo), args.branch)
    head = cache.sync()
    if args.date:
        _shas, changed = cache.changed_files_on(args.date, [])
        files = [(f.path, f.commit) for f in changed]
        label = f"{args.date} 수업"
    elif args.prefix:
        files = [(p, head) for p in cache.list_tree([args.prefix])]
        label = f"{args.prefix} 폴더"
    else:
        files = [(p, head) for p in args.files]
        label = ", ".join(args.files)
    if not files:
        raise SystemExit("고른 범위에 .ipynb · .py · .md 파일이 없습니다.")
    if len(files) > MAX_FILES:
        listing = "\n  ".join(p for p, _ in files)
        raise SystemExit(f"파일이 {len(files)}개라 너무 많습니다(최대 {MAX_FILES}). --files 로 고르세요:\n  {listing}")
    return label, [_material(p, c, cache.read_file(c, p)) for p, c in files]


def _from_local(paths: list[str]) -> tuple[str, list[Material]]:
    materials = []
    for raw_path in paths:
        path = Path(raw_path)
        if not is_learning_file(path.name):
            raise SystemExit(f".ipynb · .py · .md 만 읽습니다: {path}")
        materials.append(_material(path.name, "local", path.read_text(encoding="utf-8")))
    return ", ".join(m["path"] for m in materials), materials


def _summary(result: BuildResult, *, seconds: float, runner_version: str) -> str:
    rows = ["종류          생성  첫검증통과  고친뒤통과  종류바뀜  탈락"]
    total = [0, 0, 0, 0, 0]
    for kind, s in result.stats.items():
        if not s.drafted:
            continue
        values = (s.drafted, s.passed_first, s.passed_after_repair, s.converted, s.dropped)
        rows.append(f"{kind:<12} {values[0]:>4} {values[1]:>11} {values[2]:>11} {values[3]:>9} {values[4]:>5}")
        for i, v in enumerate(values):
            total[i] += v
    rows.append(f"{'합계':<11} {total[0]:>4} {total[1]:>11} {total[2]:>11} {total[3]:>9} {total[4]:>5}")
    composition = {}
    for p in result.problems:
        composition[p.kind] = composition.get(p.kind, 0) + 1
    guesses = result.llm_output_guesses
    lines = [
        *rows,
        "",
        f"최종 문제 {len(result.problems)}개: "
        + ", ".join(f"{k} {n}" for k, n in composition.items()),
        f"LLM이 예상한 출력이 실제와 같음: {guesses['right']} / {guesses['right'] + guesses['wrong']}",
        f"모양이 깨져 버린 초안: {len(result.malformed)}",
        f"LLM {result.usage.calls}회 · 입력 {result.usage.input_tokens:,} · 출력 {result.usage.output_tokens:,} 토큰",
        f"모델 {practice_model_name()} · Pyodide {runner_version or '(실행한 코드 없음)'} · {seconds:.1f}초",
    ]
    if result.dropped:
        lines += ["", "탈락 이유:"]
        for d in result.dropped:
            after = f" → 고친 뒤: {d['afterRepair']}" if "afterRepair" in d else ""
            lines.append(f"  - [{d['kind']}] {d['topic']}: {d['firstFailure']}{after}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="실습 문제 시험 생성")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--repo", help="GitHub 수업 저장소 주소")
    source.add_argument("--local", nargs="+", help="로컬 수업 파일")
    parser.add_argument("--branch", default="main")
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--date", help="YYYY-MM-DD (KST)")
    scope.add_argument("--prefix", help="폴더 경로")
    scope.add_argument("--files", nargs="+", help="파일 경로들")
    parser.add_argument("--no-repair", action="store_true", help="떨어진 문제를 고쳐 달라고 하지 않는다")
    parser.add_argument("--out", help="결과 JSON 경로 (기본: 저장소 캐시 폴더/practice_runs)")
    args = parser.parse_args(argv)
    if args.repo and not (args.date or args.prefix or args.files):
        parser.error("--repo 에는 --date · --prefix · --files 중 하나가 필요합니다")

    # 셸에서 넘긴 값이 파일보다 우선이다(override=False)
    load_dotenv(REPO_ROOT / ".env", override=False)
    label, materials = _from_repo(args) if args.repo else _from_local(args.local)
    print(f"[범위] {label} — 파일 {len(materials)}개: {', '.join(m['path'] for m in materials)}", flush=True)

    runner = PyodideRunner()
    started = time.monotonic()
    result = build_practice_set(
        scope_label=label, materials=materials, runner=runner, repair=not args.no_repair,
    )
    seconds = time.monotonic() - started

    out = Path(args.out) if args.out else (
        cache_root() / "practice_runs" / f"{datetime.now():%Y%m%d-%H%M%S}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"scope": label, "files": [m["path"] for m in materials], **result.to_json()},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(_summary(result, seconds=seconds, runner_version=runner.version))
    print(f"\n[결과] {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
