"""No API calls: v2 contract, factual blockers, quality gates and call limits."""

import pytest
from pydantic import ValidationError

from app.resume_review_v2.engine import ReviewEngineV2
from app.resume_review_v2.models import (
    AnalystOutput, AssertionState, Claim, Evidence, Experience,
    FactVerification, OmittedEvidence, QuestionProposal, ReviewInput,
    RevisionPlan, Usage, WriterOutput,
)
from app.resume_review_v2.validation import (
    ContractError, validate_analysis, validate_apply_snapshot, validate_candidate,
)


ORIGINAL = "문서 검색 기능을 개발했습니다."
ANSWER = "PDF를 전처리하고 Pinecone 검색용 메타데이터를 구성했어요."


def request(answer=ANSWER, existing_evidence=None):
    return ReviewInput(
        experience=Experience(
            experience_id="experience-1", kind="project", title="LMS 챗봇",
            current_text=ORIGINAL, field_path="projects[0].description",
            content_hash="hash-1", existing_evidence=existing_evidence or [],
        ),
        question="어떤 작업을 직접 했나요?", answer=answer,
        answer_source_id="answer-1" if answer else "",
    )


def evidence(state=AssertionState.USER_ASSERTED, quote="Pinecone 검색용 메타데이터를 구성했어요"):
    return Evidence(
        evidence_id="ev-1", experience_id="experience-1", fact_type="implementation",
        normalized_fact="Pinecone 검색용 메타데이터를 구성했다",
        evidence_quote=quote, source_type="user_answer", source_id="answer-1",
        assertion_state=state,
    )


def analysis(fact=None, operation="replace_field", question=None):
    fact = fact or evidence()
    return AnalystOutput(
        experience_id="experience-1", extracted_evidence=[fact],
        plan=RevisionPlan(
            objective="검색 데이터 구성의 직접 기여를 표시",
            operation=operation, selected_evidence_ids=[fact.evidence_id] if operation != "no_change" else [],
            omitted_evidence=[] if operation != "no_change" else [
                OmittedEvidence(evidence_id=fact.evidence_id, reason="이미 충분히 설명됨")
            ],
        ), question=question,
    )


def writer(text="Pinecone 검색용 메타데이터를 구성해 문서 검색 기능을 개발했습니다.", ids=None):
    return WriterOutput(
        experience_id="experience-1", operation="replace_field",
        original_quote=ORIGINAL, suggested_text=text,
        claims=[Claim(text=text, evidence_ids=ids or ["ev-1"])],
    )


def codes(result):
    return {issue.code for issue in [*result.factual_issues, *result.quality_issues]}


def test_schema_rejects_unknown_fields_and_answer_without_source():
    with pytest.raises(ValidationError):
        Evidence.model_validate({**evidence().model_dump(), "unknown": "x"})
    with pytest.raises(ValidationError):
        ReviewInput(experience=request().experience, answer="했다고요")


@pytest.mark.parametrize("bad_quote", ["없는 인용", "문서 검색 기능을 개발했습니다."])
def test_answer_evidence_must_quote_answer(bad_quote):
    with pytest.raises(ContractError):
        validate_analysis(request(), analysis(evidence(quote=bad_quote)))


def test_cross_experience_and_unknown_fact_rejected():
    fact = evidence().model_copy(update={"experience_id": "someone-else"})
    with pytest.raises(ContractError, match="cross-experience"):
        validate_analysis(request(), analysis(fact))
    draft = analysis()
    draft.plan.selected_evidence_ids = ["missing"]
    with pytest.raises(ContractError, match="unknown evidence_id"):
        validate_analysis(request(), draft)


@pytest.mark.parametrize("state", ["uncertain", "contradicted", "retracted"])
def test_uncertain_or_disputed_fact_cannot_be_selected(state):
    with pytest.raises(ContractError, match="unusable evidence state"):
        validate_analysis(request(), analysis(evidence(state=state)))


def test_selected_and_omitted_are_disjoint_and_exhaustive():
    draft = analysis()
    draft.plan.omitted_evidence = [OmittedEvidence(evidence_id="ev-1", reason="duplicate")]
    with pytest.raises(ContractError, match="both selected and omitted"):
        validate_analysis(request(), draft)
    draft.plan.selected_evidence_ids = []
    draft.plan.omitted_evidence = []
    draft.plan.operation = "no_change"
    _, normalized = validate_analysis(request(), draft)
    assert normalized.omitted_evidence[0].evidence_id == "ev-1"


def test_original_document_is_always_available_as_preserved_evidence():
    facts, plan = validate_analysis(request(), analysis())
    original_id = "original:experience-1:hash-1"
    assert original_id in plan.preserved_evidence_ids
    assert facts[original_id].evidence_quote == ORIGINAL
    assert facts[original_id].assertion_state == AssertionState.RESUME_STATED


def test_question_dedupe_and_source_type_boundary():
    ask = QuestionProposal(question="무엇을 확인했나요?", missing_fact_type="verification",
                           improvement_hypothesis="검증 근거가 생김", dedupe_key="verify-search")
    req = request().model_copy(update={"previous_question_keys": ["verify-search"]})
    with pytest.raises(ContractError, match="repeated question"):
        validate_analysis(req, analysis(question=ask))
    bad = evidence().model_copy(update={"source_type": "uploaded_document"})
    with pytest.raises(ContractError, match="not available"):
        validate_analysis(request(), analysis(bad))


def test_claim_mapping_number_technology_and_target_are_hard_failures():
    req = request()
    facts, plan = validate_analysis(req, analysis())
    draft = writer("Kubernetes로 검색을 95% 빠르게 만들었습니다.", ids=["ev-999"])
    draft.original_quote = "다른 경험의 문장"
    result = validate_candidate(req, draft, plan, facts)
    assert {"unapproved_claim_evidence", "unsupported_number", "unsupported_technology", "target_mismatch"} <= codes(result)
    assert result.status == "REWRITE"


def test_quality_can_fail_when_fact_is_grounded():
    req = request()
    facts, plan = validate_analysis(req, analysis())
    copied = writer("PDF를 전처리하고 Pinecone 검색용 메타데이터를 구성했어요.")
    result = validate_candidate(req, copied, plan, facts)
    assert "answer_copying" in codes(result)
    assert not result.factual_issues
    assert result.status == "REWRITE"


def test_long_procedural_paragraph_is_not_apply_ready_even_when_grounded():
    req = request()
    extra = [
        Evidence(evidence_id=f"ev-{i}", experience_id="experience-1", fact_type="implementation",
                 normalized_fact=phrase, evidence_quote=phrase, source_type="user_answer",
                 source_id="answer-1", assertion_state="user_asserted")
        for i, phrase in enumerate(["PDF를 전처리하고", "Pinecone 검색용 메타데이터를 구성했어요"], 2)
    ]
    facts = {item.evidence_id: item for item in [evidence(), *extra]}
    plan = RevisionPlan(objective="검색 데이터 준비", operation="replace_field",
                        selected_evidence_ids=list(facts))
    text = ("PDF를 전처리하고 Pinecone 검색용 메타데이터를 구성했어요. "
            "문서를 분할하고 저장소에 적재한 뒤 다시 검색용 데이터로 색인했습니다. "
            "수정된 문서는 다시 색인했습니다.")
    draft = WriterOutput(experience_id="experience-1", operation="replace_field",
                         original_quote=ORIGINAL, suggested_text=text,
                         claims=[Claim(text=text, evidence_ids=list(facts))])
    result = validate_candidate(req, draft, plan, facts)
    assert "procedure_overload" in codes(result)
    assert result.status == "REWRITE"


def test_independent_verification_catches_unmapped_content():
    req = request()
    facts, plan = validate_analysis(req, analysis())
    result = validate_candidate(req, writer(), plan, facts,
                                FactVerification(unclaimed_factual_content=["추가 성과 주장"]))
    assert "unclaimed_factual_content" in codes(result)


class FakeLLM:
    def __init__(self, drafts):
        self.drafts = list(drafts)
        self.writes = 0
        self.verifications = 0

    def analyze(self, req):
        return analysis(), Usage(calls=1, input_tokens=10, output_tokens=10, latency_ms=1)

    def write(self, req, plan, facts, issues=None, previous_text=""):
        assert {fact.evidence_id for fact in facts} == {"ev-1", "original:experience-1:hash-1"}
        self.writes += 1
        return self.drafts.pop(0), Usage(calls=1, input_tokens=10, output_tokens=10, latency_ms=1)

    def verify(self, req, candidate, facts):
        self.verifications += 1
        return FactVerification(), Usage(calls=1, input_tokens=10, output_tokens=10, latency_ms=1)


def test_good_path_calls_analyst_writer_and_verifier_once():
    fake = FakeLLM([writer()])
    result = ReviewEngineV2(fake).run(request())
    assert result.validation.status == "READY"
    assert result.usage.calls == 3
    assert result.usage.input_tokens == 30
    assert fake.writes == 1


def test_apply_precondition_rejects_stale_hash_or_text():
    result = ReviewEngineV2(FakeLLM([writer()])).run(request())
    validate_apply_snapshot(result.candidate, request().experience)
    stale = request().experience.model_copy(update={"content_hash": "new-version"})
    with pytest.raises(ContractError, match="content hash changed"):
        validate_apply_snapshot(result.candidate, stale)
    changed = request().experience.model_copy(update={"current_text": "새 원문"})
    with pytest.raises(ContractError, match="original text changed"):
        validate_apply_snapshot(result.candidate, changed)


def test_quality_rewrite_is_at_most_once_then_rejected():
    copied = writer("PDF를 전처리하고 Pinecone 검색용 메타데이터를 구성했어요.")
    fake = FakeLLM([copied, copied])
    result = ReviewEngineV2(fake).run(request())
    assert fake.writes == 2
    assert result.validation.status == "REJECTED"
    assert result.candidate.validation.status == "REJECTED"


def test_no_change_needs_no_writer():
    class NoChange(FakeLLM):
        def analyze(self, req):
            ask = QuestionProposal(question="어떻게 확인했나요?", missing_fact_type="verification",
                                   improvement_hypothesis="검증 근거", dedupe_key="verify")
            return analysis(operation="no_change", question=ask), Usage(calls=1)

    fake = NoChange([])
    result = ReviewEngineV2(fake).run(request())
    assert result.candidate is None
    assert result.validation.status == "NEEDS_EVIDENCE"
    assert result.usage.calls == 1


def test_writer_adapter_payload_never_contains_raw_answer():
    from app.resume_review_v2.llm import LangChainReviewLLM

    adapter = object.__new__(LangChainReviewLLM)
    seen = {}

    def capture(system, payload, schema):
        seen.update(payload)
        return writer(), Usage(calls=1)

    adapter._call = capture
    adapter.write(request(), analysis().plan, [evidence()])
    assert "user_answer" not in seen
    assert ANSWER not in str(seen)
