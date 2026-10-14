"""Opt-in dev/service boundary. Not wired to production API; no schema change."""
from django.db import transaction
from . import application_question_store as store
from .models import ApplicationPlans, ApplicationAnswers
from .application_workspace import open_application
from app.application_planning.models import VERSION, PlanningResult
from app.application_writing.models import WriteRequest, AnswerResult, ReadinessResult, WriterOutput, AnswerSentence
from app.application_writing.engine import run_answer
from app.application_writing.requirement_context import build_requirement_materials


def prepare_request(*,user_id,application_id,materials=(),previous_question_keys=()):
    # Owned app + owned active Evidence + analysis and history hash: reuse the
    # existing boundary instead of believing a caller-supplied hash or plan.
    app=open_application(user_id=user_id,application_id=application_id)
    data,current=store.planning_input(user_id=user_id,application_id=application_id,
                                      previous_question_keys=previous_question_keys)
    saved=ApplicationPlans.objects.filter(application=app,input_hash=current,version=VERSION).first()
    if not saved: raise ValueError('Missing/stale plan: replan required')
    plan=PlanningResult.model_validate(saved.content).plan
    questions=store._questions(app)
    adapted=build_requirement_materials(data,plan,questions)
    return WriteRequest(planning_input=data,plan=plan,questions=questions,materials=[*materials,*adapted],
                        plan_input_hash=saved.input_hash,current_input_hash=current)


def generate_answer(*,user_id,application_id,question_id,client,materials=(),previous_question_keys=()):
    # Ownership failures are never converted into an information disclosure.
    app=open_application(user_id=user_id,application_id=application_id)
    q=store.open_question(user_id=user_id,question_id=question_id)
    if q.application_id!=app.pk: raise ValueError('Cross-application question')
    try:
        request=prepare_request(user_id=user_id,application_id=application_id,materials=materials,
                                previous_question_keys=previous_question_keys)
    except ValueError as exc:
        gate=ReadinessResult(question_id=str(q.pk),status='BLOCKED',issues=[str(exc)])
        return AnswerResult(question_id=str(q.pk),status='BLOCKED',readiness=gate)
    # No database transaction/locks held during external calls.
    previous=[WriterOutput(question_id=str(row.question_id),sentences=[AnswerSentence(
        text=row.content,support_refs=[],claim_types=[])])
        for row in ApplicationAnswers.objects.filter(question__application=app,
            source_type='ai_generated').exclude(question=q) if row.content.strip()]
    result=run_answer(request,str(q.pk),client,previous_answers=previous)
    if result.status!='READY': return result
    with transaction.atomic():
        store._lock_app(user_id,application_id)
        fresh=prepare_request(user_id=user_id,application_id=application_id,materials=materials,
                              previous_question_keys=previous_question_keys)
        if fresh.current_input_hash!=request.current_input_hash or fresh.plan!=request.plan:
            raise ValueError('Inputs/plan changed during writing; discard draft and replan')
        ApplicationAnswers.objects.update_or_create(question=q,answer_key='phase4b:'+request.current_input_hash,
            defaults=dict(content=result.final_text,source_type='ai_generated',status='draft',
                          target_experience=None,confirmation_key='',topic_resolved=False))
    # Existing table stores prose, NOT provenance JSON. Return full validation
    # audit separately; adding a durable audit column needs a future decision.
    return result
