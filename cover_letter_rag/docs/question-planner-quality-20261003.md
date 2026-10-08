# Question value and follow-up state audit

## Observed B failure

Read-only local PostgreSQL review records 13–16, owning experience
`selfIntroduction.motivation`, source Resume 33 / local base 4 / tailored 10.

- Review 13 already extracted both motivation and job-interest intents. A combined
  semantic unit referenced them under `job_connection_and_contribution`.
  `section_questions()` only checked exact semantic_role membership, so it
  interpreted missing `motivation` and `job_connection` labels as missing meaning
  and emitted both generic questions. It did not evaluate marginal editing value.
- Review 14 received the first answer but failed with `duplicate semantic unit`
  before Writer. The adapter retained evidence but replaced intent/meaning state
  with the failed result's empty state.
- Review 15 reanalyzed the original without the earlier raw answer (only fresh
  answers were supplied). Compound labels again failed the slot check; only the
  first exact question key was blocked, leaving the second question eligible.
- Review 16 received the second answer but failed with `duplicate evidence_id:
  e8_1` before Writer. This was a delta/snapshot ID contract failure, not a finding
  that the user's answers had no value. Raw failed model responses are not stored,
  so whether that ID was an echoed old fact or a new answer fact is not recoverable.
- Separately, initial Writer candidates in records 13/15 were rejected because
  `decision_made` triggered a literal design-word gate for selecting evaluation
  criteria. A decision is not necessarily a design/ownership claim.

## Changed responsibility

The existing analysis call now proposes at most one value-assessed clarification
per experience, reusing GapQuestion. It sees original text, approved state, owning
answer/question history and separate job context. Its decision compares semantic
coverage, concrete editing benefit, specificity, relevance and applicant effort.
No additional model call or persistent schema is introduced.

The server still owns experience isolation, active source/premise validation,
unavailable topics, exact-repeat backstops and the resume-wide cap. Section label
membership and project slot diagnostics no longer authorize live questions.
There is no company-specific phrase rule, lexical similarity threshold or claim
that a null model proposal proves the original has no room for improvement.

Fresh current-answer claim IDs and semantic-unit IDs are reconciled before source
validation. Exact canonical echoes are ignored; colliding new answer claims get
turn-scoped IDs and their local references are remapped. Corrections still point
to persisted claims. Conflicting rewrites of prior source claims, wrong owners,
invented quotations and duplicate IDs within one extraction still fail closed.

Failed extraction preserves the last approved evidence/intent/meaning state.
Confirmed answers remain available for subsequent analysis even when extraction
failed. History is restricted to the owning experience; legacy slot-fill question
queues are not replayed as value-approved questions.

Writer prompt and JobRequirementProfile are unchanged. The only candidate gate
adjustment separates ordinary decision typing from explicit design wording;
unsupported ownership/leadership/design wording remains blocked and semantic
verification is still required before application.

## Verification and limits

- Backend suite excluding the previously unavailable-DB module
  `test_matching_handoff.py`: 476 passed. No new DB/model test dependency.
- Mounted B-route scripted tests cover failed follow-up, preservation of intents,
  accumulated answers, successful retry reaching Writer, and experience isolation.
- Additional tests cover compound role labels, useful clarification despite a
  known motivation, rejected question premises, ID echoes/collisions, withdrawn
  claims, exact repeats, unavailable topics and the decision/design distinction.
- Replayed saved review 13's actual extracted data and draft in memory: two old
  slot questions become zero automatic questions; plan remains replace_field;
  the old deterministic unsupported_agency false positive is gone.
- No additional LLM call, DB write, migration, AWS change, commit or push.
  No server restart or browser review was triggered.

The replay has no newly generated question proposal, so it verifies removal of
the deterministic cause, not the new model's semantic judgment. Question relevance
and naturalness still need a new human-observed B review. No full raw model payload
exists for the two failed historical extractions; collision handling is verified
against both plausible contracts with source/ownership regression tests.
