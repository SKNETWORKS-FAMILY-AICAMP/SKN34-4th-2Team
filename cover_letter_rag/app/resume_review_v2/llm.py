"""Optional live LangChain adapter; tests inject a fake ReviewLLM instead."""

import json
import time

from .models import (
    ExtractionOutput, Evidence, FactVerification, ReviewInput, RevisionPlan,
    Usage, ValidationIssue, WriterOutput, WriterDraft,
)
from .prompts import ANALYST_SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT, WRITER_SYSTEM_PROMPT
from .writing_policy import target_section
from .policy import SECTION_RULES, SOURCE_POLICY, TARGET_POLICY, POLICY_VERSION
from .section_semantics import section_contract, editorial_brief, rewrite_source_review


def scoped_evidence(request, evidence):
    """Resolve field scope from an available owning source, not a paraphrase."""
    owner = request.experience.experience_id
    sources = request.factual_resume_sources()
    rows = []
    for fact in evidence:
        row = fact.model_dump(mode='json')
        context = None
        if fact.experience_id == owner and fact.source_type == 'resume_text':
            field = None
            if fact.source_id == owner:
                source, field = sources[owner], request.experience.field_path
            elif fact.source_id.startswith(owner + ':') and fact.source_id in sources:
                source, field = sources[fact.source_id], fact.source_id[len(owner) + 1:]
            if field and fact.evidence_quote in source:
                context = dict(experience_id=owner, experience_title=request.experience.title,
                    field=field, scope='owning_experience', quote=fact.evidence_quote)
                if any(s.source_id==fact.source_id for s in request.historical_resume_sources):
                    context['source_basis']='verified_historical_source'
        elif (fact.experience_id == owner and fact.source_type == 'user_answer'
              and fact.evidence_quote in request.answer):
            # The adapter routes this history using the issued question's owner.
            context = dict(experience_id=owner, experience_title=request.experience.title,
                field='user_answer', scope='owning_experience', quote=fact.evidence_quote)
        row['source_context'] = context
        rows.append(row)
    return rows


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

    def analyze(self, request: ReviewInput) -> tuple[ExtractionOutput, Usage]:
        from app.job_requirements import classify_requirement
        sources=request.factual_resume_sources()
        experience=request.experience.model_dump(mode='json')
        experience['current_text']=sources.pop(request.experience.experience_id)
        return self._call(ANALYST_SYSTEM_PROMPT, {
            "policy_version": POLICY_VERSION,
            "target_section": target_section(request.experience),
            "section_writing_rules": SECTION_RULES[target_section(request.experience)],
            "section_contract": section_contract(target_section(request.experience)).model_dump(mode='json'),
            "experience": experience,
            "resume_sources": [dict(source_id=k,text=v) for k,v in sources.items()],
            "question": request.question,
            "user_answer": request.answer,
            "answer_source_id": request.answer_source_id,
            "existing_intents": [c.model_dump(mode='json') for c in request.existing_intents],
            "previous_semantic_units": [u.model_dump(mode='json') for u in request.previous_semantic_units],
            "question_history": request.question_history,
            "previous_question_keys": request.previous_question_keys,
            "unavailable_slots": [s.value for s in request.unavailable_slots],
            "target_context": [{**r.model_dump(mode='json'), 'kind':classify_requirement(r.text)[0]}
                               for r in request.job_requirements],
            "requirement_review_context": request.requirement_review_context,
            "prior_information_needs": [{k:v for k,v in need.items() if k!='linked_answers'}
                                        for need in request.prior_information_needs],
            "source_rule": SOURCE_POLICY,
        }, ExtractionOutput)

    def write(self, request: ReviewInput, plan: RevisionPlan, evidence: list[Evidence],
              issues: list[ValidationIssue] | None = None,
              previous_text: str = "", previous_candidate: WriterOutput | None = None) -> tuple[WriterOutput, Usage]:
        # Neither request.answer nor request.question enters the Writer prompt.
        result = self._call(WRITER_SYSTEM_PROMPT, {
            "policy_version": POLICY_VERSION,
            "target_section": target_section(request.experience),
            "section_writing_rules": SECTION_RULES[target_section(request.experience)],
            "experience": {
                "experience_id": request.experience.experience_id,
                "kind": request.experience.kind,
                "title": request.experience.title,
            },
            "approved_evidence": scoped_evidence(request, evidence),
            "approved_intents": [item.model_dump(mode='json') for item in request.approved_intents],
            "editorial_brief": editorial_brief(request),
            "original_for_editing": request.experience.current_text,
            "job_requirements": [item.model_dump(mode="json") for item in request.job_requirements],
            "previous_draft_to_fix": previous_text,
            "rewrite_source_review": rewrite_source_review(request, previous_text, previous_candidate),
            "validation_issues_to_fix": [item.model_dump(mode="json") for item in (issues or [])],
        }, WriterDraft)
        if result is None:  # Batch collector captures the call without executing it.
            return None
        draft, usage = result
        return WriterOutput(experience_id=draft.experience_id, operation='replace_field',
            original_quote=request.experience.current_text, sentences=draft.sentences), usage

    def verify(self, request: ReviewInput, candidate: WriterOutput,
               evidence: list[Evidence], core_ids: list[str],
               superseded: list[Evidence], preserved_ids: list[str] | None = None,
               previous_attempt: dict | None = None) -> tuple[FactVerification, Usage]:
        from .writing_policy import quality_candidates
        change_review=None
        if previous_attempt:
            prior=(previous_attempt.get('writer') or {}).get('sentences',[])
            current=[s.model_dump(mode='json') for s in candidate.sentences]
            def refs(sentences):
                return {(kind,eid) for sentence in sentences for kind in ('evidence_ids','intent_ids','target_context_ids')
                    for eid in sentence.get(kind,[])}
            change_review=dict(
                changed_sentence_indices=[i for i,s in enumerate(current) if not any(
                    s['text']==old.get('text') and refs([s])==refs([old]) for old in prior)],
                added_source_refs=sorted(refs(current)-refs(prior)),removed_source_refs=sorted(refs(prior)-refs(current)),
                changes_are_not_factual_verdicts=True)
        return self._call(VERIFY_SYSTEM_PROMPT, {
            "policy_version": POLICY_VERSION,
            "target_section": target_section(request.experience),
            "section_writing_rules": SECTION_RULES[target_section(request.experience)],
            "editorial_brief": editorial_brief(request),
            "approved_intents": [item.model_dump(mode='json') for item in request.approved_intents],
            "allowed_target_context": [item.model_dump(mode='json') for item in request.job_requirements],
            "original_experience_text": request.experience.current_text,
            "previous_attempt": previous_attempt,
            "candidate_change_review": change_review,
            "suggested_text": candidate.suggested_text,
            "sentences": [item.model_dump(mode="json") for item in candidate.sentences],
            "style_hints_not_failures": [i.model_dump() for i in quality_candidates(
                request.experience, candidate, {e.evidence_id: e for e in evidence})],
            "approved_evidence": scoped_evidence(request, evidence),
            # Live Writer and Verifier share editorial_brief. Do not reintroduce
            # a parallel include-all obligation through diagnostic legacy IDs.
            **({} if request.section_profile else {
                "core_evidence_ids": core_ids,
                "preserved_evidence_ids": preserved_ids or [],
            }),
            "superseded_original_evidence": [item.model_dump(mode="json") for item in superseded],
            "inactive_intents": [c.model_dump(mode='json') for c in request.existing_intents
                if c.id not in {i.id for i in request.approved_intents}],
        }, FactVerification)
