"""Actual B mounted HTTP path, domain engine and follow-up, all I/O mocked."""
import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi.testclient import TestClient
from app import main, resume_apply
from app.local_resume_site_adapter import LocalReviewService
from app.resume_review_v2.batch import BatchReviewEngine
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import (Evidence, EvidenceFacet, ExtractionOutput,
    WriterOutput, WriterDraft, RevisionSentence, FactVerification, Usage, QuestionNeed)


@pytest.fixture
def pipeline(monkeypatch):
    monkeypatch.setenv('DB_HOST', '127.0.0.1')
    monkeypatch.setenv('RESUME_REVIEW_ENGINE', 'v2-local')
    content = {'projects': [{'id': 'p1', 'name': '서비스', 'techStack': ['Python', 'FastAPI'],
                            'description': 'API를 구현했습니다.'}]}
    db = Mock()
    db.get_owned_resume.return_value = {'content': content}
    db.claim_review.return_value = {}
    reviews = {}
    db.get_ai_review.side_effect = lambda cohort, resume, uid, rid, tail=None: reviews.get(rid, {})
    db.complete_review.side_effect = lambda cohort, resume, uid, rid, data, tail=None: reviews.update({rid: data})
    calls = []
    import langchain_openai
    monkeypatch.setattr(langchain_openai, 'ChatOpenAI', lambda **kw: object())
    def invoke(self, system, payload, schema):
        stage = schema.__name__
        calls.append((stage, system, payload))
        items = payload.get('items', payload)
        rows = {}
        for key, item in items.items():
            if stage == 'BatchExtractionOutput':
                exp = item['experience']
                if exp['existing_evidence']:
                    facts = []
                    facets = []
                else:
                    facts = [Evidence(evidence_id='action', experience_id=exp['experience_id'],
                        fact_type='implementation', normalized_fact='API 구현', evidence_quote=exp['current_text'],
                        source_type='resume_text', source_id=exp['experience_id'], assertion_state='resume_stated')]
                    facets = [EvidenceFacet(evidence_id='action', slots=['actions', 'personal_role'])]
                if item['user_answer'] and '정상 조회' in item['user_answer']:
                    facts.append(Evidence(evidence_id='check', experience_id=exp['experience_id'],
                        fact_type='verification', normalized_fact=item['user_answer'], evidence_quote=item['user_answer'],
                        source_type='user_answer', source_id=item['answer_source_id'], assertion_state='user_asserted'))
                    facets.append(EvidenceFacet(evidence_id='check', slots=['validation_method']))
                question = None if item['user_answer'] else QuestionNeed(
                    experience_id=exp['experience_id'],
                    target_slot='validation_method', gap_type='missing', priority='HIGH',
                    why_needed='구현은 확인됐지만 확인 방법이 없어 동작을 점검한 근거를 구체화합니다.',
                    dedupe_key='validation-evidence')
                rows[key] = ExtractionOutput(experience_id=exp['experience_id'], extracted_evidence=facts, facets=facets,
                                             question=question)
            elif stage == 'BatchWriterDraft':
                ids = {e['evidence_id'] for e in item['approved_evidence']}
                sentences = [RevisionSentence(text='API를 구현했습니다.', evidence_ids=['action'])]
                if 'check' in ids:
                    sentences.append(RevisionSentence(text='정상 조회 결과를 대조했습니다.', evidence_ids=['check']))
                rows[key] = WriterDraft(experience_id=item['experience']['experience_id'], sentences=sentences)
            else:
                rows[key] = FactVerification()
        return schema.model_validate(rows), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    settings = SimpleNamespace(openai_model='fake', openai_reasoning_effort='medium')
    service = lambda: LocalReviewService(settings, db, BatchReviewEngine('fake', 'medium'))
    original_factory = main.build_resume_review_service
    original_overrides = main.app.dependency_overrides.copy()
    original_apply = resume_apply.gateway_dependency
    # Import the same app launched by local_resume_site.py ai, not a new test router.
    from app.local_resume_site import app as b_app
    monkeypatch.setattr(main, 'build_resume_review_service', service)
    try:
        yield TestClient(b_app), reviews, calls, db
    finally:
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides.update(original_overrides)
        main.build_resume_review_service = original_factory
        resume_apply.gateway_dependency = original_apply


def post(client, rid, **extra):
    response = client.post('/resume-review/api/v1/resumes/reviews/proxy', json={
        'uid': 'student', 'cohort_id': 'local', 'resume_id': '1',
        'review_mode': 'general', 'request_id': rid, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def test_actual_b_route_selects_one_value_assessed_question_per_experience(pipeline):
    client, reviews, calls, db = pipeline
    result = post(client, 'first')
    assert result['sentence_reviews'][0]['suggested_revision'] is None
    assert result['sentence_reviews'][0]['status'] == 'unchanged'
    record = result['telemetry']['v2_results'][0]
    assert record['project_profile']['actions']['evidence_ids'] == ['action']
    assert len(record['gap_questions']) == len(result['questions']) == 1
    assert len({q['question_id'] for q in result['questions']}) == 1
    assert all(':v2gap:' in q['question_id'] for q in result['questions'])
    assert [s for s, _, _ in calls] == ['BatchExtractionOutput', 'BatchWriterDraft', 'BatchFactVerification']
    extractor_payload = calls[0][2]['item_0']
    assert 'job_requirements' not in extractor_payload
    assert extractor_payload['experience']['title'] == '서비스'
    assert extractor_payload['resume_sources'][-1]['text'] == 'Python, FastAPI'
    writer_payload = calls[1][2]['items']['item_0']
    assert 'user_answer' not in writer_payload
    assert writer_payload['editorial_brief']['section'] == 'project'
    assert writer_payload['editorial_brief']['must_express']
    assert 'current_text' not in writer_payload['experience']
    db.complete_review.assert_called_once()  # mock only, not a DB write


def test_followup_reuses_facts_and_stops_questions_when_contribution_is_sufficient(pipeline):
    client, reviews, calls, db = pipeline
    first = post(client, 'first')
    check_question = next(q for q in first['questions'] if q['target_slot']=='validation_method')
    second = post(client, 'second', previous_review_id='first', answers=[{
        'question_id': check_question['question_id'], 'field_path': check_question['field_path'],
        'question': check_question['question'], 'answer': '정상 조회 결과를 대조했습니다.'}])
    record = second['telemetry']['v2_results'][0]
    assert record['project_profile']['validation_method']['evidence_ids'] == ['check']
    assert {e['evidence_id'] for e in record['evidence_state']} == {'action', 'check'}
    assert check_question['question'] not in [q['question'] for q in second['questions']]
    assert second['questions'] == []  # Remaining slots are not compulsory.
    writer_calls = [payload for stage, _, payload in calls if stage == 'BatchWriterDraft']
    assert all('user_answer' not in item and 'question' not in item
               for payload in writer_calls for item in payload.get('items', payload).values())


@pytest.mark.parametrize('answer,blocked', [('모르겠습니다',False),('없습니다',True)])
def test_no_information_answer_scope_without_fabricating_evidence(pipeline,answer,blocked):
    client, reviews, calls, db = pipeline
    first = post(client, 'first')
    q = next(q for q in first['questions'] if q['target_slot']=='validation_method')
    second = post(client, 'second', previous_review_id='first', answers=[{
        'question_id': q['question_id'], 'field_path': q['field_path'], 'question': q['question'], 'answer': answer}])
    record = second['telemetry']['v2_results'][0]
    assert ('validation_method' in record['unavailable_slots']) == blocked
    assert q['question'] in [a['question'] for a in second['confirmed_answers']]
    assert {e['evidence_id'] for e in record['evidence_state']} == {'action'}
    assert all('정량 수치' not in q['question'] for q in second['questions'])


@pytest.mark.parametrize('same_need',[True,False])
def test_unknown_answer_closes_issued_need_not_every_question_in_same_facet(pipeline,monkeypatch,same_need):
    client,reviews,calls,db=pipeline
    first=post(client,'first');q=first['questions'][0]
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':
            result.item_0.question=QuestionNeed(experience_id=result.item_0.experience_id,
                request_aspect=None if same_need else 'verification_result_and_limits',
                target_slot='validation_method',gap_type='missing',priority='HIGH',
                why_needed='확인된 구현 외에 비교 입력 범위를 알면 시험 범위를 구체화할 수 있습니다.',
                dedupe_key='validation-evidence' if same_need else 'validation-input-scope')
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    second=post(client,'unknown',previous_review_id='first',answers=[{
        'question_id':q['question_id'],'field_path':q['field_path'],'question':q['question'],'answer':'모르겠습니다'}])
    record=second['telemetry']['v2_results'][0];diagnostic=record['debug_trace']['question_selection']
    assert diagnostic['state']==('server_filtered' if same_need else 'selected')
    assert diagnostic['reason']==('exact_repeat' if same_need else None)
    assert bool(second['questions']) is not same_need
    assert 'validation_method' not in record['unavailable_slots']
    analysis=[p for stage,_,p in calls if stage=='BatchExtractionOutput'][-1]['item_0']
    assert analysis['user_answer']=='모르겠습니다' and any(q['question'] in item for item in analysis['question_history'])
    assert record['debug_trace']['semantic_preparation']


def test_gap_audit_does_not_reextract_old_raw_answers(pipeline):
    client, reviews, calls, db = pipeline
    post(client, 'first')
    post(client, 'audit', previous_review_id='first', review_phase='gap_audit')
    extraction_inputs = [p['item_0'] for stage, _, p in calls if stage == 'BatchExtractionOutput']
    assert extraction_inputs[-1]['user_answer'] == ''
    assert len(extraction_inputs) == 1  # Audit reuses the completed analysis/write.


def test_resume_question_cap_and_other_experience_pending_gap_survives(pipeline):
    client, reviews, calls, db = pipeline
    db.get_owned_resume.return_value['content']['projects'].append({
        'id': 'p2', 'name': '두 번째 서비스', 'description': 'API를 구현했습니다.'})
    first = post(client, 'first')
    assert len(first['questions']) <= 3
    assert len(first['telemetry']['v2_results']) == 2
    q = next(q for q in first['questions'] if q['field_path'] == 'projects[0].description' and q['target_slot']=='validation_method')
    second = post(client, 'second', previous_review_id='first', answers=[{
        'question_id': q['question_id'], 'field_path': q['field_path'], 'question': q['question'],
        'answer': '정상 조회 결과를 대조했습니다.'}])
    assert len(second['questions']) <= 3
    assert any(q['field_path'] == 'projects[1].description' for q in second['questions'])


def three_projects(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    db.get_owned_resume.return_value['content']['projects'] = [
        {'id': f'p{i}', 'name': title, 'description': 'API를 구현했습니다.'}
        for i, title in enumerate(['KKBOX 사용자 이탈 예측', '위치 기반 자동차 정비소 검색', 'AI LMS'], 1)]
    original = LangChainReviewLLM._call
    def invoke(self, system, payload, schema):
        result, usage = original(self, system, payload, schema)
        if schema.__name__ == 'BatchExtractionOutput':
            for name in type(result).model_fields:
                extraction = getattr(result, name)
                for facet in extraction.facets:
                    if facet.evidence_id == 'action':
                        facet.slots = EvidenceFacet(evidence_id='action',
                            slots=['actions', 'personal_role', 'overview', 'technical_decisions']).slots
        return result, usage
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    return client, reviews, calls, db


def test_three_project_questions_have_identity_and_answer_isolation(pipeline, monkeypatch):
    client, reviews, calls, db = three_projects(pipeline, monkeypatch)
    first = post(client, 'first')
    qs = first['questions']
    assert len(qs) == 3
    assert {q['experience_id'] for q in qs} == {'projects:p1', 'projects:p2', 'projects:p3'}
    assert len({q['question_id'] for q in qs}) == 3
    assert len({q['question'] for q in qs}) == 1  # identical text, distinct owners
    assert [q['experience_title'] for q in qs] == [p['name'] for p in db.get_owned_resume.return_value['content']['projects']]
    q = next(q for q in qs if q['experience_id'] == 'projects:p1')
    second = post(client, 'second', previous_review_id='first', answers=[{
        'question_id': q['question_id'], 'experience_id': q['experience_id'],
        'field_path': q['field_path'], 'question': q['question'], 'answer': '정상 조회 결과를 대조했습니다.'}])
    records = {r['experience']['experience_id']: r for r in second['telemetry']['v2_results']}
    assert any(e['evidence_id'] == 'check' for e in records['projects:p1']['evidence_state'])
    for identity in ['projects:p2', 'projects:p3']:
        assert all(e['evidence_id'] != 'check' for e in records[identity]['evidence_state'])
    assert second['confirmed_answers'][-1]['experience_id'] == 'projects:p1'
    fresh = [p for stage, _, p in calls if stage == 'BatchExtractionOutput'][-1]
    assert len(fresh) == 1
    assert fresh['item_0']['experience']['experience_id'] == 'projects:p1'


@pytest.mark.parametrize('override', [
    {'field_path': 'projects[1].description'}, {'experience_id': 'projects:p2'},
    {'question_id': 'unknown'},
])
def test_wrong_project_answer_rejected_before_model_or_storage(pipeline, monkeypatch, override):
    client, reviews, calls, db = three_projects(pipeline, monkeypatch)
    q = post(client, 'first')['questions'][0]
    before = len(calls)
    db.claim_review.reset_mock()
    response = client.post('/resume-review/api/v1/resumes/reviews/proxy', json={
        'uid': 'student', 'cohort_id': 'local', 'resume_id': '1', 'review_mode': 'general',
        'request_id': 'bad', 'previous_review_id': 'first', 'answers': [{
            'question_id': q['question_id'], 'experience_id': q['experience_id'],
            'field_path': q['field_path'], 'question': q['question'], 'answer': '정상 조회', **override}]})
    assert response.status_code == 422, response.text
    assert len(calls) == before
    db.claim_review.assert_not_called()


def test_title_is_display_identity_not_question_fact_source(pipeline):
    client, reviews, calls, db = pipeline
    db.get_owned_resume.return_value['content']['projects'][0]['name'] = 'KKBOX 불균형 threshold 개선'
    result = post(client, 'first')
    assert all(q['experience_title'] == 'KKBOX 불균형 threshold 개선' for q in result['questions'])
    assert all('불균형' not in q['question'] and 'threshold' not in q['question'] for q in result['questions'])
