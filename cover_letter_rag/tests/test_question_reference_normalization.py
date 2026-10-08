"""QuestionNeed contract and exact IDs; old free-text fixtures are not auto-converted."""
import pytest
from pydantic import ValidationError
from test_project_live_pipeline import pipeline
from app.resume_review_v2.models import (Experience,ReviewInput,Evidence,ExtractionOutput,
    QuestionNeed,QuestionTarget,GapQuestion,AssertionState)
from app.resume_review_v2.project_planning import prepare_review
from app.resume_review_v2.validation import ContractError
from app.resume_review_v2.question_planning import select_question,approved_question,render_question_text


def case(ids=('e3','e4'),basis=None):
    quotes=['모델과 지표를 비교했습니다.','설정별 평가값을 확인했습니다.']
    req=ReviewInput(experience=Experience(experience_id='exp',kind='project',title='비교',
        current_text=' '.join(quotes),field_path='projects[0].description',content_hash='h'))
    facts=[Evidence(evidence_id=eid,experience_id='exp',fact_type='verification',normalized_fact=quote,
        evidence_quote=quote,source_type='resume_text',source_id='exp',assertion_state='resume_stated')
        for eid,quote in zip(ids,quotes)]
    need=QuestionNeed(experience_id='exp',gap_type='clarification',target_slot='outcome',
        focus='comparison_basis',evidence_basis=list(basis or ids),priority='MEDIUM',
        why_needed='비교는 확인했지만 결과를 알아야 기여를 설명할 수 있습니다.',dedupe_key='comparison-result')
    return req,ExtractionOutput(experience_id='exp',extracted_evidence=facts,question=need)


def test_known_typed_refs_recover_without_changing_need_value():
    req,extraction=case(basis=['evidence:e3','evidence:e4'])
    p=prepare_review(req,extraction);q=p.questions[0]
    assert q.evidence_basis==['e3','e4'] and q.presuppositions==[]
    assert (q.why_needed,q.priority)==(extraction.question.why_needed,extraction.question.priority)
    assert render_question_text(extraction.question) in q.question
    assert all(e['outcome']=='normalized' for e in p.question_selection['reference_normalization'])


@pytest.mark.parametrize('reference',['missing','evidence:missing','other:e3','evidence:evidence:e3','e30','e3:other'])
def test_unrecognized_or_nonexistent_refs_are_not_guessed(reference):
    req,extraction=case(basis=[reference,'e4']);p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='inactive_or_unknown_evidence_basis'
    assert p.question_selection['reference_normalization'][0]['canonical_id']==reference


@pytest.mark.parametrize('state',['uncertain','retracted','superseded','contradicted'])
def test_reference_does_not_approve_inactive_source(state):
    req,extraction=case(basis=['evidence:e3','evidence:e4'])
    extraction.extracted_evidence[0].assertion_state=AssertionState(state)
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='inactive_or_unknown_evidence_basis'


def test_literal_prefixed_canonical_id_wins_instead_of_reviving_active_suffix():
    req,extraction=case(ids=('evidence:e3','e3'),basis=['evidence:e3','e3'])
    extraction.extracted_evidence[0].assertion_state=AssertionState.RETRACTED
    p=prepare_review(req,extraction)
    assert not p.questions
    assert p.question_selection['reference_normalization'][0]['canonical_id']=='evidence:e3'


def test_prefix_inside_real_id_can_have_one_typed_wrapper():
    req,extraction=case(ids=('evidence:e3','e4'),basis=['evidence:evidence:e3','evidence:e4'])
    assert prepare_review(req,extraction).questions[0].evidence_basis==['evidence:e3','e4']


def test_question_or_claim_owner_cannot_use_another_experience_namespace():
    req,extraction=case();extraction.question.experience_id='other'
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='question_owner_mismatch'
    req,extraction=case();extraction.extracted_evidence[0].experience_id='other'
    with pytest.raises(ContractError,match='cross-experience'):prepare_review(req,extraction)


def test_typed_ref_then_turn_collision_preserves_old_state():
    req,extraction=case(basis=['evidence:e3'])
    old=extraction.extracted_evidence[0].model_copy(deep=True);old.assertion_state=AssertionState.RETRACTED
    req.experience.existing_evidence=[old];req.answer='비교 결과를 새롭게 확인했습니다.';req.answer_source_id='new-answer'
    fresh=extraction.extracted_evidence[0]
    fresh.source_type='user_answer';fresh.source_id='new-answer';fresh.evidence_quote=req.answer
    fresh.normalized_fact=req.answer;fresh.assertion_state=AssertionState.USER_ASSERTED
    p=prepare_review(req,extraction)
    assert p.questions[0].evidence_basis[0].startswith('turn:')
    assert p.evidence['e3'].assertion_state=='retracted'


def test_bad_source_quote_is_not_bypassed():
    req,extraction=case(basis=['evidence:e3','evidence:e4']);extraction.extracted_evidence[0].evidence_quote='없는 원문'
    with pytest.raises(ContractError,match='quote absent') as caught:prepare_review(req,extraction)
    assert caught.value.diagnostics['question_reference_normalization'][0]['canonical_id']=='e3'


def test_no_candidate_is_not_created():
    req,extraction=case();extraction.question=None
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['state']=='model_not_proposed'


def test_alias_does_not_remove_unresolved_conflict():
    req,extraction=case();req.answer='설정 결과는 확실하지 않습니다.';req.answer_source_id='answer'
    f=extraction.extracted_evidence[1];f.source_type='user_answer';f.source_id='answer'
    f.evidence_quote=f.normalized_fact=req.answer;f.assertion_state=AssertionState.UNCERTAIN
    f.conflicts_with_evidence_ids=['e3']
    assert not prepare_review(req,extraction).questions


@pytest.mark.parametrize('display',['모델과 지표를 비교했다.','모델과 지표를 함께 확인했습니다.','비교하지 않았다.'])
def test_no_display_paraphrase_or_negation_is_used_as_public_premise(display):
    req,extraction=case();extraction.extracted_evidence[0].normalized_fact=display
    p=prepare_review(req,extraction)
    assert p.questions and render_question_text(extraction.question) in p.questions[0].question
    assert display not in p.questions[0].question


def test_free_prose_is_not_in_model_schema_and_correct_id_cannot_approve_bad_body():
    req,extraction=case()
    assert not {'question','presuppositions','experience_title'} & QuestionNeed.model_json_schema()['properties'].keys()
    bad={**extraction.question.model_dump(),'question':'실제 운영 성능이 개선됐는데 얼마나 개선됐나요?'}
    with pytest.raises(ValidationError):ExtractionOutput(experience_id='exp',extracted_evidence=[],question=bad)
    forged=GapQuestion(**extraction.question.model_dump(),question=bad['question'])
    assert not approved_question(forged,{f.evidence_id:f for f in extraction.extracted_evidence})


def test_legacy_is_rejected_not_laundered():
    req,extraction=case()
    legacy=GapQuestion(**extraction.question.model_dump(exclude={'contract'}),question='성과가 개선됐는데 얼마나 개선됐나요?')
    with pytest.raises(ValidationError):ExtractionOutput(experience_id='exp',extracted_evidence=[],question=legacy)
    diagnostic={};assert not select_question(req,legacy,{f.evidence_id:f for f in extraction.extracted_evidence},diagnostic)
    assert diagnostic['reason']=='legacy_question_contract'


def test_template_text_is_not_a_dedupe_key_for_distinct_needs():
    req,extraction=case();first=prepare_review(req,extraction)
    req.question_history=[first.questions[0].question]
    req.previous_question_keys=[first.questions[0].dedupe_key,first.questions[0].information_fingerprint]
    extraction.question.dedupe_key='different-measurement-condition'
    extraction.question.request_aspect='comparison_result'
    second=prepare_review(req,extraction)
    assert second.questions and second.questions[0].question!=first.questions[0].question
    extraction.question.dedupe_key='comparison-result'
    extraction.question.request_aspect=None
    repeated=prepare_review(req,extraction)
    assert not repeated.questions and repeated.question_selection['reason']=='exact_repeat'


def test_model_value_explanation_is_private_not_public_factual_reason(pipeline,monkeypatch):
    from test_project_live_pipeline import post
    from app.resume_review_v2.llm import LangChainReviewLLM
    client,reviews,calls,db=pipeline;original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput':result.item_0.question.why_needed='실제 운영 성능이 개선되었으니 성과를 수집한다.'
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    response=post(client,'private')
    q=response['questions'][0]
    assert '실제 운영 성능' not in q['question'] and '실제 운영 성능' not in q['reason']
    assert '실제 운영 성능' in response['telemetry']['v2_results'][0]['debug_trace']['question_selection']['candidate']['why_needed']


def test_old_issued_question_requires_fresh_contract_instead_of_fact_laundering(pipeline):
    from test_project_live_pipeline import post
    client,reviews,calls,db=pipeline;first=post(client,'legacy')
    q=first['questions'][0];reviews['legacy']['questions'][0]['question_contract']=None
    before=len(calls)
    response=client.post('/resume-review/api/v1/resumes/reviews/proxy',json=dict(uid='student',cohort_id='local',resume_id='1',
        review_mode='general',request_id='answer',previous_review_id='legacy',answers=[dict(question_id=q['question_id'],
        field_path=q['field_path'],question=q['question'],answer='실제로 수행했습니다.')]))
    assert response.status_code==409 and response.json()['detail']=='question_contract_changed'
    assert len(calls)==before


def test_compound_quote_with_retired_sibling_is_never_displayed_as_safe_fact():
    req,extraction=case(basis=['e3'])
    quote='필터를 구성했고 운영 성능도 개선했습니다.'
    req.experience.current_text=quote
    for f in extraction.extracted_evidence:f.evidence_quote=quote
    extraction.extracted_evidence[1].assertion_state=AssertionState.RETRACTED
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='unsafe_target_quote_scope'


def test_unrelated_inactive_sentence_does_not_disable_target_and_is_not_redisplayed():
    req,extraction=case(basis=['e3'])
    extraction.extracted_evidence[1].assertion_state=AssertionState.RETRACTED
    q=prepare_review(req,extraction).questions[0]
    c=q.target_contexts[0]
    assert c['quote']==extraction.extracted_evidence[0].evidence_quote
    assert c['evidence_ids']==['e3']
    assert extraction.extracted_evidence[1].evidence_quote not in str(c)
    assert '비활성 근거' in c['context_quote']


def test_fragment_does_not_drop_same_sentence_negation_or_decimal_condition():
    req,extraction=case(basis=['e3'])
    source='단일 변수 AUC 0.905를 확인했지만 전체 모델 성능을 검증한 것은 아닙니다.'
    req.experience.current_text=source;extraction.extracted_evidence=extraction.extracted_evidence[:1]
    extraction.extracted_evidence[0].evidence_quote='AUC 0.905'
    q=prepare_review(req,extraction).questions[0]
    assert q.target_contexts[0]['quote']==source
    assert '아닙니다' in q.target_contexts[0]['quote']


@pytest.mark.parametrize('target,reason',[
    (QuestionTarget(evidence_id='e3',anchor='없는 기술'),'question_target_anchor_absent'),
    (QuestionTarget(evidence_id='e4'),'unapproved_question_target'),
])
def test_target_must_be_in_basis_and_anchor_must_be_literal(target,reason):
    req,extraction=case(basis=['e3']);extraction.question.targets=[target]
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']==reason


def test_same_focus_other_target_is_distinct_but_renamed_key_same_target_is_blocked():
    req,extraction=case();need=extraction.question
    need.targets=[QuestionTarget(evidence_id='e3',anchor='모델')]
    need.request_aspect='comparison_result'
    first=prepare_review(req,extraction).questions[0]
    req.previous_question_keys=[first.information_fingerprint]
    need.dedupe_key='renamed'
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='same_target_information_request'
    need.targets=[QuestionTarget(evidence_id='e4',anchor='설정')]
    second=prepare_review(req,extraction).questions[0]
    assert first.question==second.question  # visible source targets, not hidden IDs, differ
    assert first.target_contexts[0]['quote']!=second.target_contexts[0]['quote']
    assert first.information_fingerprint!=second.information_fingerprint


def test_same_anchor_quote_boundary_change_does_not_create_new_need():
    req,extraction=case(basis=['e3']);extraction.extracted_evidence=extraction.extracted_evidence[:1]
    extraction.question.targets=[QuestionTarget(evidence_id='e3',anchor='모델')]
    first=prepare_review(req,extraction).questions[0]
    req.previous_question_keys=[first.information_fingerprint]
    extraction.question.dedupe_key='renamed';extraction.extracted_evidence[0].evidence_quote='모델과 지표'
    p=prepare_review(req,extraction)
    assert not p.questions and p.question_selection['reason']=='same_target_information_request'


def test_direct_renderer_cannot_resolve_other_resume_source():
    req,extraction=case(basis=['e3'])
    evidence={f.evidence_id:f for f in extraction.extracted_evidence}
    evidence['e3'].source_id='other:body'
    diagnostic={}
    assert not select_question(req,extraction.question,evidence,diagnostic)
    assert diagnostic['reason']=='question_target_source_unavailable'


def test_delivery_checkpoint_and_same_version_audit_reuse(pipeline,monkeypatch):
    from test_stage_checkpoints import staged
    from test_project_live_pipeline import post
    from app.resume_review_v2.llm import LangChainReviewLLM
    client,reviews,calls,db=pipeline;saved=staged(db,reviews)
    original=LangChainReviewLLM._call
    def invoke(self,prompt,payload,schema):
        result,usage=original(self,prompt,payload,schema)
        if schema.__name__=='BatchExtractionOutput' and result.item_0.question is not None:
            result.item_0.question.evidence_basis=['evidence:action']
            result.item_0.question.targets=[QuestionTarget(evidence_id='evidence:action',anchor='API')]
            result.item_0.question.request_aspect='verification_method'
        return result,usage
    monkeypatch.setattr(LangChainReviewLLM,'_call',invoke)
    post(client,'initial')
    raw=saved['initial']['checkpoint']['states']['projects:p1']['result']
    assert raw['gap_questions'][0]['evidence_basis']==['action']
    assert raw['gap_questions'][0]['targets']==[{'evidence_id':'action','anchor':'API'}]
    diagnostic=raw['debug_trace']['question_selection']['reference_normalization']
    post(client,'initial');final=post(client,'initial')
    assert final['questions'][0]['evidence_basis']==['action']
    assert final['questions'][0]['question_contract']=='evidence-need-v2'
    public=final['questions'][0]
    assert public['target_contexts']==raw['gap_questions'][0]['target_contexts']
    assert public['information_request_fingerprint']==raw['gap_questions'][0]['information_fingerprint']
    assert final['telemetry']['question_delivery'][0]['state']=='displayed'
    assert final['telemetry']['v2_results'][0]['debug_trace']['question_selection']['reference_normalization']==diagnostic
    before=len(calls);audit=post(client,'audit',previous_review_id='initial',review_phase='gap_audit')
    assert len(calls)==before
    public=audit['questions'][0]
    post(client,'answer',previous_review_id='audit',answers=[dict(question_id=public['question_id'],
        field_path=public['field_path'],question='client forged question',answer='정상 조회 결과를 대조했습니다.',
        question_target_contexts=[{'quote':'client forged context'}])])
    payload=next(p['item_0'] for stage,_,p in calls[before:] if stage=='BatchExtractionOutput')
    assert public['question'] in payload['question_history'][0]
    assert 'API' in payload['question_history'][0] and 'verification' not in payload['user_answer']
    assert 'client forged' not in str(payload)
