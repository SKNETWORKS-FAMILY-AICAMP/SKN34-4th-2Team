"""다른 태그 안에 들어가는 태그를 찾는다. 헷갈릴 수 있는 말의 후보다.

    python -m job_matching_bot.evaluation.scan_terms
    python -m job_matching_bot.evaluation.scan_terms --kind 직무 --top 40

## 왜 필요한가

`LIKE '%Java%'` 는 부분 문자열이라 JavaScript 도 걸린다. 실측으로 "Java" 검색
2,004건 중 198건(15%)이 Java 태그 없이 Javascript 만 있는 공고였다.

그렇다고 단어 경계로 일괄 차단하면 안 된다. 기술 태그 220종에서 겹치는 16개 중
**14개는 같은 계열**이다(Spring⊂SpringBoot, SQL⊂MySQL, HTML⊂HTML5 …). 막으면
열네 곳이 나빠지고 두 곳만 고쳐진다.

그래서 `store_search.CONFUSABLE` 에 **뜻이 갈리는 것만** 적는다. 이 도구는 그
후보를 뽑아 준다. 판단은 사람이 한다 — "같은 계열인가"는 글자로 알 수 없다.

## 언제 다시 도나

수집이 새 기술·직무 태그를 들여올 때다. 그때 다시 돌려 **이미 처리한 것을 뺀 나머지**만
보면 된다. 전부를 다시 훑지 않아도 된다.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter

from job_matching_bot.retrieval.store_search import CONFUSABLE

# 이보다 짧으면 어디에나 들어가 후보가 너무 많아진다.
MIN_LENGTH = 2


def tags(store_path, column: str) -> Counter[str]:
    connection = sqlite3.connect(f"{store_path.resolve().as_uri()}?mode=ro", uri=True)
    counter: Counter[str] = Counter()
    try:
        for (raw,) in connection.execute(
            f"SELECT {column} FROM jobs WHERE status='OPEN'"
        ):
            try:
                counter.update(t.strip() for t in json.loads(raw or "[]") if t.strip())
            except json.JSONDecodeError:
                continue
    finally:
        connection.close()
    return counter


def overlaps(counter: Counter[str]) -> list[tuple[int, str, list[str]]]:
    """어떤 태그가 어떤 태그 안에 들어가나. 흔한 것부터."""
    names = list(counter)
    found = []
    for short in names:
        if len(short) < MIN_LENGTH:
            continue
        inside = [
            long for long in names
            if long != short and short.lower() in long.lower() and len(long) > len(short)
        ]
        if inside:
            found.append((counter[short], short, sorted(inside, key=lambda n: -counter[n])))
    found.sort(reverse=True)
    return found


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="헷갈릴 수 있는 말 후보 찾기")
    parser.add_argument("--kind", choices=["기술", "직무", "전부"], default="전부")
    parser.add_argument("--top", type=int, default=20, help="종류마다 보여 줄 개수")
    parser.add_argument("--all", action="store_true", help="이미 처리한 말도 함께 본다")
    args = parser.parse_args()

    from job_matching_bot.ingest import DEFAULT_STORE

    if not DEFAULT_STORE.exists():
        print(f"저장소가 없습니다: {DEFAULT_STORE}")
        return 1

    columns = {"기술": "tech_stack", "직무": "keywords"}
    kinds = list(columns) if args.kind == "전부" else [args.kind]

    for kind in kinds:
        counter = tags(DEFAULT_STORE, columns[kind])
        found = overlaps(counter)
        handled = [f for f in found if f[1].lower() in CONFUSABLE]
        todo = [f for f in found if f[1].lower() not in CONFUSABLE]

        print(f"\n{'=' * 72}")
        print(f"{kind} 태그 {len(counter):,}종 · 다른 태그 안에 들어가는 것 {len(found):,}개")
        if handled and not args.all:
            names = ", ".join(f[1] for f in handled)
            print(f"이미 처리함({len(handled)}): {names}")
        print()

        rows = found if args.all else todo
        for count, short, inside in rows[: args.top]:
            names = ", ".join(f"{n}({counter[n]:,})" for n in inside[:3])
            more = f" 외 {len(inside) - 3}" if len(inside) > 3 else ""
            mark = "*" if short.lower() in CONFUSABLE else " "
            print(f" {mark}{short:16s}({count:>5,})  ⊂  {names}{more}")
        if len(rows) > args.top:
            print(f"    … {len(rows) - args.top:,}개 더 (--top 으로 늘리세요)")

    print(f"\n{'=' * 72}")
    print("판단 기준: 두 말이 **같은 계열**인가.")
    print("  같음 → 그대로 둔다. Spring 으로 SpringBoot 를 찾는 것은 맞다.")
    print("  다름 → store_search.CONFUSABLE 에 정규식을 적는다.")
    print("        뒤를 보는 경우:  'java': r'java(?!script)'")
    print("        앞을 보는 경우:  'go':   r'(?<![a-z])go'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
