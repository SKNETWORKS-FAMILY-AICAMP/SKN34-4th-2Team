"""Independent offline v2 orchestration. No DB, Firebase, Django or v1 imports."""

from typing import Protocol

from .models import (
    ExtractionOutput, AssertionState, Evidence, FactVerification, ReviewInput, ReviewResult,
    RevisionCandidate, RevisionPlan, Usage, ValidationIssue, ValidationResult,
    WriterOutput,
)
from .validation import validate_candidate
from .project_planning import prepare_review


class ReviewLLM(Protocol):
    def analyze(self, request: ReviewInput) -> tuple[ExtractionOutput, Usage]: ...

    def write(self, request: ReviewInput, plan: RevisionPlan, evidence: list[Evidence],
              issues: list[ValidationIssue] | None = None,
              previous_text: str = "") -> tuple[WriterOutput, Usage]: ...

    def verify(self, request: ReviewInput, candidate: WriterOutput,
               evidence: list[Evidence], core_ids: list[str],
               superseded: list[Evidence], preserved_ids: list[str] | None = None,
               previous_attempt: dict | None = None) -> tuple[FactVerification, Usage]: ...


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
        extraction, step_usage = self.llm.analyze(request)
        _add_usage(usage, step_usage)
        prepared = prepare_review(request, extraction)
        analysis, evidence, plan = prepared.analysis, prepared.evidence, prepared.analysis.plan
        request = prepared.request.model_copy(update={'previous_facets': prepared.facets})
        planning = dict(project_profile=prepared.profile, evidence_facets=prepared.facets,
            evidence_gaps=prepared.gaps, gap_questions=prepared.questions,
            unavailable_slots=request.unavailable_slots, intent_claims=prepared.intents,
            section_profile=prepared.section_profile, sentence_plan=prepared.sentence_plan)
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
                debug_trace=trace_review(request, evidence, plan, None, validation),
                **planning,
            )

        writer, validation = self._draft_and_validate(request, plan, evidence, permitted, usage)
        attempts = [{'writer': writer.model_dump(mode='json'), 'validation': validation.model_dump(mode='json')}]
        for _ in range(self.MAX_REWRITES):
            if validation.status != "REWRITE":
                break
            issues = validation.all_issues
            # Repair prose using the same approved sources. A style defect must
            # not delete evidence or desynchronize the source and meaning plans.
            previous_text = writer.suggested_text
            writer, step_usage = self.llm.write(request, plan, permitted, issues, previous_text)
            _add_usage(usage, step_usage)
            validation = self._validate(request, writer, plan, evidence, permitted, usage, attempts[-1])
            attempts.append({'writer': writer.model_dump(mode='json'), 'validation': validation.model_dump(mode='json')})
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
            debug_trace=trace_review(request, evidence, plan, writer, validation, attempts),
            **planning,
        )

    def _draft_and_validate(self, request, plan, evidence, permitted, usage):
        writer, step_usage = self.llm.write(request, plan, permitted)
        _add_usage(usage, step_usage)
        validation = self._validate(request, writer, plan, evidence, permitted, usage)
        return writer, validation

    def _validate(self, request, writer, plan, evidence, permitted, usage, previous_attempt=None):
        deterministic = validate_candidate(request, writer, plan, evidence)
        if deterministic.factual_issues or deterministic.intent_issues:
            # Do not pay for semantic verification of an already-invalid contract.
            return deterministic
        try:
            superseded = [item for item in evidence.values()
                          if item.assertion_state == AssertionState.SUPERSEDED]
            used_ids = {eid for sentence in writer.sentences for eid in sentence.evidence_ids}
            from .section_semantics import verification_sources
            verifier_evidence = verification_sources(request, plan, permitted, used_ids)
            verification, step_usage = self.llm.verify(
                request, writer, verifier_evidence, plan.core_evidence_ids, superseded, plan.preserved_evidence_ids,
                previous_attempt,
            )
            _add_usage(usage, step_usage)
        except Exception as exc:
            return ValidationResult(
                status="REJECTED",
                factual_issues=[ValidationIssue(code="verification_unavailable", detail=type(exc).__name__)],
                quality_issues=deterministic.quality_issues,
            )
        return validate_candidate(request, writer, plan, evidence, verification)


def trace_review(request, evidence, plan, writer, validation, attempts=()):
    """Internal offline/local result only; production endpoints do not expose v2."""
    from .section_semantics import section_contract
    from .writing_policy import target_section
    return dict(target_section=target_section(request.experience),
        evidence_claims=[e.model_dump(mode='json') for e in evidence.values()],
        intent_claims=[c.model_dump(mode='json') for c in request.approved_intents],
        selected_claims=dict(evidence_ids=plan.core_evidence_ids + plan.supporting_evidence_ids,
                             intent_ids=[c.id for c in request.approved_intents]),
        section_contract=section_contract(target_section(request.experience)).model_dump(mode='json'),
        section_profile=request.section_profile.model_dump(mode='json') if request.section_profile else None,
        sentence_plan=request.sentence_plan.model_dump(mode='json') if request.sentence_plan else None,
        writer_output=writer.model_dump(mode='json') if writer else None,
        validation=validation.model_dump(mode='json'), attempts=list(attempts),
        rewrite_reason=[a['validation'] for a in attempts[:-1]])
