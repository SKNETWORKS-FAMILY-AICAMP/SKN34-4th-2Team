# Resume Review Engine v2 — structural fixes, 2026-09-30

Scope: independent offline v2 core and its evaluation/tests. The production v1,
database schema, React and API routes were not changed. The 2026-09-29 evaluation
report is a historical baseline, not the result of this change.

## Contract

- `RevisionPlan` separates `core_evidence_ids` (required),
  `supporting_evidence_ids` (optional), `preserved_evidence_ids` (active
  original facts that must retain their meaning), and `omitted_evidence`.
  Core and supporting have a two-item cap for this single-field offline edit.
- Original text remains editing context and the apply target. Only atomic
  Analyst-extracted resume claims can become `resume_stated` Evidence.
- A clear `user_asserted` correction can set `supersedes_evidence_ids` and
  change the original Evidence to `superseded`. An `uncertain` answer cannot
  supersede. `conflicts_with_evidence_ids` records an unresolved conflict
  without changing the original state; conflicting facts are excluded from
  drafting until resolved.
- Writer input contains active core, supporting and preserved Evidence. Omitted,
  superseded, contradicted and retracted facts never enter Writer input.
- Writer returns `RevisionSentence(text, evidence_ids)[]`. The server joins
  sentence text to make the final `suggested_text`. There is no separately
  generated claim substring to compare with the final draft.
- Deterministic validation checks each sentence's cited Evidence, numbers and
  recognized technologies; only missing core facts cause `core_fact_unused`.
  Critical technical loss checks core facts, including whether recognized
  technology is absent from the actual text. The semantic verifier checks
  unsupported role/scope/result, active-original meaning loss and factual
  content in the draft without mapped Evidence. It receives cited and preserved
  Evidence, not unused optional supporting facts.
- At most one rewrite remains. If a procedural draft is flagged, optional
  supporting facts are moved to omitted before that rewrite; core and preserved
  facts remain available.

## Verification

`tests/test_resume_review_v2.py`: **33 passed** with plugin autoload and pytest
cache disabled. Tests cover Evidence hierarchy, explicit correction,
unresolved uncertainty, sentence provenance, per-sentence number/technology
support, verification boundaries and the one-rewrite limit. `git diff --check`
passed. The three live results below used `gpt-6-luna`, medium reasoning. Each
saved result has a Markdown file with blank Human judgement and Reason fields.

| Case | Status | Calls | Input / output tokens | LLM ms | Result |
|---|---|---:|---:|---:|---|
| 01 procedure dump | READY | 3 | 4,103 / 4,324 | 36,828 | PDF extraction, cleanup and reindexing omitted; core chunking and metadata remain. |
| 08 correction | READY | 5 | 4,679 / 4,344 | 39,781 | Both original personal implementation and model-training claims superseded; uncertain accuracy result excluded. |
| 09 claim mapping | READY | 3 | 3,180 / 2,257 | 21,422 | Docker sentence accepted through sentence provenance; posting-only Kubernetes excluded. |

Final saved executions total **11 calls, 11,962 input tokens, 10,925 output
tokens and 98,031 ms cumulative LLM latency**. These figures do not represent
total development spending: the initial run and limited reruns included failed
contracts and quality findings. Console logs and saved results together record
33 attempted calls and 40,807 / 34,280 input/output tokens across this work;
the cost dashboard remains authoritative for billing.

### Final draft excerpts

- 01: “공지·규정 문서를 검색하는 LMS 챗봇을 개발하며 RecursiveCharacterTextSplitter
  기반 문서 분할과 문서 종류·제목 메타데이터 구성을 적용해 Pinecone에 적재했습니다.”
- 08: “검색 API 연결을 담당했습니다.”
- 09: “Python으로 REST API를 개발하고 Docker 기반 로컬 실행 환경을 구성했습니다.”

The `READY` state means the configured checks passed, not that a person has
approved the Korean wording for submission. Human verdict fields are blank.
The original source of truth for resume content is unchanged. Before v2 can
replace v1 in production, Experience/Evidence persistence and resume-item
identity need separate design and implementation; do not infer that this
offline result verifies database writes or apply/revert integration.

## Saved human review files

- `evaluation/v2_results/hierarchy-20260930-final-rewrite/01_procedure_dump.md`
- `evaluation/v2_results/hierarchy-20260930-final/08_uncertain_claim.md`
- `evaluation/v2_results/hierarchy-20260930-recheck/09_job_only_technology.md`

Evaluation outputs are intentionally gitignored because they contain applicant
fixture text. The tracked result summary is this document.
