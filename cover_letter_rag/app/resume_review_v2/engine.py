"""Independent offline v2 orchestration. No DB, Firebase, Django or v1 imports."""

from typing import Protocol

from .models import (
    AnalystOutput, Evidence, FactVerification, ReviewInput, ReviewResult,
    RevisionCandidate, RevisionPlan, Usage, ValidationIssue, ValidationResult,
    WriterOutput,
)
from .validation import ContractError, validate_analysis, validate_candidate


class ReviewLLM(Protocol):
    def analyze(self, request: ReviewInput) -> tuple[AnalystOutput, Usage]: ...

    def write(self, request: ReviewInput, plan: RevisionPlan, evidence: list[Evidence],
              issues: list[ValidationIssue] | None = None,
              previous_text: str = "") -> tuple[WriterOutput, Usage]: ...

    def verify(self, request: ReviewInput, candidate: WriterOutput,
               evidence: list[Evidence]) -> tuple[FactVerification, Usage]: ...


def _add_usage(total: Usage, added: Usage) -> None:
    total.calls += added.calls
    total.input_tokens += added.input_tokens
    total.output_tokens += added.output_tokens
    total.latency_ms += added.latency_ms


class ReviewEngineV2:
    """One experience in, one validated proposal or a high-value question out."""

    MAX_REWRITES = 1

    def __init__(self, llm: ReviewLLM):
        self.llm = llm

    def run(self, request: ReviewInput) -> ReviewResult:
        usage = Usage()
        analysis, step_usage = self.llm.analyze(request)
        _add_usage(usage, step_usage)
        evidence, plan = validate_analysis(request, analysis)
        selected = [evidence[eid] for eid in plan.selected_evidence_ids]
        permitted = [evidence[eid] for eid in dict.fromkeys(
            [*plan.selected_evidence_ids, *plan.preserved_evidence_ids]
        )]

        if plan.operation == "no_change":
            validation = ValidationResult(status="NEEDS_EVIDENCE" if analysis.question else "READY")
            return ReviewResult(
                experience=request.experience, question=request.question, answer=request.answer,
                extracted_evidence=analysis.extracted_evidence, selected_evidence=selected,
                omitted_evidence=plan.omitted_evidence, plan=plan,
                proposed_question=analysis.question, candidate=None, validation=validation,
                usage=usage,
            )

        writer, validation = self._draft_and_validate(request, plan, evidence, permitted, usage)
        for _ in range(self.MAX_REWRITES):
            if validation.status != "REWRITE":
                break
            issues = [*validation.factual_issues, *validation.quality_issues]
            previous_text = writer.suggested_text
            writer, step_usage = self.llm.write(request, plan, permitted, issues, previous_text)
            _add_usage(usage, step_usage)
            validation = self._validate(request, writer, plan, evidence, permitted, usage)
        if validation.status == "REWRITE":
            validation.status = "REJECTED"  # Never expose an uncorrected draft as apply-ready.

        candidate = RevisionCandidate(
            experience_id=request.experience.experience_id,
            field_path=request.experience.field_path,
            content_hash=request.experience.content_hash,
            original_quote=writer.original_quote,
            suggested_text=writer.suggested_text,
            claims=writer.claims,
            validation=validation,
        )
        return ReviewResult(
            experience=request.experience, question=request.question, answer=request.answer,
            extracted_evidence=analysis.extracted_evidence, selected_evidence=selected,
            omitted_evidence=plan.omitted_evidence, plan=plan,
            proposed_question=analysis.question, candidate=candidate,
            validation=validation, usage=usage,
        )

    def _draft_and_validate(self, request, plan, evidence, permitted, usage):
        writer, step_usage = self.llm.write(request, plan, permitted)
        _add_usage(usage, step_usage)
        validation = self._validate(request, writer, plan, evidence, permitted, usage)
        return writer, validation

    def _validate(self, request, writer, plan, evidence, permitted, usage):
        deterministic = validate_candidate(request, writer, plan, evidence)
        if deterministic.factual_issues:
            # Do not pay for semantic verification of an already-invalid contract.
            return deterministic
        try:
            verification, step_usage = self.llm.verify(request, writer, permitted)
            _add_usage(usage, step_usage)
        except Exception as exc:
            return ValidationResult(
                status="REJECTED",
                factual_issues=[ValidationIssue(code="verification_unavailable", detail=type(exc).__name__)],
                quality_issues=deterministic.quality_issues,
            )
        return validate_candidate(request, writer, plan, evidence, verification)
