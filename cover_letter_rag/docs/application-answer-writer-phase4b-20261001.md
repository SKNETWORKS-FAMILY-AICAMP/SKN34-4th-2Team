# Phase 4B — Application Answer Writer + Readiness Gate

Branch: `feature/resume-review-quality`. Date: 2026-10-01.

Implemented an opt-in core and Django service boundary, not a production switch.
No new migration, schema/model change, RDS access, AWS change, company browsing,
v1 change, LangGraph, or React Writer integration. Existing dirty work preserved.

## A. Architecture

```text
Owned Application + fresh saved ApplicationPlan + normalized source-bound context
  -> Readiness (no LLM)
       NEEDS_INPUT: necessary material gaps; no draft, no Writer
       BLOCKED: stale/source/scope/contract error; no Writer
       READY
         -> selected material only -> structured Answer Writer
         -> server joins sentences
         -> deterministic fact/provenance + quality checks
         -> semantic fact AND quality validation (one structured call)
         -> compare other question answers (lexical + semantic candidates)
         -> PASS: READY / ai_generated draft
         -> content FAIL: one targeted rewrite -> same checks -> READY or BLOCKED
         -> verifier/transport/schema contract FAIL: BLOCKED, no resampling
```

Components are separate responsibilities, not mandatory separate LLM calls.
Normal ready path: 2 calls. Content repair path: up to 4. Deterministically bad
provenance skips the first verifier, allowing 3 calls if repair succeeds.

Changed/added files in this phase:

- `app/application_writing/{__init__,models,engine,prompts,llm}.py`
- `evaluation/application_writing_cases.py`, `application_writing_live.py`, `application_writing_recheck.py`
- `evaluation/application_writing_phase4b_results/{W1,W2,W3}.{json,md}`, `usage-summary.json`, `offline-recheck.json`
- `tests/test_application_writing.py`
- `app/application_planning/models.py`: saved plan contract/cache version `application-plan-v4b`
- `lms_api/lms/application_answer_writer.py`, `test_application_answer_writer.py`
- `lms_api/lms/application_question_store.py`: generated AI prose excluded from Planner source documents/hash
- `lms_api/lms/local_resume_e2e_ai.py`, `local_resume_e2e_api.py`, `test_local_resume_e2e.py`
- This report. Other pre-existing uncommitted changes are NOT Phase 4B changes.

## B. Readiness Contract

`ReadinessResult(question_id, status, issues, missing_information)`.

READY requires current matching saved plan, valid question analysis, explicit
coverage, approved active source IDs within declared Experience scope, and no
essential gaps. Required result needs a real selected `fact_type=result`.
Required applicant intent needs a resolved confirmed user document AND its
source-bound normalized material. Company motivation additionally needs target
snapshot material; company data never fills personal intent.

NEEDS_INPUT: high/medium gaps, blocking coverage or missing coverage, missing
core contribution, result, intent or company source. Optional detail-only partial
coverage does not block. Original Planner proposals are retained; the gate does
not replan or invent repetitive questions. Result gap duplication was removed.

BLOCKED: stale hash, question mismatch, legacy plan without coverage, unknown or
inactive IDs, wrong scope/source parent, duplicate IDs, mixed context sources,
invalid source quotes, contradictory tiers/coverage, unknown explicit count unit.

Ownership is enforced in the Django boundary. Pure offline core receives a trusted
owned snapshot and host-supplied hashes; it is NOT an HTTP authorization layer.

## C. Writer Input Contract

`writer_input()` contains question and constraints, analyzed requirements,
story_focus, declared Experience scope, core/supporting/result facts, and typed
normalized context `{source_id, source_type, key, text}`.

No full resume, unselected Experience facts, raw conversation, entire answer
history, or raw gap answer. Writer cannot reselect Experience/Evidence or change
the plan. Core must be expressed; supporting is optional. Results are used only
when supported. No arbitrary 500/700-character default.

Normalization is currently an explicit caller/dev input contract. Intent sources
must match a confirmed user document by index/topic/question and quote. Target
sources must match an actual string at the supplied snapshot path. Semantic
validation compares normalized text with source quote for inflation. Automatic
gap-answer extraction/normalization belongs to Phase 4C.

## D. Writer Output Contract

```json
{
  "question_id": "W1-Q1",
  "sentences": [{
    "text": "...",
    "support_refs": [{"source_type": "evidence", "source_id": "E1"}],
    "claim_types": ["evidence"]
  }]
}
```

`final_text = " ".join(sentence.text.strip() for sentence in sentences)`.
There is no independently generated final_text or substring/claim-copy contract.
Rejected candidate prose stays available for developer audit but `AnswerResult.final_text`
is empty unless READY. Only validated READY content is saved.

## E. Sentence Provenance

Three disjoint source namespaces: evidence / applicant_intent / target_context.
Refs must belong to approved materials for this question, with active state and
matching scope validated before Writer. Mixed-source sentences carry all relevant
refs/types. Source type sets must match claim type sets.

Rhetorical connectors may have no refs, but numbers/known technologies and the
semantic verifier still catch factual claims concealed as rhetoric. A company's
technology cannot be referenced as applicant Evidence. Semantics, not ID presence,
determines whether a source actually supports the sentence.

## F. Fact Validator

Deterministic: output question ID, approved typed refs, duplicate refs, source/type
contract, known technology/numeric support per sentence, approved core use.
Readiness ensures active states, selected scope, result type and source quotation.

Semantic: unsupported claim/role/scope/result/company/intent/number/technology,
factual content without refs, meaning lost from core, normalized source inflation.
User assertions are not external verification. No validator guarantees truth
outside the supplied source statements.

Known-number/technology regex utilities are reused from v2; they are not complete
NER/semantic proofs. Unknown technical terms and causal claims rely on the verifier.

## G. Quality Validator

Separate issue lists from fact validation. Deterministic core unused/critical
technical signal loss, required result reference missing, procedure connector
overload, explicit character or UTF-8 byte cap, cross-answer repetition candidates.
No-limit questions receive no invented cap. Unknown byte/character unit blocks;
unspecified whitespace counting conservatively includes whitespace with warning.

Semantic requirement coverage, selected story focus, contribution visibility,
technical detail, information density, natural Korean, generic motivation,
unnecessary introduction and procedure dump. Supporting omission alone is valid.
No synthetic overall score or automatic human submit-quality approval.

## H. Cross-question Duplication

Same Experience alone is NOT duplication. Different facts/focus are allowed.
Whole-answer normalized similarity >= .86, at least 40 characters, is a quality
failure. Similar long sentences produce review warnings. Other generated answers
are also supplied to the verifier as comparison material, never new Evidence.
Semantic same-event/action/result repetition may become a quality issue.
Thresholds are centralized heuristics, not complete paraphrase detection.

The Django service compares existing generated answers from the same owned
Application. Their existing table retains prose but not sentence provenance.
Concurrent other-answer updates during LLM generation are a remaining race to
address before a multi-user final workflow; no blanket production guarantee.

## I. Rewrite Policy

Maximum one rewrite per question invocation. Same immutable selected Writer
materials; previous candidate, concrete fact/quality failures, and other-answer
comparison only. Second failure returns BLOCKED, never loops.

Transport/schema failure does not trigger a new paid sample. A verifier's wrong
question/core vocabulary is its own contract failure, not a Writer fact failure.
Final code restricts verifier question/core/requirement IDs in a scoped wire schema
and stops on a malformed injected verifier response without rewriting prose.

## J. Local Mock Update

Replaced old Phase 4A.6 A-attempt2 replay with Phase 4A.7 A-attempt1. Existing
recursive ID remapping and validators remain. New plan version invalidates old
cache in place; no Plan/Question/Evidence root copies or data resets.

Actual localhost:8002 mock HTTP recheck passed after restarting only the existing
local E2E server. Q1 gaps: company_motivation/applicant_intent and
company_motivation/target_context; NO preparation_effort gap. Status label changed
from obsolete 4A.6 NO-GO to 4A.7 Planner GO, explicitly separate from Writer readiness.

Existing local counts unchanged: Resume 2, Experience 3, Evidence 17, Binding 6,
Application 1, ApplicationQuestion 3. Mock stays default and does not call OpenAI.
Optional Writer screen/buttons were not added; this phase is offline + tested
dev service, not a production UI switch.

## K. Unit Tests

Python: **120 passed** (82 previous + 38 new). Readiness states, important vs optional
gaps, zero-call missing result, stale/unknown/cross-scope/source-parent/inactive
contracts, missing intent/target, selected-only input, optional supporting,
core technical signal, three source types, deterministic assembly, unsupported
numbers/technologies, required result use, limit/byte policies, duplicate vs
different focus, max one combined rewrite, verifier wire enums/contract errors,
and no paid retry on transport failure.

```powershell
cd cover_letter_rag
..\.venv\Scripts\python.exe -m pytest tests/test_application_writing.py tests/test_application_planning_contracts.py tests/test_resume_review_v2.py tests/test_tailored_resumes.py -q
```

## L. PostgreSQL / Backend Regression

Full isolated local PostgreSQL regression: **124 passed** (116 existing + 8 new).
Final targeted Writer boundary tests: 8 passed (see execution log).
Host/user guard: 127.0.0.1:55439 / resume_v2_test_admin; disposable test database.
Existing migrations through 0014 are used to construct the test DB. No new
migration files or RDS application. No production manage.py/settings invocation.

New tests: generated plaintext draft saving, user draft preservation, no Evidence
creation or Planner input/hash pollution, ownership, stale question/Evidence,
inactive Evidence, input/plan changed during writing. External calls happen outside
the DB transaction; owned inputs and saved plan are checked again before saving.

Storage contract: existing `ApplicationAnswers.source_type=ai_generated`, `status=draft`.
There is no `generated` status. Generated draft uses a separate answer_key, never
overwrites the user's `draft`, never resolves intent or becomes applicant Evidence.

**Schema limitation:** current Answer table stores no sentence support_refs or
validation audit JSON. Full audit is returned by the service and saved in offline
evaluation files, NOT durably stored alongside every DB answer. A future decision
is necessary for persistent provenance. No unrelated JSON column is hijacked.

## M. React Regression

**269 passed / 44 files** with maxWorkers=2. `npm run build` passed; existing
large-chunk warnings remain. No React source changes or production connection.

## N. W1 Live Result

Readiness READY; first draft factual checks passed but quality verifier marked
motivation generic. Exactly one rewrite, then READY with no reported fact/quality
issues. Final text:

> 교육 관리 서비스를 개발하는 러닝테스트에서 교육 현장 서비스의 안정성을 높이고 싶어 지원했습니다. 팀원이 전체 시스템을 설계한 프로젝트에서 저는 Django API 조회 오류를 로그로 추적해 필터 조건을 수정했습니다. 수정한 조회 조건을 적용한 뒤 해당 오류가 재현되지 않는 것을 확인했습니다.

Mixed company/intent refs in first sentence, E2/E1 in second, E3 in third.
Human review fields in W1.md deliberately blank. READY means validators passed,
NOT that a person has approved APPLY_AS_IS. Retained output also passes final
scoped-verifier contract and offline recheck.

## O. W2 NEEDS_INPUT Result

Result missing: NEEDS_INPUT, original necessary result question retained, no
candidate, **Writer 0 / Validator 0 / tokens 0**. Not a Planner failure.

## P. W3 Hallucination-pressure Result

Limited API-fix ownership and modest confirmed error non-reproduction result.
Question applies strong leadership-style preference, not a mandatory unsupported
team-lead role; inventing leadership is forbidden. A truly mandatory leadership
requirement with no basis must instead remain a critical Gap/NEEDS_INPUT.

Actual live result: **BLOCKED after one rewrite**. No unsupported leadership,
numeric performance gain or enlarged ownership appeared in the generated drafts.
However the verifier returned E3 (result) in expressed_core_evidence_ids, even
though only E1/E2 are core, and criticized lack of unsupported leadership. The
rewrite subsequently omitted E2 role provenance; it is not an acceptable final
answer. Rejected drafts and both verifier outputs are preserved, not hidden.

Post-live fixes: constrain verifier ID vocabulary in JSON schema; separate
verifier contract error from Writer repair; quality criterion limited to actual
requirements/focus rather than demanding unsupported rhetorical preference.
Unit tests pass. Offline replay correctly rejects the historical verifier output
as INVALID_VERIFIER_CONTRACT and catches missing E2 in the second candidate.
**No additional live call was made after those fixes**, so post-fix W3 end-to-end
quality is still unverified. Original live artifacts are unchanged.

## Q. LLM Usage

Model: gpt-6-luna; reasoning effort: medium. Same as Phase 4A.7, no model sweep,
sampling repeats, company browsing, or LangSmith upload. API max_retries=0.

| Case | Calls | Input tokens | Output tokens | Total elapsed | Rewrites | Result |
|---|---:|---:|---:|---:|---:|---|
| W1 | 4 | 5,073 | 1,871 | 20,546 ms | 1 | READY |
| W2 | 0 | 0 | 0 | 0 ms (rounded) | 0 | NEEDS_INPUT |
| W3 | 4 | 4,037 | 2,211 | 23,109 ms | 1 | BLOCKED |
| Total | 8 | 9,110 | 4,082 | 43,655 ms | 2 | — |

Every call has provider token usage and latency. Per-stage details and reasoning
token details are retained in JSON. Both W1/W3 were initially sampled only once;
extra Writer calls were conditional repairs on actual validator failures.
Checkpoints prevent accidentally re-running fixtures. Offline recheck costs no API.

## R. Remaining Risks

1. W3 semantic false-positive/contract hardening needs an explicitly authorized
   small follow-up live check; current saved BLOCKED result must not be called success.
2. W1 submit-quality still needs human judgement. Two repaired fixtures cannot
   demonstrate broad writing quality or verifier calibration.
3. Durable answer provenance is not supported by current schema. Decide its
   storage before production final-answer workflow; don't pretend current plaintext
   draft contains a reconstructable historical audit.
4. Normalization remains an explicit source-bound dev contract. Automatic gap
   answer -> approved Evidence/Intent/context and replan is Phase 4C, not implemented.
5. Concurrent other-answer changes and paraphrase-level duplication require further
   validation; existing heuristics are candidates, not a complete semantic proof.
6. Known tech/number vocabulary and semantic verifier remain fallible. Input
   source correctness and externally verified truth are different guarantees.

## S. Go / No-Go

**Phase 4B core and safeguards implemented/tested; not all prose paths are verified.**
Independent Phase 4C dev work can build on the readiness and draft contracts, but
**NO-GO for directly wiring production final-answer generation** or claiming all
three live cases pass. Before that: human W1 review, limited post-fix W3 verifier
check, and a durable provenance decision. Keep development opt-in and v1 baseline.

Next phase remains: Gap Answer -> validated Evidence/Intent update -> automatic
replan -> readiness -> Writer retry -> final-answer workflow, without weakening
current stale/ownership/factual guards or silently accepting rejected candidates.

Structured wire constraints follow the official [OpenAI Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs).
JSON schema controls vocabulary/shape; it does not establish factual or prose quality.
