# Local Resume E2E — 2026-10-01

Branch: `feature/resume-review-quality`. Local integration **GO (mock)**; Planner semantic quality **NO-GO**. Production switching is not part of this result.

## A. Local Architecture

```text
React/Vite 127.0.0.1:5180 /local/resume-e2e
  → same-origin /api proxy → Django 127.0.0.1:8002
  → existing Application / RecruitRole / Question / Evidence services
  → PostgreSQL 127.0.0.1:55439
  → existing Analyzer/Planner validators → stored ApplicationPlan → React
```

FastAPI is unnecessary for this preview: the existing DB-free planning core is imported by the Django service, with its existing injected client interface. This does not replace the production Django/FastAPI architecture.

Changed/new local files: `lms_api/local_resume_e2e.py`, `lms_api/local_resume_e2e_{settings,urls}.py`, `lms/local_resume_e2e_{api,ai,fixture}.py`, `lms/management/commands/seed_local_resume_e2e.py`, `lms/test_local_resume_e2e.py`; React `src/main.tsx`, `features/jobApply/LocalResumeE2E.tsx`, `localResumeE2E.css`, `__tests__/localResumeE2E.test.tsx`.

## B. DB Safety

Standalone settings do not import production settings. The new entry point does not load root `.env`, refuses `--settings` overrides, disables inline publisher and LangSmith tracing. Settings/URL modules are top-level, outside `lms_server`, so that package's implicit Celery/root `.env` bootstrap is not imported. An integration assertion checks `lms_server` is absent from loaded modules. Production `DB_HOST`, `DATABASE_URL`, credentials and Celery settings are never selected by this configuration.

Only `LOCAL_DB_*` configure the local DB. Host must be exactly `localhost` or `127.0.0.1`; any other value fails during settings import before opening a connection. Local startup logs mode, host, DB name and AI mode, never passwords. Default AI mode is mock. JWT signing key is separate and fictional, not a production signing key.

Actual startup checks rejected an RDS-shaped host and `--settings=lms_server.settings` before any DB connection. Final runtime reported `production_package_loaded=False`.

Actual SQL check:

```text
current_database = resume_review_v2_test
current_user = resume_v2_test_admin
inet_server_addr = 127.0.0.1
inet_server_port = 55439
```

Existing local DB had 0011; applied existing 0012, 0013, 0014. `showmigrations lms` confirms all 0001–0014 applied. `makemigrations --check --dry-run`: No changes detected. No new migration, RDS connection, production DB access, AWS changes or data copies from RDS. Early verification invoked the existing manage.py / lms_server bootstrap, which read root `.env` without choosing its DB; final startup was isolated after discovering both bootstrap paths.

## C. Commands

### This workstation: PostgreSQL

The already initialized local cluster is left running. To start it again only when stopped:

```powershell
& 'C:\Program Files\PostgreSQL\16\bin\pg_ctl.exe' -D 'C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059bb39429f96cd70f8567ba637' -l 'C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059bb39429f96cd70f8567ba637\server.log' -o '-h 127.0.0.1 -p 55439' -w start
```

### Terminal 1: local Django

```powershell
cd 'C:\Users\MoonSungHo\skn34-st\team_project\SKN34-4th-2Team\lms_api'
$env:LOCAL_AI_MODE='mock'
& ..\.venv\Scripts\python.exe local_resume_e2e.py migrate --plan
& ..\.venv\Scripts\python.exe local_resume_e2e.py migrate
& ..\.venv\Scripts\python.exe local_resume_e2e.py seed_local_resume_e2e
& ..\.venv\Scripts\python.exe local_resume_e2e.py runserver 127.0.0.1:8002 --noreload
```

Do **not** use production `manage.py` for this preview: its existing bootstrap loads root `.env`. Use `local_resume_e2e.py` above. Stop Django using Ctrl+C; restart after Python edits when using `--noreload`.

### Terminal 2: React

```powershell
cd 'C:\Users\MoonSungHo\skn34-st\team_project\SKN34-4th-2Team\lms_react'
$env:VITE_LOCAL_RESUME_E2E='1'
$env:LMS_API_PROXY='http://127.0.0.1:8002'
npm.cmd run dev -- --host 127.0.0.1 --port 5180 --strictPort
```

Existing Vite convention reads `LMS_API_PROXY` from process environment; do not assume placing it only in `.env.local` configures that existing proxy. `VITE_LOCAL_RESUME_E2E` can alternatively be set in `.env.local`. No production API address is hard-coded. The same-origin Vite proxy makes cross-origin CORS configuration unnecessary here. Stop Vite using Ctrl+C.

### Other developers

Use a dedicated empty **local** PostgreSQL database and a local user permitted to apply the existing migrations; never point these variables to a cloud database. Set these in Terminal 1 before running the commands:

```powershell
$env:LOCAL_DB_HOST='127.0.0.1'
$env:LOCAL_DB_PORT='5432'       # your local PostgreSQL port
$env:LOCAL_DB_NAME='resume_review_v2_test'
$env:LOCAL_DB_USER='postgres'  # your own local user
# Set LOCAL_DB_PASSWORD locally if required; never paste it into chat/git.
```

The workstation cluster path above is not portable. Provision/start your existing local PostgreSQL normally and create the dedicated local database there if absent. Do not change the production DB. Use the repository's existing Python dependencies and `npm.cmd ci --ignore-scripts` for React if dependencies are missing. This task did not add packages or change lockfiles.

## D. URLs

- UI: `http://127.0.0.1:5180/local/resume-e2e`
- Actual tested reopen URL: `http://127.0.0.1:5180/local/resume-e2e?application=2dbe8039-1674-4330-97ae-d343b6cbe402`
- API prefix: `/api/local/resume-e2e` (local-only URLconf).

The route requires Vite DEV, the explicit preview flag and loopback browser host. Other routes continue rendering the existing App. Production build cannot activate the preview route.

## E. Job-first E2E

Actually clicked in the in-app browser: fictional student login → select fictional Data Analyst/AI RecruitRole → select base resume → create/open Application → tailored resume → import questions → Analyzer → Planner. Each request returned from Django and the React view showed its completed status.

The selectable posting is a fictional RecruitRole-backed local target with external Job reference `local-e2e-job`; no crawling or real `jobs.jobs` posting is required. The role, question snapshots, application and resume are real persisted local rows, not front-end mock objects.

Authentication reuses existing LMS password hashing, JWT issuance and `user_from_access` resolution. Client-supplied user ID is ignored; all service calls use authenticated ownership. Dev login uses fictional `resume-e2e@example.test / LocalE2E-only!`. It is not a production demo account.

## F. Resume-first Integration

HTTP integration test sends `entry_source=job_first` then `resume_first` with the same base/target/idempotency key. Both reach existing `create_or_open_application` and return the same Application ID. No second production screen was added.

## G. Application Reopen

Actual browser reload reopened Application `2dbe8039-1674-4330-97ae-d343b6cbe402` and persisted Plan. Workspace ID lives in URL; local JWT lives in sessionStorage under a separate local-only key. New browser session can log in again and open the same URL. Token expires after four hours; if expired, clear the local session token/reopen the browser session and log in again.

Selectors return to their placeholders after reload; the persisted workspace is still open, and its action buttons remain usable. This is a development panel, not final production UX.

## H. Tailored Resume Reuse

Actual base Resume ID `1`, tailored Resume ID `2`. Repeated create/open and repeated tailor requests, plus reload, preserved those IDs. Tailoring uses existing `ensure_tailored_resume` and `clone_bindings_for_tailored_resume`, not the production v1 global copy cache.

## I. Experience / Evidence Sharing

Observed per-user row counts:

| Stage | Resume | Experience | Evidence | Binding | Application | Question |
|---|---:|---:|---:|---:|---:|---:|
| Application created | 1 | 3 | 17 | 3 | 1 | 0 |
| Tailored created | 2 | 3 | 17 | 6 | 1 | 0 |
| Questions / Plan / reload / repeat | 2 | 3 | 17 | 6 | 1 | 3 |

Base/tailored binding pairs reference the same three Experience UUIDs. No Experience/Evidence clones. Seventeen Evidence rows = fifteen existing fictional facts + superseded old training claim + active correction. Active view/input contain sixteen facts, never the old `모델 학습을 직접 구현` claim. DB confirms one superseded row. Automated test checks the plan cannot reference inactive IDs.

Seed replay uses stable user email/cohort/legacy resume/item/source keys and existing dedup services. Running seed twice returned the same base and role IDs; test repeats it twice and checks unchanged counts. It does not reset or delete data.

## J. Questions

Three RecruitRole questions imported through existing `import_role_questions` into ApplicationQuestion snapshots: motivation/preparation, desired work/skills, challenge/result. Retry returns the same snapshots. Integration test changes the local source and confirms existing question snapshots remain unchanged.

The fictional resolved role-interest/desired-work answers from case A are saved through existing `save_answer`. They are applicant-intent documents, not Experience Evidence.

## K. Planner Preview

Each card shows raw question, asks_for, primary Experience titles, story_focus, core/supporting/result Evidence text and ID, Gap category/reason/target/proposed question. Diagnostics show duplicate-story warnings and next question. Shared active Evidence shows title/fact/assertion state; expandable debug shows binding IDs and row counts.

Mock uses saved Phase 4A.6 A2 Analyzer/Planner output, remapping only fixture IDs to persisted IDs; existing analysis/plan validators and store are executed. Missing/changed seed facts fail rather than being invented. Q1 preparation_effort over-confirmation remains visible unchanged. No new Planner algorithm or semantic fix.

Read adapter uses existing `reusable_plan`; stale plans are hidden after Evidence changes, rather than leaking inactive references. Integration test covers this.

## L. Mock / Live AI Modes

Default `LOCAL_AI_MODE=mock`: **0 actual LLM calls**, no new token usage or API charge. It validates integration, not new model quality. The old A2 generation history is not counted as this task's usage.

Optional `LOCAL_AI_MODE=live` requires explicit process `OPENAI_API_KEY`; root `.env` is not loaded. Existing `StructuredPlanningClient` and `ChatOpenAI` are reused. Optional `LOCAL_AI_MODEL` default `gpt-6-luna`, `LOCAL_AI_REASONING_EFFORT` default `medium`; no retries, timeout 180s. Live was **not executed** in this task.

Existing service caches can avoid LLM calls for already analyzed/planned workspaces, including a previously mock-planned workspace. Switching mode does not clear data/caches. For genuinely fresh live verification, create a distinct operation key through the HTTP adapter, or change inputs via existing services; do not delete/reset tables. Do not interpret the displayed live mode alone as proof that a paid call occurred.

OpenAI Docs was consulted for the optional structured-output boundary; no schema/prompt redesign was made. Reference: [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs). Computer-use browser tooling was used for real click/reload verification and screenshots.

## M. Tests

- Local PostgreSQL regression: **115 tests passed** (new initial five HTTP tests plus selected existing stores/migrations/concurrency tests), 142.086s.
- Final local HTTP suite after stale-plan/auth fixes and complete package isolation: **6 passed**, 18.880s.
- DB-free v2/Planner/tailoring contracts: **70 passed**.
- React full existing Vitest suite: **44 files / 267 tests passed**, including one new select/create/Planner-render test.
- React `npm.cmd run build`: passed. Existing large-chunk warning remains.
- `makemigrations --check --dry-run`: no changes. `git diff --check`: clean.

Commands from `lms_api` for local HTTP tests: `..\.venv\Scripts\python.exe local_resume_e2e.py test lms.test_local_resume_e2e --noinput`.
From `cover_letter_rag`: `..\.venv\Scripts\python.exe -m pytest tests/test_application_planning_contracts.py tests/test_resume_review_v2.py tests/test_tailored_resumes.py -q`.
From `lms_react`: `npm.cmd test`, `npm.cmd run build`.

Earlier attempts had a new adapter import error, incorrect Select prop and missing installed CodeMirror dependencies; fixed/imported correct schema, reused Select contract and installed existing lockfile dependencies. One pytest invocation used the wrong filename then wrong working directory; corrected before the passing run. No failed invocation was reported as success.

## N. Issues Found

Planner Q1 semantic problem remains NO-GO by design. Mock is seeded-A-only, not a general semantic evaluator. Live and a production-style FastAPI network hop are not verified. Existing jsdom scroll/navigation and React Router future-flag warnings remain despite passing tests. Narrow dev-panel debug text now wraps; this is still not production UX.

## O. Remaining Manual Steps

No user clicks are needed to complete the verified mock integration. For human review, open the route and inspect Q1 Gap, selected facts and Q3 result. Any real-LLM quality validation or Phase 4B Writer requires a separate decision/task; this result does not authorize or imply either.

## P. Screenshots / Expected UI

Saved actual browser screenshots: `C:/Users/MoonSungHo/Documents/ChatGPT/SKN-4th Project/local-resume-e2e-20261001.jpg` (final isolated server) and `local-resume-e2e-plan-20261001.jpg` (Q1 card). Browser tab is left open. Expect Local E2E Preview, mock label, workspace/base/tailored IDs, shared active facts and three question/plan cards. There is no final-answer generation button.

## Q. Go / No-Go

**GO: local mock E2E integration**, tested through real React/Django/PostgreSQL plus browser reopen/repeat. **NO-GO: Planner semantic quality / Answer Writer / production deployment.** Existing production API, v1 engine, React production flow and migration files were not switched/reworked in this task. Existing uncommitted work is preserved; no commit/push performed.

Local PostgreSQL, Django 8002 and Vite 5180 are left running for immediate inspection; no cloud resources were started or changed.

## 2026-10-01 checkpoint update (supersedes earlier implementation status)

- Real document registration is DOCX/TXT -> ordinary `resumes.content` only. No Experience, Evidence, applicant intent or target linkage is created by registration.
- First explicit Review uses the existing lazy resolver and full `ReviewEngineV2`; source facts acquire `resume_stated` only after Analyst validation. No alternate real-data analyzer or injected matching result exists.
- Real-data Mock replay was removed from runtime. Synthetic dependency doubles remain in unit tests only; the distinct fictional preview uses small committed Mock fixtures, not evaluation output dumps.
- Writer readiness, requirement ID/posting quote provenance, factual/quality validation and the one-rewrite limit are preserved. Live quality is still unverified.
- Evaluation dumps, private documents, credentials, databases and logs are excluded from the checkpoint.
- A/B before is current `origin/develop`; after is that same develop merged with this feature's improvements. Exact checkpoint/merge SHAs are reported after Git operations, without a production API switch.
