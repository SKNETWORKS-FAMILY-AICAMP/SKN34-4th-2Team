# Resume Review Engine v2 — offline core

This is an independent, **non-production** implementation. It does not change the
v1 API, Django, React, Firebase gateway, PostgreSQL schema, or apply/undo path.
Do not present a v2 candidate to users or apply it without a versioned UI/API
adapter and an explicit human review.

## Architecture and data ownership

`ReviewInput(Experience, answer, question, optional job requirements)`
→ Analyst (structured evidence and revision plan)
→ exact source/ID/state validation
→ selected Evidence only + preserved original Evidence
→ Writer (never sees the conversational answer)
→ deterministic fact/quality validation
→ independent semantic fact verification
→ at most one targeted rewrite
→ `RevisionCandidate` with `READY`, `REJECTED`, or no candidate.

`resumes.content` is still the only submitted-resume source of truth. In this
offline phase, Experience and Evidence are Pydantic objects, not new tables.
`experience_id` identifies the editing unit; `field_path` is an apply locator.
The original experience text is server-provided `resume_stated` Evidence. An
answer fact is `user_asserted`, not externally verified. Job requirements are
never applicant Evidence. The Writer only receives approved selected/preserved
facts, not raw Q&A text. It must link exact proposed-text claims to Evidence IDs.

The LLM adapter uses the project's configurable model and medium reasoning by
default. Analyst, Writer, and semantic verifier are separate calls. A no-change
question requires only Analyst. Quality/fact issues may trigger one more Writer
call and another verification, for at most five successful LLM calls in a turn.
Verification failure is closed: the candidate is not apply-ready.

The Analyst system prompt is intentionally short. Case-specific facts or fixes
belong in data, validators, or evaluation cases, not an expanding writer prompt.

## Tests and manual review

From `cover_letter_rag` using the project environment:

```powershell
python -m pytest tests/test_resume_review_v2.py -q
python -m evaluation.v2_eval --live --env-file <private-.env-path> --limit 10
python -m evaluation.v2_compare --live --env-file <private-.env-path>
python -m evaluation.v2_recheck
```

Live commands call a paid LLM; they are never started by import. Results go to
ignored `evaluation/v2_results/`. Existing case files are skipped unless
`--force` is explicitly supplied. The harness disables LangSmith tracing so
fixture content is not sent to an additional provider. Never commit the .env.

There are ten manually curated LLM examples, not a large synthetic benchmark.
The review artifact shows the original resume, question, answer, extracted,
selected and omitted Evidence, plan, candidate, claim→Evidence mapping,
validator issues, usage, and blank human verdict fields. Humans choose
`APPLY_AS_IS`, `MINOR_EDIT`, `MAJOR_EDIT`, or `REJECT`; no overall score is made.
`v2_compare` evaluates five of these against an untouched v1 follow-up with
the same fixed question/answer and a synthetic preceding review in memory.

## Current limitations (must not be described as solved)

- Exact source quoting from an LLM can fail; the engine rejects unmatched quotes.
  Only punctuation/whitespace trimming is tolerated, not paraphrase.
- The technology detector has a finite vocabulary. The semantic verifier must
  check claims the deterministic detector does not recognize.
- A source quote proves provenance, not objective truth. `user_asserted` means
  the applicant said it, not that a third party verified it.
- Analyst fact selection can still favor procedural details; the quality gate
  flags some such outputs but human review remains necessary.
- `READY` means the configured checks passed, not that a human would apply it.
  Natural Korean, information density, and actual apply desire need review.
- The offline v2 operation is `replace_field` or `no_change`. Multi-field,
  project-level atomic apply and persistent Evidence require later API/DB work.
- Usage is recorded for completed calls. API failures before a usage response
  can leave token usage unknown; attempted calls are logged separately.
