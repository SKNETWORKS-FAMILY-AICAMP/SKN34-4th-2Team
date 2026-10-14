"""Local HTTP adapters only. Production URLconf never imports this module."""
import json
import logging
from functools import wraps
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.contrib.auth.hashers import check_password
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .jwt_auth import issue_tokens, load_lms_user
from .models import (Users, Resumes, ResumeExperiences, ResumeEvidence, ResumeExperienceBindings,
                     Applications, ApplicationQuestions, ApplicationPlans)
from .application_workspace import create_or_open_application, ensure_tailored_resume, open_application, application_evidence
from .application_question_store import analyze_questions, plan_application, save_answer, reusable_plan
from .recruit_role_store import open_role, role_snapshot, import_role_questions
from .local_resume_e2e_fixture import EMAIL, fixture
from .local_resume_e2e_ai import planning_client
from .local_resume_e2e_data import local_guard, META, imported_resumes, imported_job


def endpoint(method, authenticated=True):
    def decorate(fn):
        @csrf_exempt
        @wraps(fn)
        def view(request, **kwargs):
            if not getattr(settings, 'LOCAL_RESUME_E2E', False): return JsonResponse({'detail': 'not found'}, status=404)
            if request.method != method: return JsonResponse({'detail': 'method not allowed'}, status=405)
            if authenticated and not request.lms_user: return JsonResponse({'detail': 'unauthenticated'}, status=401)
            try:
                local_guard()
                body = json.loads(request.body or b'{}')
                if not isinstance(body, dict): raise ValueError('JSON object required')
                if fn.__name__ in {'analyze','plan','write','extract_evidence'} and (body.get('ai_mode')=='live' or body.get('request_id')):
                    from .local_resume_e2e_runs import once
                    open_application(user_id=request.lms_user['id'],application_id=kwargs['application_id'])
                    result=once(request.lms_user['id'],request.path,body,lambda:fn(request,body,**kwargs))
                else:
                    result = fn(request, body, **kwargs)
                return result if isinstance(result, JsonResponse) else JsonResponse(result)
            except (ObjectDoesNotExist, PermissionError): return JsonResponse({'detail': 'not found or forbidden'}, status=404)
            except (ValueError, ValidationError, TypeError, KeyError) as exc:
                logging.getLogger(__name__).warning('Local E2E validation: %s', exc)
                return JsonResponse({'detail': '입력 또는 현재 단계가 유효하지 않습니다. 서버 로그를 확인하세요.'}, status=400)
            except Exception:
                logging.getLogger(__name__).exception('Local E2E failed')
                return JsonResponse({'detail': '로컬 처리 실패. 서버 로그를 확인하세요.'}, status=500)
        return view
    return decorate


@endpoint('POST', authenticated=False)
def login(request, body):
    user = Users.objects.get(email=body.get('email'), is_active=True)
    if not check_password(body.get('password', ''), user.password):
        return JsonResponse({'ok': False, 'detail': 'invalid password'}, status=401)
    return {'ok': True, **issue_tokens(load_lms_user(user.firebase_uid))}


@endpoint('GET')
def catalog(request, body):
    uid = request.lms_user['id']
    from .models import RecruitRoles
    real=imported_resumes(uid)
    return {'ai_mode': 'mock', 'real_resumes': [dict(id=r.pk,title=r.title,registration=registration_state(r)) for r in real],
        'real_jobs': [dict(id=j['role_id'],title=j['title'],company=j['company'],job_id=j['job_id'],snapshot_hash=j['snapshot_hash'],resume_id=r.pk)
                      for r in real for j in r.content[META].get('jobs', [])],
        'resumes': list(Resumes.objects.filter(user_id=uid, is_base_resume=True).values('id', 'title')),
        'jobs': [dict(id=str(r.pk), title=r.role_name, company=r.company.company_name, job_id='local-e2e-job')
                 for r in RecruitRoles.objects.filter(created_by_id=uid, season='LOCAL E2E').select_related('company')]}


def registration_state(resume):
    bindings = ResumeExperienceBindings.objects.filter(resume=resume)
    evidence = ResumeEvidence.objects.filter(experience_id__in=bindings.values('experience_id'))
    return {'resume_imported': True, 'experience_initialized': bindings.exists(),
        'experience_count': bindings.values('experience_id').distinct().count(),
        'evidence_extracted': evidence.count()}


def detail(user_id, app_id):
    app = open_application(user_id=user_id, application_id=app_id)
    active = application_evidence(user_id=user_id, application_id=app.pk)
    bindings = ResumeExperienceBindings.objects.filter(resume_id__in=[app.base_resume_id, app.tailored_resume_id]).select_related('experience')
    try:
        plan = reusable_plan(user_id=user_id, application_id=app.pk)
    except ValueError:  # Import/analyze not complete, or analysis is stale.
        plan = None
    return {'id': str(app.pk), 'base_resume_id': app.base_resume_id, 'tailored_resume_id': app.tailored_resume_id,
        'questions': list(app.questions.values('id', 'raw_text', 'analysis', 'source_type', 'source_reference')),
        'experiences': [dict(id=eid, title=next(b.experience.title for b in bindings if str(b.experience_id) == eid),
                            evidence=[dict(id=str(f.pk), normalized_fact=f.normalized_fact, assertion_state=f.assertion_state) for f in facts]) for eid, facts in active.items()],
        'bindings': [dict(resume_id=b.resume_id, experience_id=str(b.experience_id), item_key=b.item_key) for b in bindings],
        'counts': {'Resume': Resumes.objects.filter(user_id=user_id).count(), 'Experience': ResumeExperiences.objects.filter(user_id=user_id).count(),
                   'Evidence': ResumeEvidence.objects.filter(experience__user_id=user_id).count(), 'Binding': ResumeExperienceBindings.objects.filter(resume__user_id=user_id).count(),
                   'Application': Applications.objects.filter(user_id=user_id).count(), 'ApplicationQuestion': ApplicationQuestions.objects.filter(application__user_id=user_id).count()},
        'planner': plan.model_dump(mode='json') if plan else None, 'ai_mode': settings.LOCAL_AI_MODE,
        'data_mode': 'real' if META in app.base_resume.content else 'mock',
        'registration': registration_state(app.base_resume),
        'resume_items': [dict(section=section, item_key=section+':'+item['id'],
            title=item.get('name') or item.get('company') or item.get('course') or item.get('school') or '',
            initialized=bindings.filter(resume=app.base_resume,item_key=section+':'+item['id']).exists())
            for section in ('projects','experience','education','trainingExperience','otherActivities')
            for item in app.base_resume.content.get(section, []) if isinstance(item,dict) and item.get('id') and item.get('description')],
        'requirement_profile_linked': bool(app.requirement_profile_id),
        'semantic_status': 'Planner Phase 4A.7 GO; Writer readiness is question-specific'}


@endpoint('POST')
def create(request, body):
    uid = request.lms_user['id']
    role = open_role(user_id=uid, role_id=body['role_id'])
    if body.get('data_mode')=='real':
        job=imported_job(uid,body['base_resume_id'],role.pk)
        body={**body,'job_snapshot_hash':job['snapshot_hash']}
    app = create_or_open_application(user_id=uid, application_id=body.get('application_id'),
        base_resume_id=body['base_resume_id'], role_context_id=str(role.pk),
        job_id=role.job_id if body.get('job_snapshot_hash') else None,
        idempotency_key=body['idempotency_key'], entry_source=body.get('entry_source', 'job_first'),
        target_snapshot={**({'snapshot_hash': body['job_snapshot_hash']} if role.job_id and body.get('job_snapshot_hash') else {}), 'role_version': role.content_hash,
                         'company_name': role.company.company_name, 'job_title': role.role_name,
                         'recruit_role_snapshot': role_snapshot(role)})
    return detail(uid, app.pk)


@endpoint('GET')
def read(request, body, application_id):
    return detail(request.lms_user['id'], application_id)


@endpoint('POST')
def tailor(request, body, application_id):
    uid = request.lms_user['id']
    ensure_tailored_resume(user_id=uid, application_id=application_id)
    return detail(uid, application_id)


@endpoint('POST')
def questions(request, body, application_id):
    uid = request.lms_user['id']
    rows = import_role_questions(user_id=uid, application_id=application_id)
    # Seeded fictional intent answers, not Experience facts or production data.
    if request.lms_user['email'] == EMAIL and [q.raw_text for q in rows] == fixture()['questions']:
        for answer in fixture()['answers']:
            save_answer(user_id=uid, question_id=rows[1].pk, answer_key='local:' + answer['confirmation_key'],
                content=answer['content'], source_type=answer['source_type'], status='confirmed',
                confirmation_key=answer['confirmation_key'], topic_resolved=True)
    return detail(uid, application_id)


@endpoint('POST')
def analyze(request, body, application_id):
    import time
    tick=time.perf_counter()
    uid = request.lms_user['id']
    analyze_questions(user_id=uid, application_id=application_id, client=planning_client(body.get('ai_mode'),user_id=uid,application_id=application_id))
    return {**detail(uid,application_id),'telemetry':{'analyzer_time':time.perf_counter()-tick}}


@endpoint('POST')
def plan(request, body, application_id):
    import time
    tick=time.perf_counter()
    uid = request.lms_user['id']
    plan_application(user_id=uid, application_id=application_id, client=planning_client(body.get('ai_mode'),user_id=uid,application_id=application_id))
    return {**detail(uid,application_id),'telemetry':{'planner_time':time.perf_counter()-tick}}


def writer_request(uid,application_id):
    from .application_answer_writer import prepare_request
    from app.application_writing.models import ContextMaterial
    from .application_question_store import planning_input
    data,_=planning_input(user_id=uid,application_id=application_id)
    intent=[]
    for index,a in enumerate(data.answers):
        if a.topic_resolved and not a.target_experience_id:
            intent.append(ContextMaterial(material_id='intent:'+str(index),source_type='applicant_intent',
                question_id=a.question_id,key=a.confirmation_key,normalized_text=a.content,
                source_quote=a.content,answer_index=index))
    return prepare_request(user_id=uid,application_id=application_id,materials=intent),intent


@endpoint('GET')
def writer_readiness(request,body,application_id):
    from app.application_writing.engine import readiness,writer_input
    uid=request.lms_user['id']; app=open_application(user_id=uid,application_id=application_id)
    try:
        data,_=writer_request(uid,application_id)
        rows=[dict(**readiness(data,str(q.pk)).model_dump(mode='json'),
            preview=writer_input(data,str(q.pk))) for q in app.questions.all()]
        return {'questions':rows,'materials':[m.model_dump(mode='json') for m in data.materials]}
    except ValueError as exc:
        return {'questions':[dict(question_id=str(q.pk),status='BLOCKED',issues=[str(exc)],missing_information=[]) for q in app.questions.all()], 'materials':[]}


@endpoint('POST')
def write(request,body,application_id):
    import time
    from .application_answer_writer import generate_answer
    from .local_resume_e2e_ai import writing_client,execution_mode
    from app.application_writing.models import AnswerResult,ReadinessResult
    from app.application_writing.engine import readiness
    uid=request.lms_user['id']; app=open_application(user_id=uid,application_id=application_id)
    q=app.questions.get(pk=body['question_id']); started=time.perf_counter()
    try: data,intent=writer_request(uid,application_id); gate=readiness(data,str(q.pk))
    except ValueError as exc: gate=ReadinessResult(question_id=str(q.pk),status='BLOCKED',issues=[str(exc)]); data=None
    gate_time=time.perf_counter()-started
    if gate.status!='READY':
        result=AnswerResult(question_id=str(q.pk),status=gate.status,readiness=gate)
        return {'result':result.model_dump(mode='json'),'final_text':'','telemetry':{'llm_calls':0,'readiness_time':gate_time,'total_time':time.perf_counter()-started}}
    mode=execution_mode(body.get('ai_mode','mock'))
    class Measured:
        def __init__(self): self.inner=None; self.times={'writer_time':0,'fact_quality_validation_time':0}; self.calls=0
        def client(self):
            if self.inner is None: self.inner=writing_client(mode,user_id=uid,application_id=application_id)
            return self.inner
        def write(self,payload,*,rewrite=None):
            tick=time.perf_counter(); self.calls+=1
            try: return self.client().write(payload,rewrite=rewrite)
            finally: self.times['writer_time']+=time.perf_counter()-tick
        def verify(self,payload):
            tick=time.perf_counter(); self.calls+=1
            try: return self.client().verify(payload)
            finally: self.times['fact_quality_validation_time']+=time.perf_counter()-tick
    client=Measured()
    result=generate_answer(user_id=uid,application_id=application_id,question_id=q.pk,client=client,materials=intent)
    return {'result':result.model_dump(mode='json'),'final_text':result.final_text,
        'materials':[m.model_dump(mode='json') for m in data.materials],
        'telemetry':{**client.times,'readiness_time':gate_time,'total_time':time.perf_counter()-started,
            'mode':mode,'llm_calls':client.calls if mode=='live' else 0,'mock_calls':client.calls if mode=='mock' else 0,
            'input_tokens':None if mode=='live' else 0,'output_tokens':None if mode=='live' else 0}}


@endpoint('POST')
def extract_evidence(request,body,application_id):
    """Explicit first Review: lazy resolver -> existing full v2 engine -> persistence."""
    import os
    from django.db import transaction
    from .local_resume_e2e_ai import execution_mode
    from .resume_experience_store import build_v2_review_input, ensure_resume_item_binding, SECTIONS
    from app.resume_review_v2.llm import LangChainReviewLLM
    from app.resume_review_v2.engine import ReviewEngineV2
    from app.resume_review_v2.validation import _numbers, _technologies
    uid=request.lms_user['id']; app=open_application(user_id=uid,application_id=application_id)
    if execution_mode(body.get('ai_mode','mock'))!='live':
        raise ValueError('Raw real resume has no recorded Analyst result. Explicit Live analysis required; no manual preselected Evidence')
    if not os.environ.get('OPENAI_API_KEY'): raise ValueError('Explicit OPENAI_API_KEY required')
    locations = [(section,index) for section in SECTIONS
        for index,item in enumerate(app.base_resume.content.get(section, []))
        if isinstance(item,dict) and item.get('id') and section+':'+item['id']==body.get('item_key')]
    if len(locations)!=1: raise ValueError('Stable source item required')
    section,index=locations[0]
    if not app.base_resume.content[section][index].get('description'): raise ValueError('Source item text required')
    b=ensure_resume_item_binding(user_id=uid,resume_id=app.base_resume_id,section=section,index=index)
    data=build_v2_review_input(user_id=uid,resume_id=app.base_resume_id,item_key=b.item_key)
    client=LangChainReviewLLM(os.environ.get('LOCAL_AI_MODEL','gpt-6-luna'),os.environ.get('LOCAL_AI_REASONING_EFFORT','medium'))
    review=ReviewEngineV2(client).run(data)
    # No interpretation is prefilled by the import. Preserve the Analyst's
    # classifications only after source/contract checks, using the existing store.
    with transaction.atomic():
        fresh=build_v2_review_input(user_id=uid,resume_id=app.base_resume_id,item_key=b.item_key)
        if fresh.experience.content_hash!=data.experience.content_hash or fresh.experience.existing_evidence!=data.experience.existing_evidence:
            raise ValueError('Experience changed during analysis; discard output')
        for fact in review.extracted_evidence:
            if fact.source_type!='resume_text' or fact.assertion_state.value!='resume_stated' or fact.supersedes_evidence_ids or fact.conflicts_with_evidence_ids:
                raise ValueError('Initial resume analysis must not invent user answers/corrections')
            if _numbers(fact.normalized_fact)-_numbers(fact.evidence_quote) or _technologies(fact.normalized_fact)-_technologies(fact.evidence_quote):
                raise ValueError('Analyst expanded source number/technology')
            from .local_resume_e2e_data import digest
            if ResumeEvidence.objects.filter(experience=b.experience,source_type='resume_text',
                normalized_fact=fact.normalized_fact,evidence_quote=fact.evidence_quote).exclude(
                    assertion_state__in=['resume_stated','user_asserted']).exists():
                raise ValueError('Inactive historical fact cannot be resurrected by source reanalysis')
            ResumeEvidence.objects.get_or_create(experience=b.experience,
                source_id='local-analyst:'+digest([str(b.experience_id),data.experience.content_hash,fact.fact_type.value,fact.normalized_fact,fact.evidence_quote]),
                defaults=dict(fact_type=fact.fact_type.value,normalized_fact=fact.normalized_fact,evidence_quote=fact.evidence_quote,
                    source_type='resume_text',assertion_state='resume_stated'))
    return {**detail(uid,application_id),'review':review.model_dump(mode='json'),
        'telemetry':review.usage.model_dump(mode='json')}
