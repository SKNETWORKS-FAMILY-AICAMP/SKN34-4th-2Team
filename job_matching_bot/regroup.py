"""같은 공고를 묶어 `jobs.group_key` 에 적는다. 판정 규칙은 `retrieval/grouping.py`.

    python -m job_matching_bot.regroup              # 무엇이 묶일지만 보여 준다
    python -m job_matching_bot.regroup --apply      # 실제로 적는다
    python -m job_matching_bot.regroup --show 20    # 새로 묶인 짝을 20개까지 보여 준다

두 출처의 적재가 **모두 끝난 뒤** 부른다. 한쪽만 들어온 상태에서 돌리면 짝을 못 찾는다.

## 조용히 틀리지 않게

묶기가 잘못되면 대표가 아닌 공고가 인덱스에서 빠진다. 학생 화면에서는 그냥 공고가
없는 것으로 보이므로, 틀렸다는 사실 자체가 눈에 띄지 않는다. 그래서 셋을 둔다.

1. `--apply` 없이 부르면 아무것도 쓰지 않는다. 기본값이 이쪽이다
2. **오늘 새로 묶인 짝**을 리포트에 남긴다. 어제의 `group_key` 와 견줘 찾는다
3. 새 짝이 평소의 `SURGE_RATIO` 배를 넘으면 **적지 않고 멈춘다.** 규칙이 헐거워졌거나
   사이트가 제목 표기를 바꾼 신호다. 조용히 틀리는 것보다 안 하고 알리는 편이 낫다
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.ingestion.job_store import open_store
from job_matching_bot.retrieval import grouping

DEFAULT_STORE = ARTIFACTS_DIR / "job_store.sqlite"
DEFAULT_REPORT = ARTIFACTS_DIR / "regroup_report.json"

# 새 짝이 이미 있던 짝의 이 배수를 넘으면 멈춘다. 첫 실행은 견줄 어제가 없으므로 지나간다.
SURGE_RATIO = 3.0
# 첫 실행이나 짝이 얼마 없을 때는 배수가 쉽게 튄다. 이 수 아래면 급증으로 보지 않는다.
SURGE_FLOOR = 200


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="같은 공고 묶기")
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--apply", action="store_true", help="실제로 적는다")
    parser.add_argument("--show", type=int, default=8, help="새로 묶인 짝을 몇 개 보여 줄지")
    parser.add_argument("--force", action="store_true", help="급증해도 멈추지 않는다")
    args = parser.parse_args()

    store = open_store(args.store)
    try:
        jobs = [r.job for r in store.all_records() if r.job.status == "OPEN"]
        before = store.group_keys()
        started = datetime.now()
        groups, reps = grouping.plan(jobs)
        elapsed = (datetime.now() - started).total_seconds()

        members: dict[str, list[str]] = {}
        for job_id, key in groups.items():
            members.setdefault(key, []).append(job_id)
        multi = {k: v for k, v in members.items() if len(v) > 1}

        # 어제 이 묶음에 속하지 않던 공고가 있으면 오늘 새로 묶인 짝이다.
        fresh = [k for k, ids in multi.items() if any(before.get(i) != k for i in ids)]
        had = len(multi) - len(fresh)

        by_id = {job.job_id: job for job in jobs}
        report = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "jobs": len(jobs), "groups": len(members), "pairs": len(multi),
            "new_pairs": len(fresh), "representatives": len(reps),
            "dropped_from_index": len(jobs) - len(reps),
            "seconds": round(elapsed, 1),
        }
        print(f"공고 {len(jobs):,} → 묶음 {len(members):,}  ({elapsed:.0f}초)")
        print(f"  짝 {len(multi):,}  (어제까지 {had:,} · 오늘 새로 {len(fresh):,})")
        print(f"  대표 {len(reps):,} · 인덱스에서 빠지는 공고 {len(jobs) - len(reps):,}")

        if args.show and fresh:
            print(f"\n오늘 새로 묶인 짝 (앞 {min(args.show, len(fresh))}개)")
            for key in fresh[: args.show]:
                print("  ---")
                for job_id in members[key]:
                    job = by_id[job_id]
                    mark = "★" if job_id in reps else " "
                    print(f"   {mark} {job.source:13} {job.company[:14]:16} {job.title[:44]}")

        surge = had >= SURGE_FLOOR and len(fresh) > had * SURGE_RATIO
        if surge:
            report["surge"] = True
            print(
                f"\n[멈춤] 새 짝 {len(fresh):,}개가 기존 {had:,}개의 {SURGE_RATIO}배를 넘습니다."
                " 규칙이나 사이트 표기가 바뀌었을 수 있습니다."
            )
            if not args.force:
                print("  적지 않았습니다. 확인한 뒤 --force 를 붙이세요.")

        if args.apply and not (surge and not args.force):
            changed = store.set_group_keys(groups)
            report["written"] = changed
            print(f"\n{changed:,}건에 묶음 표시를 적었습니다.")
        elif args.apply:
            report["written"] = 0
        else:
            print("\n계획만 보였습니다. 실제로 적으려면 --apply 를 붙이세요.")

        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"리포트 {args.report}")
        return 2 if surge and not args.force else 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
