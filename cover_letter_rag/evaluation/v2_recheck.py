"""Re-evaluate saved LLM outputs with current deterministic gates, without API calls.

Semantic verifier output is not reproduced; a previous semantic rejection remains
rejected even if the deterministic recheck alone passes.
"""

import json
from pathlib import Path

from app.resume_review_v2.models import AnalystOutput, ReviewInput, WriterOutput
from app.resume_review_v2.validation import validate_analysis, validate_candidate

HERE = Path(__file__).resolve().parent


def main() -> None:
    cases = json.loads((HERE / "v2_cases.json").read_text(encoding="utf-8"))
    for case in cases:
        path = HERE / "v2_results" / f"{case['case_id']}.json"
        if not path.exists():
            print(f"{case['case_id']}: NO_RESULT")
            continue
        saved = json.loads(path.read_text(encoding="utf-8"))
        if not saved.get("candidate"):
            print(f"{case['case_id']}: {saved['validation']['status']} (no candidate)")
            continue
        request = ReviewInput.model_validate({
            key: value for key, value in case.items()
            if key in {"experience", "question", "answer", "answer_source_id", "job_requirements"}
        })
        analysis = AnalystOutput.model_validate({
            "experience_id": request.experience.experience_id,
            "extracted_evidence": saved["extracted_evidence"],
            "plan": saved["plan"],
            "question": saved.get("proposed_question"),
        })
        evidence, plan = validate_analysis(request, analysis)
        candidate = saved["candidate"]
        writer = WriterOutput.model_validate({
            "experience_id": candidate["experience_id"], "operation": "replace_field",
            "original_quote": candidate["original_quote"],
            "suggested_text": candidate["suggested_text"], "claims": candidate["claims"],
        })
        checked = validate_candidate(request, writer, plan, evidence)
        issues = [item.code for item in [*checked.factual_issues, *checked.quality_issues]]
        print(f"{case['case_id']}: saved={saved['validation']['status']} "
              f"current_deterministic={checked.status} issues={','.join(issues) or '-'}")


if __name__ == "__main__":
    main()
