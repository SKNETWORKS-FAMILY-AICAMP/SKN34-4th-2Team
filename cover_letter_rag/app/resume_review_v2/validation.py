"""Deterministic evidence, claim and writing-quality gates for v2."""

import re

from .models import (
    AnalystOutput, AssertionState, Evidence, Experience, FactType, OmittedEvidence,
    FactVerification, ReviewInput, RevisionPlan, ValidationIssue,
    ValidationResult, WriterOutput, RevisionCandidate, ClaimType,
)
from .policy import (REPRESENTATIVE_COLLECTION_MIN,
                     REPRESENTATIVE_SIGNAL_MIN)


class ContractError(ValueError):
    """The model violated a structural/source contract; never silently recover."""
    def __init__(self, message, diagnostics=None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


ALLOWED_STATES = {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}
# Compatibility for the separate application-writing engine. Resume Review v2
# treats these connectors as reviewer hints, never a standalone rejection rule.
PROCEDURE_PATTERN = re.compile(r"(?:한 뒤|하고 나서|그다음|이후|했으며|하였으며|하면서)")
NUMBER_PATTERN = re.compile(r"(?<![\w])\d+(?:[.,]\d+)*(?:\s*(?:%|초|분|시간|건|명|회|배|개월|년|ms))?")
TECH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:Pinecone|Redis|PostgreSQL|Django|FastAPI|Python|React|"
    r"Docker|Kubernetes|AWS|S3|RDS|Spring Boot|Java|TypeScript|"
    r"JavaScript|LangChain|PyTorch|TensorFlow|OpenAI|GitHub Actions|"
    r"RecursiveCharacterTextSplitter|Haversine|MySQL|CSV|Logistic Regression|"
    r"Random Forest|XGBoost|LightGBM|CatBoost|Scikit-learn|Pandas|Streamlit|SQL|F1|PR-AUC)(?![A-Za-z0-9_])", re.IGNORECASE,
)


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
            raise ContractError(f"cross-experience evidence: {fact.evidence_id}",
                {'phase':'evidence_sources', 'reference_category':'wrong_experience', 'reference_id':fact.evidence_id})
        if fact.evidence_id in evidence:
            raise ContractError(f"duplicate evidence_id: {fact.evidence_id}")
        if fact.evidence_id in extracted_ids:
            if fact.source_type == 'resume_text' and fact.assertion_state in ALLOWED_STATES and any(
                    old.assertion_state in {AssertionState.SUPERSEDED, AssertionState.RETRACTED, AssertionState.CONTRADICTED}
                    and (_normalized(old.evidence_quote) == _normalized(fact.evidence_quote)
                         or _normalized(old.normalized_fact) == _normalized(fact.normalized_fact))
                    for old in experience.existing_evidence):
                raise ContractError('inactive source assertion cannot be reactivated by extraction')
            if fact.source_type == "resume_text":
                sources = {item.source_id: item.text for item in request.resume_sources}
                if len(sources) != len(request.resume_sources) or experience.experience_id in sources:
                    raise ContractError('duplicate resume source_id')
                sources = request.factual_resume_sources()
                source = sources.get(fact.source_id)
                if source is None:
                    raise ContractError("resume source_id mismatch",
                        {'phase':'evidence_sources', 'reference_category':'wrong_source', 'reference_id':fact.evidence_id})
            elif fact.source_type == "user_answer":
                source = request.answer
                if not request.answer or fact.source_id != request.answer_source_id:
                    raise ContractError("answer source_id mismatch",
                        {'phase':'evidence_sources', 'reference_category':'wrong_source', 'reference_id':fact.evidence_id})
            else:
                raise ContractError("uploaded document source is not available in offline v2")
            exact_quote = _exact_source_quote(source, fact.evidence_quote)
            if exact_quote is None:
                raise ContractError(f"evidence quote absent from source: {fact.evidence_id}",
                    {'phase':'evidence_sources', 'reference_category':'quote_absent', 'reference_id':fact.evidence_id})
            fact.evidence_quote = exact_quote
            if re.search(
                    r'하고 싶|싶습니다|계획입니다|예정입니다|하겠습니다|되겠습니다|기여하겠|성장하겠', exact_quote):
                raise ContractError('applicant intent cannot be a performed factual claim')
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
    if plan.operation == "replace_field" and not core and not request.section_profile:
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
    intent: list[ValidationIssue] = []
    section: list[ValidationIssue] = []
    experience = request.experience
    if writer.experience_id != experience.experience_id:
        factual.append(ValidationIssue(code="wrong_experience", detail="Writer targeted another experience"))
    if writer.original_quote != experience.current_text:
        factual.append(ValidationIssue(code="target_mismatch", detail="Original text differs from the experience snapshot"))
    if not writer.original_quote or writer.original_quote not in experience.current_text:
        factual.append(ValidationIssue(code="missing_target", detail="Original quote is absent"))

    allowed_ids = set(plan.core_evidence_ids) | set(plan.supporting_evidence_ids) | set(plan.preserved_evidence_ids)
    mapped_ids: set[str] = set()
    intents = {c.id: c for c in request.approved_intents}
    targets = {r.requirement_id: r for r in request.job_requirements if r.posting_quote.strip()}
    from .section_semantics import agency_issues, ACTIVE
    units = {u.id: u for u in request.section_profile.original_semantic_units} if request.section_profile else {}
    covered = set()
    paragraph_refs = {uid: set() for uid in units}
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
            evidence[eid].evidence_quote
            for eid in sentence_ids
        )
        factual.extend(agency_issues(sentence, {eid:evidence[eid] for eid in sentence_ids},
            request.approved_intents, experience.model_copy(update={
                'current_text':request.factual_resume_sources()[experience.experience_id]}), request.resume_sources))
        typed_sources = {evidence[eid].fact_type for eid in sentence_ids}
        requires_fact = {
            ClaimType.ACTION: {FactType.ACTION, FactType.IMPLEMENTATION},
            ClaimType.VALIDATION: {FactType.VERIFICATION},
            ClaimType.OUTCOME: {FactType.RESULT}, ClaimType.SCALE: {FactType.SCOPE, FactType.DURATION},
        }
        for typ in sentence.claim_types:
            # Fact labels are not an entailment oracle: context may describe
            # participation/learning, and implementation may describe a result.
            # Only the unambiguous tool-only escalation is a mechanical blocker.
            if not request.section_profile and typ in requires_fact and typed_sources == {FactType.TECHNOLOGY}:
                factual.append(ValidationIssue(code='unsupported_typed_claim', detail=typ.value))
        if not sentence.evidence_ids and not sentence.intent_ids and not sentence.target_context_ids:
            factual.append(ValidationIssue(code='unclaimed_factual_content', detail=sentence.text))
        for cid in sentence.intent_ids:
            if cid not in intents or intents[cid].state not in ACTIVE:
                intent.append(ValidationIssue(code='unapproved_intent', detail=cid))
            else:
                source_text += ' ' + intents[cid].evidence_quote
        for rid in sentence.target_context_ids:
            if rid not in targets:
                factual.append(ValidationIssue(code='unapproved_target_context', detail=rid))
            else:
                source_text += ' ' + targets[rid].posting_quote
        supplied = {('applicant_evidence', eid) for eid in sentence_ids} | {
            ('applicant_intent', cid) for cid in sentence.intent_ids if cid in intents} | {
            ('target_context', rid) for rid in sentence.target_context_ids if rid in targets}
        for uid in sentence.semantic_unit_ids:
            unit = units.get(uid)
            refs = {(r.type, r.id) for r in unit.source_refs} if unit else set()
            if unit is None or not refs & supplied:
                section.append(ValidationIssue(code='unapproved_semantic_coverage', detail=uid))
            else:
                paragraph_refs[uid].update(refs & supplied)
        # Legacy/project factual provenance remains valid without copying unit IDs.
        if request.section_profile and request.section_profile.section_type == 'project':
            for uid, unit in units.items():
                paragraph_refs[uid].update({(r.type, r.id) for r in unit.source_refs} & supplied)
        intent.extend(validate_intent_sentence(sentence, intents))
        for number in sorted(_numbers(sentence.text) - _numbers(source_text)):
            factual.append(ValidationIssue(code="unsupported_number", detail=number))
        for tech in sorted(_technologies(sentence.text) - _technologies(source_text)):
            factual.append(ValidationIssue(code="unsupported_technology", detail=tech))
    for uid, refs in paragraph_refs.items():
        from .section_semantics import coverage_context_refs
        try:
            contextual = coverage_context_refs(request, units[uid], evidence)
        except ContractError:
            contextual = set()
            section.append(ValidationIssue(code='invalid_context_reference', detail=uid))
        expected = {(r.type, r.id) for r in units[uid].source_refs} - contextual
        if expected <= refs or (refs and uid in request.section_profile.optional_semantics):
            covered.add(uid)
    # This is citation completeness across the paragraph, not entailment.
    # Sentence fact gates above and the independent semantic verifier remain.
    editorial_advice = []
    if verification is not None:
        for text in verification.unsupported_claims:
            factual.append(ValidationIssue(code="semantic_unsupported_claim", detail=text))
        for text in verification.unclaimed_factual_content:
            factual.append(ValidationIssue(code="unclaimed_factual_content", detail=text))
        for text in verification.weakened_original_facts:
            factual.append(ValidationIssue(code="weakened_original_fact", detail=text))
        for text in verification.critical_technical_signal_loss:
            quality.append(ValidationIssue(code="critical_technical_signal_loss", detail=text))
        quality.extend(verification.quality_issues)
        editorial_advice = list(verification.editorial_advice)
        intent.extend(ValidationIssue(code='unsupported_intent', detail=t) for t in verification.unsupported_intents)
        section.extend(ValidationIssue(code='SECTION_MEANING_LOSS', detail=t) for t in verification.section_meaning_loss)

    coverage_issues = validate_section_coverage(request.section_profile, covered)
    for issue in coverage_issues:
        unit = units.get(issue.detail)
        if unit is not None:
            expected = {(r.type,r.id) for r in unit.source_refs} - {(r.type,r.id) for r in unit.context_source_refs}
            missing = expected - paragraph_refs.get(unit.id,set())
            issue.detail = f'{unit.id}: incomplete_reference_coverage; missing=' + ','.join(f'{typ}:{eid}' for typ,eid in sorted(missing))
    section.extend(coverage_issues)

    # The live section profile is the meaning contract, not a second per-fact
    # checklist. Legacy offline requests without it retain their ID-based gate.
    core_unused = set(plan.core_evidence_ids) - mapped_ids if not request.section_profile else set()
    if core_unused:
        quality.append(ValidationIssue(code="core_fact_unused", detail=", ".join(sorted(core_unused))))
    tech_ids = [eid for eid in plan.core_evidence_ids if not request.section_profile and evidence[eid].fact_type in
                {FactType.TECHNOLOGY, FactType.IMPLEMENTATION, FactType.TECHNICAL_DECISION}]
    for eid in tech_ids:
        expected_technologies = _technologies(
            f"{evidence[eid].normalized_fact} {evidence[eid].evidence_quote}"
        )
        present = _technologies(writer.suggested_text)
        missing = expected_technologies - present
        # A technology collection can retain representative signal without naming
        # every member. Atomic implementation/decision facts still retain their
        # specific technology, and relevant posting keywords cannot disappear.
        job_technologies = _technologies(' '.join(
            f'{r.text} {r.posting_quote}' for r in request.job_requirements))
        representative_list = (evidence[eid].fact_type == FactType.TECHNOLOGY
            and len(expected_technologies) >= REPRESENTATIVE_COLLECTION_MIN
            and len(expected_technologies & present) >= REPRESENTATIVE_SIGNAL_MIN
            and '등' in writer.suggested_text
            and not (expected_technologies & job_technologies) - present)
        if eid not in mapped_ids or (missing and not representative_list):
            quality.append(ValidationIssue(code="critical_technical_signal_loss", detail=eid))
    # Lexical style signals are hints to the semantic reviewer, not blockers.
    # Similarity to a good original is not a reason to force another paraphrase.
    status = "REWRITE" if factual or intent or section or quality else "READY"
    if verification is not None and status == 'READY' and (
            verification.revision_quality != 'improved'
            or _normalized(writer.suggested_text) == _normalized(experience.current_text)):
        status = 'UNCHANGED'
        quality.append(ValidationIssue(code='no_clear_improvement',
            detail=verification.comparison_reason or '원문보다 명확한 개선이 없어 원문을 유지합니다.'))
    return ValidationResult(status=status, factual_issues=factual, intent_issues=intent,
                            section_issues=section, quality_issues=quality,
                            editorial_advice=editorial_advice)


def is_explicit_intention(text):
    return bool(re.search(r'싶|계획입니다|계획하고 있|예정입니다|목표로 하|목표입니다|성장하겠|기여하겠|이해하겠|하고자|지원하고자',text))


def validate_intent_sentence(sentence, intents):
    """Intent presence/state gate; novel semantic goals use verifier findings."""
    from .section_semantics import ACTIVE
    # A plan/goal noun can describe past work or an observed limitation. Only
    # explicit intention predicates trigger this mechanical presence check;
    # the independent verifier still judges untagged or novel semantic goals.
    is_intent = is_explicit_intention(sentence.text) or (not sentence.evidence_ids and bool(
        set(sentence.claim_types) & {ClaimType.MOTIVATION, ClaimType.PLAN}))
    if is_intent and not any(cid in intents and intents[cid].state in ACTIVE for cid in sentence.intent_ids):
        return [ValidationIssue(code='unsupported_intent', detail=sentence.text)]
    return []


def validate_section_coverage(profile, covered):
    """Source-backed unit coverage; verifier checks actual paraphrased meaning."""
    if not profile:
        return []
    code = 'TECHNICAL_SIGNAL_LOSS' if profile.section_type == 'project' else 'SECTION_MEANING_LOSS'
    return [ValidationIssue(code=code, detail=uid) for uid in sorted(set(profile.required_semantics) - covered)]


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
