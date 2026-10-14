"""Small, one-run-per-case human review harness for the offline v2 core.

From cover_letter_rag:
  python -m evaluation.v2_eval --live --env-file PATH --limit 10

Existing case results are skipped unless --force is supplied. No DB or React access.
"""

import argparse
import json
import os
from pathlib import Path

from app.resume_review_v2 import ReviewEngineV2, ReviewInput
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.validation import ContractError


HERE = Path(__file__).resolve().parent
CASES = HERE / "v2_cases.json"
OUTPUT = HERE / "v2_results"


def render_review(result: dict, case: dict) -> str:
    candidate = result.get("candidate") or {}
    sentences = candidate.get("sentences") or []
    evidence = [*(case["experience"].get("existing_evidence") or []),
                *(result.get("extracted_evidence") or [])]
    by_id = {item["evidence_id"]: item for item in evidence}
    plan = result.get("plan") or {}

    def describe(item: dict) -> str:
        relations = []
        if item.get("supersedes_evidence_ids"):
            relations.append(f"supersedes={','.join(item['supersedes_evidence_ids'])}")
        if item.get("conflicts_with_evidence_ids"):
            relations.append(f"unresolved_conflict={','.join(item['conflicts_with_evidence_ids'])}")
        suffix = f" | {'; '.join(relations)}" if relations else ""
        return (f"- {item['evidence_id']} ({item['fact_type']}, {item['assertion_state']}): "
                f"{item['normalized_fact']} | 인용: {item['evidence_quote']}{suffix}")

    def group(title: str, ids: list[str]) -> list[str]:
        return ["", title, *(
            f"- {eid}: {by_id[eid]['normalized_fact']}" if eid in by_id else f"- {eid}: (근거 조회 필요)"
            for eid in ids
        )]

    lines = [
        f"# {case['case_id']} — {case['failure_type']}",
        "", "[기존 이력서]", case["experience"]["current_text"],
        "", "[질문]", case.get("question", ""),
        "", "[사용자 답변]", case.get("answer", ""),
        "", "[기존 Evidence]",
    ]
    lines.extend(describe(item) for item in evidence if item["source_type"] == "resume_text")
    lines.extend(["", "[새로 추출된 Evidence]"])
    lines.extend(describe(item) for item in evidence if item["source_type"] == "user_answer")
    lines.extend(["", "[Superseded / Contradicted Evidence]"])
    lines.extend(describe(item) for item in evidence if
                 item["assertion_state"] in {"superseded", "contradicted"} or
                 item.get("conflicts_with_evidence_ids"))
    lines.extend(group("[Core Evidence]", plan.get("core_evidence_ids") or []))
    lines.extend(group("[Supporting Evidence]", plan.get("supporting_evidence_ids") or []))
    lines.extend(group("[Preserved Evidence]", plan.get("preserved_evidence_ids") or []))
    lines.extend(["", "[Omitted Evidence + reason]"])
    lines.extend(f"- {item['evidence_id']}: {item['reason']}"
                 for item in result.get("omitted_evidence") or [])
    lines.extend(["", "[Revision Plan]", json.dumps(plan, ensure_ascii=False, indent=2),
                  "", "[Writer Sentences + Evidence IDs]"])
    lines.extend(f"- {sentence['text']} → {', '.join(sentence['evidence_ids'])}" for sentence in sentences)
    lines.extend(["", "[Final Suggested Text]", candidate.get("suggested_text") or "(수정안 없음)",
                  "", "[Validator Result]",
                  json.dumps(result.get("validation"), ensure_ascii=False, indent=2),
                  "", "[LLM Calls / Tokens / Latency]",
                  json.dumps(result.get("usage"), ensure_ascii=False),
                  "", "Human judgement:", "", "Reason:", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Authorize actual LLM calls")
    parser.add_argument("--env-file", type=Path, help="Optional private .env path; never copied to outputs")
    parser.add_argument("--model", help="Defaults to RESUME_V2_MODEL or OPENAI_MODEL")
    parser.add_argument("--effort", default="medium")
    parser.add_argument("--case-id", action="append", help="Run only these case IDs")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="Explicitly rerun existing cases")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.live:
        parser.error("live calls require --live; dry-run prevents accidental API spending")
    if not 1 <= args.limit <= 12:
        parser.error("--limit must be 1..12 for this small manual evaluation")
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
    # This is an offline quality fixture. Never send applicant/evaluation content
    # to an additional tracing provider just because the development .env enables it.
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is absent; provide a private --env-file or environment variable")
    model = args.model or os.getenv("RESUME_V2_MODEL") or os.getenv("OPENAI_MODEL")
    if not model:
        parser.error("set --model, RESUME_V2_MODEL, or OPENAI_MODEL")

    cases = json.loads(CASES.read_text(encoding="utf-8"))
    if args.case_id:
        selected = set(args.case_id)
        cases = [case for case in cases if case["case_id"] in selected]
        unknown = selected - {case["case_id"] for case in cases}
        if unknown:
            parser.error(f"unknown case IDs: {sorted(unknown)}")
    cases = cases[:args.limit]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    llm = LangChainReviewLLM(model, args.effort)
    engine = ReviewEngineV2(llm)
    failures = 0
    for case in cases:
        json_path = args.output_dir / f"{case['case_id']}.json"
        md_path = args.output_dir / f"{case['case_id']}.md"
        if json_path.exists() and not args.force:
            print(f"SKIP {case['case_id']} (already run)")
            continue
        attempts_before = llm.attempted_calls
        usage_before = llm.recorded_usage.model_copy()
        try:
            request = ReviewInput.model_validate({
                key: value for key, value in case.items()
                if key in {"experience", "question", "answer", "answer_source_id", "job_requirements", "previous_question_keys"}
            })
            result = engine.run(request)
        except Exception as exc:
            # Do not dump exception arguments: SDK errors can contain request data.
            detail = str(exc) if isinstance(exc, ContractError) else ""
            print(f"ERROR {case['case_id']}: {type(exc).__name__} {detail} "
                  f"attempted_calls={llm.attempted_calls - attempts_before} "
                  f"recorded_tokens={llm.recorded_usage.input_tokens - usage_before.input_tokens}/"
                  f"{llm.recorded_usage.output_tokens - usage_before.output_tokens}")
            failures += 1
            continue
        payload = result.model_dump(mode="json")
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(render_review(payload, case), encoding="utf-8")
        print(f"DONE {case['case_id']} status={result.validation.status} calls={result.usage.calls} "
              f"tokens={result.usage.input_tokens}/{result.usage.output_tokens} "
              f"latency_ms={result.usage.latency_ms}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
