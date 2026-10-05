"""B-1/B-2/B-3 acceptance through real source/plan/Writer/validator/rewrite code.

All model transport is scripted. These tests do not establish live prose quality.
"""
import pytest
from app.resume_review_v2.models import (Experience, ReviewInput, Evidence, ExtractionOutput,
    ApplicantIntentClaim, SemanticUnit, SourceRef, WriterDraft, RevisionSentence,
    FactVerification, Usage, ClaimType)
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.engine import ReviewEngineV2
from app.resume_review_v2.validation import validate_candidate, ContractError
from app.resume_review_v2.project_planning import prepare_review


def intent(cid, quote, typ, identity):
    return ApplicantIntentClaim(id=cid, source_section_id=identity, intent_type=typ,
        text=quote, source_type='resume_text', source_id=identity, evidence_quote=quote,
        state='resume_stated')


def unit(uid, role, meaning, typ, cid):
    return SemanticUnit(id=uid, semantic_role=role, meaning=meaning,
        source_refs=[SourceRef(type=typ, id=cid)])


def golden_case(name):
    identity = 'selfIntroduction.aspiration' if name == 'B-1' else 'selfIntroduction.motivation' if name == 'B-2' else 'projects:garage'
    facts, intents, units = [], [], []
    if name == 'B-1':
        rows = [
            ('early', '입사 초기 회사 데이터 구조와 서비스 흐름을 빠르게 이해하고 싶습니다.', 'short_term_plan', 'early_adaptation'),
            ('work', '기존 분석과 지표가 의사결정에 어떻게 사용되는지 파악하고 싶습니다.', 'learning_plan', 'work_understanding'),
            ('contribution', 'Python과 SQL로 실무에 기여하고 싶습니다.', 'contribution_plan', 'short_term_contribution'),
            ('automation', '반복 분석과 데이터 확인을 자동화하고 싶습니다.', 'improvement_goal', 'improvement_plan'),
            ('growth', '장기적으로 분석을 서비스 개선과 의사결정에 연결하는 분석가로 성장하고 싶습니다.', 'long_term_goal', 'long_term_direction'),
        ]
        for cid, quote, typ, role in rows:
            intents.append(intent(cid, quote, typ, identity))
            units.append(unit(cid, role, quote, 'applicant_intent', cid))
        text = ' '.join(r[1] for r in rows)
        valid = [
            RevisionSentence(text='입사 초기 회사의 데이터 구조와 서비스 흐름, 기존 분석·지표의 의사결정 활용 방식을 이해하고 싶습니다.',
                intent_ids=['early', 'work'], semantic_unit_ids=['early', 'work'], claim_types=['future_plan']),
            RevisionSentence(text='Python과 SQL로 실무에 기여하며 반복 분석과 데이터 확인을 자동화하고 싶습니다.',
                intent_ids=['contribution', 'automation'], semantic_unit_ids=['contribution', 'automation'], claim_types=['future_plan']),
            RevisionSentence(text='장기적으로 분석을 서비스 개선과 의사결정에 연결하는 분석가로 성장하고 싶습니다.',
                intent_ids=['growth'], semantic_unit_ids=['growth'], claim_types=['future_plan']),
        ]
        bad = valid[1:]
    elif name == 'B-2':
        a = '데이터 분석을 실제 의사결정과 서비스 개선에 연결하고 싶어 지원했습니다.'
        b = '통계와 ML을 학습하며 이러한 관점을 형성했습니다.'
        c = 'KKBOX, 정비소 검색, AI LMS 프로젝트를 경험했습니다.'
        d = '앞으로 실제 데이터에서 문제를 발견해 서비스와 의사결정에 연결하고 싶습니다.'
        text = ' '.join([a, b, c, d])
        intents = [intent('reason', a, 'motivation', identity), intent('direction', d, 'contribution_plan', identity)]
        for cid, quote in [('origin', b), ('projects', c)]:
            facts.append(Evidence(evidence_id=cid, experience_id=identity, fact_type='context',
                normalized_fact=quote, evidence_quote=quote, source_type='resume_text', source_id=identity, assertion_state='resume_stated'))
        units = [unit('reason', 'motivation', a, 'applicant_intent', 'reason'),
                 unit('origin', 'motivation_origin', b, 'applicant_evidence', 'origin'),
                 unit('projects', 'supporting_experience', c, 'applicant_evidence', 'projects'),
                 unit('direction', 'intended_contribution', d, 'applicant_intent', 'direction')]
        valid = [
            RevisionSentence(text='분석을 실제 의사결정과 서비스 개선에 활용하는 업무에 관심이 있어 지원했습니다.', intent_ids=['reason'], semantic_unit_ids=['reason'], claim_types=['motivation']),
            RevisionSentence(text='통계·ML 학습에서 형성한 관점을 KKBOX, 정비소 검색, AI LMS 프로젝트 경험으로 뒷받침했습니다.', evidence_ids=['origin', 'projects'], semantic_unit_ids=['origin', 'projects'], claim_types=['learning']),
            RevisionSentence(text='실제 데이터의 문제를 찾아 서비스 개선과 의사결정으로 이어가는 분석을 하고 싶습니다.', intent_ids=['direction'], semantic_unit_ids=['direction'], claim_types=['future_plan']),
        ]
        bad = [valid[1]]
    else:
        rows = [('python', 'technology', 'Python 사용'), ('pandas', 'technology', 'Pandas 사용'),
                ('streamlit', 'technology', 'Streamlit 사용'), ('distance', 'implementation', 'Haversine 거리 계산 구현'),
                ('filter', 'implementation', '정비소 필터 구현'), ('test', 'verification', '주요 기능 직접 테스트')]
        text = '. '.join(r[2] for r in rows)
        for cid, typ, quote in rows:
            facts.append(Evidence(evidence_id=cid, experience_id=identity, fact_type=typ,
                normalized_fact=quote, evidence_quote=quote, source_type='resume_text', source_id=identity, assertion_state='resume_stated'))
        valid = [RevisionSentence(text='Python·Pandas를 활용하고 Haversine 거리 계산과 정비소 필터를 구현했습니다.',
            evidence_ids=['python', 'pandas', 'distance', 'filter'], claim_types=['technology_used', 'action_performed']),
            RevisionSentence(text='주요 기능을 직접 테스트했습니다.', evidence_ids=['test'], claim_types=['validation_performed'])]
        bad = [RevisionSentence(text='Python·Pandas 기반 데이터 처리와 Streamlit 서비스 구현을 맡아 Haversine과 필터를 구현했습니다.',
            evidence_ids=[f.evidence_id for f in facts], claim_types=['role_owned'])]
    path = 'projects[0].description' if name == 'B-3' else identity + '.body'
    req = ReviewInput(experience=Experience(experience_id=identity, kind='project' if name == 'B-3' else 'other',
        title=name, current_text=text, field_path=path, content_hash='hash'))
    extraction = ExtractionOutput(experience_id=identity, extracted_evidence=facts, intent_claims=intents, semantic_units=units)
    return req, extraction, valid, bad


class ScriptedTransport(LangChainReviewLLM):
    def __init__(self, case, first_bad=True):
        self.request, self.extraction, self.valid, self.bad = golden_case(case)
        self.case, self.first_bad, self.writes, self.calls = case, first_bad, 0, []

    def _call(self, system, payload, schema):
        self.calls.append((schema.__name__, payload))
        if schema is ExtractionOutput:
            result = self.extraction
        elif schema is WriterDraft:
            self.writes += 1
            result = WriterDraft(experience_id=self.request.experience.experience_id,
                sentences=self.bad if self.first_bad and self.writes == 1 else self.valid)
        else:
            # Scripted semantic verdicts, not a substitute for testing a real model.
            text = payload['suggested_text']
            missing = []
            if self.case == 'B-1' and '입사 초기' not in text: missing = ['early_adaptation', 'work_understanding']
            if self.case == 'B-2' and '지원' not in text: missing = ['motivation', 'intended_contribution']
            result = FactVerification(section_meaning_loss=missing)
        return result, Usage(calls=1)


@pytest.mark.parametrize('name', ['B-1', 'B-2', 'B-3'])
def test_golden_pipeline_sources_plan_input_validator_and_rewrite(name):
    transport = ScriptedTransport(name)
    result = ReviewEngineV2(transport).run(transport.request)
    assert result.validation.status == 'READY', result.validation.model_dump()
    assert transport.writes == 2
    writes = [p for schema, p in transport.calls if schema == 'WriterDraft']
    assert writes[1]['validation_issues_to_fix']
    assert 'current_text' not in writes[0]['experience']
    assert 'original_experience_text' not in writes[0]
    assert writes[0]['editorial_brief']['must_express']
    assert writes[0]['editorial_brief']['section'] == {'B-1': 'future_plan', 'B-2': 'motivation', 'B-3': 'project'}[name]
    assert result.debug_trace['sentence_plan'] == result.sentence_plan.model_dump(mode='json')
    if name != 'B-3':
        assert result.project_profile is None
        assert result.intent_claims
        assert {u.id for u in result.section_profile.original_semantic_units} >= set(result.section_profile.required_semantics)
        assert any(i['code'] == 'SECTION_MEANING_LOSS' for i in writes[1]['validation_issues_to_fix'])
        assert '입사 초기' in result.candidate.suggested_text if name == 'B-1' else '지원' in result.candidate.suggested_text
    else:
        assert result.project_profile is not None
        assert result.intent_claims == []
        assert any(i['code'] == 'unsupported_agency' for i in writes[1]['validation_issues_to_fix'])
        assert '맡아' not in result.candidate.suggested_text


@pytest.mark.parametrize('name', ['B-1', 'B-2'])
def test_golden_loss_detected_even_when_writer_falsely_cites_all_units(name):
    transport = ScriptedTransport(name)
    transport.bad[0].semantic_unit_ids = [u.id for u in transport.extraction.semantic_units]
    # Proper source IDs can be cited without actually expressing those meanings.
    transport.bad[0].intent_ids = [c.id for c in transport.extraction.intent_claims]
    transport.bad[0].evidence_ids = [f.evidence_id for f in transport.extraction.extracted_evidence]
    result = ReviewEngineV2(transport).run(transport.request)
    assert result.validation.status == 'READY'
    writes = [p for schema, p in transport.calls if schema == 'WriterDraft']
    assert any(i['code'] == 'SECTION_MEANING_LOSS' for i in writes[1]['validation_issues_to_fix'])


def test_golden_unsupported_intent_and_target_contamination_blocked():
    req, extraction, valid, _ = golden_case('B-1')
    prepared = prepare_review(req, extraction)
    from app.resume_review_v2.models import WriterOutput, JobRequirement
    writer = WriterOutput(experience_id=req.experience.experience_id, original_quote=req.experience.current_text,
        operation='replace_field', sentences=[RevisionSentence(text='보험 산업 혁신을 주도하고 싶습니다.', target_context_ids=['job'])])
    prepared.request.job_requirements = [JobRequirement(requirement_id='job', text='보험 혁신', posting_quote='보험 분석 우대')]
    verdict = validate_candidate(prepared.request, writer, prepared.analysis.plan, prepared.evidence)
    assert verdict.status == 'REWRITE'
    assert verdict.intent_issues
    assert any(i.code == 'unsupported_agency' for i in verdict.factual_issues)
    # Even a real intent ID does not support a novel goal: semantic verifier flags it.
    writer.sentences[0].intent_ids = ['early']
    verdict = validate_candidate(prepared.request, writer, prepared.analysis.plan, prepared.evidence,
        FactVerification(unsupported_intents=['보험 산업 혁신은 사용자 의도가 아님']))
    assert verdict.intent_issues


def test_golden_intent_quote_and_cross_section_source_validation():
    req, extraction, _, _ = golden_case('B-1')
    extraction.intent_claims[0].evidence_quote = '없는 포부'
    with pytest.raises(ContractError, match='intent quote'): prepare_review(req, extraction)
    req, extraction, _, _ = golden_case('B-1')
    extraction.intent_claims[0].source_section_id = 'selfIntroduction.motivation'
    with pytest.raises(ContractError, match='cross-section'): prepare_review(req, extraction)


@pytest.mark.parametrize('verb', ['맡았습니다', '담당했습니다', '주도했습니다', '리드했습니다', '책임졌습니다', '총괄했습니다', '설계했습니다'])
def test_b3_agency_verbs_do_not_follow_from_technology_or_generic_action(verb):
    req, extraction, _, _ = golden_case('B-3')
    prepared = prepare_review(req, extraction)
    from app.resume_review_v2.models import WriterOutput
    writer = WriterOutput(experience_id=req.experience.experience_id, operation='replace_field',
        original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='Python 데이터 처리를 ' + verb, evidence_ids=['python', 'pandas'])])
    result = validate_candidate(prepared.request, writer, prepared.analysis.plan, prepared.evidence)
    assert any(i.code == 'unsupported_agency' for i in result.factual_issues)


def test_no_past_fact_created_from_future_intent():
    req, extraction, _, _ = golden_case('B-1')
    extraction.extracted_evidence = [Evidence(evidence_id='fabricated-past', experience_id=req.experience.experience_id,
        fact_type='action', normalized_fact='Python으로 실무 기여', evidence_quote=extraction.intent_claims[2].evidence_quote,
        source_type='resume_text', source_id=req.experience.experience_id, assertion_state='resume_stated')]
    with pytest.raises(ContractError, match='intent cannot be'): prepare_review(req, extraction)


def test_uncertain_intent_is_not_approved_or_protected():
    req, extraction, _, _ = golden_case('B-1')
    extraction.intent_claims[0].state = 'uncertain'
    extraction.semantic_units = [u for u in extraction.semantic_units if u.id != 'early']
    prepared = prepare_review(req, extraction)
    assert 'early' not in prepared.section_profile.intent_claim_ids
    assert 'early' not in prepared.section_profile.required_semantics


def test_rewrite_cannot_silently_accept_a_second_section_loss():
    transport = ScriptedTransport('B-1')
    transport.valid = transport.bad
    result = ReviewEngineV2(transport).run(transport.request)
    assert transport.writes == 2
    assert result.validation.status == 'REJECTED'
    assert result.validation.section_issues
    assert len(result.debug_trace['attempts']) == 2


def test_technical_inventory_is_not_mandatory_motivation_content():
    req, extraction, _, _ = golden_case('B-2')
    quote = 'Streamlit 사용'
    req.experience.current_text += ' ' + quote
    extraction.extracted_evidence.append(Evidence(evidence_id='optional-tool',
        experience_id=req.experience.experience_id, fact_type='technology',
        normalized_fact=quote, evidence_quote=quote, source_type='resume_text',
        source_id=req.experience.experience_id, assertion_state='resume_stated'))
    prepared = prepare_review(req, extraction)
    assert 'fact:optional-tool' in prepared.section_profile.optional_semantics
    assert 'fact:optional-tool' not in prepared.section_profile.required_semantics


def test_future_plan_does_not_inherit_project_generic_technical_density_gate():
    from app.resume_review_v2.writing_policy import quality_candidates
    from app.resume_review_v2.models import WriterOutput
    req, _, _, _ = golden_case('B-1')
    writer = WriterOutput(experience_id=req.experience.experience_id, operation='replace_field',
        original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text='다양한 경험을 배우며 역량을 강화하고 싶습니다.', intent_ids=['early'])])
    assert 'low_information_density' not in {i.code for i in quality_candidates(req.experience, writer)}
