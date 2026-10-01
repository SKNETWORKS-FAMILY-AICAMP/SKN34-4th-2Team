# RecruitRole / Company target context integration

Scope: `feature/resume-review-quality`, isolated PostgreSQL only. Production RDS,
LLM APIs, production routes, React, and v1 are not changed or exercised.

## A. Existing Schema Audit

`MigrationLoader(connection).graph.leaf_nodes('lms')` before this change returned
only `0013_application_questions_answers`. The existing sequence is
0011 Experience/Evidence/Binding → 0012 Application → 0013 Questions/Answers/Plan.

Repository models/migrations/crawler SQL contain no Company/CompanyInfo/
company_profiles/RecruitRole identity table. `jobs.jobs` instead stores company
display strings and company_type per posting. Those are source listing attributes,
not an independent company identity table.

Ownership: `lms/migrations/0003_jobs_schema.py` freezes jobs schema SQL using
RunSQL. `scripts/firestore_to_postgres/jobs_schema.sql` is the crawler bootstrap
schema; `job_matching_bot/ingestion/sqlite_store.py`, despite its legacy name,
uses PostgreSQL/psycopg. No Django Jobs ORM model owns the posting table.

This audit establishes the repository/migration baseline, NOT the current common
RDS catalog. Any manually added teammate table on RDS remains **unconfirmed**;
read-only production catalog reconciliation is required before deployment. This
phase does not contact RDS or assume that a manually created table is absent there.

## B. Migration Decision

New `lms/migrations/0014_recruit_role_context.py` depends on 0013, containing:

- RunSQL adding nullable `jobs.jobs.apply_method` and a CHECK.
- Managed `public.company_profiles` and `public.recruit_roles` models.

0011–0013 and earlier migrations were not rewritten or renamed. No parallel leaf,
merge migration, new schema, cover_letters table, or Application root is introduced.
The reverse operation removes only the new column/tables. Reverse migration is
tested locally but would discard NEW context data; it is not a safe production
rollback procedure and was not run on RDS.

## C. Job apply_method

Nullable varchar(16), values HOMEPAGE / SITE / EMAIL / OTHER, enforced by
`ck_job_apply_method`; `JobApplyMethod` supplies Django TextChoices.
`set_job_apply_method` is an admin-only parameterized write boundary.
Crawler ingestion still uses explicit preexisting column lists: it does not
automatically infer this field and does not overwrite it during posting upserts.
Its original schema bootstrap is not a replacement for applying 0014.

`posted_at` remains untouched. JobKorea reads JSON-LD `datePosted` in
`crawling/jobkorea.py`, propagates it in `ingestion/jobkorea.py` and tests it as
the posting date. Saramin may leave it NULL. Application opening date must not be
silently assigned to this column; that is a separate future requirement.

## D. Company Model Decision

Create one public managed CompanyProfiles model. Actual identity is UUID PK;
RecruitRoles.company is a PROTECT FK to it. Optional type/logo/homepage are NULL.
Company metadata creation/update is admin-only. Roles display the current company
name via FK; no second live company_name column is added to RecruitRoles.
Application's frozen source context explicitly retains the historical display
label, not a second editable company source of truth.

## E. company_key Strategy

NFKC, casefold, legal `(주)`/주식회사 prefix/suffix removal and whitespace removal
produce a UNIQUE lookup key. Display-name or lookup-key edits do not alter UUID.
Lookup does not implicitly rename/overwrite an existing profile. Ambiguous company
names require manual admin resolution; no fuzzy auto-merge or legal-entity proof
is claimed.

## F. RecruitRole Model

UUID id; company FK; season/role_name; original role_description; requirements
JSON; questions JSON; content_hash; source_type; nullable source_url/job_id;
nullable created_by/verified_by Users SET_NULL; verification_status;
nullable verified_at; immutable dedupe_owner; nonnegative use_count; timestamps.

Requirements accept either source `{required, preferred, responsibilities}` string
arrays or the existing JobRequirement list contract (`must/preferred/task`, etc.).
Question templates preserve text and explicit positive character_limit,
count_unit/include_spaces; order is validated unique and sorted at submission.

Service submissions create new content versions instead of editing referenced
source content. Direct ORM/SQL writes are trusted infrastructure and can bypass
service policies; they must not be exposed as user endpoints.

## G. Target Context Boundary

```text
CompanyProfiles → RecruitRoles → Application.role_context_id + source snapshot
                                 ↓
                           ApplicationQuestions → ApplicationAnswers

Base Resume → ResumeExperienceBinding → Experience → Evidence
```

RecruitRole requirements, company metadata, and templates enter only Target
Context. No evidence extraction or applicant fact persistence happens in these
services. Kubernetes in a role requirement does NOT imply applicant experience.

## H. Source / Verification Policy

Shared query requires company_site + verified + nonempty source_url. `other`
is private even if verified. Pending/rejected official sources are owner/admin
only. Active users are required. Only current role `admin` can moderate; instructor
is not silently granted admin rights. A URL establishes traceability, not proof
that the domain is official: verification is explicitly a human admin decision.

Ordinary users cannot delete verified content or moderate states. There is no
content update endpoint; edits are new pending versions. Delete and moderate
serialize on the role row. Private foreign roles cannot be read/deleted/attached
through the native Application adapter. Deleted-owner private rows are admin-only,
never automatically shared or reassigned.

## I. content_hash Strategy

SHA256 over canonical JSON of description + requirements + question templates.
NFC string normalization, whitespace/line-ending collapse, sorted dictionary keys,
compact serialization; list ordering and real wording remain significant.
Original description/question text is stored intact. This is formatting-level
normalization, NOT semantic equivalence, translation, or paraphrase detection.
Hash is version/dedupe signal, not Role or Company identity.

## J. Dedup / Unique Policy

- Official conditional unique: company, season, role_name, content_hash.
- Private conditional unique: company, season, role_name, content_hash,
  dedupe_owner (original creator's numeric id serialized as an immutable scope).

The additional private scope is not used for authorization. It solves NULL
semantics without merging different users' records or blocking a second SET_NULL
due to NULLS NOT DISTINCT. Creator remains a nullable FK; new private submissions
require a real active owner. Retained scopes remain distinct after creator NULL.
Company-row locking serializes submission dedupe; DB unique constraints remain
the final defense. Official duplicates do not leak another owner's pending content.

## K. Application Integration

Reuse `role_context_id` varchar external reference; native adapter stores Role
UUID string. No recruit_role_id/target_role_id duplicate field is introduced.
It is intentionally not converted into a FK: 0012 already permits historical
external string references, so blindly casting existing values to UUID or deleting
them would be unsafe. Native attachment is checked in the service boundary.

`create_role_application` uses existing create_application; freezes selected
Role id/hash/source content in target_snapshot.recruit_role_snapshot and supplies
role_version. UUID+version determine native context identity; historical company
display labels do not break idempotent retries after company rename. Existing
legacy/Job-only request identity behavior is preserved.

Job only, Role only, and Job + Role all work. Deleted Job does not delete Role.
Deleted Role does not delete Application or its Questions/Answers: the external
reference and owned frozen source snapshot remain. Existing Application open never
requires a live Role. Creating/carrying a new native Application requires a current
accessible source; copying a deleted source into a NEW workspace is not enabled.

## L. Question Snapshot Integration

`import_role_questions` routes frozen templates through existing `import_questions`.
No duplicate ApplicationQuestion creation implementation. Explicit source metadata
uses optional constraint overrides; conflicts with an explicit raw-text limit,
unit, or whitespace rule reject the whole import transaction.

Reference is Role UUID + content hash; existing import keys remain unchanged for
old callers. Retry does not overwrite edited question rows. Later Role source
changes do not change an existing application's frozen source/questions.
Import locks Application and increments `use_count` with F() on first nonempty
import only. Counter is approximate derived telemetry, not identity or evidence.

`application_question_store._target` passes frozen Role description/requirements
without duplicating template questions into context. Existing Analyzer/Planner
prompts and semantic contracts were not changed.

## M. PostgreSQL Tests

Local cluster: PostgreSQL 16, 127.0.0.1:55439, resume_v2_test_admin. Test settings
hard-code the isolated database and reject accidental production settings.

Tests cover fresh full migrations, 0013→0014, reverse→reapply, preserved
Experience/Evidence/Binding/Application/Questions/Answers, new PK/FK/check/index
constraints, company uniqueness/stable identity, hash normalization, official and
private dedupe, NULL creator scopes, concurrent submission, sharing/ownership,
native context forgery, unchanged question snapshots, source metadata, apply_method
CHECK/NULL and unchanged posted_at, and deleted source survival.

Full Users.delete exposed an EXISTING failure: collector queries missing unmanaged
`assignment_submissions`. We did not restore legacy tables or alter global deletion.
Regression explicitly records that failure, separately exercises new SET_NULL
handlers, and tests distinct orphan scopes. Therefore whole-account deletion is
**BLOCKED**, not falsely reported as successfully verified.

Final run: **115 PostgreSQL tests passed in 84.860 seconds**, including 24 new
context/migration tests and 91 existing regression tests. Full fresh test database
was created and destroyed by Django. The assertion of the known legacy deletion
failure is included; passing that diagnostic test does NOT mean Users.delete works.

## N. Existing Regression Tests

PostgreSQL regression command includes new recruit-role tests, Phase4A planning,
Application Workspace, Experience/Evidence persistence, concurrency/migrations,
and existing ResumeDelete/ResumeWriteValidation tests.
Existing v2 core + tailored-resume pytest: 40 passed, no live LLM calls.
`makemigrations --check --dry-run`: no changes; Django check: no issues.
Final migration graph has one leaf: `0014_recruit_role_context`. Read-only
`SELECT current_database(), current_user` on the isolated base connection returned
`resume_review_v2_test / resume_v2_test_admin`, not production credentials.
`git diff --check` was clean. Total verified tests: 115 + 40 = 155.

## O. Schema/Data Conflicts Found

1. Existing role_context_id permits external strings: unsafe to cast/replace as FK.
2. Target snapshots originally allow only bounded strings: native structured
   source snapshot needs explicit validated support.
3. Source character limit may be metadata rather than text: parser-only import
   would lose it, or contradictory overrides could silently overwrite it.
4. Nullable creator dedupe using created_by alone loses uniqueness after deletion.
5. Global User ORM deletion queries absent legacy tables (existing defect).
6. Common RDS's manually created tables are unknown; repository audit is not proof
   of production compatibility.

## P. Changes Made to Resolve Them

Reuse one external role reference + native adapter; validate source snapshot against
authorized Role; cap serialized native snapshot at 100,000 characters; reuse
existing import with validated metadata; retain immutable dedupe scope; lock new
delete/moderation and dedupe/import boundaries. Global legacy deletion is left
explicitly blocked, without an unrelated workaround.

Changed/created this phase: models.py, 0014_recruit_role_context.py,
recruit_role_store.py, application_workspace.py, application_question_store.py,
test_recruit_role_context.py, and this report. Earlier uncommitted implementation
files remain preserved; no commit/push was requested or performed.

## Q. Remaining Risks

- Before RDS deployment, inspect actual public/jobs tables/columns/indexes and
  migration recorder. Resolve any teammate manual-table ownership conflict first.
- Global account deletion is not supported by the current absent legacy-table
  relations. SET_NULL contract is ORM behavior; direct SQL DELETE of Users is not
  automatically made safe by Django on_delete.
- User-facing production APIs/React are not wired; caller must use the native
  service adapter, not arbitrary ORM writes.
- Company lookup normalization is not definitive entity resolution.
- Raw ingestion does not auto-detect apply_method; verified metadata needs caller
  input. URL provenance still needs admin verification.
- Snapshot consistency is service-enforced, not an Application FK/database trigger.
- Existing Phase4A.5 complex Planner semantic failure remains untouched.

## R. Go / No-Go

**GO to Phase4A.6 Planner correction**: final isolated tests passed.
**NO-GO to Answer Writer/production cutover**: previous Experience scope, result
semantics and gap type failures still require Phase4A.6 work. **NO production
migration approval implied**. Global account deletion remains separately blocked.
