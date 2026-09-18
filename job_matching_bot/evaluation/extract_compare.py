"""공고 요구역량 추출: LLM(`coach`) vs 요건 구간 사전 대조를 같은 공고로 잰다.

    python -m job_matching_bot.evaluation.extract_compare --sample 200

## 왜 있나

야간 배치는 LLM 추출을 끄고 사전 대조만 쓴다(`sync.py --no-llm`). 끈 이유와 효과를 잰
기록이 없었다. 켜면 무엇을 더 잡는지, 무엇을 지어내는지, 얼마나 걸리는지를 숫자로 남긴다.

## 재는 것

- 필수·우대 기술을 1개 이상 잡은 공고 비율, 공고당 기술 수
- 사전에 없는 기술(LLM만 잡을 수 있는 것)
- 근거 문장이 원문에 없어 버린 기술 수(지어낸 것)
- 두 방식이 같은 기술을 필수로 본 비율
- 건당 시간·토큰과 하루 신규 분량으로 환산

캐시를 쓰지 않는다. 캐시에 걸리면 시간과 토큰이 0으로 잡힌다.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from job_matching_bot.config import ARTIFACTS_DIR
from job_matching_bot.env import ensure_loaded

RUNS_DIR = ARTIFACTS_DIR / "eval_runs"


def sample_jobs(store: Path, size: int, seed: int) -> list[dict]:
    """열린 공고 중 상세가 있는 것을 무작위로. 이미지 본문도 섞인 그대로 둔다."""
    con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT job_id, title, description, body_is_image FROM jobs "
        "WHERE status='OPEN' AND description IS NOT NULL AND description != ''"
    ).fetchall()
    con.close()
    random.Random(seed).shuffle(rows)
    return [
        {"job_id": r[0], "title": r[1] or "", "body": r[2] or "", "body_is_image": bool(r[3])}
        for r in rows[:size]
    ]


def run_one(job: dict) -> dict:
    from job_matching_bot.coach.requirement_extractor import RequirementExtractor
    from job_matching_bot.coach.skill_source import _rule_based

    rule = _rule_based(job["title"], job["body"])
    began = time.perf_counter()
    try:
        result = RequirementExtractor().extract(job["title"], job["body"])
        skills = result.extraction.skills
        llm = {
            "required": [s.name for s in skills if s.requirement_type == "REQUIRED"],
            "preferred": [s.name for s in skills if s.requirement_type == "PREFERRED"],
            "unknown": [s.name for s in skills if s.requirement_type == "UNKNOWN"],
            "evidence": {s.name: s.evidence for s in skills},
            "category": {s.name: s.category for s in skills},
            "usage": result.usage,
            "attempts": result.attempts,
            "error": None,
        }
    except Exception as error:  # noqa: BLE001 — 실패도 결과다
        llm = {"required": [], "preferred": [], "unknown": [], "evidence": {}, "category": {}, "usage": {},
               "attempts": 0, "error": f"{type(error).__name__}: {str(error)[:200]}"}
    llm["seconds"] = round(time.perf_counter() - began, 2)
    return {
        **{k: job[k] for k in ("job_id", "title", "body_is_image")},
        "rule": {k: rule[k] for k in ("required_skills", "preferred_skills", "unknown_skills", "method")},
        "llm": llm,
    }


def summarize(results: list[dict], daily_new: int) -> dict:
    from job_matching_bot.ingestion.saramin_tech_vocab import _tech_keys
    from job_matching_bot.ingestion.skill_extractor import SKILL_ALIASES
    from job_matching_bot.matching.skill_normalize import canonical_skill

    dictionary = {canonical_skill(name) for name in SKILL_ALIASES} | set(_tech_keys())
    ok = [r for r in results if not r["llm"]["error"]]
    n = len(results)

    def has(r, side):
        if side == "rule":
            return bool(r["rule"]["required_skills"] or r["rule"]["preferred_skills"])
        return bool(r["llm"]["required"] or r["llm"]["preferred"])

    def count(r, side):
        if side == "rule":
            return len(r["rule"]["required_skills"]) + len(r["rule"]["preferred_skills"])
        return len(r["llm"]["required"]) + len(r["llm"]["preferred"])

    # LLM은 기술만이 아니라 도메인·태도(SOFT)도 뽑는다. 사전 대조와 견줄 것은 기술 갈래뿐이다.
    tech_kinds = {"LANGUAGE", "FRAMEWORK", "DATABASE", "INFRA", "TOOL"}
    kinds = [
        r["llm"]["category"].get(name, "")
        for r in ok for name in r["llm"]["required"] + r["llm"]["preferred"]
    ]
    outside = [
        name for r in ok for name in r["llm"]["required"] + r["llm"]["preferred"]
        if r["llm"]["category"].get(name) in tech_kinds and canonical_skill(name) not in dictionary
    ]
    llm_names = sum(count(r, "llm") for r in ok)
    dropped = sum(r["llm"]["usage"].get("dropped_unevidenced", 0) for r in ok)
    agree_total = agree_hit = 0
    for r in ok:
        rule_req = {canonical_skill(s) for s in r["rule"]["required_skills"]}
        llm_req = {canonical_skill(s) for s in r["llm"]["required"]}
        if rule_req:
            agree_total += len(rule_req)
            agree_hit += len(rule_req & llm_req)
    seconds = sorted(r["llm"]["seconds"] for r in ok)
    tokens_in = [r["llm"]["usage"].get("input_tokens", 0) for r in ok]
    tokens_out = [r["llm"]["usage"].get("output_tokens", 0) for r in ok]
    text = [r for r in results if not r["body_is_image"]]
    return {
        "공고": n,
        "LLM 실패": n - len(ok),
        "본문이 이미지뿐": n - len(text),
        "기술을 1개 이상 잡은 공고": {
            "사전 대조": sum(has(r, "rule") for r in results),
            "LLM": sum(has(r, "llm") for r in ok),
        },
        "글 본문 공고 중 1개 이상": {
            "사전 대조": sum(has(r, "rule") for r in text),
            "LLM": sum(has(r, "llm") for r in text if not r["llm"]["error"]),
            "모수": len(text),
        },
        "공고당 필수+우대 기술 수(평균)": {
            "사전 대조": round(sum(count(r, "rule") for r in results) / max(n, 1), 2),
            "LLM": round(llm_names / max(len(ok), 1), 2),
        },
        "LLM이 뽑은 역량 갈래": dict(sorted(
            {k: kinds.count(k) for k in set(kinds)}.items(), key=lambda kv: -kv[1]
        )),
        "LLM이 잡은 기술(도메인·태도 제외) 중 사전에 없는 것": {
            "건수": len(outside),
            "기술 중 비율": round(len(outside) / max(sum(k in tech_kinds for k in kinds), 1), 3),
            "예": sorted(set(outside))[:40],
        },
        "근거가 원문에 없어 버린 기술": dropped,
        "사전 대조가 필수로 본 기술을 LLM도 필수로 본 비율": round(agree_hit / max(agree_total, 1), 3),
        "스키마 재시도(2회 이상)": sum(1 for r in ok if r["llm"]["attempts"] > 1),
        "건당 초": {
            "중앙값": seconds[len(seconds) // 2] if seconds else None,
            "90%": seconds[int(len(seconds) * 0.9)] if seconds else None,
        },
        "건당 토큰(평균)": {
            "입력": round(statistics.mean(tokens_in)) if tokens_in else None,
            "출력": round(statistics.mean(tokens_out)) if tokens_out else None,
        },
        f"하루 신규 {daily_new:,}건 환산": {
            "입력 토큰": round(statistics.mean(tokens_in) * daily_new) if tokens_in else None,
            "출력 토큰": round(statistics.mean(tokens_out) * daily_new) if tokens_out else None,
            "순서대로 부르면 분": round(statistics.mean(seconds) * daily_new / 60) if seconds else None,
        },
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="LLM 요구역량 추출 vs 사전 대조")
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--seed", type=int, default=14)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--daily-new", type=int, default=3814, help="환산에 쓸 하루 신규 상세 건수")
    parser.add_argument("--store", type=Path, default=ARTIFACTS_DIR / "job_store.sqlite")
    args = parser.parse_args()

    ensure_loaded()
    jobs = sample_jobs(args.store, args.sample, args.seed)
    print(f"표본 {len(jobs)}건 · 동시 {args.workers}", flush=True)
    results: list[dict] = []
    began = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for index, result in enumerate(pool.map(run_one, jobs), 1):
            results.append(result)
            if index % 20 == 0:
                print(f"  {index}/{len(jobs)} · {time.time() - began:.0f}초", flush=True)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = RUNS_DIR / f"{stamp}-extract.json"
    summary = summarize(results, args.daily_new)
    path.write_text(json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"결과 원본: {path} · {time.time() - began:.0f}초")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
