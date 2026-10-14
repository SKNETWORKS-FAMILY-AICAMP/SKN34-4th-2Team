"""R16 saved failure shapes, exercised without a model or database."""
from app.resume_review_v2.models import (
    ApplicantIntentClaim, Evidence, EvidenceFacet, Experience, ExtractionOutput,
    InformationReview, QuestionReview, ReviewInput, RevisionPlan,
    RevisionSentence, SectionSemanticProfile, SemanticUnit, SourceDocument, SourceRef,
    WriterOutput,
)
from app.resume_review_v2.project_planning import merge_facets, prepare_review
from app.resume_review_v2.question_planning import (
    information_status, reconcile_deferred_needs, review_information,
)
from app.resume_review_v2.llm import LangChainReviewLLM
from app.models import ConfirmationAnswer


def fact(quote, *, kind='technology', source='p', owner='p'):
    return Evidence(evidence_id='e',experience_id=owner,fact_type=kind,
        normalized_fact=quote,evidence_quote=quote,source_type='resume_text',
        source_id=source,assertion_state='resume_stated')


def test_coarse_technology_type_keeps_quoted_implementation_but_not_ownership():
    # R16 review 147 preserved the exact action quote, not its raw facet slots.
    quote='Python의 OpenAI SDK로 LLM API를 호출하는 코드를 직접 구현했습니다.'
    active={'e':fact(quote)};repairs=[]
    facet=EvidenceFacet(evidence_id='e',slots=['technologies','actions','personal_role'])
    resolved=merge_facets(active,[],[facet],repairs)
    assert [slot.value for slot in resolved[0].slots]==['technologies','actions']
    assert repairs[0]['removed_slots']==['personal_role']
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='API',
        current_text=quote,field_path='projects[0].description',content_hash='h'))
    extracted=ExtractionOutput(experience_id='p',extracted_evidence=[active['e']],facets=[facet])
    prepared=prepare_review(req,extracted)
    assert prepared.profile.actions.evidence_ids==['e']
    assert not prepared.profile.personal_role.evidence_ids
    assert prepared.semantic_preparation['facet_repairs'][0]['removed_slots']==['personal_role']


def test_technology_inventory_and_other_owner_never_establish_action_or_role():
    inventory=fact('Python, OpenAI SDK',source='p:techStack')
    resolved=merge_facets({'e':inventory},[],[
        EvidenceFacet(evidence_id='e',slots=['actions','personal_role'])])
    assert [slot.value for slot in resolved[0].slots]==['technologies']
    assert inventory.experience_id=='p'
    req=ReviewInput(experience=Experience(experience_id='p',kind='project',title='API',
        current_text='서비스를 만들었습니다.',field_path='projects[0].description',content_hash='h'),
        resume_sources=[SourceDocument(source_id='p:techStack',text=inventory.evidence_quote)])
    extraction=ExtractionOutput(experience_id='p',extracted_evidence=[inventory],
        semantic_units=[SemanticUnit(id='false-action',semantic_role='action',
            meaning='Python으로 API를 구현했다',source_refs=[SourceRef(type='applicant_evidence',id='e')])])
    prepared=prepare_review(req,extraction)
    assert prepared.request.section_profile.original_semantic_units[0].semantic_role=='technology'
    assert prepared.analysis.plan.operation=='no_change'


def test_source_terms_in_comma_inventory_do_not_reject_challenge_analysis():
    # Initial raw Analyze of review 143 used commas where the quote used 부터/까지.
    quote=('Logistic Regression부터 Random Forest, XGBoost, LightGBM, CatBoost까지 '
           '비교하고 ROC-AUC와 PR-AUC를 확인했습니다.')
    req=ReviewInput(experience=Experience(experience_id='c',kind='other',title='어려움',
        current_text=quote,field_path='selfIntroduction.challenge',content_hash='h'))
    e=fact(quote,kind='verification',source='c',owner='c')
    extraction=ExtractionOutput(experience_id='c',extracted_evidence=[e],semantic_units=[
        SemanticUnit(id='comparison',semantic_role='validation',meaning='모델과 평가 지표를 비교했습니다.',
            source_refs=[SourceRef(type='applicant_evidence',id='e')],
            optional_details=['Logistic Regression, Random Forest, XGBoost, LightGBM, CatBoost',
                              'ROC-AUC, PR-AUC'])])
    prepared=prepare_review(req,extraction)
    unit=prepared.request.section_profile.original_semantic_units[0]
    assert len(unit.optional_details)==2
    assert not prepared.semantic_preparation.get('excluded_optional_details')
    assert prepared.evidence['e'].evidence_quote==quote


def need(fingerprint, *, question='Python을 어디에 사용했나요?', aspect='technology_application',
         requirement='req-3',owner='p'):
    return dict(dedupe_key='p:value:requirement:python_application',
        information_fingerprint=fingerprint,experience_id=owner,owner_scope='experience',
        target_slot='technologies',request_aspect=aspect,requirement_id=requirement,
        question=question)


def test_same_need_with_two_source_fingerprints_closes_once_after_answer():
    # Review 146 kept the same server need twice after the source span changed.
    a,b=need('source-need:61d18'),need('source-need:ba776')
    a['target_contexts']=[dict(type='applicant_source',source_type='resume_text',
        source_id='p:techStack',anchors=['Python'])]
    b['target_contexts']=[dict(type='applicant_source',source_type='resume_text',
        source_id='p:techStack',anchors=['Python 활용'])]
    prior={'requirement_context_hash':'job-epoch', 'gap_questions':[a,b],
        'debug_trace':{'question_selection':{'opportunities':[
            dict(state='proposed',key=a['information_fingerprint'],need=a,requirement_id='req-3'),
            dict(state='deferred',key=b['information_fingerprint'],need=b,requirement_id='req-3')]}}}
    current={'requirement_context_hash':'job-epoch','gap_questions':[],
        'debug_trace':{'question_selection':{'review_state':'reviewed','opportunities':[
            dict(state='answered',information_need_id=a['dedupe_key'],target_slot='technologies',
                 request_aspect='technology_application',requirement_id='req-3',evidence_ids=['answer'])]}}}
    reconcile_deferred_needs(current,prior,'job-epoch')
    assert current['gap_questions']==[]
    rows=current['debug_trace']['question_selection']['opportunities']
    assert len(rows)==1 and rows[0]['state']=='answered'
    summary=information_status([dict(experience=dict(experience_id='p'),validation=dict(status='READY'),
        **current)],[],[],[],[],'job-epoch')
    assert summary['state']=='resolved' and summary['open_opportunities']==0


def test_same_need_id_with_different_scope_stays_ambiguous():
    a=need('source-need:a');b=need('source-need:b')
    a['target_contexts']=[dict(type='applicant_source',source_type='resume_text',source_id='p:techStack')]
    b['target_contexts']=[dict(type='applicant_source',source_type='resume_text',source_id='p:otherField')]
    prior={'requirement_context_hash':'job-epoch','gap_questions':[a,b]}
    current={'requirement_context_hash':'job-epoch','gap_questions':[],
        'debug_trace':{'question_selection':{'opportunities':[
            dict(state='answered',information_need_id=a['dedupe_key'])]}}}
    reconcile_deferred_needs(current,prior,'job-epoch')
    assert len(current['gap_questions'])==2
    assert current['debug_trace']['question_selection']['opportunities'][0]['reason']=='ambiguous_or_unknown_information_need'


def test_unassigned_completion_requires_the_issued_question_and_target_epoch():
    pending=need('source-need:p',requirement='req-3')
    pending['owner_scope']='unassigned'
    record=dict(experience=dict(experience_id='p'),validation=dict(status='REJECTED'),
        requirement_context_hash='job-epoch',debug_trace=dict(question_selection=dict(
            review_state='reviewed',opportunities=[dict(state='proposed',key=pending['information_fingerprint'],
                need=pending,requirement_id='req-3')])))
    answer=ConfirmationAnswer(question_id='issued-question',experience_id='other',field_path='projects[1].description',
        question=pending['question'],answer='Python으로 분석했습니다.',
        information_need_id=pending['dedupe_key'])
    unresolved=information_status([record],[],[],[answer],[],'job-epoch')
    assert unresolved['decisions'][0]['state']=='proposed'
    ledger=[dict(context_hash='job-epoch',requirement_id='req-3',experience_id='other',
        disposition='provided',answer=answer.answer,question_data=dict(owner_scope='unassigned',
            information_need_id=pending['dedupe_key'],question_id='issued-question'))]
    resolved=information_status([record],[],[],[answer],ledger,'job-epoch')
    assert resolved['decisions'][0]['state']=='answered'
    ledger[0]['context_hash']='stale-job'
    assert information_status([record],[],[],[answer],ledger,'job-epoch')['decisions'][0]['state']=='proposed'


def test_future_plan_sufficient_uses_validated_intent_not_fictitious_past_fact():
    quote='입사 초기에는 서비스 흐름을 이해하겠습니다.'
    experience=Experience(experience_id='future',kind='other',title='입사 후 포부',
        current_text=quote,field_path='selfIntroduction.aspiration',content_hash='h')
    intent=ApplicantIntentClaim(id='i',source_section_id='future',intent_type='short_term_plan',
        text=quote,source_type='resume_text',source_id='future',evidence_quote=quote,state='resume_stated')
    req=ReviewInput(experience=experience,approved_intents=[intent])
    extraction=ExtractionOutput(experience_id='future',extracted_evidence=[],question_review=QuestionReview(
        experience_state='reviewed',reason='계획 확인',items=[InformationReview(
            state='sufficient',reason='미래 계획이 출처에 제시됨')]))
    _,diagnostics=review_information(req,extraction,{},[])
    assert diagnostics['opportunities'][0]['state']=='sufficient'
    assert diagnostics['opportunities'][0]['evidence_ids']==['i']
    req.approved_intents=[]
    _,unapproved=review_information(req,extraction,{},[])
    assert unapproved['opportunities'][0]['state']=='not_reviewed'


def test_rewrite_input_identifies_previously_expressed_protected_meanings():
    text='문장을 바로 생성하는 대신 근거를 구조화했습니다. 지원 문항을 분석해 근거를 선택했습니다.'
    experience=Experience(experience_id='p',kind='project',title='서비스',current_text=text,
        field_path='projects[0].description',content_hash='h')
    unit=SemanticUnit(id='analysis',semantic_role='action',meaning='지원 문항을 분석해 근거를 선택했습니다.',
        source_refs=[SourceRef(type='applicant_evidence',id='e')])
    decision=SemanticUnit(id='decision',semantic_role='decision',meaning='문장을 바로 생성하는 대신 근거를 구조화했습니다.',
        source_refs=[SourceRef(type='applicant_evidence',id='d')])
    req=ReviewInput(experience=experience,section_profile=SectionSemanticProfile(
        section_type='project',original_semantic_units=[unit,decision],required_semantics=['analysis','decision']))
    candidate=WriterOutput(experience_id='p',operation='replace_field',original_quote=text,
        sentences=[RevisionSentence(text='문장을 바로 생성하는 대신 근거를 구조화했습니다.',
            evidence_ids=['d'],semantic_unit_ids=['decision']),
            RevisionSentence(text='지원 문항에 맞는 근거를 선택했습니다.',
                evidence_ids=['e'],semantic_unit_ids=['analysis'])])
    client=LangChainReviewLLM.__new__(LangChainReviewLLM);captured=[]
    client._call=lambda system,payload,schema:captured.append(payload)
    assert client.write(req,RevisionPlan(objective='편집',operation='replace_field'),[],
        previous_text=text,previous_candidate=candidate) is None
    review=captured[0]['rewrite_source_review']
    assert review['prior_draft_coverage']==[
        dict(sentence_index=0,semantic_unit_ids=['decision'],evidence_ids=['d'],intent_ids=[]),
        dict(sentence_index=1,semantic_unit_ids=['analysis'],evidence_ids=['e'],intent_ids=[])]
    assert review['prior_draft_is_not_approved'] is True
