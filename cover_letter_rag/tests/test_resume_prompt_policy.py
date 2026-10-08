"""Prompt consistency and factual-vs-quality contracts; no external calls."""
import pytest
from app.resume_review_v2 import policy
from app.resume_review_v2.prompts import (ANALYST_SYSTEM_PROMPT,
    WRITER_SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT)
from app.resume_review_v2.llm import LangChainReviewLLM
from app.resume_review_v2.models import (Experience, Evidence, ReviewInput,
    RevisionPlan, RevisionSentence, WriterOutput, FactVerification, OmittedEvidence,
    ValidationIssue)
from app.resume_review_v2.validation import validate_candidate


@pytest.mark.parametrize('prompt', [ANALYST_SYSTEM_PROMPT, WRITER_SYSTEM_PROMPT, VERIFY_SYSTEM_PROMPT])
def test_roles_share_one_authoritative_policy(prompt):
    for canonical in [policy.FACTUAL_POLICY]:
        assert prompt.count(canonical) == 1
    assert 'Preserve every supported detail' not in prompt
    assert '2~3' not in prompt
    assert 'all missing information' not in prompt


@pytest.mark.parametrize('source_id,quote,expected', [
    ('exp:techStack', 'Python, PostgreSQL', 'owning_experience'),
    ('global:techStack', 'Python, PostgreSQL', None),
    ('other:techStack', 'Python, PostgreSQL', None),
    ('exp:techStack', 'Python, AWS', None),
])
def test_writer_and_verifier_resolve_scope_from_owning_source_not_normalization(source_id, quote, expected):
    from app.resume_review_v2.models import SourceDocument
    req, _, plan = fixture()
    req.resume_sources = [SourceDocument(source_id=k, text='Python, PostgreSQL')
                          for k in ('exp:techStack', 'global:techStack', 'other:techStack')]
    fact = Evidence(evidence_id='stack', experience_id='exp', fact_type='technology',
        normalized_fact='이력서 기술 스택', evidence_quote=quote, source_type='resume_text',
        source_id=source_id, assertion_state='resume_stated')
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    calls = []
    client._call = lambda system, payload, schema: calls.append(payload)
    client.write(req, plan, [fact])
    client.verify(req, draft(req, [('기술 스택에는 Python, PostgreSQL이 포함됩니다.', ['stack'])]), [fact], [], [])
    for payload in calls:
        scope = payload['approved_evidence'][0]['source_context']
        assert (scope['scope'] if scope else None) == expected
        if scope:
            assert scope['field'] == 'techStack' and scope['experience_id'] == 'exp'
    assert fact.normalized_fact == '이력서 기술 스택'  # Stored evidence is not silently rewritten.


def fixture():
    exp = Experience(experience_id='exp', kind='project', title='분석',
        current_text='캐시 장애를 분석했습니다.', field_path='projects[0].description', content_hash='h')
    facts = {
        'problem': '캐시 갱신 누락으로 응답 데이터가 오래되는 원인을 분석했습니다.',
        'decision': 'TTL 갱신 대신 이벤트 기반 무효화를 선택해 Redis 캐시와 원본 데이터의 일관성을 확보했습니다.',
        'optional': '로그 파일을 읽고 작업 기록을 저장했습니다.',
    }
    evidence = {key: Evidence(evidence_id=key, experience_id='exp',
        fact_type='technical_decision' if key == 'decision' else 'action',
        normalized_fact=text, evidence_quote=text, source_type='user_answer',
        source_id='answer', assertion_state='user_asserted') for key, text in facts.items()}
    req = ReviewInput(experience=exp, answer=' '.join(facts.values()), answer_source_id='answer')
    plan = RevisionPlan(objective='문제 원인과 직접 판단', operation='replace_field',
        core_evidence_ids=['problem', 'decision'], supporting_evidence_ids=['optional'])
    return req, evidence, plan


def draft(req, rows):
    return WriterOutput(experience_id='exp', operation='replace_field',
        original_quote=req.experience.current_text,
        sentences=[RevisionSentence(text=text, evidence_ids=ids) for text, ids in rows])


def test_many_useful_sentences_not_a_length_failure():
    req, ev, plan = fixture()
    for key, text, kind in [
        ('verification', '동일 요청을 반복 실행하고 데이터 수정 이벤트 발생 전후의 캐시 갱신 직후 반환값을 원본 데이터와 대조했습니다.', 'verification'),
        ('result', '검증 결과 갱신 이후 오래된 데이터가 반환되지 않음을 확인했습니다.', 'result'),
    ]:
        ev[key] = Evidence(evidence_id=key, experience_id='exp', fact_type=kind,
            normalized_fact=text, evidence_quote=text, source_type='user_answer',
            source_id='answer', assertion_state='user_asserted')
    plan.supporting_evidence_ids = ['verification', 'result']
    plan.omitted_evidence = [OmittedEvidence(evidence_id='optional', reason='낮은 정보 가치')]
    rows = [
        ('캐시 갱신 누락으로 응답 데이터가 오래되는 원인을 분석했습니다.', ['problem']),
        ('TTL 갱신 대신 이벤트 기반 무효화를 선택해 Redis 캐시와 원본 데이터의 일관성을 확보했습니다.', ['decision']),
        (ev['verification'].normalized_fact, ['verification']),
        (ev['result'].normalized_fact, ['result']),
    ]
    writer = draft(req, rows)
    assert len(writer.sentences) > 3
    assert len(writer.suggested_text) > 180
    result = validate_candidate(req, writer, plan, ev, FactVerification())
    assert result.status == 'READY'
    assert not result.factual_issues
    assert 'verbosity' not in {i.code for i in result.quality_issues}


def test_supported_optional_details_can_all_be_unused():
    req, ev, plan = fixture()
    writer = draft(req, [('캐시 갱신 누락 원인을 분석해 TTL 갱신 대신 이벤트 기반 Redis 캐시 무효화를 구현했습니다.', ['problem', 'decision'])])
    result = validate_candidate(req, writer, plan, ev, FactVerification())
    assert result.status == 'READY'
    assert not result.factual_issues


def test_compression_cannot_erase_core_problem_solving_meaning():
    req, ev, plan = fixture()
    writer = draft(req, [('Redis를 사용해 작업했습니다.', ['problem', 'decision'])])
    result = validate_candidate(req, writer, plan, ev, FactVerification(
        critical_technical_signal_loss=['이벤트 기반 무효화 선택과 원인 분석이 사라짐']))
    assert result.status == 'REWRITE'
    assert not result.factual_issues
    assert 'critical_technical_signal_loss' in {i.code for i in result.quality_issues}


def test_unsupported_facts_stay_factual_failures():
    req, ev, plan = fixture()
    writer = draft(req, [('Redis와 Pinecone을 적용해 응답 시간을 90% 줄였습니다.', ['decision'])])
    result = validate_candidate(req, writer, plan, ev,
        FactVerification(unsupported_claims=['확인되지 않은 응답 시간 개선']))
    assert {'unsupported_number', 'unsupported_technology', 'semantic_unsupported_claim'} <= {i.code for i in result.factual_issues}


def test_initial_and_rewrite_use_same_policy_and_do_not_restore_optional_facts():
    req, ev, plan = fixture()
    plan.supporting_evidence_ids = []
    plan.omitted_evidence = [OmittedEvidence(evidence_id='optional', reason='낮은 정보 가치')]
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    calls = []
    client._call = lambda system, payload, schema: calls.append((system, payload))
    approved = [ev[eid] for eid in plan.core_evidence_ids]
    client.write(req, plan, approved)
    client.write(req, plan, approved, [ValidationIssue(code='procedure_overload', detail='나열')], '기존 후보')
    assert calls[0][0] == calls[1][0] == WRITER_SYSTEM_PROMPT
    assert calls[0][1]['section_writing_rules'] == calls[1][1]['section_writing_rules'] == policy.PROJECT_POLICY
    assert 'Edit the complete paragraph' in calls[1][1]['section_writing_rules']
    assert 'Independent findings may stay independent' in calls[1][1]['section_writing_rules']
    assert 'instead of enumerating the same features a second time' in ' '.join(calls[1][1]['section_writing_rules'].split())
    assert 'preserves argument and order' not in calls[1][0]
    assert 'not wording or original prose order' in calls[1][0]
    assert policy.REWRITE_POLICY in calls[1][0]
    assert 'revision_plan' not in calls[1][1]
    assert 'optional' not in {e['evidence_id'] for e in calls[1][1]['approved_evidence']}
    restored = draft(req, [('작업 기록을 저장했습니다.', ['optional'])])
    assert 'unapproved_claim_evidence' in {i.code for i in validate_candidate(req, restored, plan, ev).factual_issues}


def test_analyst_and_writer_use_same_section_and_high_value_question_policy():
    req, ev, plan = fixture()
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    calls = []
    client._call = lambda system, payload, schema: calls.append((system, payload))
    client.analyze(req)
    client.write(req, plan, list(ev.values()))
    for _, payload in calls:
        assert payload['target_section'] == 'project'
        assert payload['section_writing_rules'] == policy.PROJECT_POLICY
        assert payload['policy_version'] == policy.POLICY_VERSION
    assert calls[1][1]['editorial_brief']['section'] == 'project'
    assert 'current_text' not in calls[1][1]['experience']
    assert 'job_requirements' not in calls[0][1]
    assert 'Select at most two' not in calls[0][0]


def test_verifier_uses_the_same_paragraph_policy_without_an_enumeration_quota():
    req, evidence, plan = fixture()
    calls = []
    client = LangChainReviewLLM.__new__(LangChainReviewLLM)
    client._call = lambda system, payload, schema: calls.append((system, payload))
    client.verify(req, draft(req, [('캐시 원인을 분석했습니다.', ['problem'])]), list(evidence.values()),
                  plan.core_evidence_ids, [])
    assert calls[0][1]['section_writing_rules'] == policy.PROJECT_POLICY
    assert 'no fixed sentence count' in calls[0][1]['section_writing_rules']
    assert 'Do not invent causality' in ' '.join(calls[0][1]['section_writing_rules'].split())
    assert 'length alone' in calls[0][0]
