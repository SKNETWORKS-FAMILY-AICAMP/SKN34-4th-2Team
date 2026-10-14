# Resume Review v2: product-quality repair

Branch: `feature/resume-review-quality`. No commit/push, migration, RDS writes or AWS changes.

## Historical root causes (local review 12, policy 4)

Read only from PostgreSQL `127.0.0.1:55439/resume_review_v2_test`.
The relevant three records are preserved locally in ignored
`evaluation/runs/historical_b12_sources.json`.

- B-1: extraction retained the initial adaptation/work-understanding plan as
  `item_7_e1`. The project profile classified all three plans as learning/insight.
  Selection omitted `item_7_e1`, retained `item_7_e2` as support and `item_7_e3`
  as core. The Writer never received the omitted meaning; validation returned READY.
- B-2: `item_8_e1` contained the learning-origin perspective and `item_8_e5`
  the intended work direction. Selection omitted both, selecting only the three
  project actions. The resulting experience summary passed validation.
- B-3: the actual adapter also supplied a role field, not only technology names.
  Its quote was `데이터 처리 및 Streamlit 서비스 구현`; extraction normalized this
  as `프로젝트에서 데이터 처리 및 Streamlit 서비스 구현 역할을 맡았다.`
  (`item_1_e7`). Writer combined that expanded paraphrase with technology evidence
  and emitted ownership wording. The old verifier accepted it. This is an
  extraction/quote-entailment failure before it is a Writer wording problem.

## Repair

Keep Experience isolation, exact source quotations, active/superseded/conflicted
states, applicant/context separation and at most one rewrite. No new persistent model.

- Writer/Verifier receive one derived editorial brief rather than RevisionPlan,
  SectionProfile and SentencePlan simultaneously. Existing plan fields remain in
  telemetry for backward compatibility, but SentencePlan is not a generation step.
- Original section text reaches editing and independent semantic verification.
  Original text is context, never authority for uncited or superseded claims.
- Motivation examples are optional support; the reason, origin and stated
  direction are protected. Future-plan meanings are not project-slot selections.
- Exact owning field-path aliases and equivalent facet labels are normalized;
  unknown source IDs and cross-experience references still fail closed.
- Fact typing is a hint, not a general entailment oracle. Tool-only escalation
  and unsupported ownership are still blocked. Scope/tense are checked semantically.
- Lexical style heuristics are reviewer hints. Original/answer similarity alone
  no longer forces rewriting. Rewriting does not delete supporting sources.
- Verifier compares the result with the original. No clear improvement produces
  UNCHANGED, no apply-ready proposal, and a user-visible explanation.
- Known actions with validation do not trigger role/context slot completion.
  A stated motivation with support does not cause a generic connection question.

## Repeatable evaluation

Run in `cover_letter_rag` with the repository `.venv` Python:

```powershell
& '..\.venv\Scripts\python.exe' -m evaluation.section_quality_live --live --label unique_clean
& '..\.venv\Scripts\python.exe' -m evaluation.section_quality_live --live --rough --via-http --label unique_rough
& '..\.venv\Scripts\python.exe' -m evaluation.section_quality_counterexamples --live --source evaluation/runs/section_unique_clean.json --label unique_negative
```

These commands make paid OpenAI calls using the configured model. Only the API
key is loaded into the environment. No database is accessed. `--via-http` executes
the actual mounted B route and LocalReviewService with an ephemeral store; this
does not claim Django/browser/persistent-storage E2E coverage.

Golden criteria are in `evaluation/fixtures/section_quality_golden.json`:
required meanings, optional details and forbidden claims, not reference wording.
`--rough` repeats existing sentences and uses list formatting without adding facts.
Counterexamples intentionally attach valid IDs to invalid text to test actual
semantic verification, rather than accepting Writer citations as proof.

## Browser verification

Use the existing startup commands in `local-existing-react-b.md` and visit
`http://127.0.0.1:5180/resume`. Start a **new review**; opening an old saved review
does not regenerate its stored suggestions. Use the local fixture account only.

Check original vs revision for early adaptation, motivation hierarchy and no
ownership expansion; verify unchanged results have no apply action, questions do
not repeat already stated work, and apply/undo preserves the correct field.

The read-only `evaluation/runs/section-quality-comparison.html` shows saved real
model outputs and is not a substitute for checking the product UI. Automatic
startup of the local browser servers was blocked by command execution policy.

## Final validation (2026-10-03)

- Final actual-model B HTTP-route run: `section_editorial_readability_http_20261003.json`,
  configured `gpt-6-luna`, 3 calls, 56.080 seconds. All three cases READY with no
  rewrite or follow-up question. Reading the outputs confirmed the required
  meaning and absence of ownership expansion; repeated text was removed.
- Already polished input: all three cases UNCHANGED in
  `section_editorial_v6_20261003.json`, rather than proposing unnecessary edits.
- Adversarial candidates with valid citation IDs: all three rejected for the
  intended semantic defects in `counterexamples_editorial_v6_20261003.json`.
- Backend final run excluding `test_matching_handoff.py`: 461 passed.
  Earlier whole-suite run: 480 passed, 12 setup errors because that separate
  module requires an unavailable PostgreSQL database on localhost:5432.
  The full suite is therefore not green.
- Frontend review window/session tests: 14 passed. `git diff --check` passed.
- No RDS/production writes, AWS changes, migrations, commits or pushes were made.
  Browser/Django end-to-end verification remains unperformed.

## Limits

This small Golden evaluation does not establish a production win rate. Judges
can over-reject valid paraphrases or disagree about an edit's benefit. A full
eleven-section job-targeted live run and real multi-turn browser flow still need
human verification. Historical policy-4 output is evidence of the old failure;
opening it is not evidence that the new policy failed.
