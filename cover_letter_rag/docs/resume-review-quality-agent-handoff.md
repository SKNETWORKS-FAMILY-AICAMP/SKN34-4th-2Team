# Resume Review Quality Branch — Agent Handoff

## Purpose and branch strategy

This document records the working state and guardrails for continuing the Resume Review quality work across agents. Before changing code, read this document and inspect the current branch, `git status`, and the relevant diff.

- Work branch: `feature/resume-review-quality`
- Baseline: `develop`
- This is an isolated quality-improvement branch, not a replacement for `develop`.
- Keep existing team features intact. Consider integration only after quality, factual safety, useful questions, browser behavior, latency, regression risk, API compatibility, and migration conflicts have been reviewed.
- Do not commit, push, merge, or rebase unless the user explicitly asks.

## Product principles

Resume Review v2 is a source-grounded editing system, not just a sentence generator.

- A user answer is evidence for understanding experience; it is not the final resume sentence.
- A confirmed fact does not have to appear in every final sentence.
- Preserve important original meaning, but not original wording, order, duplication, or routine chronology.
- Keep valuable technical implementation and reasoning when they improve the target section.
- Never invent or inflate role, ownership, leadership, result, metric, scope, duration, or intent.
- Job posting/company information is TargetContext, not applicant evidence or intent. Use it to select and connect supported experience only.
- Do not force a revision when it is not meaningfully better; unchanged outcomes are valid.
- Validate both directions: every output claim needs a source, and important source meaning must not be silently lost.
- Similarity scores alone do not establish factuality or writing quality.

Canonical source separation:

```text
ApplicantEvidence != ApplicantIntent != TargetContext
```

The runtime flow should remain understandable and thin:

```text
source-linked evidence and intent
→ section purpose and editing plan
→ useful, safe questions when needed
→ writer
→ factual, intent, section, and quality validation
→ READY / UNCHANGED / REJECTED
→ at most one conditional rewrite
```

Avoid adding overlapping Profile/Plan representations without a demonstrated need. A project profile is a derived view, not a checklist that forces every populated slot into prose. Keep ApplicantIntent a focused runtime domain concept unless persistence requirements justify expanding it.

## Evidence and question behavior

Evidence states include `resume_stated`, `user_asserted`, `uncertain`, `contradicted`, `retracted`, and `superseded`. Preserve Experience identity and source quotes. Exclude inactive or unresolved-conflict evidence from Writer input. Clear user corrections can supersede a prior claim; uncertain answers cannot.

Questions should seek information that would materially improve the target section. Do not re-ask known information, fill empty slots by quota, or assume an unsupported action in a question. Project questions retain `experience_id` and a display title from generation through UI display and answer routing. Answers stay isolated to the addressed Experience. The existing whole-resume maximum of three simultaneous questions remains in force.

## Local B environment

The B browser setup uses the existing React UI and local services:

| Service | Address |
| --- | --- |
| React | `http://127.0.0.1:5180` |
| Django | `127.0.0.1:8002` |
| Resume Review AI (v2-local) | `127.0.0.1:8003` |
| PostgreSQL | `127.0.0.1:55439` |

React proxies `/api` to Django 8002. Django and the AI adapter must use the isolated loopback database configuration. Start commands are documented in `local-existing-react-b.md` and `lms_api/local_resume_site.py`.

### Existing PostgreSQL test cluster — preserve it

- PostgreSQL 16, local `trust` authentication
- Host/port: `127.0.0.1:55439`
- Database/user: `resume_review_v2_test` / `resume_v2_test_admin`
- Existing data directory: `C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059bb39429f96cd70f8567ba637`

Never run `initdb`, create/seed a replacement database, delete or replace this data directory, or switch to another Temp PostgreSQL directory when investigating B review history. Do not run migrations or seed commands without explicit user authorization.

Before starting PostgreSQL, check whether port 55439 is already listening. If it is stopped, use this existing cluster directory; do not initialize a new one:

```powershell
$dataDir = 'C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059bb39429f96cd70f8567ba637'
& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' `
  -D $dataDir `
  -l 'C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059-startup.log' `
  -o '-h 127.0.0.1 -p 55439' `
  -w start
```

The startup log is deliberately outside the data directory's `server.log`: using the latter for `pg_ctl -l` caused a Windows file-sharing conflict with PostgreSQL logging. Then check readiness and identity:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\pg_isready.exe' -h 127.0.0.1 -p 55439
& 'C:\Program Files\PostgreSQL\16\bin\psql.exe' `
  -h 127.0.0.1 -p 55439 -U resume_v2_test_admin -d resume_review_v2_test `
  -c "SELECT current_database(), current_user, inet_server_addr(), inet_server_port();"
```

The data directory is under Windows Temp. It persists across a normal PostgreSQL stop/start, but Windows Temp cleanup can remove files or empty directories. A missing directory is not permission to initialize or replace the cluster; inspect the PostgreSQL log and preserve the existing files.

### Last verified database state — 2026-10-04

The original cluster was started after restoring missing empty PostgreSQL runtime directories in the same data directory and allowing WAL recovery. It accepted connections on `127.0.0.1:55439`; the database identity matched the values above. A read-only query found eight review rows with IDs 17–24: IDs 17–23 were `complete`; ID 24 remained `processing`. No row was changed by that check. Do not reset or replay ID 24 without inspecting its request/trace and deciding with the user.

## Fixed A/B target

Use the user's existing A/B selection; do not rerun recommendation to replace it.

- Resume source: base Resume ID `33`
- B local source: database ID `4`, public ID `local-ab-source-resume-33`
- B tailored Resume: database ID `10`
- Posting: Saramin `rec_idx=55149877`
- Company: `(주)스카이키`
- Title: `(주)스카이키 AI 활용 데이터 분석/데이터 엔지니어 채용 공고`
- Internal job ID: `SARAMIN-55149877`
- Existing JobRequirementProfile: 14 requirements; it is derived from the selected posting, not a mock profile.

Keep Resume, Job snapshot, user answers, and model conditions fixed when comparing A (`develop` review) with B (v2). Do not run matching again as part of an editing-engine comparison.

## Current quality findings from browser tests

Observed improvements include source-linked evidence, stronger role/result checks, more section-aware writing, semantic preservation checks, and the ability to leave already-good content unchanged. These are not a claim that every live result is ready to submit.

Previously observed remaining writing issue: after new evidence arrives, Writer can append it to the end of the old paragraph instead of reorganizing the paragraph's full argument. Avoid repeating feature names and serially listing evidence. Recompose around relationships actually supported by sources (for example, problem → decision → implementation → verification → result); do not force every element or a fixed STAR template.

Specific browser notes:

- KKBOX threshold answer: threshold 0.2 had the best F1 among the values tried (0.5: about 0.2257; 0.3: 0.2538; 0.2: 0.2612; 0.1: 0.2592). Writer reflected the answer; factuality and technical detail were judged good, though some listing remained.
- KKBOX `days_to_expire`: directional AUC about 0.905 and shorter time-to-expiry associated with higher churn likelihood were reflected. The paragraph still listed analysis, result, and insight rather than composing a single argument (partial pass).
- Garage search: direct functional testing was reflected, but the old feature description was repeated before adding the test sentence (partial pass).
- A prior AI LMS flow returned useful answers but showed no revision card. Diagnose its stored request traces before changing code: inspect analysis, new Evidence/semantic units, merged state, editing plan, Writer call, candidate status, and UI mapping. Establish whether a candidate was never produced or lost in UI first.

## gap_audit and latency

Historical measurements recorded an approximately 165-second timeout when `gap_audit` re-ran analysis and writing for all 11 Experiences despite only one Experience changing and no new Evidence being extracted for the others. A later state-reuse improvement is expected to reuse completed analysis and writing and verify only pending candidates; changed input should invalidate only the affected Experience stages.

Never treat verifier timeout as success, expose unverified candidates as READY, or reset a rewrite limit on every audit. Do not weaken writing/factual policies solely to reduce latency. Confirm current runtime traces before assuming the state-reuse behavior is still active.

## Test and live-call policy

- Run tests directly related to the change during implementation; avoid repeating the full suite after every small edit.
- Run the broader Resume Review regression once at the end when requested by the task.
- Add tests only for risks existing tests do not already cover.
- Mock tests prove contracts and wiring, not real writing quality.
- Use a small number of representative real-model/browser cases when live quality assessment is necessary; do not repeat live calls indiscriminately.
- Clearly distinguish mocked/scripted results from real model and human review.

## Data, infrastructure, and Git guardrails

Unless explicitly authorized, do not perform RDS/production writes or migrations, AWS changes, production seeding, or destructive database operations. Prefer local B PostgreSQL and read-only inspection for historical traces. Do not expose `.env` secrets.

Without a direct user request, do not commit, push, merge into `develop`, rebase, or modify teammates' branches. Before any eventual integration, review current develop, the complete feature diff, migration graph, API contracts, React integration, existing Resume regressions, local-only files, debug exposure, and browser smoke-test results.

## Working method

1. Read this handoff and check the current branch/status/diff.
2. Trace the relevant runtime path and stored traces before changing code.
3. Identify whether the defect is in representation, planning, Writer, validation, state, or UI.
4. Fix the root cause with the smallest coherent change; avoid accumulating rules, duplicate representations, giant conditionals, blanket templates, and similarity-only quality gates.
5. Run focused tests, then the requested final regression once.
6. Report changed files, evidence, test/live-call counts, and remaining limitations. Do not describe mock results as browser/model validation.

## Next investigations

1. Inspect the two AI LMS post-answer review records (including record 24) and trace why no candidate card appeared; avoid retrying an in-progress request until its persisted state is understood.
2. Improve whole-paragraph recomposition when new Evidence is added, using source-backed relationships rather than appending a final sentence.
3. Resume B browser testing against the fixed Resume and Job.
4. Measure the initial-review latency stages before optimizing.
5. Check whether forwarding JobRequirementProfile group/kind to Writer changes decisions or prose quality before extending that contract.
