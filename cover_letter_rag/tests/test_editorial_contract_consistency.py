"""New contract regressions. Scripted verdicts do not prove model writing quality."""
import pytest
from app.resume_review_v2.models import (Evidence, Experience, ReviewInput,
    ExtractionOutput, SemanticUnit, SourceRef, RevisionSentence, WriterOutput,
    FactVerification)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.section_semantics import editorial_brief, verification_sources, agency_issues
from app.resume_review_v2.validation import validate_candidate
from app.resume_review_v2.llm import LangChainReviewLLM


def prepared_models(kind):
    quote = 'Logistic Regression, Random Forest, XGBoost, LightGBM, CatBoost 모델을 비교했습니다.'
    request = ReviewInput(experience=Experience(experience_id='exp', kind='project',
        title='모델 비교', field_path='projects[0].description', current_text=quote, content_hash='h'))
    fact = Evidence(evidence_id='models', experience_id='exp', fact_type=kind,
        normalized_fact=quote, evidence_quote=quote, source_type='resume_text',
        source_id='exp', assertion_state='resume_stated')
    extraction = ExtractionOutput(experience_id='exp', extracted_evidence=[fact],
        semantic_units=[SemanticUnit(id='comparison', semantic_role='action',
            meaning='분류 모델 비교', source_refs=[SourceRef(type='applicant_evidence', id='models')])])
    prepared = prepare_review(request, extraction)
    candidate = WriterOutput(experience_id='exp', operation='replace_field', original_quote=quote,
        sentences=[RevisionSentence(text='Logistic Regression과 XGBoost 등 분류 모델을 비교했습니다.',
            evidence_ids=['models'], semantic_unit_ids=['comparison'], claim_types=['action_performed'])])
    return prepared, candidate


@pytest.mark.parametrize('kind', ['implementation', 'verification', 'technology'])
def test_same_quoted_comparison_can_compress_inventory_regardless_of_fact_type(kind):
    p, candidate = prepared_models(kind)
    result = validate_candidate(p.request, candidate, p.analysis.plan, p.evidence, FactVerification())
    assert result.status == 'READY', result.model_dump()
    # Fewer names is allowed; losing the comparison is still not allowed.
    result = validate_candidate(p.request, candidate, p.analysis.plan, p.evidence,
        FactVerification(section_meaning_loss=['모델 비교 방법이 사라짐']))
    assert result.status == 'REWRITE'


def test_live_verifier_and_writer_share_brief_without_parallel_id_obligations():
    p, candidate = prepared_models('implementation')
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    payloads = []
    client._call = lambda system, payload, schema: payloads.append(payload)
    client.write(p.request, p.analysis.plan, list(p.evidence.values()))
    client.verify(p.request, candidate, list(p.evidence.values()), p.analysis.plan.core_evidence_ids, [])
    assert payloads[0]['editorial_brief'] == payloads[1]['editorial_brief'] == editorial_brief(p.request)
    assert 'core_evidence_ids' not in payloads[1]
    assert 'preserved_evidence_ids' not in payloads[1]


def test_multiple_checks_are_available_not_all_core_and_material_meaning_keeps_sources():
    p, _ = prepared_models('implementation')
    request = p.request.model_copy(deep=True)
    request.experience.current_text += ' 주요 기능을 직접 테스트했습니다. 실행 로그를 확인했습니다.'
    facts = list(p.evidence.values())
    for eid, text in [('check', '주요 기능을 직접 테스트했습니다.'), ('log', '실행 로그를 확인했습니다.')]:
        facts.append(Evidence(evidence_id=eid, experience_id='exp', fact_type='verification',
            normalized_fact=text, evidence_quote=text, source_type='resume_text', source_id='exp', assertion_state='resume_stated'))
    p = prepare_review(request, ExtractionOutput(experience_id='exp', extracted_evidence=facts))
    checks = {'check', 'log'}
    assert len(checks & set(p.analysis.plan.core_evidence_ids)) == 1
    optional = (checks - set(p.analysis.plan.core_evidence_ids)).pop()
    assert optional in p.analysis.plan.supporting_evidence_ids
    assert optional not in p.analysis.plan.preserved_evidence_ids
    used = p.analysis.plan.core_evidence_ids
    candidate = WriterOutput(experience_id='exp', operation='replace_field',
        original_quote=request.experience.current_text, sentences=[RevisionSentence(
            text=' '.join(p.evidence[eid].evidence_quote for eid in used), evidence_ids=used)])
    assert validate_candidate(p.request, candidate, p.analysis.plan, p.evidence,
        FactVerification()).status == 'READY'
    # If the Analyst explicitly identifies a high-value relationship, it is
    # protected as meaning, even when its source happens to be supporting.
    profile = p.request.section_profile
    unit = next(u for u in profile.original_semantic_units if u.source_refs[0].id == optional)
    profile.required_semantics.append(unit.id)
    assert optional in {e.evidence_id for e in verification_sources(p.request,
        p.analysis.plan, list(p.evidence.values()), set())}


@pytest.mark.parametrize('kind', ['role', 'action', 'context', 'technology'])
def test_explicit_role_quote_not_fact_label_controls_agency(kind):
    fact = Evidence(evidence_id='role', experience_id='exp', fact_type=kind,
        normalized_fact='API 담당', evidence_quote='API 연동을 담당했습니다.',
        source_type='resume_text', source_id='exp', assertion_state='resume_stated')
    sentence = RevisionSentence(text='API 연동을 담당했습니다.', evidence_ids=['role'], claim_types=['role_owned'])
    assert not agency_issues(sentence, {'role': fact})
    fact.evidence_quote = 'API 연동 기술 사용'
    assert agency_issues(sentence, {'role': fact})


@pytest.mark.parametrize('claim,semantic_error', [
    ('모델 전체 ROC-AUC가 약 0.905였습니다.', '단일 변수 분석 결과를 전체 모델 성능으로 확대'),
    ('MySQL 연동을 구현했습니다.', '향후 연계 고려를 구현 완료로 변경'),
    ('가까운 자동차 정비소를 구현했습니다.', '검색 서비스라는 구현 대상 손실'),
])
def test_supported_terms_do_not_authorize_scope_tense_or_object_changes(claim, semantic_error):
    p, candidate = prepared_models('implementation')
    quote = ('days_to_expire 단일 변수의 directional AUC는 약 0.905였습니다. '
             '향후 MySQL 연계를 고려했습니다. 가까운 정비소를 찾는 서비스를 구현했습니다.')
    # These quotes are from this test only; no earlier threshold/F1 results.
    p.request.experience.current_text = quote
    p.evidence['models'].normalized_fact = quote
    p.evidence['models'].evidence_quote = quote
    candidate.original_quote = quote
    candidate.sentences[0].text = claim
    result = validate_candidate(p.request, candidate, p.analysis.plan, p.evidence,
        FactVerification(unsupported_claims=[semantic_error]))
    assert any(i.code == 'semantic_unsupported_claim' for i in result.factual_issues)
    assert result.status != 'READY'


def test_profile_compression_does_not_disable_number_or_technology_blockers():
    p, candidate = prepared_models('technology')
    candidate.sentences[0].text = 'Redis를 적용해 99% 개선했습니다.'
    result = validate_candidate(p.request, candidate, p.analysis.plan, p.evidence)
    assert {'unsupported_number', 'unsupported_technology'} <= {i.code for i in result.factual_issues}
    p.evidence['models'].evidence_quote = 'days_to_expire 단일 변수의 directional AUC는 약 0.905였습니다.'
    p.evidence['models'].normalized_fact = p.evidence['models'].evidence_quote
    candidate.sentences[0].text = 'directional AUC는 약 0.906였습니다.'
    result = validate_candidate(p.request, candidate, p.analysis.plan, p.evidence)
    assert 'unsupported_number' in {i.code for i in result.factual_issues}
