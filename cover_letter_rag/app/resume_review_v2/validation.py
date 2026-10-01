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
    extracted_ids = {item.evidence_id for item in analysis.extracted_evidence}
    for original_fact in [*experience.existing_evidence, *analysis.extracted_evidence]:
        fact = original_fact.model_copy(deep=True)
        if fact.experience_id != experience.experience_id:
            raise ContractError(f"cross-experience evidence: {fact.evidence_id}")
        if fact.evidence_id in evidence:
            raise ContractError(f"duplicate evidence_id: {fact.evidence_id}")
        if fact.evidence_id in extracted_ids:
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

    # Only an explicit, certain user correction can supersede an atomic resume fact.
    # The original text is editing context, never an all-purpose evidence citation.
    blocked_by_conflict: set[str] = set()
    for fact in evidence.values():
        if fact.conflicts_with_evidence_ids:
            for target_id in fact.conflicts_with_evidence_ids:
                target = evidence.get(target_id)
                if target is None or target_id == fact.evidence_id:
                    raise ContractError(f"invalid conflicting evidence_id: {target_id}")
                if fact.source_type == "user_answer" and target.source_type == "resume_text":
                    answer_fact, resume_fact = fact, target
                elif fact.source_type == "resume_text" and target.source_type == "user_answer":
                    answer_fact, resume_fact = target, fact
                else:
                    raise ContractError(f"invalid unresolved conflict relation: {fact.evidence_id}")
                if answer_fact.assertion_state not in {
                    AssertionState.UNCERTAIN, AssertionState.USER_ASSERTED,
                }:
                    raise ContractError(f"invalid unresolved conflict state: {answer_fact.evidence_id}")
                if resume_fact.evidence_id in answer_fact.supersedes_evidence_ids:
                    continue  # An explicit correction resolves this pair.
                blocked_by_conflict.add(resume_fact.evidence_id)
                if answer_fact.assertion_state == AssertionState.USER_ASSERTED:
                    blocked_by_conflict.add(answer_fact.evidence_id)
        if not fact.supersedes_evidence_ids:
            continue
        if fact.source_type != "user_answer" or fact.assertion_state != AssertionState.USER_ASSERTED:
            raise ContractError(f"uncertain or non-answer correction: {fact.evidence_id}")
        if len(set(fact.supersedes_evidence_ids)) != len(fact.supersedes_evidence_ids):
            raise ContractError(f"duplicate superseded evidence_id: {fact.evidence_id}")
        for target_id in fact.supersedes_evidence_ids:
            target = evidence.get(target_id)
            if target is None or target.source_type != "resume_text" or target.assertion_state not in {
                AssertionState.RESUME_STATED, AssertionState.SUPERSEDED,
            }:
                raise ContractError(f"invalid superseded evidence_id: {target_id}")
            target.assertion_state = AssertionState.SUPERSEDED

    plan = analysis.plan.model_copy(deep=True)
    core = plan.core_evidence_ids
    supporting = plan.supporting_evidence_ids
    preserved = plan.preserved_evidence_ids
    omitted = [item.evidence_id for item in plan.omitted_evidence]
    groups = [core, supporting, preserved, omitted]
    if any(len(set(group)) != len(group) for group in groups):
        raise ContractError("duplicate evidence_id within a plan group")
    if set(core) & set(supporting) or set(omitted) & (set(core) | set(supporting) | set(preserved)):
        raise ContractError("core/supporting/omitted evidence groups must be disjoint")
    all_ids = [eid for group in groups for eid in group]
    for evidence_id in all_ids:
        if evidence_id not in evidence:
            raise ContractError(f"unknown evidence_id: {evidence_id}")
    for evidence_id in [*core, *supporting, *preserved]:
        if evidence[evidence_id].assertion_state not in ALLOWED_STATES:
            raise ContractError(f"unusable evidence state: {evidence_id}")
        if evidence_id in blocked_by_conflict:
            raise ContractError(f"unresolved conflict evidence: {evidence_id}")
    # Every extracted fact outside the approved groups is explicitly omitted.
    for evidence_id in sorted(extracted_ids - set(all_ids)):
        plan.omitted_evidence.append(OmittedEvidence(
            evidence_id=evidence_id,
            reason="이번 수정안의 작성 근거로 선택되지 않음",
        ))
    if plan.operation == "replace_field" and not core:
        raise ContractError("a revision requires core evidence")
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

    allowed_ids = set(plan.core_evidence_ids) | set(plan.supporting_evidence_ids) | set(plan.preserved_evidence_ids)
    mapped_ids: set[str] = set()
    for sentence in writer.sentences:
        if not sentence.text.strip():
            factual.append(ValidationIssue(code="empty_sentence", detail="Writer returned a blank sentence"))
        sentence_ids: set[str] = set()
        for evidence_id in sentence.evidence_ids:
            if evidence_id not in allowed_ids or evidence_id not in evidence:
                factual.append(ValidationIssue(code="unapproved_claim_evidence", detail=evidence_id))
            elif evidence[evidence_id].assertion_state not in ALLOWED_STATES:
                factual.append(ValidationIssue(code="unusable_claim_evidence", detail=evidence_id))
            else:
                mapped_ids.add(evidence_id)
                sentence_ids.add(evidence_id)
        source_text = " ".join(
            f"{evidence[eid].normalized_fact} {evidence[eid].evidence_quote}"
            for eid in sentence_ids
        )
        for number in sorted(_numbers(sentence.text) - _numbers(source_text)):
            factual.append(ValidationIssue(code="unsupported_number", detail=number))
        for tech in sorted(_technologies(sentence.text) - _technologies(source_text)):
            factual.append(ValidationIssue(code="unsupported_technology", detail=tech))
    if verification is not None:
        for text in verification.unsupported_claims:
            factual.append(ValidationIssue(code="semantic_unsupported_claim", detail=text))
        for text in verification.unclaimed_factual_content:
            factual.append(ValidationIssue(code="unclaimed_factual_content", detail=text))
        for text in verification.weakened_original_facts:
            factual.append(ValidationIssue(code="weakened_original_fact", detail=text))
        for text in verification.critical_technical_signal_loss:
            quality.append(ValidationIssue(code="critical_technical_signal_loss", detail=text))

    core_unused = set(plan.core_evidence_ids) - mapped_ids
    if core_unused:
        quality.append(ValidationIssue(code="core_fact_unused", detail=", ".join(sorted(core_unused))))
    tech_ids = [eid for eid in plan.core_evidence_ids if evidence[eid].fact_type in
                {FactType.TECHNOLOGY, FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION}]
    for eid in tech_ids:
        expected_technologies = _technologies(
            f"{evidence[eid].normalized_fact} {evidence[eid].evidence_quote}"
        )
        if eid not in mapped_ids or expected_technologies - _technologies(writer.suggested_text):
            quality.append(ValidationIssue(code="critical_technical_signal_loss", detail=eid))
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
    if (len(procedural_ids) >= 4 and not high_value_ids
            and (len(writer.sentences) >= 4 or len(writer.suggested_text) >= 110)):
        quality.append(ValidationIssue(
            code="procedure_overload", detail="four procedural facts expanded into a long revision",
        ))
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
