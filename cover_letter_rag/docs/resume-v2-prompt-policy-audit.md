# Resume Review B: policy-4 conflict audit and implementation

## Actual live path

Ordinary React reviewSession initial / submitAnswer / gap_audit
→ Django /api/resume-review
→ B AI /resume-review/api/v1/resumes/reviews/proxy
→ LocalReviewService → BatchReviewEngine
→ ExtractionOutput → source/state/correction validation
→ ProjectEvidenceProfile → useful gaps → guarded questions → RevisionPlan
→ Writer → deterministic fact/quality checks → semantic fact/quality verifier
→ at most one rewrite → legacy response/apply contract.

Both single-experience and batch engines use prepare_review(). HTTP integration
tests call the actual mounted B route, replacing the gateway/model transport,
not planning logic. V1, Application Workspace, migrations and RDS are untouched.
React only distinguishes stable B gap identities; legacy questions keep their
old behavior.

## Responsibility and domain contract

ExtractionOutput has exactly experience_id, extracted_evidence and facets.
The LLM no longer selects facts or generates questions. AnalystOutput remains
an internal assembled compatibility contract, not the live extraction schema.
Facets classify slots/materiality; they are not new applicant facts.

ProjectEvidenceProfile is an Evidence-ID-only projection with eleven slots:
overview, purpose_or_problem, problem_observation, personal_role, technologies,
actions, technical_decisions, validation_method, outcome, insight_or_learning,
scale_or_constraints. Only active non-conflicting evidence populates it.
Technology facts cannot establish role/action/validation by classification.

Structured output constrains shape, not factual correctness; source and semantic
validation remain separate. See [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

Source-quote-based project type conservatively distinguishes ML, data analysis,
AI service, frontend/backend/fullstack, data engineering, generic software and
unknown. It changes planning priorities, not applicant facts. Job requirements
never enter extraction; selection/Writer use them only as relevance context.

## Gap / question / answer lifecycle

Gaps prioritize direct contribution and meaningful verification, not completing
every slot or STAR. Purpose/context + role/actions + validation/outcome may be
sufficient even with empty insight/scale slots. Working features, observations
and supported insights count; no forced KPI.

Question guard validates active basis IDs, exact premise-to-fact mapping, source
quote support and approved wording. Threshold clarification requires evidence
of a personally performed comparison; team context cannot support it. Open
questions cannot presume imbalance, Accuracy, threshold changes or variables.
Arbitrary generated wording is rejected even with a valid declared premise.

The actual UI response exposes at most three questions for the whole Resume.
Stable experience/slot/focus/premise fingerprints distinguish same-field gaps.
Only answered keys are suppressed; other unanswered questions survive follow-up.
Explicit no/unknown answers mark unavailable slots without positive evidence.
Fresh answers alone are extracted. Prior atomic evidence/facets are reused, and
Profile/gaps/selection are recomputed. Existing local review JSON holds metadata;
no DB table or migration is added.

## Selection / writing / validation / rewrite

Removed hard max-two core/support quotas. One representative per important meaning
is core; secondary context is optional. Overview, scale and secondary insights
do not become mandatory prose merely because their slots are populated.
Preserved facts protect selected original role/decision/result and narrow identity,
not all original details. Duplicate assertions do not create extra obligations.

Canonical priority: factual safety → applicant provenance → section fitness
→ evidence value → writing quality → length. Project prose should expose supported
problem-solving, implementation/decisions, verification and outcomes. Original
syntax and a fixed 2–3-sentence limit are not protected. Other section writing
rules remain in the common Writer.

Semantic verification returns factual findings and quality_issues separately in
the same existing call. Python flags duplication, enumeration and reporting/
chronology candidates. Reasoning exemption uses cited Evidence types, not magic
words such as “원인”; it is not proof of naturalness. Supporting omission and
sentence restructuring are not factual failures. Core reasoning/technical signal
must remain meaningful. Initial/rewrite use the same canonical Writer policy.
Optional procedure detail pruned for rewrite cannot cite itself back; preserved
IDs are never removed by that optional-pruning step.

## Prior first-phase rules removed / integrated

| Old responsibility/rule | Final owner/rule |
|---|---|
| Analyst extraction + selection + questions | Extraction only; Python projection/planning/selection |
| Core/support at most two | Value-based independent meanings; no fixed count quota |
| Prompt-only question premise safety | Typed gaps, safe builder and deterministic guard |
| Re-extract old Q&A history | New answer only + stored atomic evidence/facets |
| Same field/topic collapses B questions | Stable gap identity, legacy fallback unchanged |
| Suppress all generated questions | Suppress answered keys; retain unanswered gaps |
| Three per project produces many visible questions | Whole-Resume cap of three |
| Sentence-count / length-only failure | Density, redundancy and section fitness |
| Keyword-only reasoning bypass | Cited reasoning/verification + semantic quality checks |
| Different preservation/rewrite definitions | Shared policy.py and writing_policy.py |

Retained: source quotes, active assertion states, uncertainty/conflict exclusion,
clear correction supremacy, unsupported number/technology blockers, sentence
provenance, original/apply locator, fail-closed verifier, maximum-one rewrite.
V1 baseline prompts/workflow/fact checker are unchanged.

## Executed A/B/C Python planner output

These are executed deterministic outputs from supplied evidence fixtures,
not live extraction/Writer outputs.

A — Churn-prediction context and Python/XGBoost only:
- 프로젝트에서 팀 전체 작업과 구분해 본인이 직접 담당한 부분은 무엇인가요?
- 모델 성능은 어떤 기준이나 지표로 평가했나요? 정량 수치가 없어도 괜찮습니다.

B — A plus explicitly asserted class imbalance:
- 클래스 불균형은 어떤 데이터나 분포를 보고 확인했나요?
- A's direct-role and open evaluation questions remain useful.
The browser globally prioritizes HIGH questions before this MEDIUM clarification.

C — B plus Accuracy/F1/PR-AUC evaluation and personally performed threshold
comparison: zero questions, since context, contribution and verification are
sufficient. Known metrics are not re-asked. When important context/evaluation is
missing, confirmed threshold work can instead support a comparison-basis follow-up.

## Verification scope and remaining limits

Unit/HTTP tests cover forged premises, source identity, fresh-answer reuse,
qualitative outcomes, correction/conflict recomputation, optional omission,
unsupported facts, materiality, section rules, rewrite and stable UI identity.
The mounted HTTP path is verified with model/DB mocks, not a paid browser review.

Conservative type/clarification recognizers may miss unusual wording. Facets and
materiality still depend on extraction quality. Exact quotes cannot prove external
truth or full semantic fidelity; existing verifier and human inspection remain
necessary. Gap planning is project-specific; other sections retain common writing/
provenance, without the new project slot questions. No performance/quality gain
is inferred from mocks. The user must evaluate actual model output in the browser.

Planned batch calls: extraction-only/no-change 1; ordinary draft 3 (extraction,
Writer, verifier); conditional rewrite at most 5. Profile/gaps/questions/selection
add zero calls. Actual LLM calls in this task: 0. No RDS/AWS writes, migrations,
commit or push. Final test results are reported in the task handoff.
