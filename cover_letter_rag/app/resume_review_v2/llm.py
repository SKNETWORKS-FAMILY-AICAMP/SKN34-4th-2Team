"""Optional live LangChain adapter; tests inject a fake ReviewLLM instead."""

import json
import time

from .models import (
    AnalystOutput, Evidence, FactVerification, ReviewInput, RevisionPlan,
    Usage, ValidationIssue, WriterOutput,
)
from .prompts import ANALYST_SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT, WRITER_SYSTEM_PROMPT


class LangChainReviewLLM:
    def __init__(self, model: str, reasoning_effort: str = "medium"):
        from langchain_openai import ChatOpenAI

        self.model_name = model
        self.attempted_calls = 0
        self.recorded_usage = Usage()
        self.model = ChatOpenAI(
            model=model, reasoning_effort=reasoning_effort,
            use_responses_api=True, max_retries=0,
        )

    def _call(self, system: str, payload: dict, schema):
        chain = self.model.with_structured_output(schema, method="json_schema", include_raw=True)
        start = time.monotonic()
        self.attempted_calls += 1
        response = chain.invoke([
            ("system", system),
            ("human", json.dumps(payload, ensure_ascii=False, default=str)),
        ])
        elapsed = round((time.monotonic() - start) * 1000)
        raw = response["raw"]
        tokens = getattr(raw, "usage_metadata", None) or {}
        usage = Usage(
            calls=1, input_tokens=tokens.get("input_tokens", 0) or 0,
            output_tokens=tokens.get("output_tokens", 0) or 0,
            latency_ms=elapsed,
        )
        self.recorded_usage.calls += usage.calls
        self.recorded_usage.input_tokens += usage.input_tokens
        self.recorded_usage.output_tokens += usage.output_tokens
        self.recorded_usage.latency_ms += usage.latency_ms
        if response.get("parsing_error") or response.get("parsed") is None:
            raise RuntimeError(f"{schema.__name__} structured output failed")
        return response["parsed"], usage

    def analyze(self, request: ReviewInput) -> tuple[AnalystOutput, Usage]:
        return self._call(ANALYST_SYSTEM_PROMPT, {
            "experience": request.experience.model_dump(mode="json"),
            "question": request.question,
            "user_answer": request.answer,
            "answer_source_id": request.answer_source_id,
            "job_requirements": [item.model_dump(mode="json") for item in request.job_requirements],
            "previous_question_keys": request.previous_question_keys,
            "source_rule": "resume_text source_id is experience_id; user_answer source_id is answer_source_id",
        }, AnalystOutput)

    def write(self, request: ReviewInput, plan: RevisionPlan, evidence: list[Evidence],
              issues: list[ValidationIssue] | None = None,
              previous_text: str = "") -> tuple[WriterOutput, Usage]:
        # Neither request.answer nor request.question enters the Writer prompt.
        return self._call(WRITER_SYSTEM_PROMPT, {
            "experience": {
                "experience_id": request.experience.experience_id,
                "kind": request.experience.kind,
                "title": request.experience.title,
                "current_text": request.experience.current_text,
            },
            "approved_evidence": [item.model_dump(mode="json") for item in evidence],
            "revision_plan": plan.model_dump(mode="json"),
            "job_requirements": [item.model_dump(mode="json") for item in request.job_requirements],
            "previous_draft_to_fix": previous_text,
            "validation_issues_to_fix": [item.model_dump(mode="json") for item in (issues or [])],
            "target_rule": "original_quote must equal current_text in this offline phase",
        }, WriterOutput)

    def verify(self, request: ReviewInput, candidate: WriterOutput,
               evidence: list[Evidence], core_ids: list[str],
               superseded: list[Evidence]) -> tuple[FactVerification, Usage]:
        return self._call(VERIFY_SYSTEM_PROMPT, {
            "original_experience_text": request.experience.current_text,
            "suggested_text": candidate.suggested_text,
            "sentences": [item.model_dump(mode="json") for item in candidate.sentences],
            "approved_evidence": [item.model_dump(mode="json") for item in evidence],
            "core_evidence_ids": core_ids,
            "superseded_original_evidence": [item.model_dump(mode="json") for item in superseded],
        }, FactVerification)
