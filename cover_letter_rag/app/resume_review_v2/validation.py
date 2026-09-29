"""Deterministic evidence, claim and writing-quality gates for v2."""

import re
from difflib import SequenceMatcher

from .models import (
    AnalystOutput, AssertionState, Evidence, Experience, FactType, OmittedEvidence,
    FactVerification, ReviewInput, RevisionPlan, ValidationIssue,
    ValidationResult, WriterOutput, RevisionCandidate,
)


class ContractError(ValueError):
    """The model violated a structural/source contract; never silently recover."""


ALLOWED_STATES = {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?:\s*(?:%|초|분|시간|건|명|회|배|개월|년|ms))?")
TECH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:Pinecone|Redis|PostgreSQL|Django|FastAPI|Python|React|"
    r"Docker|Kubernetes|AWS|S3|RDS|Spring Boot|Java|TypeScript|"
    r"JavaScript|LangChain|PyTorch|TensorFlow|OpenAI|GitHub Actions|"
    r"RecursiveCharacterTextSplitter)(?![A-Za-z0-9_])", re.IGNORECASE,
)
PROCEDURE_PATTERN = re.compile(r"(?:한 뒤|하고 나서|그다음|이후|했으며|하였으며|하면서)")
COPY_THRESHOLD = 0.83
DUPLICATION_THRESHOLD = 0.91
VERBOSITY_RATIO = 1.8


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _numbers(text: str) -> set[str]:
    return {re.sub(r"\s+", "", match.group()).casefold() for match in NUMBER_PATTERN.finditer(text)}


def _technologies(text: str) -> set[str]:
    return {match.group().casefold() for match in TECH_PATTERN.finditer(text)}


def _exact_source_quote(source: str, proposed: str) -> str | None:
    """Allow punctuation/whitespace trimming, never a paraphrased source quote."""
    if proposed in source:
        return proposed
    trimmed = proposed.strip(" \t\r\n\"'“”‘’.,。")
    if trimmed and trimmed in source:
        return trimmed
    return None


def validate_analysis(request: ReviewInput, analysis: AnalystOutput) -> tuple[dict[str, Evidence], RevisionPlan]:
    """Reject fabricated source quotes, cross-experience facts and invalid selection."""
    experience = request.experience
    if analysis.experience_id != experience.experience_id:
        raise ContractError("analysis experience_id mismatch")
    evidence: dict[str, Evidence] = {}
    for fact in [*experience.existing_evidence, *analysis.extracted_evidence]:
        if fact.experience_id != experience.experience_id:
            raise ContractError(f"cross-experience evidence: {fact.evidence_id}")
        if fact.evidence_id in evidence:
            raise ContractError(f"duplicate evidence_id: {fact.evidence_id}")
        if fact.evidence_id in {item.evidence_id for item in analysis.extracted_evidence}:
            if fact.source_type == "resume_text":
                source = experience.current_text
                if fact.source_id != experience.experience_id:
                    raise ContractError("resume source_id mismatch")
            elif fact.source_type == "user_answer":
                source = request.answer
                if not request.answer or fact.source_id != request.answer_source_id:
                    raise ContractError("answer source_id mismatch")
            else:
                raise ContractError("uploaded document source is not available in offline v2")
            exact_quote = _exact_source_quote(source, fact.evidence_quote)
            if exact_quote is None:
                raise ContractError(f"evidence quote absent from source: {fact.evidence_id}")
            fact.evidence_quote = exact_quote
        evidence[fact.evidence_id] = fact

    plan = analysis.plan
    # The original document is first-class applicant evidence even if the Analyst
    # extracts only new answer facts. Preserving it never turns a job posting into
    # applicant evidence, and the Writer must still cite it for original claims.
    original_id = f"original:{experience.experience_id}:{experience.content_hash}"
    if original_id not in evidence:
        evidence[original_id] = Evidence(
            evidence_id=original_id, experience_id=experience.experience_id,
            fact_type=FactType.CONTEXT, normalized_fact=experience.current_text,
            evidence_quote=experience.current_text, source_type="resume_text",
            source_id=experience.experience_id,
            assertion_state=AssertionState.RESUME_STATED,
        )
    if plan.operation == "replace_field" and original_id not in plan.preserved_evidence_ids:
        plan.preserved_evidence_ids.append(original_id)
    selected = plan.selected_evidence_ids
    preserved = plan.preserved_evidence_ids
    omitted = [item.evidence_id for item in plan.omitted_evidence]
    if len(set(selected)) != len(selected) or len(set(omitted)) != len(omitted):
        raise ContractError("duplicate selected/omitted evidence_id")
    if set(selected) & set(omitted):
        raise ContractError("evidence cannot be both selected and omitted")
    for evidence_id in [*selected, *preserved, *omitted]:
        if evidence_id not in evidence:
            raise ContractError(f"unknown evidence_id: {evidence_id}")
    for evidence_id in [*selected, *preserved]:
        if evidence[evidence_id].assertion_state not in ALLOWED_STATES:
            raise ContractError(f"unusable evidence state: {evidence_id}")
    # Model-selected facts are authoritative for drafting. Anything it extracted but
    # did not select is an explicit omission, never an implicit extra Writer input.
    for evidence_id in sorted(set(f.evidence_id for f in analysis.extracted_evidence) - set(selected) - set(omitted)):
        plan.omitted_evidence.append(OmittedEvidence(
            evidence_id=evidence_id,
            reason="분석에서 확인됐지만 이번 수정안의 핵심 사실로 선택되지 않음",
        ))
    if plan.operation == "replace_field" and not selected:
        raise ContractError("a revision requires selected evidence")
    if analysis.question and analysis.question.dedupe_key in request.previous_question_keys:
        raise ContractError("repeated question")
    return evidence, plan


def validate_candidate(
    request: ReviewInput,
    writer: WriterOutput,
    plan: RevisionPlan,
    evidence: dict[str, Evidence],
    verification: FactVerification | None = None,
) -> ValidationResult:
    """Hard factual blockers and separate, explainable writing-quality flags."""
    factual: list[ValidationIssue] = []
    quality: list[ValidationIssue] = []
    experience = request.experience
    if writer.experience_id != experience.experience_id:
        factual.append(ValidationIssue(code="wrong_experience", detail="Writer targeted another experience"))
    if writer.original_quote != experience.current_text:
        factual.append(ValidationIssue(code="target_mismatch", detail="Original text differs from the experience snapshot"))
    if not writer.original_quote or writer.original_quote not in experience.current_text:
        factual.append(ValidationIssue(code="missing_target", detail="Original quote is absent"))

    allowed_ids = set(plan.selected_evidence_ids) | set(plan.preserved_evidence_ids)
    mapped_ids: set[str] = set()
    for claim in writer.claims:
        if claim.text not in writer.suggested_text:
            factual.append(ValidationIssue(code="claim_not_in_text", detail=claim.text))
        for evidence_id in claim.evidence_ids:
            if evidence_id not in allowed_ids or evidence_id not in evidence:
                factual.append(ValidationIssue(code="unapproved_claim_evidence", detail=evidence_id))
            elif evidence[evidence_id].assertion_state not in ALLOWED_STATES:
                factual.append(ValidationIssue(code="unusable_claim_evidence", detail=evidence_id))
            else:
                mapped_ids.add(evidence_id)

    allowed_text = " ".join(
        f"{evidence[eid].normalized_fact} {evidence[eid].evidence_quote}"
        for eid in allowed_ids if eid in evidence
    )
    for number in sorted(_numbers(writer.suggested_text) - _numbers(allowed_text)):
        factual.append(ValidationIssue(code="unsupported_number", detail=number))
    for tech in sorted(_technologies(writer.suggested_text) - _technologies(allowed_text)):
        factual.append(ValidationIssue(code="unsupported_technology", detail=tech))
    if verification is not None:
        for text in verification.unsupported_claims:
            factual.append(ValidationIssue(code="semantic_unsupported_claim", detail=text))
        for text in verification.unclaimed_factual_content:
            factual.append(ValidationIssue(code="unclaimed_factual_content", detail=text))
        for text in verification.weakened_original_facts:
            factual.append(ValidationIssue(code="weakened_original_fact", detail=text))

    selected_unused = set(plan.selected_evidence_ids) - mapped_ids
    if selected_unused:
        quality.append(ValidationIssue(code="selected_fact_unused", detail=", ".join(sorted(selected_unused))))
    tech_ids = [eid for eid in plan.selected_evidence_ids if evidence[eid].fact_type in
                {FactType.TECHNOLOGY, FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION}]
    if tech_ids and not set(tech_ids) & mapped_ids:
        quality.append(ValidationIssue(code="critical_technical_signal_loss", detail=", ".join(tech_ids)))
    if len(writer.suggested_text) >= 25 and request.answer:
        similarity = SequenceMatcher(None, _normalized(request.answer), _normalized(writer.suggested_text)).ratio()
        if similarity >= COPY_THRESHOLD:
            quality.append(ValidationIssue(code="answer_copying", detail=f"similarity={similarity:.2f}"))
    if len(writer.suggested_text) >= 40:
        similarity = SequenceMatcher(None, _normalized(experience.current_text), _normalized(writer.suggested_text)).ratio()
        if similarity >= DUPLICATION_THRESHOLD:
            quality.append(ValidationIssue(code="duplication", detail=f"similarity={similarity:.2f}"))
    if len(PROCEDURE_PATTERN.findall(writer.suggested_text)) >= 3:
        quality.append(ValidationIssue(code="procedure_overload", detail="three or more sequential connectors"))
    procedural_ids = [eid for eid in mapped_ids if evidence[eid].fact_type in
                      {FactType.ACTION, FactType.IMPLEMENTATION, FactType.TECHNOLOGY}]
    high_value_ids = [eid for eid in mapped_ids if evidence[eid].fact_type in
                      {FactType.TECHNICAL_DECISION, FactType.RESULT, FactType.VERIFICATION}]
    if len(writer.claims) >= 4 and len(procedural_ids) >= 4 and not high_value_ids:
        quality.append(ValidationIssue(code="procedure_overload", detail="four procedure claims without a decision or result"))
    if (len(procedural_ids) >= 3 and not high_value_ids
            and len(writer.suggested_text) >= 75
            and writer.suggested_text.count(".") >= 2):
        quality.append(ValidationIssue(
            code="procedure_overload",
            detail="long multi-sentence account of implementation steps without a higher-level contribution",
        ))
    if len(writer.suggested_text) > max(180, len(experience.current_text) * VERBOSITY_RATIO):
        quality.append(ValidationIssue(code="verbosity", detail="large increase over original experience"))

    # A flagged candidate is never silently presented as apply-ready. One rewrite is allowed.
    status = "REWRITE" if factual or quality else "READY"
    return ValidationResult(status=status, factual_issues=factual, quality_issues=quality)


def validate_apply_snapshot(candidate: RevisionCandidate, current: Experience) -> None:
    """Offline precondition shared with a future transactional apply adapter."""
    if candidate.validation.status != "READY":
        raise ContractError("candidate is not apply-ready")
    if candidate.experience_id != current.experience_id:
        raise ContractError("experience changed")
    if candidate.content_hash != current.content_hash:
        raise ContractError("content hash changed")
    if candidate.original_quote != current.current_text:
        raise ContractError("original text changed")
