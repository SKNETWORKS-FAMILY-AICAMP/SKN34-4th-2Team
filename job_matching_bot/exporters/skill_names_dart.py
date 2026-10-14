"""수집한 공고가 실제로 요구하는 기술 이름을 앱의 Dart 상수로 내보낸다.

    python -m job_matching_bot.exporters.skill_names_dart

앱은 이력서 기술스택 태그 후보로 이 목록을 쓴다. 손으로 고른 기본 목록만 두면 공고에
쓰인 표기(예: 'MS-SQL')를 사용자가 못 고르고, 그러면 검색에 걸리지 않는다.

예전에는 앱이 공고 8.4MB를 통째로 안고 있으면서 거기서 기술 이름을 뽑았다. 공고는
이제 서버에서 오므로 **이름 목록만** 남기면 된다.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

DEFAULT_OUTPUT = Path("lib/features/resume/ai_coach/data/generated/job_skill_names.g.dart")
# 한 번만 나온 이름은 오타이거나 그 회사만 쓰는 말일 때가 많다.
MIN_COUNT = 2

HEADER = '''// 자동 생성 파일. 직접 고치지 마세요.
// 만드는 법: python -m job_matching_bot.exporters.skill_names_dart
//
// 수집한 채용공고가 요구하는 기술 이름. {count}개 공고에서 {kept}개를 추렸다
// ({min_count}건 이상 나온 것만). 이력서 기술스택 태그 후보로 쓴다.

const jobSkillNames = <String>[
'''


def collect(store_path: Path, min_count: int) -> tuple[list[str], int]:
    from job_matching_bot.ingestion.job_store import open_store

    store = open_store(store_path).load()
    try:
        counts: Counter[str] = Counter()
        total = 0
        for record in store.all_records():
            total += 1
            job = record.job
            for name in [*job.required_skills, *job.preferred_skills, *job.tech_stack]:
                name = name.strip()
                if name:
                    counts[name] += 1
    finally:
        store.close()

    # 많이 쓰이는 이름부터. 같은 횟수면 이름순으로 두어 다시 만들어도 순서가 같다.
    kept = sorted(
        (name for name, count in counts.items() if count >= min_count),
        key=lambda name: (-counts[name], name.lower()),
    )
    return kept, total


def render(names: list[str], total: int, min_count: int) -> str:
    lines = [HEADER.format(count=total, kept=len(names), min_count=min_count)]
    for name in names:
        lines.append("  " + repr(name).replace('"', r"\"") + ",\n")
    lines.append("];\n")
    return "".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    from job_matching_bot.ingest import DEFAULT_STORE

    parser = argparse.ArgumentParser(description="기술 이름 목록 내보내기")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-count", type=int, default=MIN_COUNT)
    args = parser.parse_args()

    names, total = collect(args.store, args.min_count)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(names, total, args.min_count), encoding="utf-8", newline="\n")
    size = args.out.stat().st_size / 1024
    print(f"공고 {total:,}건에서 기술 이름 {len(names)}개 → {args.out} ({size:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
