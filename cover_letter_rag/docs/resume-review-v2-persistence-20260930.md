# Resume Review v2 persistence boundary (2026-09-30)

This is opt-in infrastructure. It does not replace the v1 API, apply flow, React, or the DB-free v2 core. Migration `lms.0011_resume_experience_evidence` follows the manager `0008`–`0010` chain, is additive, and has **not** been applied to RDS. Isolated PostgreSQL verification and minimal copy/retry fixes are documented in [the PostgreSQL verification report](resume-review-v2-postgres-verification-20260930.md); that report supersedes the initial unverified limitations below.

## Identity and lifecycle

- `resume_experiences`: one actual project/employment/education/activity per user. Title is descriptive, never an identity or merge key. No global applicant assertions are inferred.
- `resume_evidence`: atomic, source-quoted facts under exactly one Experience. Source provenance is `source_type`, `source_id`, `evidence_quote`; job requirements never enter this table as applicant facts. `source_id` must be a stable caller-supplied resume revision/answer reference; no separate SourceRecord is created in this phase.
- `resume_experience_bindings`: `(resume_id, item_key)` unique; one Experience may be bound to multiple Resume documents. `field_path` and `display_order` are mutable locators, not identity.

On first use, `ensure_resume_item_binding` reuses the existing React item `id` as `section:id`. Only legacy items without an `id` receive a persisted `_experience_item_key` UUID in Resume.content. It creates a new Experience rather than guessing that similar titles are the same. Reordering refreshes the locator by key; subsequent independent resumes are not auto-merged. `clone_bindings_for_tailored_resume` requires a proven `base_resume` or `source_tailored_resume` relationship and matching stable keys in the target content. It copies only bindings, never Experience or Evidence rows. If a copy pipeline removes or changes item ids, the binding must be reconciled explicitly; title matching is prohibited.

## Corrections and writer input

`record_user_evidence` locks the Experience and target Evidence inside one transaction. A certain correction inserts a `user_asserted` fact, links `supersedes_evidence`, and marks the target `superseded`. A second correction against that now-inactive target is rejected. Every lookup is scoped to `experience_id` plus owner, never normalized fact or technology. An uncertain answer inserts `uncertain` with `conflicts_with_evidence`; the original remains `resume_stated` in storage but is withheld from `load_active_evidence` until the conflict is resolved. Other Experiences are untouched.

The active query returns only `resume_stated` / `user_asserted` without an unresolved uncertain conflict. Contradicted, retracted, superseded and uncertain rows do not reach the v2 input. `build_v2_review_input` loads the owned Binding/Experience and active Evidence, checks the stable item key against current Resume.content, computes a content hash, then builds the existing Pydantic `ReviewInput`. The v2 engine still has no Django/DB import. No production API invokes this adapter yet.

## Validation and remaining work

The disposable SQLite test settings avoid RDS and bypass the PostgreSQL-only `jobs` migration. Tests cover cross-Experience correction isolation, repeat correction, rollback, uncertain conflict, state filtering, reorder, React-native ids, tailored sharing without row copies, ownership, and an offline v2 engine invocation from a DB-built input. Existing 33 v2 unit tests still pass. PostgreSQL-specific migration/concurrency behavior and real RDS application remain **unverified** because no local test PostgreSQL server was available; SQLite does not validate PostgreSQL row locks. Before any production activation, run migration and concurrent correction tests on an isolated PostgreSQL test DB, then review/apply `0008` to the chosen RDS DB in a separate deployment step. Also verify that every resume copy/save path preserves item `id`; this phase does not wire the adapter to production or persist v2-generated extraction automatically.

The common Application workspace should wait until PostgreSQL verification and the adapter's source-id/copy-path contracts are confirmed. A future user-global assertion model, if needed, must be separate from Experience Evidence.
