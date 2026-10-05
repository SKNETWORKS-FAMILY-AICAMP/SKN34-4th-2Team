"""Project planning contracts and A–L regression, with zero external calls."""
import pytest
from pydantic import ValidationError
from app.resume_review_v2.models import (Evidence, EvidenceFacet, ExtractionOutput,
    Experience, ReviewInput, ProjectSlot as S, GapQuestion, QuestionPresupposition,
    FactVerification, SourceDocument, RevisionSentence, WriterOutput, RevisionPlan)
from app.resume_review_v2.project_planning import (prepare_review, build_profile,
    active_facts, detect_gaps, plan_questions, validate_question)
from app.resume_review_v2.validation import ContractError, validate_candidate


def case(rows, *, existing=(), answer='', previous_facets=(), keys=(), unavailable=()):
    text = '\n'.join(row[1] for row in rows)
    exp = Experience(experience_id='project', kind='project', title='테스트 프로젝트',
        current_text=text, field_path='projects[0].description', content_hash='h',
        existing_evidence=list(existing))
    req = ReviewInput(experience=exp, answer=answer, answer_source_id='answer' if answer else '',
        previous_facets=list(previous_facets), previous_question_keys=list(keys), unavailable_slots=list(unavailable))
    facts, facets = [], []
    for index, (kind, quote, slots) in enumerate(rows):
        eid = f'ev-{index}'
        facts.append(Evidence(evidence_id=eid, experience_id='project', fact_type=kind,
            normalized_fact=quote, evidence_quote=quote, source_type='resume_text', source_id='project', assertion_state='resume_stated'))
        facets.append(EvidenceFacet(evidence_id=eid, slots=slots))
    extraction = ExtractionOutput(experience_id='project', extracted_evidence=facts, facets=facets)
    return req, extraction


MINIMAL = [('context', '이탈 예측 프로젝트', [S.OVERVIEW]),
           ('technology', 'Python과 XGBoost 사용', [S.TECHNOLOGIES])]
IMBALANCE = ('context', '클래스 불균형 데이터였음', [S.OBSERVATION])
METRICS = ('verification', '불균형 때문에 Accuracy와 F1, PR-AUC로 평가함', [S.VALIDATION])
THRESHOLD = ('action', 'XGBoost threshold를 여러 값으로 비교함', [S.ACTIONS, S.ROLE])


def questions(rows):
    req, output = case(rows)
    prepared = prepare_review(req, output)
    # Exercise the old deterministic diagnostic suggestions independently.
    # They no longer authorize live questions without semantic value assessment.
    prepared.questions = plan_questions(req.experience.experience_id, prepared.gaps, prepared.evidence)
    return prepared


def test_minimal_ml_does_not_assume_metrics_imbalance_or_comparison():
    prepared = questions(MINIMAL)
    assert prepared.profile.project_type == 'machine_learning'
    assert 1 <= len(prepared.questions) <= 3
    assert prepared.analysis.plan.operation == 'no_change'
    combined = ' '.join(q.question for q in prepared.questions)
    assert all(s not in combined for s in ['Accuracy', 'threshold', '불균형', '중요한 변수'])
    assert all(not q.presuppositions for q in prepared.questions)


def test_imbalance_enables_only_supported_observation_followup():
    prepared = questions([*MINIMAL, IMBALANCE])
    assert prepared.questions[0].target_slot == S.OBSERVATION
    assert prepared.questions[0].presuppositions[0].evidence_ids == ['ev-2']
    assert all('Accuracy 대신' not in q.question and 'threshold' not in q.question for q in prepared.questions)


def test_known_metrics_and_reason_are_not_reasked():
    prepared = questions([*MINIMAL, IMBALANCE, METRICS])
    assert prepared.profile.validation_method.evidence_ids == ['ev-3']
    assert all(q.target_slot != S.VALIDATION for q in prepared.questions)
    assert all('어떤 지표' not in q.question for q in prepared.questions)


def test_threshold_followup_only_after_comparison_evidence():
    before = questions([*MINIMAL, IMBALANCE, METRICS])
    after = questions([*MINIMAL, IMBALANCE, METRICS, THRESHOLD])
    assert all('threshold' not in q.question for q in before.questions)
    # These facts now support a useful contribution; if already sufficient there
    # is no obligation to ask. Removing overview exposes a high-value clarification.
    partial = questions([MINIMAL[1], THRESHOLD])
    followup = next(q for q in partial.questions if q.target_slot == S.DECISIONS)
    assert followup.evidence_basis == ['ev-1']
    assert '비교' in followup.question
    assert after.questions == []


@pytest.mark.parametrize('text,basis', [
    ('Accuracy 대신 어떤 지표를 사용했나요?', 'Accuracy를 사용했다'),
    ('threshold를 어떻게 조정했나요?', 'threshold를 조정했다'),
    ('불균형 데이터를 어떻게 처리했나요?', '불균형이었다'),
    ('중요한 변수는 무엇인가요?', '중요한 변수를 확인했다'),
])
def test_fabricated_question_premises_or_wording_rejected(text, basis):
    prepared = questions(MINIMAL)
    q = GapQuestion(experience_id='project', question=text, gap_type='clarification', target_slot=S.DECISIONS,
        evidence_basis=['ev-1'], priority='HIGH', why_needed='판단', dedupe_key='bad',
        presuppositions=[QuestionPresupposition(fact=basis, evidence_ids=['ev-1'])])
    with pytest.raises(ContractError): validate_question(q, prepared.evidence)


def test_forged_wording_with_real_premise_still_rejected():
    prepared = questions([*MINIMAL, IMBALANCE])
    q = prepared.questions[0].model_copy(update={'question': '불균형을 해결한 성과는 몇 퍼센트인가요?'})
    with pytest.raises(ContractError, match='wording'): validate_question(q, prepared.evidence)


def sufficient_rows():
    return [
        ('context', '가까운 정비소를 찾기 어려운 문제', [S.PURPOSE]),
        ('role', '위치 기반 조회 기능을 직접 담당', [S.ROLE]),
        ('implementation', '사용자 위치와 위경도로 Haversine 거리순 조회 구현', [S.ACTIONS]),
        ('implementation', '브랜드·유형 필터와 운영시간 기반 영업 여부 표시', [S.ACTIONS]),
        ('technology', 'CSV 데이터를 MySQL 연계 구조로 정리', [S.TECHNOLOGIES]),
        ('verification', '알려진 위치와 거리순 결과를 대조해 정상 조회를 확인', [S.VALIDATION]),
    ]


def test_vehicle_and_sufficient_evidence_need_no_slot_filling_questions():
    prepared = questions(sufficient_rows())
    assert prepared.questions == []
    assert not prepared.profile.insight_or_learning.evidence_ids
    assert not prepared.profile.scale_or_constraints.evidence_ids
    assert len(prepared.analysis.plan.core_evidence_ids) > 2
    assert prepared.profile.technologies.evidence_ids == ['ev-4']


def test_lms_preserves_decision_and_verification_not_every_internal_object():
    rows = [
        ('context', '첨삭에서 없는 경험이 추가되는 문제', [S.PURPOSE]),
        ('role', '사실 검증 흐름 직접 설계', [S.ROLE]),
        ('implementation', 'RAG 검색과 Evidence 기반 첨삭 구현', [S.ACTIONS]),
        ('technical_decision', '문장별 근거를 연결하도록 설계', [S.DECISIONS]),
        ('verification', '허위 역할과 수치를 포함한 후보를 검증', [S.VALIDATION]),
        ('action', 'InternalPlanCache와 HelperObject를 생성', [S.ACTIONS]),
    ]
    req, output = case(rows)
    output.facets[-1].material = False
    prepared = prepare_review(req, output)
    core = prepared.analysis.plan.core_evidence_ids
    assert {'ev-0', 'ev-1', 'ev-2', 'ev-3', 'ev-4'} <= set(core)
    assert 'ev-5' in {o.evidence_id for o in prepared.analysis.plan.omitted_evidence}


def test_job_context_cannot_create_profile_or_question_premise():
    from app.resume_review_v2.models import JobRequirement
    req, output = case(MINIMAL)
    req.job_requirements = [JobRequirement(requirement_id='j', text='PostgreSQL React', posting_quote='PostgreSQL React 우대')]
    prepared = prepare_review(req, output)
    assert prepared.profile.technologies.evidence_ids == ['ev-1']
    assert all('PostgreSQL' not in q.question and 'React' not in q.question for q in prepared.questions)


def test_inactive_and_unresolved_conflicts_do_not_populate_profile():
    req, output = case(MINIMAL)
    output.extracted_evidence[1].assertion_state = 'uncertain'
    prepared = prepare_review(req, output)
    assert prepared.profile.technologies.evidence_ids == []
    # The active overview itself states churn prediction; the uncertain technology
    # is excluded, but does not erase that supported planning signal.
    assert prepared.profile.project_type == 'machine_learning'


def test_extraction_can_propose_one_question_but_not_a_revision_plan():
    assert set(ExtractionOutput.model_fields) == {'experience_id', 'extracted_evidence', 'facets', 'intent_claims', 'semantic_units', 'question'}
    req, output = case(MINIMAL)
    with pytest.raises(ValidationError):
        ExtractionOutput.model_validate({**output.model_dump(), 'plan': {}})


def test_unknown_facet_and_cross_experience_source_fail():
    req, output = case(MINIMAL)
    output.facets.append(EvidenceFacet(evidence_id='job-req', slots=[S.TECHNOLOGIES]))
    with pytest.raises(ContractError, match='unknown profile'): prepare_review(req, output)


def test_progressive_answer_updates_profile_and_does_not_reask_metrics():
    req, initial = case(MINIMAL)
    first = prepare_review(req, initial)
    req2 = req.model_copy(deep=True)
    req2.experience.existing_evidence = list(first.evidence.values())
    req2.previous_facets = first.facets
    req2.answer, req2.answer_source_id = '불균형 때문에 F1과 PR-AUC로 평가했습니다.', 'answer'
    fresh = Evidence(evidence_id='metrics', experience_id='project', fact_type='verification',
        normalized_fact=req2.answer, evidence_quote=req2.answer, source_type='user_answer', source_id='answer', assertion_state='user_asserted')
    second = prepare_review(req2, ExtractionOutput(experience_id='project', extracted_evidence=[fresh],
        facets=[EvidenceFacet(evidence_id='metrics', slots=[S.VALIDATION, S.OBSERVATION])]))
    assert second.profile.validation_method.evidence_ids == ['metrics']
    assert all(q.target_slot != S.VALIDATION for q in second.questions)
    assert second.questions == []  # A diagnostic gap alone no longer asks the user.


def test_unavailable_answer_and_answered_key_prevent_repetition():
    req, output = case(MINIMAL, unavailable=[S.VALIDATION])
    first = prepare_review(req, output)
    assert all(q.target_slot != S.VALIDATION for q in first.questions)
    req.previous_question_keys = [q.dedupe_key for q in first.questions]
    second = prepare_review(req, output)
    assert not {q.dedupe_key for q in first.questions} & {q.dedupe_key for q in second.questions}


def test_slot_profile_is_evidence_ids_only_and_not_another_fact_store():
    prepared = questions(sufficient_rows())
    for slot in S:
        assert set(type(getattr(prepared.profile, slot)).model_fields) == {'evidence_ids'}
        assert set(getattr(prepared.profile, slot).evidence_ids) <= set(active_facts(prepared.evidence))


def test_quality_semantic_report_is_not_mixed_with_fact_failure():
    from app.resume_review_v2.models import ValidationIssue
    req, output = case(sufficient_rows())
    prepared = prepare_review(req, output)
    writer = WriterOutput(experience_id='project', operation='replace_field', original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='Haversine으로 조회했습니다.', evidence_ids=list(dict.fromkeys(
            prepared.analysis.plan.core_evidence_ids + ['ev-2'])))])
    verdict = FactVerification(quality_issues=[ValidationIssue(code='core_reasoning_loss', detail='검증과 데이터 구조화가 사라짐')])
    validation = validate_candidate(req, writer, prepared.analysis.plan, prepared.evidence, verdict)
    assert not validation.factual_issues
    assert 'core_reasoning_loss' in {i.code for i in validation.quality_issues}


def test_declared_same_experience_source_is_quote_checked():
    req, output = case(MINIMAL)
    req.resume_sources = [SourceDocument(source_id='project:techStack', text='Python, XGBoost')]
    output.extracted_evidence[1].source_id = 'project:techStack'
    output.extracted_evidence[1].evidence_quote = 'Python, XGBoost'
    assert prepare_review(req, output).profile.technologies.evidence_ids == ['ev-1']
    output.extracted_evidence[1].evidence_quote = 'PostgreSQL'
    with pytest.raises(ContractError, match='quote absent'): prepare_review(req, output)


def test_team_comparison_context_is_not_an_applicant_action_premise():
    team = ('context', '팀원이 threshold를 여러 값으로 비교함', [S.OVERVIEW])
    prepared = questions([MINIMAL[1], team])
    assert all('threshold' not in q.question for q in prepared.questions)


def test_technology_facet_cannot_invent_role_or_action():
    req, output = case(MINIMAL)
    output.facets[-1].slots = [S.TECHNOLOGIES, S.ACTIONS]
    with pytest.raises(ContractError, match='technology names'): prepare_review(req, output)


def test_qualitative_outcome_is_sufficient_without_kpi():
    rows = sufficient_rows()
    rows[-1] = ('result', '정상 조회 흐름을 완성했습니다.', [S.OUTCOME])
    prepared = questions(rows)
    assert prepared.questions == []


def test_keyword_only_reasoning_cannot_bypass_procedure_candidate():
    from app.resume_review_v2.writing_policy import quality_candidates
    req, output = case(sufficient_rows())
    facts = {e.evidence_id: e for e in output.extracted_evidence}
    writer = WriterOutput(experience_id='project', operation='replace_field', original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='원인이라는 말을 쓰고 먼저 읽은 뒤 이후 저장했으며 마지막으로 조회했습니다.', evidence_ids=['ev-2'])])
    assert 'procedure_overload' in {i.code for i in quality_candidates(req.experience, writer, facts)}


def test_correction_recomputes_profile_without_superseded_original():
    req, output = case([('action', '모델 학습을 직접 구현했습니다.', [S.ACTIONS, S.ROLE])])
    req.answer = '모델 학습은 팀원이 했고 저는 API 연동을 담당했습니다.'
    req.answer_source_id = 'answer'
    correction = Evidence(evidence_id='corrected', experience_id='project', fact_type='implementation',
        normalized_fact='API 연동 담당', evidence_quote=req.answer, source_type='user_answer',
        source_id='answer', assertion_state='user_asserted', supersedes_evidence_ids=['ev-0'])
    output.extracted_evidence.append(correction)
    output.facets.append(EvidenceFacet(evidence_id='corrected', slots=[S.ROLE, S.ACTIONS]))
    prepared = prepare_review(req, output)
    assert prepared.evidence['ev-0'].assertion_state == 'superseded'
    assert prepared.profile.actions.evidence_ids == ['corrected']
    assert 'ev-0' not in prepared.analysis.plan.core_evidence_ids
    assert 'corrected' in prepared.analysis.plan.core_evidence_ids


def test_unresolved_conflict_excluded_without_superseding_original():
    req, output = case([('action', '모델 학습을 직접 구현했습니다.', [S.ACTIONS, S.ROLE])])
    req.answer = '아마 팀원이 했던 것 같아요.'
    req.answer_source_id = 'answer'
    doubt = Evidence(evidence_id='doubt', experience_id='project', fact_type='role',
        normalized_fact='모델 학습 담당이 불확실함', evidence_quote=req.answer,
        source_type='user_answer', source_id='answer', assertion_state='uncertain',
        conflicts_with_evidence_ids=['ev-0'])
    output.extracted_evidence.append(doubt)
    prepared = prepare_review(req, output)
    assert prepared.evidence['ev-0'].assertion_state == 'resume_stated'
    assert prepared.profile.actions.evidence_ids == []
    assert prepared.analysis.plan.operation == 'no_change'
