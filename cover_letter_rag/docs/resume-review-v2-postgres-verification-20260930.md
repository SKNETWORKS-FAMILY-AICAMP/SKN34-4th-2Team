# Resume Review v2 PostgreSQL verification — 2026-09-30

## A. Test Environment

- PostgreSQL **16.15**, 64-bit Windows, installed binaries under `C:\Program Files\PostgreSQL\16\bin`.
- Independent `initdb` cluster in `C:\Users\MOONSU~1\AppData\Local\Temp\resume-v2-pg-ddc2b059bb39429f96cd70f8567ba637`.
- Bound only to `127.0.0.1:55439`; isolated test administrator `resume_v2_test_admin`, local trust authentication. No Windows service, AWS resources, RDS, or production credentials changed.
- Fresh database `resume_review_v2_test`; Django runner creates/drops `test_resume_review_v2`.
- Settings: `lms_server.resume_v2_postgres_test_settings`, explicitly fixed localhost/port/name/user. The PG suite refuses other settings during discovery, before test DB creation. External AI, Firebase Auth, S3, Pinecone and LLM calls: **0**. Gateway tests replace only `_pg` with a connection to the isolated test DB and bypass Firebase initialization.
- The initial sandbox attempt could initialize files but could not start PostgreSQL because Windows restricted-token creation failed. Normal-user execution successfully started the independent server. The test server is stopped after verification; temporary cluster files are retained for reproducibility.

## B. Migration Result

The request calls the Resume migration `0008`. After merging develop, its actual filename is **`0011_resume_experience_evidence.py`**, depending on manager `0010_submission_task_questions`. Manager `0008`–`0010` are not renumbered.

1. Empty PostgreSQL database → full Django migration graph, including `lms.0001` through `lms.0011`: **PASS**.
2. Historical `0007` state → fixtures → manager `0010` → Resume `0011`: **PASS**.
3. `0011 → 0010 → 0011` rollback/reapply: **PASS**.
4. Entire JSON row snapshots of `users`, base/tailored `resumes`, `resume_tailorings.review_session`, and `resume_ai_reviews` match before/after migration and rollback/reapply: **PASS**.
5. `makemigrations --check --dry-run`: no changes. Django system check: no issues.

Rollback reverses CreateModel by dropping the three v2 tables. It therefore **loses any Experience/Evidence/Binding rows in those tables**. The test uses disposable data and confirms older Resume data survives; it does not imply a populated production rollback is lossless. No migration was applied to RDS.

## C. PostgreSQL Schema Result

Actual catalogs contain **3 UUID PKs, 6 FKs, `(resume_id,item_key)` UNIQUE, nonnegative display_order CHECK, and 13 indexes** across the three new tables. FKs are DEFERRABLE INITIALLY DEFERRED. Timestamp and provenance columns are present through the applied migration/ORM inserts.

| Relationship | Django deletion policy | Verified implication |
|---|---|---|
| Experience → User | CASCADE | No user deletion is exposed by this v2 service |
| Evidence → Experience | CASCADE | Deleting an unbound Experience with a single fact deletes only its Evidence |
| Binding → Experience | PROTECT | An Experience used by a Resume cannot be deleted through the ORM |
| Binding → Resume | CASCADE | Removing a Resume removes its bindings; shared Experience/Evidence remain |
| Evidence → superseded/conflicting Evidence | PROTECT | Correction history is protected against deleting referenced facts |

Django on_delete is ORM behavior. The actual PostgreSQL FKs use default NO ACTION, not SQL ON DELETE CASCADE. Existing raw-SQL Resume deletion paths now explicitly clean bindings before deleting the Resume, preserving shared Experience/Evidence.

`assertion_state` currently has Django choices, not a PostgreSQL enum/CHECK. Owner equality and same-Experience correction relations are validated by the service, not by cross-table DB constraints. Direct SQL callers must not bypass that service.

## D. Experience Isolation

Project 1 and Project 2 contain the **same normalized fact and fact_type**. Correcting Project 1 makes its old Evidence `superseded` and creates a `user_asserted` API contribution. Project 2's Evidence remains `user_asserted`. Attempting to use Project 2's Evidence as Project 1's correction target raises ValueError without mutation. **PASS**.

## E. Concurrency Result

Expected policy: independent corrections of one active Evidence are serialized; the first succeeds and the second checks current state and is rejected as stale. Identical retries return the original successor.

- Two worker sessions were observed in PostgreSQL `pg_stat_activity` waiting on the held Experience row lock. After release: **one success, one stale ValueError, exactly one successor**.
- Same source/fact request twice: same Evidence UUID, one row.
- Retry of a committed correction: same successor even though target is now superseded.
- Two identical concurrent retries: same successor UUID, one row.
- Forced `lock_timeout=250ms`: PostgreSQL `55P03` surfaces as Django OperationalError; transaction rollback leaves the original active and no successor. A subsequent correction succeeds. No automatic retry is introduced.
- Chain `E1 → E2 → E3`: only E3 is active and appears in the adapter input.

Idempotency uses the existing Experience lock and `(Experience, source_type, source_id, fact_type, normalized_fact)` lookup. Reusing this tuple with another quote or correction target is rejected. This guarantee applies to writes through this service; no large idempotency subsystem or new schema constraint was added.

## F. Binding Identity

The actual paths inspected/tested are:

| Path | Item identity behavior |
|---|---|
| React new item (`ResumeSections.tsx`) | Generates an item `id` when creating the item |
| React create/save (`repository.ts`, `ResumeEditScreen.tsx`) | Sends content with existing item ids; spread edits preserve other item fields |
| Django create/update (`commands.op_upsert_sql`) | JSON serializes content without regenerating/removing item ids |
| React bootstrap (`bootstrap.ts`) | Passes project/experience item arrays through; item-level fallback keys survive |
| Tailoring/preprocessing (`alignDraft.ts`, `JobApplyScreen.tsx`) | Reorders existing item objects, retaining ids |
| AI review/apply copy (`FirebaseGateway.create_tailored_resume`) | Deep-copies content and now copies existing bindings in the same transaction |
| Editable workspace copy (`promote_tailored_resume`) | Deep-copies tailored content, copies its bindings, records source_tailored_resume FK |
| Apply/undo (`apply_or_undo`) | Changes/reverts content fields while retaining existing item ids and bindings |

Item id is unique within a document/section; document-level binding UNIQUE includes the Resume ID. Reusing an item id in a proven copy therefore does not conflict. Experience identity is the separate UUID.

## G. Tailored Copy Result

Actual gateway calls create review copy, apply copy and promoted editable copy. Before: **Experience 1 / Evidence 1 / Binding 1**. After: **1 / 1 / 4**. Retrying review/apply creation does not add bindings or experiences. Both gateway calls and Django bulk binding copy were exercised against real PostgreSQL.

If a stable native/shared-fallback key exists, lazy access also handles a source binding created after the copy, or opening the copy before the base: initialize/reuse the proven source's Experience first. No title-based merging is used.

## H. field_path Reordering

Actual Django save moves `project-123` from `projects[0]` to `projects[2]`. The adapter finds it by stable key, refreshes the locator to `projects[2].description`, and retains the same Experience UUID. **PASS**.

## I. Ownership

Binding another user's Experience, reading another user's Evidence and correcting another user's Evidence are rejected. Raw copy verifies source/target owners and the Experience owner; stable item keys do not authorize cross-user sharing. **PASS**.

## J. v2 Adapter

PostgreSQL-loaded input contains only usable `resume_stated` / `user_asserted` Evidence; uncertain, contradicted, retracted, superseded and facts blocked by uncertain conflicts are excluded. The adapter input runs through the unchanged DB-free engine with a fake LLM client. No actual model request was sent.

One Experience with 21 Evidence rows uses **3 SELECTs** at the normal adapter boundary. Cloning 12 bindings uses at most **9 captured queries**, including transaction statements; the former per-binding ORM lookups were replaced by bulk write. No benchmark/cache was added.

## K. Test Results

| Category | Result |
|---|---|
| SQLite persistence tests, separately executed | 11 passed |
| Existing persistence tests repeated on PostgreSQL | 11 passed |
| PostgreSQL historical migration/rollback/data preservation | 1 passed, plus fresh full migration command |
| New PostgreSQL transaction/isolation/retry/timeout tests | 8 passed |
| New PostgreSQL binding/create/save/copy/apply/undo/deletion tests | 10 passed |
| New PostgreSQL schema test | 1 passed |
| New PostgreSQL adapter query-count test | 1 passed |
| Existing mocked delete/ownership contract regressions | 5 passed (not presented as DB tests) |
| Existing DB-free v2 tests | 33 passed |
| Existing tailored service tests | 7 passed |

The final combined Django run had **36 passes**; the additional targeted PostgreSQL lock-timeout test had **1 pass**. Thus 37 distinct Django tests passed (32 exercising PostgreSQL; 5 mocked contract regressions). SQLite and PostgreSQL counts are deliberately separate.

Reproduce after starting the isolated server:

```powershell
cd lms_api
python manage.py test lms.test_resume_experience_store lms.test_resume_experience_postgres lms.tests.ResumeDeleteTests lms.tests.ResumeWriteValidationTests --settings=lms_server.resume_v2_postgres_test_settings --noinput
python manage.py makemigrations --check --dry-run --settings=lms_server.resume_v2_postgres_test_settings
```

## L. Code Fixes Made During Verification

- `lms/resume_experience_store.py`: Experience-locked idempotent replay; source-first lazy binding for proven copies; ambiguous unkeyed legacy copies rejected; batch ORM binding copy to remove N+1.
- `app/resume_binding_copy.py` (new): transaction-local raw SQL binding copy, owned source/target verification, stable-key locator refresh, batch insert, incompatible existing binding rejection. On pre-0011 schemas it has no bindings to copy and returns without changing Resume content.
- `app/firebase_gateway.py`: hooks at actual review/apply/promotion creation and existing-copy retry; explicit binding cleanup in raw Resume deletion.
- `lms/commands.py`: explicit binding cleanup in raw Resume deletion, gated by table availability.
- `lms/test_resume_experience_store.py`, `lms/tests.py`: adjust retry expectation/source ids and the old-schema mocked delete fixture.
- `lms/test_resume_experience_postgres.py`, `lms_server/resume_v2_postgres_test_settings.py` (new): isolated migration/concurrency/copy test infrastructure with production-settings guard.
- No new migration/schema field, production settings, React change or LLM workflow was needed in this verification step.

## M. Remaining Risks

1. An already-existing legacy copy without item id or a shared fallback key cannot be safely reconciled to its source by title or position. v2 lazy binding **blocks it without creating another Experience**. Initialize the original's stable key before a new copy, or later provide an explicit reconciliation operation for old copies. This limitation is tested and not mislabeled as a successful legacy-copy mapping.
2. PostgreSQL constraints do not express owner equality across rows, valid state enumeration or service-level source/fact uniqueness. All new service/copy paths enforce their relevant invariants, but arbitrary external SQL can bypass them.
3. RDS migration/deployment and production React activation remain outside scope. PostgreSQL tests do not prove production network availability.
4. Cross-document historical correction awareness in future Analyst integration still needs a domain review: active-only Writer input is verified, but an unedited older Resume source must not resurrect a superseded claim during later extraction. No LLM evaluation was performed in this phase.
5. Source ids must remain stable caller-supplied references. Original source archival and HTTP mapping of stale/lock errors are later integration contracts.

## N. Go / No-Go

**GO for the next common Application workspace implementation on this verified persistence foundation**, with the explicit conservative policy for unkeyed legacy copies. All ten required migration/transaction/normal-copy/ownership/adapter conditions have been reproduced in isolated PostgreSQL.

**Not a production rollout approval.** Keep production migration/activation separate, and retain the legacy-copy block until explicit source identity is established. No new Application model, LangGraph component or self-introduction engine was implemented here.
