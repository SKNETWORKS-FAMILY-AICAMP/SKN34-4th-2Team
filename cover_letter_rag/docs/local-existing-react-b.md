# Existing React / local B adapter

The ordinary LMS React UI is used without new screen changes. Production v1 code
and develop are unchanged. Start from `feature/resume-review-quality`:

```powershell
# Terminal 1, repository/lms_api
& '..\.venv\Scripts\python.exe' local_resume_site.py runserver 127.0.0.1:8002 --noreload
# Terminal 2, repository/lms_api
& '..\.venv\Scripts\python.exe' local_resume_site.py ai
# Terminal 3, repository/lms_react
$env:VITE_LOCAL_RESUME_E2E='0'
$env:LMS_API_PROXY='http://127.0.0.1:8002'
npm.cmd run dev -- --host 127.0.0.1 --port 5180 --strictPort
```

Open `http://127.0.0.1:5180/resume`, not `/local/resume-e2e`.
Use the existing fictional local account `resume-e2e@example.test` /
`LocalE2E-only!`; production quick-login accounts are not copied.

Flow: React 5180 -> normal Django API 8002 -> B review API 8003 -> v2 core.
Both processes lock DB_HOST to loopback and use PostgreSQL 55439. Inline publishing
and external LangSmith tracing are disabled. Only the OpenAI key is deliberately
loaded by the launcher; no source DB credentials are printed.

The B process reuses existing context/tailoring/session/apply/undo endpoints, but
replaces the review service factory with a v2 adapter in that process only.
The v1 prompt, generation workflow and React are not rewritten. v2 READY candidates
map to the existing SentenceReview contract; rejected candidates cannot be applied.
Request replay, owner checks and input hashes remain enforced. Atomic evidence and
supersession state are retained in local review telemetry between follow-up turns.

Frozen user-selected target: `SARAMIN-55149877`, source Resume 33, local copy 4
(public ID `local-ab-source-resume-33`). The local copy has linked_job_id so the
existing UI reads the linked posting rather than running recommendation again.
Applicant content was copied unchanged; it is not a fixture or an AI-tailored draft.
Snapshot: `c66c3172aff177730b071d533364823bdb8f3cf895bd78a1fd5932c4c4f926f9`.
Existing matching requirement profile contains 14 requirements. No extraction was
performed. Requirement rows start unconfirmed; v2 does not fabricate v1 requirement
match scores. Recommendation algorithms are not changed.

Verified: normal login/bootstrap 200; Django -> running B context 200; cached
requirements 200/14; v2 adapter/core unit tests 41 passed; v2-ready response works
with the existing deterministic apply builder; diff whitespace check passed.
The initial live review exceeded the UI's 180-second timeout: the old adapter
ran a complete generation/verification pipeline serially for each experience.
The adapter now batches Analyst, Writer and semantic verification across experiences.
Normal requests use three calls; at most one conditional batch rewrite and recheck
may add two calls. Each experience retains independent evidence and validators.
The request has a 165-second LLM budget, SDK retries are disabled, and stage usage
is persisted during execution. If conditional repair cannot be verified within
the budget, those candidates remain non-applicable; verified independent results
are not discarded. Shared job requirements are included once per batch, unchanged.
Browser rendering and interactive apply/undo still require human verification.
The browser automation tool rejected the local URL, and was not bypassed.

This adapter covers ordinary and job-targeted Resume Review, not the separate
Application question-answer Writer UI. It is not production rollout configuration.
No migrations, RDS writes, develop edits, commit or push were performed.

2026-10-02 timeout fix verification:
- Offline adapter/core/batch tests: 49 passed.
- Normal Django review API -> running B API -> local storage: HTTP 200, 132.52 s.
- Final request: batch_smoke_dca6f124032246b2a0b1915de66adfc4.
- Final request used 5 calls, 23,105 input tokens / 17,408 output tokens.
- All 11 narrative targets returned. Three rewritten project candidates failed
  semantic fact-preservation checks and were not exposed as apply-ready. Four
  confirmation questions were returned. This verifies execution, not as-is quality.
- Two preceding diagnostics failed (150 s timeout, then analysis contract error).
  Total attempted live calls in this fix: 11; usage of timed-out calls is unknown.
- Old interrupted serial request was marked failed in local DB, never replayed.
- No Pinecone, recommender rerank, requirement extraction, RDS or v1 modifications.
