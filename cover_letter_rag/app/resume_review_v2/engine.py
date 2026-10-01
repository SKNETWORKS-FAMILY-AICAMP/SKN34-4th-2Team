"""Independent offline v2 orchestration. No DB, Firebase, Django or v1 imports."""

from typing import Protocol

from .models import (
    AnalystOutput, AssertionState, Evidence, FactVerification, OmittedEvidence, ReviewInput, ReviewResult,
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
               evidence: list[Evidence], core_ids: list[str],
               superseded: list[Evidence]) -> tuple[FactVerification, Usage]: ...


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
        extracted = [evidence[item.evidence_id] for item in analysis.extracted_evidence]
        selected = [evidence[eid] for eid in [*plan.core_evidence_ids, *plan.supporting_evidence_ids]]
        permitted = [evidence[eid] for eid in dict.fromkeys(
            [*plan.core_evidence_ids, *plan.supporting_evidence_ids, *plan.preserved_evidence_ids]
        )]

        if plan.operation == "no_change":
            validation = ValidationResult(status="NEEDS_EVIDENCE" if analysis.question else "READY")
            return ReviewResult(
                experience=request.experience, question=request.question, answer=request.answer,
                extracted_evidence=extracted, selected_evidence=selected,
                omitted_evidence=plan.omitted_evidence, plan=plan,
                proposed_question=analysis.question, candidate=None, validation=validation,
                usage=usage,
            )

        writer, validation = self._draft_and_validate(request, plan, evidence, permitted, usage)
        for _ in range(self.MAX_REWRITES):
            if validation.status != "REWRITE":
                break
            issues = [*validation.factual_issues, *validation.quality_issues]
            if any(issue.code == "procedure_overload" for issue in issues) and plan.supporting_evidence_ids:
                removed = set(plan.supporting_evidence_ids)
                plan.omitted_evidence.extend(
                    OmittedEvidence(evidence_id=eid, reason="절차 나열을 줄이기 위해 재작성에서 제외")
                    for eid in plan.supporting_evidence_ids
                )
                plan.supporting_evidence_ids = []
                permitted = [item for item in permitted if item.evidence_id not in removed]
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
            sentences=writer.sentences,
            validation=validation,
        )
        selected = [evidence[eid] for eid in [*plan.core_evidence_ids, *plan.supporting_evidence_ids]]
        return ReviewResult(
            experience=request.experience, question=request.question, answer=request.answer,
            extracted_evidence=extracted, selected_evidence=selected,
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
            superseded = [item for item in evidence.values()
                          if item.assertion_state == AssertionState.SUPERSEDED]
            used_ids = {eid for sentence in writer.sentences for eid in sentence.evidence_ids}
            verifier_evidence = [item for item in permitted if
                                 item.evidence_id in used_ids or
                                 item.evidence_id in plan.preserved_evidence_ids]
            verification, step_usage = self.llm.verify(
                request, writer, verifier_evidence, plan.core_evidence_ids, superseded,
            )
            _add_usage(usage, step_usage)
        except Exception as exc:
            return ValidationResult(
                status="REJECTED",
                factual_issues=[ValidationIssue(code="verification_unavailable", detail=type(exc).__name__)],
                quality_issues=deterministic.quality_issues,
            )
        return validate_candidate(request, writer, plan, evidence, verification)
