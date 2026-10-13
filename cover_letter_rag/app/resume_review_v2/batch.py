"""Local site batch orchestration; preserves the per-experience v2 validators."""
import copy
import os
import time
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pydantic import ConfigDict, create_model
from .llm import LangChainReviewLLM
from .engine import _add_usage, trace_review, unwritten_validation, failed_preparation
from .models import (AnalystOutput, WriterOutput, FactVerification, ReviewResult,
                     RevisionCandidate, RevisionPlan, ValidationResult, ValidationIssue, Usage, AssertionState)
from .validation import validate_candidate, ContractError
from .policy import BATCH_POLICY
from .project_planning import prepare_review


# Experiences per LLM request and concurrent requests per stage (11-12 experiences → 6 requests).
# RESUME_REVIEW_CHUNK_SIZE=100 restores the former single request per stage.
CHUNK_SIZE = max(1, int(os.environ.get('RESUME_REVIEW_CHUNK_SIZE') or 2))
MAX_PARALLEL = 6
# Process-wide cap on in-flight review requests. One review fits exactly; a second
# concurrent review waits for a slot instead of tripping the tokens-per-minute limit
# (2 workers x 6 x ~12k tokens/min stays under 200k TPM).
LLM_SLOTS = threading.BoundedSemaphore(int(os.environ.get('RESUME_REVIEW_MAX_CONCURRENCY') or 6))
RATE_LIMIT_RETRIES = 2
# Each chunk runs analyze → write → verify → rewrite on its own instead of waiting for
# the slowest chunk at every stage (2026-10-13, same resume and time: 163s → 125s).
# RESUME_REVIEW_PIPELINE=0 restores stage-by-stage execution.
PIPELINE = (os.environ.get('RESUME_REVIEW_PIPELINE') or '1').strip() != '0'
# A pipelined chunk starts a new stage only with this much request budget left;
# otherwise it saves and the next request continues it with a fresh budget.
STAGE_MIN_SECONDS = {'analyze': 90, 'write': 60, 'verify': 45}


def configured_stage_efforts():
    """Analyze at low effort by default; Writer and Verifier keep the configured effort.

    Three paired runs (2026-10-13, two postings): analyze 96s → 59s, output tokens −22%,
    READY 8.3 → 8.0 and the same questions where it mattered (students see at most 3).
    Lowering Writer too added contract failures and rejections. RESUME_REVIEW_ANALYZE_EFFORT=medium restores.
    """
    effort = (os.environ.get('RESUME_REVIEW_ANALYZE_EFFORT') or 'low').strip()
    return {'analyze': effort}


def analysis_weight(request):
    """Expected Analyze output for one experience: it re-quotes its sources, so text length.

    Projects also yield a project profile and more evidence per character (2026-10-13:
    about 4 output tokens per source character against 2.8 for other sections).
    """
    chars = len(request.experience.current_text) + len(request.answer or '') + sum(
        len(s.text) for s in request.resume_sources)
    return chars * (1.4 if request.experience.kind == 'project' else 1.0)


def balanced_groups(requests, size):
    """Chunks of at most `size` with similar Analyze work, so no chunk holds two long projects.

    The slowest chunk sets the review time; adjacent grouping put the two longest
    projects together (63s) while a short pair finished in 22s. Same requests and calls,
    only the neighbours change. Heaviest first into the lightest open chunk; deterministic.
    """
    if not requests:
        return {}
    count = -(-len(requests) // size)
    loads, groups = [0.0] * count, [[] for _ in range(count)]
    order = sorted(range(len(requests)), key=lambda i: (-analysis_weight(requests[i]), i))
    for i in order:
        g = min((g for g in range(count) if len(groups[g]) < size), key=lambda g: (loads[g], g))
        groups[g].append(i)
        loads[g] += analysis_weight(requests[i])
    return {str(g): [requests[i].experience.experience_id for i in sorted(members)]
            for g, members in enumerate(groups)}


class StageBoundary(Exception):
    """Completed work is persisted; the next HTTP request gets a fresh budget."""


def shared_context_payload(captured):
    items = {f'item_{i}': dict(row[1]) for i, row in enumerate(captured)}
    shared = {}
    for key in ('job_requirements', 'target_context', 'allowed_target_context'):
        value = captured[0][1].get(key)
        if (value or key == 'job_requirements' and value is not None) and all(row[1].get(key) == value for row in captured):
            shared['shared_' + key] = value
            for item in items.values():
                item.pop(key)
    return {**shared, 'items': items} if shared else items


class BatchReviewEngine:
    def __init__(self, model, reasoning_effort, budget_seconds=165, on_progress=None, stage_limited=False):
        self.model_name, self.reasoning = model, reasoning_effort
        self.deadline = time.monotonic() + budget_seconds
        self.usage = Usage()
        self.stages = []
        self.attempted_calls = 0
        self.on_progress = on_progress
        self.stage_limited = stage_limited
        self.request_calls = 0
        self.checkpoint = {}
        self._lock = threading.RLock()
        self.chunk_size = CHUNK_SIZE
        # Reasoning effort per stage ('analyze' / 'write' / 'verify'); unset stages use reasoning_effort.
        self.stage_efforts = {}
        self._writer = threading.Lock()
        self._progress_version = self._written_version = 0
        self.llm_window = None  # (first request start, last request end) in this HTTP request, for timing logs
        self.pipeline = PIPELINE
        # A pipelined chunk is a shallow copy whose counters, slots and progress belong to root.
        self.root, self.chunk_id = self, None

    def _counters(self):
        if self.root is not self:
            return {}  # Counted once on the root checkpoint, not copied into every chunk.
        return dict(usage=self.usage.model_dump(), stages=self.stages, attempted_calls=self.attempted_calls)

    def _progress(self, wait=True):
        """Record bookkeeping and persist it through on_progress.

        A write is a DB round trip (seconds from a dev PC to RDS). Chunks must not queue
        behind each other's writes, so concurrent calls coalesce: one writer at a time
        sends the newest state, and wait=False returns at once while another writes.
        Callers that must be durable (stage end, single-threaded paths) wait.
        """
        if self.root is not self:
            with self._lock:
                # Publish a shallow copy: later top-level edits stay private until the next publish.
                self.root.checkpoint.setdefault('chunks', {})[self.chunk_id] = dict(self.checkpoint)
            # Chunks never wait for a DB write (about 1s each from a dev PC, queued across six
            # chunks it added ~30s per request); the root writes durably before control leaves.
            return self.root._progress(wait=False)
        with self._lock:
            self.checkpoint.update(usage=self.usage.model_dump(), stages=self.stages,
                                   attempted_calls=self.attempted_calls)
            self._progress_version += 1
        if not self.on_progress:
            return
        while self._writer.acquire(blocking=wait):
            try:
                with self._lock:
                    if self._written_version == self._progress_version:
                        return
                    version = self._progress_version
                    state = copy.deepcopy(dict(self.usage.model_dump(), stages=self.stages,
                        attempted_calls=self.attempted_calls, stage_checkpoint=self.checkpoint))
                self.on_progress(state)
                self._written_version = version
            finally:
                self._writer.release()

    def _save_states(self, states, completed):
        for state in states.values():
            self._sync_work(state)
        self.checkpoint = dict(version=1, input_signature=self.checkpoint.get('input_signature'),
            stage_outputs=self.checkpoint.get('stage_outputs', {}), states={key: dict(
            request=s['request'].model_dump(mode='json'), result=self._result(key, s).model_dump(mode='json'),
            evidence=[e.model_dump(mode='json') for e in s['evidence'].values()],
            needs_write=s['needs_write'], needs_verify=s.get('needs_verify', False),
            write_count=s['write_count']) for key, s in states.items()},
            completed={key: r.model_dump(mode='json') for key, r in completed.items()}, **self._counters())
        self._progress()

    @staticmethod
    def _sync_work(state):
        """Flags describe remaining work, not a second independent verdict.

        Recover repairable REWRITE checkpoints written with both flags off.
        Terminal verdicts never acquire another writing attempt; unavailable
        verification resumes the same draft without consuming a rewrite.
        """
        status = state['validation'].status
        writer = state['writer']
        if status == 'REWRITE' and writer is not None:
            if state.get('needs_verify') and not state['validation'].factual_issues and not state['validation'].intent_issues:
                state['needs_write'] = False
                return  # Quality flags alone do not skip independent verification.
            remaining = state['write_count'] < 2
            state['needs_write'], state['needs_verify'] = remaining, False
            if not remaining:
                state['validation'].status = 'REJECTED'
        elif status == 'REJECTED':
            retry_verify = writer is not None and any(
                issue.code == 'verification_unavailable' for issue in state['validation'].all_issues)
            state['needs_write'], state['needs_verify'] = False, retry_verify
        elif writer is not None:
            state['needs_write'] = False
        else:
            state['needs_verify'] = False

    @staticmethod
    def _record_attempt(state):
        state['attempts'].append({'writer': state['writer'].model_dump(mode='json'),
                                 'validation': state['validation'].model_dump(mode='json')})

    @staticmethod
    def _result(key, s):
        r, a, p, e, w, v = (s[name] for name in ('request', 'analysis', 'plan', 'evidence', 'writer', 'validation'))
        candidate = RevisionCandidate(experience_id=key, field_path=r.experience.field_path,
            content_hash=r.experience.content_hash, original_quote=w.original_quote,
            suggested_text=w.suggested_text, sentences=w.sentences, validation=v) if w else None
        return ReviewResult(experience=r.experience, question=r.question, answer=r.answer,
            extracted_evidence=[e[x.evidence_id] for x in a.extracted_evidence],
            selected_evidence=[e[eid] for eid in p.core_evidence_ids + p.supporting_evidence_ids],
            omitted_evidence=p.omitted_evidence, plan=p, proposed_question=a.question,
            spelling_fixes=r.spelling_fixes,
            candidate=candidate, validation=v, usage=Usage(),
            debug_trace={**trace_review(r, e, p, w, v, s['attempts']),
                         'writer_attempts': s['write_count'],
                         'question_selection': s.get('question_selection', {'state':'not_recorded'}),
                         'semantic_preparation': s.get('semantic_preparation', {'state':'not_recorded'}),
                         **({'extraction_failure':s['extraction_failure']} if s.get('extraction_failure') else {})}, **s['planning'])

    def _batch(self, method, items):
        """One stage over many experiences, split into concurrent requests.

        Generation time follows output length, so one envelope for 11-12
        experiences took 120-220s and crossed the 165s request budget on slow
        API hours. Experiences are analyzed independently; only the shared job
        context is repeated per chunk. The whole group counts as one stage.
        """
        if not items:
            return {}
        keys = list(items)
        size = self.chunk_size
        chunks = [{k: items[k] for k in keys[i:i + size]} for i in range(0, len(keys), size)]
        prepared = [self._prepare(method, chunk) for chunk in chunks]
        stage_outputs = self.checkpoint.get('stage_outputs', {})
        if self.stage_limited and any(p[-1] not in stage_outputs for p in prepared):
            if self.root is not self:
                if self.deadline - time.monotonic() < STAGE_MIN_SECONDS.get(method, 45):
                    raise StageBoundary()
            elif self.request_calls:
                raise StageBoundary()
        try:
            if len(chunks) == 1:
                return self._call_once(method, chunks[0], prepared[0])
            rows, failure = {}, None
            with ThreadPoolExecutor(max_workers=min(MAX_PARALLEL, len(chunks))) as pool:
                futures = [pool.submit(self._call_once, method, c, p) for c, p in zip(chunks, prepared)]
                for future in futures:
                    try:
                        rows.update(future.result())
                    except Exception as exc:  # Finished chunks stay in stage_outputs for the retry.
                        failure = failure or exc
            if failure:
                raise failure
            return rows
        finally:
            self._progress()  # Durable output, including every finished chunk, before control leaves this stage.

    def _prepare(self, method, items):
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
        original_payload = {f'item_{i}': row[1] for i, row in enumerate(captured)}
        payload = shared_context_payload(captured)
        from app.review_workflow import digest
        stage_key = digest([method, payload])
        return captured, schema, envelope, original_payload, payload, stage_key

    def _request(self, stage, system, payload, envelope):
        """One LLM request inside a process-wide slot; rate limits wait and retry within the budget."""
        from langchain_openai import ChatOpenAI
        from openai import RateLimitError
        if not LLM_SLOTS.acquire(timeout=max(0.0, self.deadline - time.monotonic())):
            raise TimeoutError('local_review_deadline_exceeded')
        try:
            for attempt in range(RATE_LIMIT_RETRIES + 1):
                remaining = self.deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('local_review_deadline_exceeded')
                client = LangChainReviewLLM.__new__(LangChainReviewLLM)
                client.model = ChatOpenAI(model=self.model_name,
                    reasoning_effort=self.stage_efforts.get(stage['stage'], self.reasoning),
                    use_responses_api=True, max_retries=0, timeout=remaining)
                client.attempted_calls, client.recorded_usage = 0, Usage()
                try:
                    return client._call(system, payload, envelope)
                except RateLimitError:
                    pause = 2 ** (attempt + 1)
                    # Keep enough budget for the retried request itself.
                    if attempt == RATE_LIMIT_RETRIES or self.deadline - time.monotonic() < pause + 30:
                        raise
                    with self._lock:
                        stage['rate_limit_retries'] = attempt + 1
                    time.sleep(pause)
        finally:
            LLM_SLOTS.release()

    def _call_once(self, method, items, prepared):
        captured, schema, envelope, original_payload, payload, stage_key = prepared
        root = self.root
        # Chunks run on worker threads; shared bookkeeping and progress writes are serialized.
        with self._lock:
            cached = self.checkpoint.get('stage_outputs', {}).get(stage_key)
            if cached:
                result_type = WriterOutput if method == 'write' else schema
                return {key: result_type.model_validate(row) for key, row in cached.items()}
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('local_review_deadline_exceeded')
            root.attempted_calls += 1
            root.request_calls += 1
            stage = {'stage': method, 'items': len(items), 'status': 'running',
                'budget_at_start_ms': round(remaining * 1000),
                'payload_before_bytes': len(json.dumps(original_payload, ensure_ascii=False).encode()),
                'payload_bytes': len(json.dumps(payload, ensure_ascii=False).encode())}
            if self.chunk_id is not None:
                stage['chunk'] = self.chunk_id
            root.stages.append(stage)
        self._progress(wait=False)
        started = time.monotonic()
        try:
            result, usage = self._request(stage, captured[0][0] + '\n' + BATCH_POLICY, payload, envelope)
            rows = {key: getattr(result, f'item_{i}') for i, key in enumerate(items)}
            if method == 'write':
                rows = {key: WriterOutput(experience_id=row.experience_id, operation='replace_field',
                    original_quote=items[key][0].experience.current_text, sentences=row.sentences)
                    for key, row in rows.items()}
            with self._lock:
                _add_usage(root.usage, usage)
                stage.update(status='complete', **usage.model_dump())
                self.checkpoint.setdefault('stage_outputs', {})[stage_key] = {key:row.model_dump(mode='json') for key,row in rows.items()}
                self.checkpoint.update(self._counters())
            return rows  # _batch persists before control leaves the stage.
        except Exception as exc:
            with self._lock:
                stage.update(status='failed', error_type=type(exc).__name__)
            raise
        finally:
            ended = time.monotonic()
            with self._lock:
                stage['wall_ms'] = round((ended - started) * 1000)
                window = root.llm_window
                root.llm_window = (min(window[0], started), max(window[1], ended)) if window else (started, ended)
            self._progress(wait=False)

    def run_many(self, requests, resume_records=None, checkpoint=None):
        checkpoint = checkpoint or {}
        stagewise_saved = 'chunks' not in checkpoint and any(
            key in checkpoint for key in ('analyses', 'states', 'stage_outputs', 'completed'))
        # A small group (one answered question) is one chunk: still one request, not one per stage.
        if self.pipeline and self.root is self and requests and not stagewise_saved:
            return self._run_pipelined(requests, resume_records or {}, checkpoint)
        return self._run_stagewise(requests, resume_records, checkpoint)

    def _out_of_time(self):
        """A pipelined chunk interrupted by the request deadline continues in the next request."""
        return self.stage_limited and self.root is not self and self.deadline - time.monotonic() < 5

    def _child(self, chunk_id):
        child = copy.copy(self)
        child.root, child.chunk_id = self, chunk_id
        child.chunk_size = 10 ** 6  # One request per stage inside the chunk.
        child.checkpoint, child.pipeline = {}, False
        return child

    def _work_groups(self, requests, resume_records):
        """Balance only experiences that call the LLM; reused records share one call-free chunk."""
        def reused(r):
            record = resume_records.get(r.experience.experience_id)
            return record is not None and not any(i.get('code') == 'verification_unavailable'
                for i in (record.get('validation') or {}).get('factual_issues') or [])
        groups = balanced_groups([r for r in requests if not reused(r)], self.chunk_size)
        kept = [r.experience.experience_id for r in requests if reused(r)]
        if kept:
            groups[str(len(groups))] = kept
        return groups

    def _run_pipelined(self, requests, resume_records, checkpoint):
        """Chunks of CHUNK_SIZE experiences run the whole review concurrently.

        Each chunk keeps its own checkpoint under checkpoint['chunks'][id]; a finished
        chunk is stored as results only. When the request budget runs out, finished and
        interrupted chunks are saved and StageBoundary hands the rest to the next request.
        """
        from .audit_resume import stage_signature
        indexed = {r.experience.experience_id: r for r in requests}
        if len(indexed) != len(requests):
            raise ContractError('duplicate experience identity')
        signature = stage_signature(requests, self.model_name, self.reasoning)
        if checkpoint.get('input_signature') != signature:
            checkpoint = {}
        self.checkpoint = checkpoint
        if checkpoint:
            self.usage = Usage.model_validate(checkpoint.get('usage', {}))
            self.stages = list(checkpoint.get('stages', []))
            self.attempted_calls = checkpoint.get('attempted_calls', 0)
        saved = checkpoint.get('chunks', {})
        self.checkpoint.update(input_signature=signature, mode='pipelined', chunks=dict(saved))
        # A resumed review keeps the grouping its chunk checkpoints were saved under.
        keys = list(indexed)
        groups = checkpoint.get('groups') or ({  # Saved before balancing: chunks were adjacent.
            str(i // self.chunk_size): keys[i:i + self.chunk_size] for i in range(0, len(keys), self.chunk_size)}
            if saved else self._work_groups(requests, resume_records))
        self.checkpoint['groups'] = groups
        self.chunk_count = len(groups)

        def run(chunk_id):
            done = saved.get(chunk_id, {}).get('results')
            if done is not None and {r['experience']['experience_id'] for r in done} == set(groups[chunk_id]):
                return [ReviewResult.model_validate(r) for r in done]
            chunk_keys = groups[chunk_id]
            results = self._child(chunk_id).run_many([indexed[k] for k in chunk_keys],
                {k: resume_records[k] for k in chunk_keys if k in resume_records},
                copy.deepcopy(saved.get(chunk_id) or {}))
            with self._lock:
                self.checkpoint['chunks'][chunk_id] = {'results': [r.model_dump(mode='json') for r in results]}
            self._progress(wait=False)
            return results

        outcomes, failure, boundary = {}, None, False
        with ThreadPoolExecutor(max_workers=len(groups)) as pool:
            futures = {chunk_id: pool.submit(run, chunk_id) for chunk_id in groups}
            for chunk_id, future in futures.items():
                try:
                    outcomes[chunk_id] = future.result()
                except StageBoundary:
                    boundary = True
                except Exception as exc:
                    failure = failure or exc
        self._progress()  # Every finished and interrupted chunk is durable before control leaves.
        if failure and not (self.stage_limited and self.deadline - time.monotonic() < 5):
            raise failure
        if failure or boundary:
            raise StageBoundary()
        by_id = {r.experience.experience_id: r for chunk_id in groups for r in outcomes[chunk_id]}
        results = [by_id[key] for key in indexed]
        for r in results:
            r.usage = Usage()
        if results:
            results[0].usage = self.usage.model_copy()
        return results

    def _run_stagewise(self, requests, resume_records=None, checkpoint=None):
        # The local adapter admits only records with identical owning inputs.
        # Completed results are reused; unavailable verification resumes from
        # the saved draft, never from a fabricated successful verdict.
        resume_records = resume_records or {}
        indexed = {r.experience.experience_id: r for r in requests}
        if len(indexed) != len(requests):
            raise ContractError('duplicate experience identity')
        from .models import ReviewInput, Evidence, ExtractionOutput
        from .audit_resume import stage_signature
        signature = stage_signature(requests, self.model_name, self.reasoning)
        checkpoint = checkpoint or {}
        if checkpoint and checkpoint.get('input_signature') != signature:
            checkpoint = {}  # No partial stage can survive changed owning inputs.
        self.checkpoint = checkpoint
        self.checkpoint['input_signature'] = signature
        if checkpoint and self.root is self:
            self.usage = Usage.model_validate(checkpoint.get('usage', {}))
            self.stages = list(checkpoint.get('stages', []))
            self.attempted_calls = checkpoint.get('attempted_calls', 0)
        analyses = {key: ExtractionOutput.model_validate(value) for key, value in checkpoint.get('analyses', {}).items()}
        missing = {key: (r,) for key, r in indexed.items() if key not in resume_records and key not in analyses and key not in checkpoint.get('states', {})}
        analyses.update(self._batch('analyze', missing))
        # Save raw extraction before planning; a process crash here must not pay
        # for another Analyze. Input identity is checked before any restore.
        self.checkpoint.update(input_signature=signature, analyses={k:v.model_dump(mode='json') for k,v in analyses.items()},
            **self._counters())
        self._progress()
        states = {}
        completed = {key: ReviewResult.model_validate(value) for key, value in checkpoint.get('completed', {}).items()}
        for key, r in indexed.items():
            if key in completed:
                continue
            if key in checkpoint.get('states', {}):
                raw = checkpoint['states'][key]
                r = ReviewInput.model_validate(raw['request'])
                saved = ReviewResult.model_validate(raw['result'])
                evidence = {e.evidence_id:e for e in map(Evidence.model_validate, raw['evidence'])}
                writer = WriterOutput(experience_id=key, operation='replace_field',
                    original_quote=saved.candidate.original_quote, sentences=saved.candidate.sentences) if saved.candidate else None
                states[key] = dict(request=r, analysis=AnalystOutput(experience_id=key,
                    extracted_evidence=saved.extracted_evidence, plan=saved.plan, question=saved.proposed_question),
                    evidence=evidence, plan=saved.plan,
                    permitted=[evidence[eid] for eid in dict.fromkeys(saved.plan.core_evidence_ids + saved.plan.supporting_evidence_ids + saved.plan.preserved_evidence_ids)],
                    writer=writer, validation=saved.validation, planning={name:getattr(saved,name) for name in
                        ('project_profile','evidence_facets','evidence_gaps','gap_questions','unavailable_slots','intent_claims','section_profile','sentence_plan','requirement_matches','requirement_warnings')},
                    attempts=list(saved.debug_trace.get('attempts', [])), write_count=raw['write_count'],
                    needs_write=raw['needs_write'], needs_verify=raw['needs_verify'],
                    extraction_failure=saved.debug_trace.get('extraction_failure'))
                states[key]['question_selection'] = saved.debug_trace.get('question_selection', {'state':'not_recorded'})
                states[key]['semantic_preparation'] = saved.debug_trace.get('semantic_preparation', {'state':'not_recorded'})
                continue
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
                    'evidence_gaps', 'gap_questions', 'unavailable_slots', 'intent_claims', 'section_profile', 'sentence_plan', 'requirement_matches', 'requirement_warnings')}
                states[key] = dict(request=r, analysis=AnalystOutput(experience_id=key,
                    extracted_evidence=[], plan=plan, question=saved.proposed_question), evidence=evidence,
                    plan=plan, permitted=[evidence[eid] for eid in dict.fromkeys(
                        plan.core_evidence_ids + plan.supporting_evidence_ids + plan.preserved_evidence_ids)],
                    writer=writer, validation=saved.validation, planning=planning, attempts=attempts,
                    write_count=max(1, count), needs_write=False, needs_verify=True)
                states[key]['question_selection'] = saved.debug_trace.get('question_selection', {'state':'not_recorded'})
                states[key]['semantic_preparation'] = saved.debug_trace.get('semantic_preparation', {'state':'not_recorded'})
                continue
            failure = None
            try:
                prepared = prepare_review(r, analyses[key])
                analysis, evidence, plan = prepared.analysis, prepared.evidence, prepared.analysis.plan
                r = prepared.request.model_copy(update={'previous_facets': prepared.facets})
                planning = dict(project_profile=prepared.profile, evidence_facets=prepared.facets,
                    evidence_gaps=prepared.gaps, gap_questions=prepared.questions,
                    unavailable_slots=r.unavailable_slots, intent_claims=prepared.intents,
                    section_profile=prepared.section_profile, sentence_plan=prepared.sentence_plan,
                    requirement_matches=prepared.requirement_matches, requirement_warnings=prepared.requirement_warnings)
                validation = unwritten_validation(plan) if plan.operation == 'no_change' else ValidationResult(status='NEEDS_EVIDENCE' if self.stage_limited else 'READY')
            except ContractError as exc:
                rejected=failed_preparation(r,analyses[key],exc)
                failure=rejected.debug_trace['extraction_failure']
                evidence=getattr(exc,'approved_evidence',{})
                plan=rejected.plan
                analysis = AnalystOutput(experience_id=key, extracted_evidence=rejected.extracted_evidence, plan=plan)
                planning = {}
                validation = rejected.validation
            permitted = [evidence[eid] for eid in dict.fromkeys(
                plan.core_evidence_ids + plan.supporting_evidence_ids + plan.preserved_evidence_ids)]
            states[key] = dict(request=r, analysis=analysis, evidence=evidence, plan=plan,
                               permitted=permitted, writer=None,
                               validation=validation, planning=planning, attempts=[], write_count=0, needs_write=plan.operation != 'no_change', needs_verify=False,
                               extraction_failure=failure)
            states[key]['question_selection'] = ({'state':'analysis_failed', 'reason':'analysis_contract_invalid'}
                if failure else prepared.question_selection)
            states[key]['semantic_preparation'] = ({'state':'analysis_failed', 'reason':'analysis_contract_invalid'}
                if failure else prepared.semantic_preparation)
        self._save_states(states, completed)
        self.checkpoint['input_signature'] = signature
        self._progress()
        pending = {k: s for k, s in states.items() if s['needs_write'] or s.get('needs_verify')}
        for attempt in range(2):
            if not pending:
                break
            # Never spend the entire remaining budget on a rewrite with no time to verify it.
            if attempt and self.deadline - time.monotonic() < 30:
                if self.stage_limited:
                    self._save_states(states, completed)
                    raise StageBoundary()
                break
            try:
                writes = self._batch('write', {k: (s['request'], s['plan'], s['permitted'],
                    s['validation'].all_issues,
                    s['writer'].suggested_text if s['writer'] else '',
                    s['writer']) for k, s in pending.items() if s['needs_write']})
            except StageBoundary:
                raise
            except Exception:
                if self._out_of_time():
                    raise StageBoundary()
                if not attempt:
                    raise
                break  # Existing failing candidates remain non-applicable.
            verify = {}
            for k, s in pending.items():
                if k in writes:
                    s['writer'] = writes[k]
                    s['write_count'] += 1
                    s['needs_write'] = False
                    s['needs_verify'] = True
                writer = s['writer']
                s['validation'] = validate_candidate(s['request'], writer, s['plan'], s['evidence'])
                if self.stage_limited and s['validation'].status == 'READY':
                    s['validation'] = ValidationResult(status='NEEDS_EVIDENCE', factual_issues=[
                        ValidationIssue(code='verification_pending', detail='후보는 생성됐지만 독립 검증이 완료되지 않았습니다.')])
                if (not s['validation'].factual_issues or all(i.code == 'verification_pending' for i in s['validation'].factual_issues)) and not s['validation'].intent_issues:
                    used = {eid for sentence in writer.sentences for eid in sentence.evidence_ids}
                    from .section_semantics import verification_sources
                    verify[k] = (s['request'], writer,
                        verification_sources(s['request'], s['plan'], s['permitted'], used),
                        s['plan'].core_evidence_ids,
                        [e for e in s['evidence'].values() if e.assertion_state == AssertionState.SUPERSEDED],
                        s['plan'].preserved_evidence_ids,
                        s['attempts'][-1] if s['attempts'] else None)
                else:
                    s['needs_verify'] = False
                    self._record_attempt(s)
            self._save_states(states, completed)
            self.checkpoint['input_signature'] = signature
            self._progress()
            try:
                verified = self._batch('verify', verify)
            except StageBoundary:
                raise
            except Exception as exc:
                if self._out_of_time():
                    raise StageBoundary()  # The saved draft is verified in the next request.
                # A timeout cannot turn unverified text into an apply-ready revision,
                # and cannot erase independent candidates already verified successfully.
                for k in verify:
                    states[k]['validation'] = ValidationResult(status='REJECTED',
                        factual_issues=[ValidationIssue(code='verification_unavailable', detail=type(exc).__name__)])
                break
            for k, verification in verified.items():
                s = states[k]
                s['validation'] = validate_candidate(s['request'], s['writer'], s['plan'], s['evidence'], verification)
                s['needs_verify'] = False
                self._record_attempt(s)
            self._save_states(states, completed)
            pending = {k: s for k, s in pending.items() if s['needs_write'] or s['needs_verify']}
            self.checkpoint['input_signature'] = signature
            self._progress()
        results = []
        for key, s in states.items():
            r, a, p, e, w, v = (s[name] for name in ('request', 'analysis', 'plan', 'evidence', 'writer', 'validation'))
            if v.status == 'REWRITE':
                v.status = 'REJECTED'
            results.append(self._result(key, s))
        by_id = {r.experience.experience_id: r for r in results}
        by_id.update(completed)
        results = [by_id[key] for key in indexed]
        # Request-wide usage counted once, not multiplied by number of experiences.
        if results:
            results[0].usage = self.usage.model_copy()
        return results
