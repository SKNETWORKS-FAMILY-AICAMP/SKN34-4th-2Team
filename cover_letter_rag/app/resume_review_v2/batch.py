"""Local site batch orchestration; preserves the per-experience v2 validators."""
import time
from pydantic import ConfigDict, create_model
from .llm import LangChainReviewLLM
from .engine import _add_usage, trace_review
from .models import (AnalystOutput, WriterOutput, FactVerification, ReviewResult,
                     RevisionCandidate, RevisionPlan, ValidationResult, ValidationIssue, Usage, AssertionState)
from .validation import validate_candidate, ContractError
from .policy import BATCH_POLICY
from .project_planning import prepare_review


class BatchReviewEngine:
    def __init__(self, model, reasoning_effort, budget_seconds=165, on_progress=None):
        self.model_name, self.reasoning = model, reasoning_effort
        self.deadline = time.monotonic() + budget_seconds
        self.usage = Usage()
        self.stages = []
        self.attempted_calls = 0
        self.on_progress = on_progress

    def _progress(self):
        if self.on_progress:
            self.on_progress(dict(self.usage.model_dump(), stages=self.stages,
                                  attempted_calls=self.attempted_calls))

    def _batch(self, method, items):
        if not items:
            return {}
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('local_review_deadline_exceeded')
        from langchain_openai import ChatOpenAI
        collector = LangChainReviewLLM.__new__(LangChainReviewLLM)
        captured = []
        collector._call = lambda system, payload, schema: captured.append((system, payload, schema))
        for args in items.values():
            getattr(collector, method)(*args)
        schema = captured[0][2]
        envelope = create_model('Batch' + schema.__name__,
            __config__=ConfigDict(extra='forbid'),
            **{f'item_{i}': (schema, ...) for i in range(len(items))})
        # Stable keyed envelope makes missing/duplicate results a schema error.
        payload = {f'item_{i}': row[1] for i, row in enumerate(captured)}
        common_requirements = captured[0][1].get('job_requirements')
        if common_requirements is not None and all(row[1].get('job_requirements') == common_requirements for row in captured):
            for item in payload.values():
                item.pop('job_requirements')
            payload = {'shared_job_requirements': common_requirements, 'items': payload}
        client = LangChainReviewLLM.__new__(LangChainReviewLLM)
        client.model = ChatOpenAI(model=self.model_name, reasoning_effort=self.reasoning,
            use_responses_api=True, max_retries=0, timeout=remaining)
        client.attempted_calls, client.recorded_usage = 0, Usage()
        self.attempted_calls += 1
        started = time.monotonic()
        stage = {'stage': method, 'items': len(items), 'status': 'running'}
        self.stages.append(stage)
        self._progress()
        try:
            result, usage = client._call(captured[0][0] +
                '\n' + BATCH_POLICY,
                payload, envelope)
            _add_usage(self.usage, usage)
            stage.update(status='complete', **usage.model_dump())
            if time.monotonic() >= self.deadline:
                raise TimeoutError('local_review_deadline_exceeded')
            rows = {key: getattr(result, f'item_{i}') for i, key in enumerate(items)}
            if method == 'write':
                rows = {key: WriterOutput(experience_id=row.experience_id, operation='replace_field',
                    original_quote=items[key][0].experience.current_text, sentences=row.sentences)
                    for key, row in rows.items()}
            return rows
        except Exception as exc:
            stage.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            stage['wall_ms'] = round((time.monotonic() - started) * 1000)
            self._progress()

    def run_many(self, requests, resume_records=None):
        # The local adapter admits only records with identical owning inputs.
        # Completed results are reused; unavailable verification resumes from
        # the saved draft, never from a fabricated successful verdict.
        resume_records = resume_records or {}
        indexed = {r.experience.experience_id: r for r in requests}
        if len(indexed) != len(requests):
            raise ContractError('duplicate experience identity')
        analyses = self._batch('analyze', {key: (r,) for key, r in indexed.items() if key not in resume_records})
        states = {}
        completed = {}
        for key, r in indexed.items():
            if key in resume_records:
                raw = resume_records[key]
                saved = ReviewResult.model_validate({name: raw[name] for name in ReviewResult.model_fields if name in raw})
                saved.experience = r.experience.model_copy(deep=True)
                saved.extracted_evidence = []  # Already in the persisted evidence state.
                saved.usage = Usage()
                if saved.candidate:
                    saved.candidate.content_hash = r.experience.content_hash
                retry_verify = any(i.code == 'verification_unavailable' for i in saved.validation.all_issues)
                if not retry_verify:
                    completed[key] = saved
                    continue
                if saved.candidate is None:
                    raise ContractError('verification checkpoint has no candidate')
                evidence = {e.evidence_id: e for e in r.experience.existing_evidence}
                plan = saved.plan
                r = r.model_copy(update={'section_profile': saved.section_profile,
                    'sentence_plan': saved.sentence_plan,
                    'approved_intents': [c for c in saved.intent_claims if c.state in
                        {AssertionState.RESUME_STATED, AssertionState.USER_ASSERTED}]})
                writer = WriterOutput(experience_id=key, operation='replace_field',
                    original_quote=saved.candidate.original_quote, sentences=saved.candidate.sentences)
                attempts = list(saved.debug_trace.get('attempts', []))
                # Old timeout records did not append the interrupted attempt.
                last_is_current = bool(attempts and attempts[-1]['writer'] == writer.model_dump(mode='json'))
                count = saved.debug_trace.get('writer_attempts', len(attempts) + (not last_is_current))
                planning = {name: getattr(saved, name) for name in ('project_profile', 'evidence_facets',
                    'evidence_gaps', 'gap_questions', 'unavailable_slots', 'intent_claims', 'section_profile', 'sentence_plan')}
                states[key] = dict(request=r, analysis=AnalystOutput(experience_id=key,
                    extracted_evidence=[], plan=plan, question=saved.proposed_question), evidence=evidence,
                    plan=plan, permitted=[evidence[eid] for eid in dict.fromkeys(
                        plan.core_evidence_ids + plan.supporting_evidence_ids + plan.preserved_evidence_ids)],
                    writer=writer, validation=saved.validation, planning=planning, attempts=attempts,
                    write_count=max(1, count), needs_write=False)
                continue
            try:
                prepared = prepare_review(r, analyses[key])
                analysis, evidence, plan = prepared.analysis, prepared.evidence, prepared.analysis.plan
                r = prepared.request.model_copy(update={'previous_facets': prepared.facets})
                planning = dict(project_profile=prepared.profile, evidence_facets=prepared.facets,
                    evidence_gaps=prepared.gaps, gap_questions=prepared.questions,
                    unavailable_slots=r.unavailable_slots, intent_claims=prepared.intents,
                    section_profile=prepared.section_profile, sentence_plan=prepared.sentence_plan)
                validation = ValidationResult(status='NEEDS_EVIDENCE' if analysis.question else 'READY')
            except ContractError as exc:
                # Reject only this experience; do not weaken evidence validation
                # or discard unrelated, correctly grounded experiences.
                evidence = {}
                plan = RevisionPlan(objective='근거 검증 실패로 원문 유지', operation='no_change')
                analysis = AnalystOutput(experience_id=key, extracted_evidence=[], plan=plan)
                planning = {}
                validation = ValidationResult(status='REJECTED', factual_issues=[
                    ValidationIssue(code='analysis_contract_invalid', detail=str(exc))])
            permitted = [evidence[eid] for eid in dict.fromkeys(
                plan.core_evidence_ids + plan.supporting_evidence_ids + plan.preserved_evidence_ids)]
            states[key] = dict(request=r, analysis=analysis, evidence=evidence, plan=plan,
                               permitted=permitted, writer=None,
                               validation=validation, planning=planning, attempts=[], write_count=0, needs_write=True)
        pending = {k: s for k, s in states.items() if s['plan'].operation != 'no_change'}
        for attempt in range(2):
            if not pending:
                break
            # Never spend the entire remaining budget on a rewrite with no time to verify it.
            if attempt and self.deadline - time.monotonic() < 30:
                break
            try:
                writes = self._batch('write', {k: (s['request'], s['plan'], s['permitted'],
                    s['validation'].all_issues,
                    s['writer'].suggested_text if s['writer'] else '') for k, s in pending.items() if s['needs_write']})
            except Exception:
                if not attempt:
                    raise
                break  # Existing failing candidates remain non-applicable.
            verify = {}
            for k, s in pending.items():
                if k in writes:
                    s['writer'] = writes[k]
                    s['write_count'] += 1
                writer = s['writer']
                s['validation'] = validate_candidate(s['request'], writer, s['plan'], s['evidence'])
                if not s['validation'].factual_issues and not s['validation'].intent_issues:
                    used = {eid for sentence in writer.sentences for eid in sentence.evidence_ids}
                    from .section_semantics import verification_sources
                    verify[k] = (s['request'], writer,
                        verification_sources(s['request'], s['plan'], s['permitted'], used),
                        s['plan'].core_evidence_ids,
                        [e for e in s['evidence'].values() if e.assertion_state == AssertionState.SUPERSEDED],
                        s['plan'].preserved_evidence_ids,
                        s['attempts'][-1] if s['attempts'] else None)
            try:
                verified = self._batch('verify', verify)
            except Exception as exc:
                # A timeout cannot turn unverified text into an apply-ready revision,
                # and cannot erase independent candidates already verified successfully.
                for k in verify:
                    states[k]['validation'] = ValidationResult(status='REJECTED',
                        factual_issues=[ValidationIssue(code='verification_unavailable', detail=type(exc).__name__)])
                break
            for k, verification in verified.items():
                s = states[k]
                s['validation'] = validate_candidate(s['request'], s['writer'], s['plan'], s['evidence'], verification)
            for s in pending.values():
                s['attempts'].append({'writer': s['writer'].model_dump(mode='json'),
                                      'validation': s['validation'].model_dump(mode='json')})
            pending = {k: s for k, s in pending.items() if s['validation'].status == 'REWRITE' and s['write_count'] < 2}
            for s in pending.values():
                s['needs_write'] = True
        results = []
        for key, s in states.items():
            r, a, p, e, w, v = (s[name] for name in ('request', 'analysis', 'plan', 'evidence', 'writer', 'validation'))
            if v.status == 'REWRITE':
                v.status = 'REJECTED'
            candidate = RevisionCandidate(experience_id=key, field_path=r.experience.field_path,
                content_hash=r.experience.content_hash, original_quote=w.original_quote,
                suggested_text=w.suggested_text, sentences=w.sentences, validation=v) if w else None
            results.append(ReviewResult(experience=r.experience, question=r.question, answer=r.answer,
                extracted_evidence=[e[x.evidence_id] for x in a.extracted_evidence],
                selected_evidence=[e[eid] for eid in p.core_evidence_ids + p.supporting_evidence_ids],
                omitted_evidence=p.omitted_evidence, plan=p, proposed_question=a.question,
                candidate=candidate, validation=v, usage=Usage(),
                debug_trace={**trace_review(r, e, p, w, v, s['attempts']),
                             'writer_attempts': s['write_count']}, **s['planning']))
        by_id = {r.experience.experience_id: r for r in results}
        by_id.update(completed)
        results = [by_id[key] for key in indexed]
        # Request-wide usage counted once, not multiplied by number of experiences.
        if results:
            results[0].usage = self.usage.model_copy()
        return results
