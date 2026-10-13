"""Pipelined chunks: each chunk runs its own analyze → write → verify; no network."""
import copy
from test_project_live_pipeline import pipeline  # noqa: F401 — fixture
import threading
import pytest
from app.resume_review_v2 import batch
from app.resume_review_v2.batch import BatchReviewEngine, StageBoundary
from app.resume_review_v2.models import (Evidence, Experience, ExtractionOutput, FactVerification,
    ReviewInput, RevisionSentence, Usage, WriterDraft)


def experiences(n=4):
    return [ReviewInput(experience=Experience(experience_id=str(i), kind='project', title='API',
        current_text='API 구현', field_path=f'projects[{i}].description', content_hash='h')) for i in range(n)]


class Scripted(BatchReviewEngine):
    """Answers every LLM request at the envelope level; on_call(method, chunk) runs first."""

    def __init__(self, on_call=None, **kwargs):
        super().__init__('fake', 'medium', **kwargs)
        self.log, self.on_call = [], on_call
        self.pipeline = True

    def _request(self, stage, system, payload, envelope):
        method, chunk = stage['stage'], stage.get('chunk')
        with self._lock:
            self.log.append((method, chunk))
        if self.on_call:
            self.on_call(method, chunk)
        items = payload.get('items', payload)
        rows = {}
        for name, item in items.items():
            eid = (item.get('experience') or {}).get('experience_id')
            if method == 'analyze':
                rows[name] = ExtractionOutput(experience_id=eid, extracted_evidence=[Evidence(
                    evidence_id='ev-' + eid, experience_id=eid, fact_type='action', normalized_fact='API 구현',
                    evidence_quote='API 구현', source_type='resume_text', source_id=eid, assertion_state='resume_stated')])
            elif method == 'write':
                rows[name] = WriterDraft(experience_id=eid, sentences=[
                    RevisionSentence(text='API를 구현했습니다.', evidence_ids=['ev-' + eid])])
            else:
                rows[name] = FactVerification()
        return envelope.model_validate({k: v.model_dump(mode='json') for k, v in rows.items()}), Usage(calls=1)


def test_chunk_verifies_while_another_chunk_is_still_analyzing():
    # Stage-by-stage execution cannot verify chunk 0 before chunk 1 finishes analyzing.
    verifying = threading.Event()
    def on_call(method, chunk):
        if method == 'verify' and chunk == '0':
            verifying.set()
        if method == 'analyze' and chunk == '1':
            assert verifying.wait(5), 'chunk 1 analysis blocked chunk 0'
    engine = Scripted(on_call)
    results = engine.run_many(experiences())
    assert [r.experience.experience_id for r in results] == ['0', '1', '2', '3']
    assert all(r.validation.status == 'READY' for r in results)
    assert sorted(engine.log) == sorted((m, c) for m in ('analyze', 'write', 'verify') for c in ('0', '1'))
    assert {s['chunk'] for s in engine.stages} == {'0', '1'}
    assert engine.attempted_calls == 6 and engine.usage.calls == 6
    assert results[0].usage.calls == 6 and all(r.usage.calls == 0 for r in results[1:])


def test_verify_failure_rejects_only_its_own_chunk():
    def on_call(method, chunk):
        if method == 'verify' and chunk == '1':
            raise RuntimeError('verifier unavailable')
    engine = Scripted(on_call)
    results = {r.experience.experience_id: r for r in engine.run_many(experiences())}
    failed = set(engine.checkpoint['groups']['1'])
    assert {k: r.validation.status for k, r in results.items()} == {
        k: 'REJECTED' if k in failed else 'READY' for k in results}
    assert all(results[k].validation.factual_issues[0].code == 'verification_unavailable' for k in failed)


def test_long_projects_are_not_grouped_together():
    # 2026-10-13: adjacent grouping put the two longest projects in one chunk (63s) and a
    # short pair in another (22s); the slowest chunk sets the whole review time.
    from app.resume_review_v2.batch import balanced_groups
    def item(i, kind, chars):
        return ReviewInput(experience=Experience(experience_id=str(i), kind=kind, title='t',
            current_text='가' * chars, field_path=f'f[{i}]', content_hash='h'))
    requests = [item(0, 'project', 1094), item(1, 'project', 992), item(2, 'project', 913), item(3, 'project', 453),
                item(4, 'other', 1021), item(5, 'other', 684), item(6, 'other', 1199), item(7, 'other', 676),
                item(8, 'other', 299), item(9, 'other', 243), item(10, 'other', 456), item(11, 'other', 398)]
    groups = balanced_groups(requests, 2)
    assert sorted(k for g in groups.values() for k in g) == sorted(str(i) for i in range(12))
    assert all(len(g) == 2 for g in groups.values())
    assert not any({'0', '1'} <= set(g) for g in groups.values())
    weight = {r.experience.experience_id: len(r.experience.current_text) * (1.4 if r.experience.kind == 'project' else 1)
              for r in requests}
    heaviest = max(sum(weight[k] for k in g) for g in groups.values())
    assert heaviest < 0.75 * (weight['0'] + weight['1'])  # adjacent grouping's heaviest chunk
    assert balanced_groups(requests, 2) == groups  # Deterministic across requests.


def test_budget_end_saves_chunks_and_next_request_continues_only_unfinished(monkeypatch):
    monkeypatch.setattr(batch, 'STAGE_MIN_SECONDS', {'analyze': 0, 'write': 0, 'verify': 0})
    def slow_write(method, chunk):
        if method == 'write' and chunk == '1':
            raise TimeoutError('request budget exhausted')
    written = []
    first = Scripted(slow_write, budget_seconds=3, stage_limited=True, on_progress=written.append)
    with pytest.raises(StageBoundary):
        first.run_many(experiences())
    saved = written[-1]['stage_checkpoint']
    assert saved['mode'] == 'pipelined'
    assert 'results' in saved['chunks']['0'] and 'states' in saved['chunks']['1']
    assert all('stages' not in chunk for chunk in saved['chunks'].values())  # Counted once at the root.
    monkeypatch.setattr(batch, 'STAGE_MIN_SECONDS', {'analyze': 90, 'write': 60, 'verify': 45})
    second = Scripted(stage_limited=True)
    results = second.run_many(experiences(), checkpoint=copy.deepcopy(saved))
    assert second.log == [('write', '1'), ('verify', '1')]
    assert all(r.validation.status == 'READY' for r in results)
    assert second.attempted_calls == len(first.stages) + 2


def test_low_budget_stops_before_starting_a_stage(monkeypatch):
    monkeypatch.setattr(batch, 'STAGE_MIN_SECONDS', {'analyze': 0, 'write': 999, 'verify': 0})
    engine = Scripted(stage_limited=True)
    with pytest.raises(StageBoundary):
        engine.run_many(experiences())
    assert sorted(engine.log) == [('analyze', '0'), ('analyze', '1')]
    assert all('states' in chunk for chunk in engine.checkpoint['chunks'].values())


def test_stagewise_checkpoint_finishes_stagewise():
    old = Scripted(stage_limited=True)
    old.pipeline = False
    with pytest.raises(StageBoundary):
        old.run_many(experiences())  # One stage per request: analysis only.
    engine = Scripted()
    results = engine.run_many(experiences(), checkpoint=copy.deepcopy(old.checkpoint))
    assert all(r.validation.status == 'READY' for r in results)
    assert all(chunk is None for _, chunk in engine.log) and engine.log[0][0] == 'write'


def test_pipeline_off_runs_stage_by_stage(monkeypatch):
    monkeypatch.setattr(batch, 'PIPELINE', False)
    engine = BatchReviewEngine('fake', 'medium')
    assert engine.pipeline is False


def test_staged_service_finishes_small_review_in_one_request(pipeline, monkeypatch):
    # 2026-10-13: one answered question took three requests (analyze · write · verify),
    # each paying ~20s of setup and DB outside the LLM. Pipelined, it is one request.
    from test_stage_checkpoints import staged
    from test_project_live_pipeline import post
    monkeypatch.setattr(batch, 'PIPELINE', True)
    client, reviews, calls, db = pipeline
    saved = staged(db, reviews)
    final = post(client, 'initial')
    assert final['telemetry']['execution']['state'] == 'verified'
    assert [stage for stage, _, _ in calls] == ['BatchExtractionOutput', 'BatchWriterDraft', 'BatchFactVerification']
    assert {s.get('chunk') for s in final['telemetry']['stages']} == {'0'}
    db.complete_review.assert_called_once()
    assert saved['initial']['checkpoint']['mode'] == 'pipelined'


def test_new_work_copy_of_promoted_copy_reuses_its_source_review(pipeline, monkeypatch):
    # 2026-10-13: 재첨삭 on an editing copy (matched_…) reviewed an unchanged resume from scratch.
    from test_stage_checkpoints import staged
    from test_project_live_pipeline import post
    monkeypatch.setattr(batch, 'PIPELINE', True)
    client, reviews, calls, db = pipeline
    staged(db, reviews)
    first = post(client, 'first')
    assert first['telemetry']['execution']['state'] == 'verified'
    used = len(calls)
    db.get_owned_tailored_resume.return_value = db.get_owned_resume.return_value
    db.latest_review_response.return_value = None  # The new work copy has no review yet.
    db.promoted_source_review.return_value = reviews['first']
    again = post(client, 'again', tailored_resume_id='tailored_new')
    db.promoted_source_review.assert_called_once()
    assert len(calls) == used  # Unchanged items reuse the source review: no LLM call.
    assert again['telemetry']['audit_resume']['reused_experiences'] == 1
    db.latest_review_response.return_value = {'review_id': 'again'}
    post(client, 'third', tailored_resume_id='tailored_new')
    db.promoted_source_review.assert_called_once()  # Only a work copy without history looks back.


def test_worker_budget_runs_whole_review_and_keeps_fingerprint(pipeline, monkeypatch):
    # The Celery worker calls the AI server directly (600s), not through nginx (210s).
    from test_stage_checkpoints import staged
    from test_project_live_pipeline import post
    from app.models import FirestoreResumeReviewRequest
    from types import SimpleNamespace
    from app import main
    from app.local_resume_site_adapter import LocalReviewService
    monkeypatch.setattr(batch, 'PIPELINE', True)
    client, reviews, calls, db = pipeline
    staged(db, reviews)
    # As in production: no injected engine, one engine per request with that request's budget.
    settings = SimpleNamespace(openai_model='fake', openai_reasoning_effort='medium')
    monkeypatch.setattr(main, 'build_resume_review_service', lambda: LocalReviewService(settings, db))
    final = post(client, 'initial', stage_budget_seconds=540)
    assert all(s['budget_at_start_ms'] > 500_000 for s in final['telemetry']['stages'])
    plain = post(client, 'plain')
    assert all(s['budget_at_start_ms'] <= 165_000 for s in plain['telemetry']['stages'])
    request = dict(cohort_id='c', resume_id='r', request_id='x')
    assert (FirestoreResumeReviewRequest(**request, stage_budget_seconds=540).model_dump()
            == FirestoreResumeReviewRequest(**request).model_dump())
