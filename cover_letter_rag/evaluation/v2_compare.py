"""Run the untouched v1 follow-up with exactly the v2 fixture's question and answer.

Uses the existing v1 MemoryGateway and a synthetic preceding review. It does not
change production data, and does not ask a second model to fabricate an applicant
answer. Read the paired Markdown manually; this script makes no quality verdict.
"""

import argparse
import json
import os
from pathlib import Path

from app.config import get_settings
from app.models import ConfirmationAnswer, FirestoreResumeReviewRequest
from app.resume_review import ResumeReviewService, extract_review_fields
from app.review_workflow import digest, item_references
from evaluation.review_eval import MemoryGateway

HERE = Path(__file__).resolve().parent
COMPARE_IDS = (
    "01_procedure_dump", "02_keep_technical_signal", "04_action_without_result",
    "05_confirmed_result", "09_job_only_technology",
)


def run_v1(case: dict) -> dict:
    exp = case["experience"]
    content = {"projects": [{
        "id": exp["experience_id"], "name": exp["title"],
        "description": exp["current_text"],
    }]}
    field_path = "projects[0].description"
    fields, _ = extract_review_fields(content)
    refs = item_references(content, fields)
    previous = {
        "review_id": "baseline", "input_hash": digest(content),
        "item_refs": refs, "confirmed_answers": [], "requirement_map": [],
        "summary": "", "questions": [{
            "question_id": "comparison-question", "field_path": field_path,
            "question": case["question"], "reason": "비교용 동일 질문",
            "topic": "action", "priority": 1,
        }],
    }
    gateway = MemoryGateway(content, {"source": {"job_id": "none", "snapshot_hash": "none"}})
    gateway.states["baseline"] = {"response": previous}
    service = ResumeReviewService(get_settings(), gateway)
    request = FirestoreResumeReviewRequest(
        cohort_id="comparison", resume_id="comparison", review_mode="general",
        previous_review_id="baseline", expected_input_hash=previous["input_hash"],
        answers=[ConfirmationAnswer(
            question_id="comparison-question", field_path=field_path,
            question=case["question"], answer=case["answer"],
        )],
    )
    response = service.review("offline-comparison-token", request).model_dump(mode="json")
    return {
        "case_id": case["case_id"],
        "v1_suggestions": [item for item in response["sentence_reviews"]
                           if item["field_path"] == field_path and item.get("suggested_revision")],
        "v1_questions": response["questions"],
        "v1_telemetry": response["telemetry"],
    }


def paired_markdown(case: dict, v1: dict, v2: dict) -> str:
    v1_text = "\n\n".join(item["suggested_revision"] for item in v1["v1_suggestions"]) or "(수정안 없음)"
    v2_text = (v2.get("candidate") or {}).get("suggested_text") or "(수정안 없음)"
    return "\n".join([
        f"# {case['case_id']} v1/v2 비교", "", "[동일 입력]",
        f"원문: {case['experience']['current_text']}", f"질문: {case['question']}",
        f"답변: {case['answer']}", "", "[v1]", v1_text, "", "[v2]", v2_text,
        f"v2 판정: {v2['validation']['status']}", "", "Human judgement:",
        "V1 | V2 | 비슷함", "", "이유:", "", "실제 적용 의향:",
        "v1: APPLY_AS_IS | MINOR_EDIT | MAJOR_EDIT | REJECT",
        "v2: APPLY_AS_IS | MINOR_EDIT | MAJOR_EDIT | REJECT", "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--case-id", action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not args.live:
        parser.error("v1 baseline API calls require --live")
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file)
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY is absent")
    cases = {case["case_id"]: case for case in json.loads((HERE / "v2_cases.json").read_text(encoding="utf-8"))}
    ids = args.case_id or COMPARE_IDS
    if not 1 <= len(ids) <= 8 or any(case_id not in cases for case_id in ids):
        parser.error("select 1..8 known case IDs")
    output = HERE / "v2_results"
    output.mkdir(parents=True, exist_ok=True)
    failures = 0
    for case_id in ids:
        path = output / f"{case_id}_v1.json"
        v2_path = output / f"{case_id}.json"
        if not v2_path.exists():
            print(f"SKIP {case_id}: v2 result absent")
            continue
        if path.exists() and not args.force:
            print(f"SKIP {case_id}: v1 already run")
            continue
        try:
            v1 = run_v1(cases[case_id])
        except Exception as exc:
            print(f"ERROR {case_id}: {type(exc).__name__}")
            failures += 1
            continue
        v2 = json.loads(v2_path.read_text(encoding="utf-8"))
        path.write_text(json.dumps(v1, ensure_ascii=False, indent=2), encoding="utf-8")
        (output / f"{case_id}_compare.md").write_text(
            paired_markdown(cases[case_id], v1, v2), encoding="utf-8",
        )
        print(f"DONE {case_id} v1_suggestions={len(v1['v1_suggestions'])}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
