"""Golden sources travel through the actual mounted B adapter/batch HTTP route."""
from test_project_live_pipeline import pipeline, post
from test_section_golden import golden_case
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import WriterDraft, FactVerification, Usage


def test_b_live_path_keeps_section_sources_and_repairs_all_three_goldens(pipeline, monkeypatch):
    client, reviews, calls, db = pipeline
    cases = {golden_case(name)[0].experience.experience_id: golden_case(name) for name in ['B-1', 'B-2', 'B-3']}
    db.get_owned_resume.return_value['content'] = {
        'projects': [{'id': 'garage', 'name': '자동차 정비소', 'description': cases['projects:garage'][0].experience.current_text}],
        'selfIntroduction': {
            'motivation': {'body': cases['selfIntroduction.motivation'][0].experience.current_text},
            'aspiration': {'body': cases['selfIntroduction.aspiration'][0].experience.current_text},
        },
    }
    writes = {}
    def invoke(self, system, payload, schema):
        calls.append((schema.__name__, system, payload))
        rows = {}
        for key, item in payload.get('items', payload).items():
            if schema.__name__ == 'BatchExtractionOutput':
                identity = item['experience']['experience_id']
                rows[key] = cases[identity][1]
            elif schema.__name__ == 'BatchWriterDraft':
                identity = item['experience']['experience_id']
                writes[identity] = writes.get(identity, 0) + 1
                rows[key] = WriterDraft(experience_id=identity,
                    sentences=cases[identity][3 if writes[identity] == 1 else 2])
                assert 'current_text' not in item['experience']
                assert item['editorial_brief']['section'] == item['target_section']
            else:
                text = item['suggested_text']
                missing = ['early_adaptation'] if item['target_section'] == 'future_plan' and '입사 초기' not in text else (
                    ['motivation'] if item['target_section'] == 'motivation' and '지원' not in text else [])
                rows[key] = FactVerification(section_meaning_loss=missing)
        return schema.model_validate(rows), Usage(calls=1)
    monkeypatch.setattr(LangChainReviewLLM, '_call', invoke)
    result = post(client, 'golden-b')
    records = {r['experience']['experience_id']: r for r in result['telemetry']['v2_results']}
    assert set(records) == set(cases)
    assert all(r['validation']['status'] == 'READY' for r in records.values())
    assert all(count == 2 for count in writes.values())
    assert records['selfIntroduction.aspiration']['project_profile'] is None
    assert records['selfIntroduction.motivation']['project_profile'] is None
    assert records['selfIntroduction.aspiration']['intent_claims']
    assert records['selfIntroduction.motivation']['intent_claims']
    assert records['projects:garage']['intent_claims'] == []
    for record in records.values():
        assert record['debug_trace']['rewrite_reason']
        assert record['debug_trace']['sentence_plan']['items']
    assert '입사 초기' in records['selfIntroduction.aspiration']['candidate']['suggested_text']
    assert '지원' in records['selfIntroduction.motivation']['candidate']['suggested_text']
    assert '맡아' not in records['projects:garage']['candidate']['suggested_text']
    verifications = [p for stage, _, p in calls if stage == 'BatchFactVerification']
    assert all(item['previous_attempt'] is None for item in verifications[0].values())
    for item in verifications[-1].values():
        assert 'core_evidence_ids' not in item
        assert 'preserved_evidence_ids' not in item
        prior = item['previous_attempt']
        assert prior['validation']['status'] == 'REWRITE'
        assert prior['writer']['sentences']
