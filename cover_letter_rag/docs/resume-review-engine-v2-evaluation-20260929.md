# Resume Review Engine v2: first offline implementation check

This report distinguishes **code working** from **submission quality proven**.
The core was run on ten small, fictional Korean resume examples using the
configured `gpt-6-luna` model and medium reasoning. No DB, production API,
React, or AWS resource was changed. LangSmith tracing was disabled for the run.
Human verdict fields in `evaluation/v2_results/*.md` remain blank for review.

## Deterministic tests

- `tests/test_resume_review_v2.py`: **19 passed**. Covers strict schemas,
  source quotes, experience IDs, assertion states, selected/omitted Evidence,
  question dedupe, unsupported numbers/technology, target and claim mapping,
  quality failure, one-rewrite limit, stale apply hash, and answer exclusion
  from the Writer input.
- Targeted v1/v2 tests (`test_resume_review_v2.py`, `test_resume_review.py`,
  `test_resume_quality.py`): **107 passed**.
- Full `cover_letter_rag/tests` was attempted. It has **one v1 test failure**
  (`FirebaseGateway._db` has no setter) and **12 collection/setup errors** in
  `test_matching_handoff.py` because an offline PostgreSQL URL is absent.
  These are outside v2 and were not bypassed by connecting to the target RDS.

## Ten live examples (one saved result per case)

`calls` and tokens below are for the saved successful execution of each case;
earlier contract-failure attempts are not included and their API usage cannot
be reconstructed from the old harness logs. The harness now records attempted
calls for future failures. LLM latency is the sum of reported model calls,
not end-to-end user-visible latency.

| Case | Saved status | Calls | Input / output tokens | LLM ms | Observation |
|---|---:|---:|---:|---:|---|
| 01 procedure dump | READY at run time | 3 | 3,633 / 3,266 | 32,375 | Still lists steps; current deterministic gate now flags `procedure_overload`. **Not a quality success.** |
| 02 technical signal | READY | 5 | 6,472 / 4,933 | 47,218 | Redis, TTL, parallel calls, and supported latency result remain visible. |
| 03 duplicate answer | READY, no candidate | 1 | 1,140 / 1,334 | 12,281 | Avoided forced rewrite. |
| 04 action without result | READY | 5 | 4,937 / 3,608 | 35,063 | JWT and authorization work retained; no invented outcome. |
| 05 confirmed result | READY | 3 | 3,166 / 1,894 | 20,657 | Result retained, but Korean phrasing needs human editing. |
| 06 team versus self | READY | 3 | 2,944 / 2,099 | 20,797 | Kept own React/Django work, did not claim crawler/model training. |
| 07 no result | NEEDS_EVIDENCE, no candidate | 1 | 1,120 / 1,277 | 13,219 | Did not invent usage metrics; asks about implementation instead. |
| 08 uncertain/correction | REJECTED | 5 | 3,782 / 2,593 | 29,406 | New user correction conflicts with original “implemented”; v2 currently cannot resolve/retract original fact. |
| 09 job-only technology | REJECTED | 3 | 3,123 / 2,108 | 21,063 | Did not insert Kubernetes, but failed exact claim-span mapping after one rewrite. |
| 10 already good | READY, no candidate | 1 | 1,147 / 2,133 | 19,656 | Avoided unnecessary rewrite. |

Saved executions: **30 completed LLM calls**, 31,464 input and 25,245 output
tokens, 251,735 ms cumulative LLM latency. This is **not** total API cost:
contract failures and intentional, limited reruns during development are not
included in these saved-result totals.

`python -m evaluation.v2_recheck` reruns deterministic gates on saved results
without API calls. It now marks case 01 `REWRITE` for procedure overload;
case 08 remains rejected by its saved semantic verification, even though a
deterministic-only recheck cannot reproduce that semantic finding.

## Five same-input v1/v2 comparisons

The v1 engine was **not modified**. Its in-memory follow-up was given the
same original experience, question, and answer as v2. Paired outputs and
blank human verdicts are in `evaluation/v2_results/*_compare.md`.

- 01: both outputs list processing steps. v2 omits some lower-value steps but
  is still not clearly apply-as-is.
- 02: both preserve Redis/parallel processing and 2.8→0.6 second result;
  v1 wording is at least as natural in this sample.
- 04: both describe JWT and role access without inventing a result; similar.
- 05: both preserve the SQL-query reduction but both use awkward Korean phrasing.
- 09: both generated the same useful Docker sentence; v2 withheld it because
  its claim text was not an exact substring of the revision.

No claim that v2 beats v1 is justified from these five examples. The most
important next work is resolving contradictory user corrections, improving
claim-span generation without relaxing provenance, and making procedural
writing fail or condense reliably. A person must fill the apply verdicts.
