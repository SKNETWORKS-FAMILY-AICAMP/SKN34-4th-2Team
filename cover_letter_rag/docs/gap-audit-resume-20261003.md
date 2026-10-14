# Gap audit processing resume — 2026-10-03

## Scope

The local B adapter now admits reusable per-experience results before invoking the batch engine. The engine reuses completed results and resumes unavailable semantic verification from the saved candidate. It does not run extraction/planning or Writer again for admitted inputs. Existing Writer, deterministic validation, semantic verification, Question Planner policy, and the one-rewrite limit remain in force.

This uses two digests in existing review result JSON, not a new cache or database schema. `audit_source_hash` identifies owning source material; `audit_input_hash` includes source, answer history, evidence/intent/semantic state, question state, job requirements/snapshot, model settings, and policy version. Unrelated experience edits do not invalidate an established checkpoint. Changed source is rebuilt from current source and owning answer history; other changed inputs invalidate reuse. The global apply hash is rebound to the current resume on reused candidates.

Timeout results stay rejected until verification succeeds. A resumed candidate may use its remaining existing rewrite allowance if verification finds a problem; repeated audit cannot reset that allowance. Completed rejection is also reusable unless it represents unavailable verification or failed analysis.

Legacy records have no auxiliary-source snapshot. They are reused only when the original entire-resume hash and saved job/model/policy context match. A legacy record with a changed whole-resume hash is conservatively recomputed once. Safe per-experience reuse then becomes available through the new checkpoint. No retrospective hash is fabricated.

## Offline mounted B HTTP results

Fake model transport and in-memory mocked persistence; no live model, network, or database operations. Counts are API batches, with experience count in parentheses. Each scenario below has a successful resumed verifier; a semantic failure may trigger the existing bounded rewrite path.

| Audit scenario | Analyze | Writer | Verifier | Reused | Reanalyzed | HTTP elapsed, one local run |
|---|---:|---:|---:|---:|---:|---:|
| 11 saved drafts, previous verifier timeout | 0 | 0 | 1 (11) | 11 | 0 | 24.74 ms |
| Answered experience completed; 10 pending drafts | 0 | 0 | 1 (10) | 11 | 0 | 20.55 ms |
| One source changed; 10 pending unchanged drafts | 1 (1) | 1 (1) | 1 (11) | 10 | 1 | 20.33 ms |
| All 11 already completed | 0 | 0 | 0 | 11 | 0 | 17.00 ms |

These milliseconds measure application/serialization overhead under fake transport, not production latency. The existing historical audit log spent 90.812 s analyzing and 38.203 s writing all 11: 129.015 s of repeated work. With all owning inputs unchanged these stages are removed; with one source changed, only its analyze/write remains. Actual final elapsed is unmeasured and depends on verifier runtime and any necessary bounded rewrite. Its timeout remains governed by the existing request deadline; the old 35.766 s timeout is not a prediction of new verification time.

The local PostgreSQL connection timed out during this task, so the original reviews 17–19 were not replayed. The 11/1 shape was reproduced with the existing mounted-route fixture. Golden B-1/B-2/B-3 additionally verify that the initial and resumed verifier payloads are identical, including intent/meaning and evidence context.

## Validation

490 tests passed in 5.31 s:

`python -B -m pytest cover_letter_rag/tests --ignore=cover_letter_rag/tests/test_matching_handoff.py -p no:cacheprovider --tb=short`

The excluded matching handoff module creates/writes PostgreSQL fixtures; it was not executed. Tests cover unchanged resume, one changed text/title/technology/role, answer follow-up, evidence retraction, job/model/reasoning changes, repeated verifier timeout, cross-audit rewrite limit, legacy conservative fallback, and golden verifier context preservation. `git diff --check` passed.

No actual LLM calls, database changes, migrations, AWS/RDS changes, browser automation, commits, or pushes were performed for this change. No running server was restarted. New audit counts are exposed in `telemetry.audit_resume`; existing `telemetry.stages` retains batch items, status, usage, and elapsed.

## Changed paths for this optimization

- `app/local_resume_site_adapter.py`: checkpoint admission/persistence and reuse telemetry.
- `app/resume_review_v2/audit_resume.py`: source/input identity and conservative legacy admission.
- `app/resume_review_v2/batch.py`: completed-result reuse and saved-draft verification resume.
- `tests/test_gap_audit_resume.py`, `tests/test_project_live_pipeline.py`: offline regression coverage.

Earlier uncommitted quality changes remain in the worktree; they are not part of this latency change. Context reduction, concurrency changes, and a broader cache framework are intentionally outside this first optimization.
