"""날짜별 복습 문제 — 파일 단위로 새로 생긴 부분만 출제한다.

수업일을 차례로 돌며 「이미 출제한 셀」 기록(coverage)을 이어 간다. 기록은 JSON 파일로
받고 돌려준다. 나중에 DB 를 붙이면 이 파일 자리만 바뀐다.

    # 계획만 (LLM 을 부르지 않는다 — 어느 파일의 어느 부분으로 몇 문제 낼지)
    python -m study_notes.practice.daily --repo https://github.com/ORG/REPO \\
        --dates 2026-09-11 2026-09-14 2026-09-15 --plan-only

    # 실제 출제 · 검증. 기록은 --coverage 에 남고 다음 실행이 이어 쓴다
    python -m study_notes.practice.daily --repo ... --dates 2026-09-16 --coverage cov.json

루트 .env 의 OPENAI_API_KEY, PRACTICE_MODEL 을 쓴다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from study_notes.git_tools import RepoCache, cache_root, parse_repo_url
from study_notes.practice.build import build_practice_set
from study_notes.practice.generate import practice_model_name
from study_notes.practice.increments import DayPlan, FileCoverage, plan_day
from study_notes.practice.runner import REPO_ROOT, PyodideRunner


def load_coverage(path: Path) -> dict[str, FileCoverage]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item["path"]: FileCoverage.from_json(item) for item in data.get("files", [])}


def save_coverage(path: Path, coverage: dict[str, FileCoverage]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"files": [c.to_json() for c in coverage.values()]}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


def describe(plan: DayPlan) -> str:
    rows = [f"[{plan.date}] 바뀐 파일 {len(plan.files)}개 · 출제 {len(plan.targets)}개 파일"]
    for f in plan.files:
        state = f"건너뜀 — {f.skipped}" if f.skipped else f"{f.quota}문제"
        cont = " · 이어짐" if f.continues and not f.skipped else ""
        rows.append(
            f"  {f.path}\n    새 셀 {len(f.new_cells)}개({f.new_chars:,}자) · 이미 출제한 셀 {len(f.seen_cells)}개 → {state}{cont}"
        )
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="날짜별 파일 단위 복습 문제")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--dates", nargs="+", required=True, help="YYYY-MM-DD, 오래된 날부터")
    parser.add_argument("--coverage", help="출제 범위 기록 JSON (없으면 새로 시작, 끝나면 저장)")
    parser.add_argument("--plan-only", action="store_true", help="LLM 을 부르지 않고 계획만 본다")
    parser.add_argument("--out", help="결과 JSON 폴더 (기본: 저장소 캐시 폴더/practice_daily)")
    args = parser.parse_args(argv)

    load_dotenv(REPO_ROOT / ".env", override=False)
    cov_path = Path(args.coverage) if args.coverage else None
    coverage = load_coverage(cov_path) if cov_path else {}
    out_dir = Path(args.out) if args.out else cache_root() / "practice_daily"
    cache = RepoCache("trial", "practice", parse_repo_url(args.repo), args.branch)
    cache.sync()
    runner = None if args.plan_only else PyodideRunner()

    for date in sorted(args.dates):
        _shas, changed = cache.changed_files_on(date, [])
        files = [(f.path, f.commit, cache.read_file(f.commit, f.path)) for f in changed]
        plan = plan_day(date, files, coverage)
        print(describe(plan), flush=True)
        if not plan.targets:
            print("  → 출제할 새 내용 없음\n")
            continue
        if runner is not None:
            started = time.monotonic()
            result = build_practice_set(
                scope_label=f"{date} 수업 — 새로 진행한 부분",
                materials=plan.materials(),
                runner=runner,
                focus_note=plan.focus_note(),
            )
            by_file: dict[str, int] = {}
            for p in result.problems:
                for f in p.source_files or ["(근거 없음)"]:
                    by_file[f] = by_file.get(f, 0) + 1
            print(
                f"  → 문제 {len(result.problems)}개 · 파일별 {by_file} · LLM {result.usage.calls}회 "
                f"입력 {result.usage.input_tokens:,} 출력 {result.usage.output_tokens:,} · {practice_model_name()} · "
                f"{time.monotonic() - started:.1f}초"
            )
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{date}.json").write_text(
                json.dumps({"date": date, "plan": [
                    {"path": f.path, "quota": f.quota, "newCells": len(f.new_cells), "seenCells": len(f.seen_cells), "skipped": f.skipped}
                    for f in plan.files
                ], **result.to_json()}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        # 계획만 볼 때도 기록은 이어 간다 — 다음 날 계획이 앞날을 반영하도록
        coverage = plan.coverage_after(coverage)
        print()

    if cov_path:
        save_coverage(cov_path, coverage)
        print(f"[출제 범위 기록] {cov_path}")
    if runner is not None:
        print(f"[결과] {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
