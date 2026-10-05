"""Writing-policy regression examples, not live-generated LLM results."""
import pytest
from app.resume_review_v2.models import (Experience, Evidence, ReviewInput, RevisionPlan,
    WriterOutput, RevisionSentence, FactVerification, JobRequirement, FactType)
from app.resume_review_v2.validation import validate_candidate
from app.resume_review_v2.writing_policy import target_section, quality_candidates
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.policy import PROJECT_POLICY


def setup(facts):
    text = ' '.join(facts.values())
    experience = Experience(experience_id='exp', kind='project', title='프로젝트',
        current_text=text, field_path='projects[0].description', content_hash='hash')
    evidence = {key: Evidence(evidence_id=key, experience_id='exp', fact_type=kind,
        normalized_fact=quote, evidence_quote=quote, source_type='resume_text',
        source_id='exp', assertion_state='resume_stated')
        for key, (kind, quote) in {k: ('implementation', v) for k, v in facts.items()}.items()}
    return ReviewInput(experience=experience), evidence


def output(request, sentences):
    return WriterOutput(experience_id='exp', operation='replace_field',
        original_quote=request.experience.current_text,
        sentences=[RevisionSentence(text=text, evidence_ids=ids) for text, ids in sentences])


def test_vehicle_related_facts_merge_and_optional_filters_can_be_omitted():
    req, ev = setup({'location': '사용자 위치', 'coords': '정비소 위경도',
        'distance': '거리순 조회', 'h': 'Haversine 거리 계산', 'brand': '브랜드 공식센터 필터',
        'type': '정비소 유형 필터', 'hours': '운영시간 기반 영업 여부 표시',
        'csv': 'CSV 데이터', 'mysql': 'MySQL 연계를 고려한 브랜드·정비 유형 구조로 정리'})
    plan = RevisionPlan(objective='핵심 기능과 데이터 구조', operation='replace_field',
        core_evidence_ids=['h', 'mysql'], supporting_evidence_ids=['brand', 'type'],
        preserved_evidence_ids=['location', 'coords', 'distance', 'hours', 'csv'])
    sentences = [
        ('사용자 위치와 정비소 위경도를 기반으로 Haversine 거리를 계산해 가까운 정비소를 거리순으로 조회하는 서비스를 구현했습니다.',
         ['location', 'coords', 'distance', 'h']),
        ('브랜드 공식센터·정비소 유형 필터와 운영시간 기반 영업 여부 표시 기능을 추가했으며, CSV 데이터를 MySQL 연계를 고려한 브랜드·정비 유형 구조로 정리했습니다.',
         ['brand', 'type', 'hours', 'csv', 'mysql'])]
    assert validate_candidate(req, output(req, sentences), plan, ev, FactVerification()).status == 'READY'
    compact = [sentences[0], ('운영시간 기반 영업 여부를 표시하고 CSV 데이터를 MySQL 연계를 고려한 브랜드·정비 유형 구조로 정리했습니다.',
                              ['hours', 'csv', 'mysql'])]
    result = validate_candidate(req, output(req, compact), plan, ev, FactVerification())
    assert result.status == 'READY'  # unused supporting IDs are not missing facts


def model_case():
    req, ev = setup({'models': 'Logistic Regression, Random Forest, XGBoost, LightGBM, CatBoost, SVM 분류 모델 비교',
        'metrics': 'ROC-AUC 지표 비교', 'result': 'threshold 조정으로 Recall 40% 개선'})
    ev['models'].fact_type = FactType.TECHNOLOGY
    ev['result'].fact_type = FactType.RESULT
    plan = RevisionPlan(objective='모델 비교와 확인된 결과', operation='replace_field',
        core_evidence_ids=['models', 'result'], supporting_evidence_ids=['metrics'])
    draft = output(req, [('Logistic Regression, Random Forest, XGBoost 등 분류 모델의 ROC-AUC를 비교했습니다.', ['models', 'metrics']),
        ('threshold를 조정해 Recall을 40% 개선했습니다.', ['result'])])
    return req, ev, plan, draft


def test_kkbox_representative_models_metrics_and_threshold_remain():
    req, ev, plan, draft = model_case()
    assert validate_candidate(req, draft, plan, ev, FactVerification()).status == 'READY'


def test_abstract_model_summary_loses_critical_signal():
    req, ev, plan, draft = model_case()
    draft.sentences[0].text = '여러 모델의 ROC-AUC를 비교했습니다.'
    result = validate_candidate(req, draft, plan, ev)
    assert 'critical_technical_signal_loss' in {i.code for i in result.quality_issues}


def test_job_critical_model_cannot_be_compressed_away():
    req, ev, plan, draft = model_case()
    req.job_requirements = [JobRequirement(requirement_id='j1', text='LightGBM 경험', posting_quote='LightGBM 경험 우대')]
    result = validate_candidate(req, draft, plan, ev)
    assert 'critical_technical_signal_loss' in {i.code for i in result.quality_issues}


def test_compression_still_blocks_unsupported_numbers_and_technology():
    req, ev, plan, draft = model_case()
    draft.sentences[1].text = 'Redis를 적용해 Recall을 99% 개선했습니다.'
    result = validate_candidate(req, draft, plan, ev)
    assert {'unsupported_number', 'unsupported_technology'} <= {i.code for i in result.factual_issues}


@pytest.mark.parametrize('path,kind,expected', [
    ('projects[1].description', 'other', 'project'), ('experience[0].description', 'other', 'career'),
    ('selfIntroduction.motivation.body', 'project', 'motivation'),
    ('trainingExperience[0].description', 'activity', 'education')])
def test_section_is_explicit_from_apply_locator(path, kind, expected):
    req, _, _, _ = model_case()
    req.experience.field_path, req.experience.kind = path, kind
    assert target_section(req.experience) == expected


@pytest.mark.parametrize('text,code', [
    ('사용자 위치를 기준으로 정비소의 거리를 계산하는 기능을 구현했습니다. 사용자 위치를 기준으로 정비소의 거리를 계산하는 기능을 구현했습니다.', 'semantic_redundancy'),
    ('다양한 경험과 여러 기술, 전반적인 관련 작업으로 역량을 강화했습니다.', 'low_information_density'),
    ('Python, Django, Redis, Docker, AWS, PostgreSQL을 사용했습니다.', 'excessive_enumeration'),
    ('데이터를 확인했습니다. 조건을 판단했습니다. 파일을 검토했습니다.', 'report_like_prose'),
    ('향후 분석 시스템을 구현할 계획입니다.', 'section_mismatch'),
    ('먼저 파일을 읽은 뒤 처리하고 이후 저장했으며 마지막으로 조회했습니다.', 'unnecessary_chronology'),
    ('먼저 파일을 읽고 필요 없는 부분을 제거한 뒤 불필요한 내용을 정리하고 이후 다시 저장했습니다.', 'low_value_detail_retention')])
def test_quality_candidates_are_rewrite_reasons(text, code):
    req, ev, plan, _ = model_case()
    draft = output(req, [(text, ['models'])])
    assert code in {i.code for i in quality_candidates(req.experience, draft)}
    assert validate_candidate(req, draft, plan, ev).status == 'REWRITE'


def test_self_intro_does_not_receive_project_sentence_budget():
    req, _, _, _ = model_case()
    req.experience.field_path = 'selfIntroduction.intro.body'
    draft = output(req, [('분석의 배경입니다. 역할을 설명합니다. 문제를 다룹니다. 경험을 연결합니다.', ['models'])])
    assert 'section_mismatch' not in {i.code for i in quality_candidates(req.experience, draft)}


def test_writer_payload_keeps_raw_answer_out_and_verifier_has_protected_ids():
    req, ev, plan, draft = model_case()
    req.answer, req.answer_source_id = '대화체 답변이에요', 'answer'
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    captured = []
    client._call = lambda prompt, payload, schema: captured.append(payload)
    client.write(req, plan, list(ev.values()))
    assert captured[-1]['target_section'] == 'project'
    assert captured[-1]['section_writing_rules'] == PROJECT_POLICY
    assert 'user_answer' not in captured[-1]
    client.verify(req, draft, list(ev.values()), ['models'], [], ['result'])
    assert captured[-1]['preserved_evidence_ids'] == ['result']
    assert captured[-1]['core_evidence_ids'] == ['models']
