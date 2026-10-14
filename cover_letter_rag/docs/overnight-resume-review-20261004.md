# Overnight stabilization — 2026-10-04

## Checkpoint 1: preserved baseline
- Branch `feature/resume-review-quality`, HEAD `4b92b10`; existing dirty files retained.
- Read-only local PostgreSQL inspection: reviews 17–23 complete, 24 processing; no writes.
- Historical inputs located: AI LMS review 20 / 23, KKBOX 21, garage 22.
- Next: replay only saved Experience Writer/Verifier inputs; no whole-resume extraction, matching or DB persistence.
- No commits, pushes, migrations, RDS/AWS operations.

## Checkpoint 2: actual Verifier replay
- `evaluation/runs/overnight_verifier_scope_20261004.json`: saved analysis/selection replay, real Writer/Verifier (not a complete fresh Analyst evaluation).
- Review 20: initial specificity/scope loss, corrected by one rewrite; READY, 4 calls, 20,073 input / 4,404 output tokens, 45.532s.
- Review 23: project techStack correctly resolved as owning Experience in both Verifier calls. No unsupported claim; rewrite introduced LMS-context and validator-purpose omissions, correctly REJECTED. 4 calls, 23,840 / 6,304 tokens, 60.767s.
- Both second Verifiers received the previous Writer and first verdict. Historical delayed reuse/scope errors did not recur. No READY forcing or relaxed verification.

## Checkpoint 3: small general changes
- Writer: removed original-prose-order preservation; canonical project policy now recomposes the whole paragraph from supported relations, combining implementation/verification without duplicate feature inventory. No schema/template/length quota change.
- Training label: regular Resume `course` is used without changing Experience IDs. Replayed questions resolve labels from current owning Resume instead of stale record titles.
- Next: focused tests, KKBOX/garage live replay, duplication investigation, final regression once.

## Checkpoint 4: first Writer evaluation, not automatic success
- Focused Python tests: 66 passed after fixing two test assertions and including repo root in PYTHONPATH. First invocation also had fixture import errors, not application regressions.
- UI tests: 17 passed (reviewWindow/reviewSession); existing rejection/no-apply tests retained.
- KKBOX review 21: READY, 2 calls, 10,263 / 1,887 tokens, 20.047s. AUC/direction/variable significance connected; model list still dense. No invented relationship between threshold experiment and single-variable finding.
- Garage review 22: READY, 2 calls, 7,537 / 1,381 tokens, 14.032s, but human inspection still finds repeated feature inventory. **Writing goal not yet met despite verifier approval.**
- Replay recovered old exact quote sources from earlier actual reviews where applying a revision had changed current_text; eval-only historical source aliases recorded. No source invented, no DB edits. Two preflight failures spent 0 API calls.
- Canonical project policy clarified implementation/check as one coherent passage, no second feature inventory. Only failed garage case will be rechecked once; KKBOX not rerun.
- Education/project relationship absent from the B request/model; cannot prove which listed projects belong to this course. No guessed cross-experience linking or question suppression.

## Checkpoint 5: final verification
- Garage-only recheck: `evaluation/runs/overnight_garage_recomposition_recheck_20261004.json`, 2 calls, 7,616 / 1,343 tokens, 14.922s; READY. Check is now next to implementation, before data preparation rather than a closing append. Some feature repetition persists: **partial improvement, not complete elimination**. No further paid repetitions.
- Python focused 66 passed; final policy-specific 14 passed (subset, do not add to unique count).
- React related 18 passed; `tsc -b --pretty false` passed. Training label works for both new responses and persisted internal-ID conversations, resolving stable item ID even after array reordering.
- Final backend run exactly once: **497 passed in 5.07s**. `test_matching_handoff.py` (32 collected tests) excluded because its PostgreSQL store fixture issues DELETE/INSERT/DDL. Do not run it against this B history cluster.
- Added 3 Python test cases and 2 UI cases; expanded existing policy assertions. Earlier unrelated fixture import failures resolved with repo-root PYTHONPATH, no application workaround.
- Actual model `gpt-6-luna`, configured reasoning unchanged. **14 paid Writer/Verifier calls total**, 69,329 input / 15,319 output tokens, 155.300s summed API latency. Analyst, recommendation, requirement extraction: 0 calls. No failed/retried API calls; 2 source preflight failures were before any API attempt.
- Raw reports contain each complete prompt/payload, initial candidate, first verdict, rewrite, second verdict, deterministic result, usage and empty human judgement fields. All saved B reviews left unchanged.
- `git diff --check` passed (existing CRLF normalization warning only). No commit/push/merge/rebase/migration or RDS/AWS/production writes.

## Live comparison — saved historical output vs current generated output

### KKBOX
Before (review 21):
> KKBOX 사용자 데이터를 활용해 사용자 이탈을 예측했습니다. 약 99만 건 중 이탈 비율이 약 6.4%인 클래스 불균형을 확인해 Accuracy만으로 평가하기 어렵다고 판단하고, Logistic Regression, Decision Tree, Random Forest, XGBoost, LightGBM, CatBoost를 Precision, Recall, F1, ROC-AUC, PR-AUC로 비교했습니다. XGBoost의 threshold별 F1을 비교한 결과, 테스트한 값 중 0.2에서 가장 높은 0.2612를 기록했습니다. 또한 단일 변수 분석에서 days_to_expire의 directional AUC는 약 0.905였으며, 만료일까지 남은 일수가 짧을수록 이탈 가능성이 높아지는 방향성이 나타났습니다.

After (real Writer/Verifier replay):
> KKBOX 사용자 데이터로 사용자 이탈을 예측했습니다. 약 99만 건의 데이터에서 이탈 비율이 약 6.4%인 클래스 불균형을 확인해 Accuracy만으로 평가하기 어렵다고 판단하고, Logistic Regression, Decision Tree, Random Forest, XGBoost, LightGBM, CatBoost를 Precision, Recall, F1, ROC-AUC, PR-AUC로 비교했습니다. XGBoost의 threshold를 조정해 비교한 결과, 테스트한 값 중 0.2에서 F1이 가장 높았으며(0.2612), days_to_expire는 단일 변수 기준 directional AUC 약 0.905를 보였습니다. 만료일까지 남은 일수가 짧을수록 이탈 가능성이 높아지는 방향성이 뚜렷해 이탈 예측에서 중요한 변수임을 분석했습니다.

Technical facts retained; the directional finding now explains variable significance. Still a dense model/metric list. Threshold and single-variable findings are independent; no fabricated causality is needed. This case was not rerun after the final clarification of the same canonical project policy.

### Garage
Before (review 22):
> 사용자 위치를 기준으로 가까운 자동차 정비소를 찾는 서비스를 구현하고, 정비소 주소와 위·경도 데이터에 Haversine 거리 계산을 적용해 거리순으로 정렬했습니다. 브랜드 공식 서비스센터와 정비소 종류를 필터링하고, 운영시간 데이터가 있는 경우 영업 중 여부를 표시했습니다. 초기에는 CSV를 사용하고, 이후 MySQL 연계를 고려해 브랜드와 정비 유형 데이터를 구조화했습니다. 사용자 위치 기준 거리순 정렬, 브랜드·정비소 유형 필터, 운영시간에 따른 영업 여부 표시가 정상 동작하는지 직접 테스트했습니다.

After (garage-only recheck):
> 사용자 위치로 가까운 자동차 정비소를 찾는 서비스를 구현하고, 정비소 주소와 위·경도 데이터를 활용한 Haversine 거리 계산으로 정비소를 거리순 정렬했습니다. 브랜드 공식 서비스센터와 정비소 종류를 필터링하고 운영시간 데이터가 있는 경우 영업 여부를 표시했으며, 거리순 정렬과 필터·영업 여부 표시가 정상 동작하는지 직접 테스트했습니다. 초기에는 CSV를 사용하고, 이후 MySQL 연계를 고려해 브랜드와 정비 유형 데이터를 구조화했습니다.

Implementation and checking now form one passage; shortened repeat remains. Automatic READY is not the final human submission-quality decision.

## Remaining limitations / next step
- AI LMS case 2 rewrite introduced genuine source-context/validator-purpose loss and was rejected. No scope false positive, but rewrite regression remains.
- Verifier approved both garage versions despite repeated feature wording. Quality sensitivity is still weaker than factual sensitivity.
- Training/project question overlap is plausible but unproven: no declared course→project relation or cross-experience context in the current B Analyst request. Do not guess membership or copy Evidence across owners.
- Paid evaluations replayed saved extraction/selection through the real single-experience Writer/Verifier methods. They are not a fresh whole-resume Analyst+batch+browser E2E run; deterministic mounted-B tests cover those contracts.
- Most valuable next step: human review of these actual drafts and one manual B follow-up, focusing on rewrite regressions and semantic repetition rather than expanding the evaluation suite.

## Optional: initial-request latency inspection (no latency code changes)
The 105s Analyze / 39s Writer / ~20s remaining Verifier budget figures are the user's historical measurements, not a new timing run. Code candidates, highest expected value first:
1. `batch.py::_batch` shares only `job_requirements`; Analyst uses `target_context` and Verifier `allowed_target_context`, so their identical requirements are repeated per item. Hoist shared target context without changing provenance/content.
2. `ExtractionOutput` repeats atomic Evidence quote + normalized fact + owner/source/state metadata, facets and semantic-unit meanings/refs per Experience. Date fields are emitted null; long source quotes and verbose JSON increase output generation. Assess a compact transport mapped deterministically into the unchanged domain contract, not removing facts or safety.
3. Writer/Verifier duplicate `evidence_quote` in `source_context.quote`, plus normalized fact, semantic-unit meanings and complete original text. Remove literal duplicate transport while preserving exact source, owning field and the independent original-vs-revision check.
4. `_batch` uses one large schema envelope for all initial Experience items and one shared request deadline. A large Analyst output consumes the downstream verification budget. Bound batch transport/scheduling only after measuring real per-stage tokens and deadline needs; no unverified parallelization or reasoning downgrade implemented.
5. Initial prompts send section policy per item; repeated constants/empty Experience fields can be shared or omitted from transport. Lower expected impact than long quotes/requirements and extraction output.

## Optional: develop integration checklist (no fetch/merge/rebase)
- Inspected existing local `origin/develop` ref: `2c740c8bb94890947787278c8be5367d0304c304`; **remote freshness not verified**.
- High-conflict surfaces: `lms_api/lms/models.py`, Resume/Job/tailored API handlers and requirement cache wiring, `ResumeEditScreen`, `ReviewWindow`, `reviewSession`, app routes/styles. Preserve explicit save/draft protection and old apply/revert/requirement_map contracts.
- Domain migrations 0011–0014 and experimental empty bridge `0015_merge_resume_and_manager` (dependencies 0014 + 0101) require graph review against the then-current develop leaves. Do not edit/renumber 0014 or team 0100-series migrations blindly. No migration run here.
- Carry forward Experience/Evidence/Application ownership and sentence provenance; keep v1 baseline callable. UI optional question identity/title and `validation_status` must remain backwards compatible; rejected drafts never become applyable.
- Keep B `local_resume_site*`, fixed loopback DB/proxy settings, historical replay scripts/reports and private real-data fixtures out of automatic production routing. Review tracked/untracked status deliberately rather than `git add .`.
- Before integration: isolated migration tests, Resume/Job/tailored API contract tests, fact corrections/ownership/provenance, Planner question isolation, Writer/rewrite safety, save/polling, apply/undo/session and UI status regressions. Current PostgreSQL write-fixture tests need a disposable isolated environment, not B history/RDS.

## Browser handoff
- B apps were not running at the final port check; launched existing local entry points (not new services): Django 8002, AI 8003, ordinary React 5180.
- `http://127.0.0.1:5180/resume` and AI `/openapi.json`: HTTP 200; all four ports including the unchanged PG 55439 listening.
- No automated browser review, login, recommendation or apply request executed. Browser submission quality remains for the user's manual test.
