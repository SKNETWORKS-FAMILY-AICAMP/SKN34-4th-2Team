"""목록 수집 결과를 상세 크롤 입력으로 바꾼다. 인기순으로 정렬하고 이미 받은 건 뺀다.

    python build_detail_queue.py \
        --list output/saramin_all_raw.json \
        --detail output/saramin_detail.jsonl \
        --output output/saramin_detail_queue.json

정렬 기준 (앞에 올수록 먼저 받는다):
1. `badge`에 "TOP100"이 있는 공고 — 사이트가 지원자 수로 매긴 인기 표식
2. 같은 등급 안에서는 대분류 내 지원순 순위(`list_rank`)가 앞선 것
3. 그다음 마감이 늦은 것 — 받아 두면 오래 쓸 수 있다

**다섯 자리 중 한 자리는 가장 오래 기다린 공고에 준다.** 큐는 밤마다 처음부터 다시
만들어지므로, 인기 순위만으로 세우면 뒤쪽 공고는 어제도 뒤였고 오늘도 뒤다. 밤에
받는 양은 한정돼 있어 순위가 밀린 공고는 영영 차례가 오지 않는다. 실제로 목록에서
본 4만 건 중 1만 5천 건이 제목만 있는 채로 남았다. 한 자리를 떼어 두면 인기 공고를
거의 그대로 지키면서도 밀린 것이 매일 조금씩 줄어든다.

한 공고가 여러 대분류에 걸리면(통합 채용) 가장 앞선 순위 하나만 남긴다.
상세를 이미 태그까지 받은 공고(`tags` 필드 있음)는 큐에서 뺀다. 상세 크롤러의
`--refetch-without tags` 와 같은 기준이라, 예전 파서로 받은 것은 다시 받는다.

이미지 공고는 목록에서 알 수 없어 여기서 못 거른다. 받은 뒤 인덱스에서 제외한다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from job_matching_bot.ingestion.excluded_roles import is_excluded

KST = timezone(timedelta(hours=9))
_DEADLINE_RE = re.compile(r"~\s*(\d{2})\.(\d{2})")


def deadline_key(support_text: str, now: datetime) -> str:
    """'~09.20(일)' 을 'YYYY-MM-DD' 로. 없으면 '9999' — 상시 채용은 뒤로 보내지 않고 앞에 둔다."""
    match = _DEADLINE_RE.search(support_text or "")
    if not match:
        return "9999-12-31"
    month, day = int(match.group(1)), int(match.group(2))
    year = now.year
    # 12월에 1월 마감을 보면 이듬해다.
    if month < now.month - 6:
        year += 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def priority(record: dict[str, Any], now: datetime) -> tuple[int, int, str]:
    top = 0 if "TOP100" in (record.get("badge") or "") else 1
    # `or`로 기본값을 주면 순위 0이 거짓으로 걸려 맨 뒤로 밀린다. 없을 때만 밀어낸다.
    raw_rank = record.get("list_rank")
    rank = 10**9 if raw_rank is None else int(raw_rank)
    # 마감이 늦을수록 앞에: 문자열 역순을 위해 음수 대신 뒤집힌 키를 쓴다.
    deadline = deadline_key(record.get("support_text", ""), now)
    return (top, rank, "".join(chr(0x10FFFF - ord(c)) for c in deadline))


OLDEST_EVERY = 5
"""몇 자리마다 한 번씩 '가장 오래 기다린 공고'를 끼워 넣나."""


def _interleave(
    ranked: list[dict[str, Any]],
    waiting_since: dict[str, str],
    every: int,
) -> list[dict[str, Any]]:
    """인기순 줄에 오래 기다린 공고를 [every]자리마다 하나씩 끼워 넣는다.

    처음 본 시각을 모르는 공고(그 값이 생기기 전에 쌓인 것)는 가장 오래 기다린
    것으로 본다. 실제로 그렇다 — 오래됐으니 기록이 없다.
    """
    if every <= 1 or not ranked:
        return ranked
    oldest = sorted(
        ranked,
        key=lambda r: waiting_since.get(str(r.get("source_job_id") or ""), ""),
    )
    picked: set[int] = set()
    out: list[dict[str, Any]] = []
    rank_i = old_i = 0
    while len(out) < len(ranked):
        take_old = len(out) % every == every - 1
        source = oldest if take_old else ranked
        i = old_i if take_old else rank_i
        while i < len(source) and id(source[i]) in picked:
            i += 1
        if i >= len(source):
            # 한쪽이 바닥나면 남은 쪽으로 채운다.
            source, i = (ranked, rank_i) if take_old else (oldest, old_i)
            while i < len(source) and id(source[i]) in picked:
                i += 1
            if i >= len(source):
                break
        out.append(source[i])
        picked.add(id(source[i]))
        if source is oldest:
            old_i = i + 1
        else:
            rank_i = i + 1
    return out


def build_queue(
    list_records: list[dict[str, Any]],
    detailed_ids: set[str],
    now: datetime,
    waiting_since: dict[str, str] | None = None,
    detail_categories: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]], Counter]:
    """목록에서 본 공고 중 상세를 받을 것을 골라 순서대로 세운다.

    `detail_categories`를 주면 **그 대분류만** 큐에 담는다. 목록은 전부 훑되 상세는
    일부만 받기 위한 것이다.

    일요일 전체 훑기가 14개 대분류를 훑는데, IT 밖 대분류의 상세를 다 받으려면
    13만 건에 38일이 걸린다. 하룻밤에 4,500건씩 받으니 다음 일요일 전에 못 끝내고,
    그러면 큐 숫자가 "밀린 양"이라는 뜻을 잃는다.

    목록만 훑어도 **사라짐 판정은 그대로 된다.** 그게 일요일 훑기의 다른 역할이고,
    거기에는 상세가 필요 없다. 상세를 넓히고 싶으면 대분류를 매일 훑는 목록에
    하나씩 추가한다. 그러면 며칠 걸리는지 미리 알고 시작할 수 있다.
    """
    allowed = set(detail_categories) if detail_categories is not None else None
    best: dict[str, dict[str, Any]] = {}
    stats: Counter = Counter()
    for record in list_records:
        job_id = str(record.get("source_job_id") or "")
        if not job_id:
            stats["id 없음"] += 1
            continue
        if allowed is not None and str(record.get("cat_mcls") or "") not in allowed:
            stats["상세 대상 아닌 대분류"] += 1
            continue
        if job_id in detailed_ids:
            stats["이미 상세 있음"] += 1
            continue
        if is_excluded(record.get("job_sectors") or []):
            stats["제외 직종(배달·배송·운전)"] += 1
            continue
        current = best.get(job_id)
        if current is None or priority(record, now) < priority(current, now):
            if current is not None:
                stats["대분류 중복(앞선 순위로 대체)"] += 1
            best[job_id] = record
        else:
            stats["대분류 중복"] += 1
    queue = sorted(best.values(), key=lambda r: priority(r, now))
    if waiting_since is not None:
        queue = _interleave(queue, waiting_since, OLDEST_EVERY)
    stats["큐에 담김"] = len(queue)
    stats["TOP100"] = sum(1 for r in queue if "TOP100" in (r.get("badge") or ""))
    return queue, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="인기순 상세 크롤 입력 만들기")
    parser.add_argument("--list", type=Path, default=Path("output/saramin_all_raw.json"))
    parser.add_argument("--detail", type=Path, default=Path("output/saramin_detail.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("output/saramin_detail_queue.json"))
    parser.add_argument("--limit", type=int, default=None, help="앞에서부터 이 건수만 담는다")
    args = parser.parse_args()

    list_records = json.loads(args.list.read_text(encoding="utf-8"))
    detailed: set[str] = set()
    if args.detail.exists():
        # str.splitlines()는 U+2028 같은 유니코드 줄바꿈에서도 끊는다. 공고 본문에
        # 그런 문자가 있어 한 건이 둘로 쪼개지므로 개행 문자로만 자른다.
        for line in args.detail.read_text(encoding="utf-8").split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # 크롤이 중단되며 잘린 마지막 줄
            if "tags" in row:
                detailed.add(str(row.get("source_job_id") or ""))

    now = datetime.now(KST)
    queue, stats = build_queue(list_records, detailed, now)
    if args.limit:
        queue = queue[: args.limit]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(queue, ensure_ascii=False), encoding="utf-8")

    print(f"목록 {len(list_records):,}건 → 큐 {len(queue):,}건 저장: {args.output}")
    for key, value in stats.most_common():
        print(f"  {key}: {value:,}")
    print(f"  예상 소요: {len(queue) * 4 / 3600:.1f}시간 (요청 간격 4초)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
