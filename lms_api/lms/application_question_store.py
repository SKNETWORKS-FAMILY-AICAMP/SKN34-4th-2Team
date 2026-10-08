"""Opt-in Phase 4A persistence boundary. Never creates Evidence or final answers."""
import hashlib
import json
import sys
from pathlib import Path
from typing import get_args

from django.db import transaction

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'cover_letter_rag'))
from app.application_planning.engine import parse_constraints, validate_analysis, validate_plan
from app.application_planning.models import (
    ANALYSIS_VERSION, VERSION, AskKey, Constraints, Question, QuestionAnalysis,
    Fact, PlanningExperience, PlanningInput, AnswerDocument, PlanningResult,
)
from .models import (Applications, ApplicationQuestions, ApplicationAnswers, ApplicationPlans,
                     ResumeExperienceBindings, ResumeEvidence)
from .application_workspace import open_application, application_evidence


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _lock_app(user_id, application_id):
    return Applications.objects.select_for_update().get(pk=application_id, user_id=user_id)


@transaction.atomic
def import_questions(*, user_id, application_id, questions, source_type='manual', source_reference='',
                     constraints_overrides=None):
    _lock_app(user_id, application_id)
    if source_type not in {'manual', 'recruit_role', 'job_posting', 'document_extraction', 'legacy'}:
        raise ValueError('Unknown question source')
    if not isinstance(source_reference, str) or len(source_reference) > 255:
        raise ValueError('Invalid source reference')
    if constraints_overrides is not None and len(constraints_overrides) != len(questions):
        raise ValueError('Constraint metadata must align with source questions')
    rows = []
    for order, text in enumerate(questions):
        if not isinstance(text, str) or not text.strip(): raise ValueError('Question text required')
        constraints = parse_constraints(text)
        metadata = constraints_overrides[order] if constraints_overrides is not None else {}
        if metadata:
            if constraints.character_limit is not None and metadata.get('character_limit') is not None and constraints.character_limit != metadata['character_limit']:
                raise ValueError('Template limit contradicts question source text')
            if constraints.character_limit is not None and constraints.count_unit != 'unknown' and metadata.get('count_unit', constraints.count_unit) != constraints.count_unit:
                raise ValueError('Template count unit contradicts question source text')
            if constraints.include_spaces is not None and 'include_spaces' in metadata and metadata['include_spaces'] != constraints.include_spaces:
                raise ValueError('Template whitespace rule contradicts question source text')
            constraints = Constraints.model_validate({**constraints.model_dump(), **metadata})
        key = digest([source_type, source_reference, order, text])
        if metadata:
            key = digest([key, metadata])
        row, _ = ApplicationQuestions.objects.get_or_create(application_id=application_id, import_key=key,
            defaults=dict(order=order, raw_text=text, source_type=source_type,
                source_reference=source_reference, **constraints.model_dump()))
        # Import retry never overwrites user-edited snapshots.
        rows.append(row)
    return rows


def open_question(*, user_id, question_id):
    return ApplicationQuestions.objects.get(pk=question_id, application__user_id=user_id)


@transaction.atomic
def edit_question(*, user_id, question_id, raw_text):
    q = open_question(user_id=user_id, question_id=question_id)
    _lock_app(user_id, q.application_id)
    q.refresh_from_db()
    if not isinstance(raw_text, str) or not raw_text.strip(): raise ValueError('Question text required')
    if q.raw_text != raw_text:
        q.raw_text = raw_text
        for key, value in parse_constraints(raw_text).model_dump().items(): setattr(q, key, value)
        q.analysis = {}
        q.analysis_version = None
        q.analysis_input_hash = ''
        q.save()
    return q


def open_answer(*, user_id, answer_id):
    return ApplicationAnswers.objects.get(pk=answer_id, question__application__user_id=user_id)


@transaction.atomic
def save_answer(*, user_id, question_id, content, answer_key='draft', source_type='user_draft',
                status='draft', target_experience_id=None, confirmation_key='', topic_resolved=False):
    q = open_question(user_id=user_id, question_id=question_id)
    _lock_app(user_id, q.application_id)
    if source_type not in {'user_draft', 'user_supplement'} or status not in {'draft', 'confirmed'}:
        raise ValueError('Only user documents are supported; AI generation is not connected')
    if not isinstance(content, str) or not isinstance(answer_key, str) or not answer_key or len(answer_key) > 128:
        raise ValueError('Invalid answer')
    if confirmation_key and confirmation_key not in get_args(AskKey): raise ValueError('Unknown confirmation topic')
    if topic_resolved and (status != 'confirmed' or not content.strip() or target_experience_id or
        confirmation_key not in {'company_motivation','role_motivation','desired_work','future_plan'}):
        raise ValueError('Only explicit confirmed applicant intent can resolve an intent topic')
    if target_experience_id and not ResumeExperienceBindings.objects.filter(
        resume_id=q.application.base_resume_id, experience_id=target_experience_id,
        experience__user_id=user_id).exists():
        raise ValueError('Answer target is not a bound owned Experience')
    row, _ = ApplicationAnswers.objects.update_or_create(question=q, answer_key=answer_key,
        defaults=dict(content=content, source_type=source_type, status=status,
                      target_experience_id=target_experience_id, confirmation_key=confirmation_key,
                      topic_resolved=topic_resolved))
    return row


def _questions(app):
    return [Question(question_id=str(q.pk), raw_text=q.raw_text, constraints=Constraints(
        character_limit=q.character_limit, count_unit=q.count_unit, include_spaces=q.include_spaces))
        for q in app.questions.all()]


def _target(app):
    context = dict(app.target_snapshot)
    role = context.pop('recruit_role_snapshot', None)
    if role:
        context['recruit_role'] = {k: v for k, v in role.items() if k != 'questions'}
    context.update(job_id=app.job_id, role_context_id=app.role_context_id)
    if app.requirement_profile_id:
        from .requirement_profile_link import validate_profile
        from app.job_requirements import REQUIREMENT_PROMPT_VERSION
        validate_profile(app.requirement_profile,app.job_id,app.target_snapshot)
        context['requirement_profile_key'] = app.requirement_profile_id
        context['requirements'] = app.requirement_profile.requirements
        context['requirement_profile_source'] = dict(profile_key=app.requirement_profile_id,
            job_id=app.job_id,snapshot_hash=app.target_snapshot['snapshot_hash'],prompt_version=REQUIREMENT_PROMPT_VERSION)
    return context


def analyze_questions(*, user_id, application_id, client):
    app = open_application(user_id=user_id, application_id=application_id)
    questions, target = _questions(app), _target(app)
    if not questions: raise ValueError('Import questions first')
    before = digest(dict(questions=[q.model_dump() for q in questions], target=target))
    cached = list(app.questions.all())
    if all(q.analysis_version == ANALYSIS_VERSION and q.analysis_input_hash == before for q in cached):
        return [QuestionAnalysis.model_validate(q.analysis) for q in cached]
    # Structured clients may return shared Pydantic objects. Do not let their
    # output alias mutate the authoritative input used by validators.
    batch = validate_analysis(questions, client.analyze([q.model_copy(deep=True) for q in questions], dict(target)))
    with transaction.atomic():
        app = _lock_app(user_id, application_id)
        current = digest(dict(questions=[q.model_dump() for q in _questions(app)], target=_target(app)))
        if before != current: raise ValueError('Question/target changed during analysis; retry required')
        rows = {str(q.pk): q for q in app.questions.all()}
        for analysis in batch.questions:
            q = rows[analysis.question_id]
            q.analysis = analysis.model_dump(mode='json')
            q.analysis_version, q.analysis_input_hash = ANALYSIS_VERSION, before
            q.save(update_fields=['analysis', 'analysis_version', 'analysis_input_hash', 'updated_at'])
    return batch.questions


def planning_input(*, user_id, application_id, previous_question_keys=()):
    app = open_application(user_id=user_id, application_id=application_id)
    rows = list(app.questions.all())
    analysis_hash = digest(dict(questions=[q.model_dump() for q in _questions(app)], target=_target(app)))
    if not rows or any(q.analysis_version != ANALYSIS_VERSION or q.analysis_input_hash != analysis_hash for q in rows):
        raise ValueError('Question analysis is missing or stale')
    active = application_evidence(user_id=user_id, application_id=application_id)
    bindings = ResumeExperienceBindings.objects.filter(resume_id=app.base_resume_id).select_related('experience').order_by('item_key')
    experiences = {}
    for binding in bindings:
        exp = binding.experience
        if exp.user_id != user_id: raise ValueError('Experience ownership mismatch')
        if exp.status != 'active': continue
        experiences[str(exp.pk)] = PlanningExperience(experience_id=str(exp.pk), title=exp.title, kind=exp.kind,
            evidence=[Fact(evidence_id=str(e.pk), experience_id=str(exp.pk), fact_type=e.fact_type,
                           normalized_fact=e.normalized_fact, assertion_state=e.assertion_state)
                      for e in active[str(exp.pk)]])
    answers = [AnswerDocument(question_id=str(a.question_id), content=a.content, source_type=a.source_type,
        target_experience_id=str(a.target_experience_id) if a.target_experience_id else None,
        confirmation_key=a.confirmation_key if a.status == 'confirmed' else '', topic_resolved=a.topic_resolved)
        for a in ApplicationAnswers.objects.filter(question__application=app,
            source_type__in=['user_draft', 'user_supplement']).order_by('id')]
    data = PlanningInput(application_id=str(app.pk), questions=[QuestionAnalysis.model_validate(q.analysis) for q in rows],
        experiences=list(experiences.values()), target_context=_target(app), answers=answers,
        previous_question_keys=list(previous_question_keys))
    # State/history signature invalidates old plans; history text never goes to Planner.
    history = list(ResumeEvidence.objects.filter(experience_id__in=experiences).order_by('id').values(
        'id', 'assertion_state', 'normalized_fact', 'updated_at'))
    signature = [dict(id=str(h['id']), state=h['assertion_state'], fact=h['normalized_fact'],
                      updated_at=h['updated_at'].isoformat()) for h in history]
    return data, digest(dict(data=data.model_dump(mode='json'), history=signature, version=VERSION))


def plan_application(*, user_id, application_id, client, previous_question_keys=()):
    data, before = planning_input(user_id=user_id, application_id=application_id,
                                  previous_question_keys=previous_question_keys)
    cached = ApplicationPlans.objects.filter(application_id=application_id, input_hash=before, version=VERSION).first()
    if cached: return PlanningResult.model_validate(cached.content)
    result = validate_plan(data, client.plan(data.model_copy(deep=True)))
    with transaction.atomic():
        _lock_app(user_id, application_id)
        fresh, current = planning_input(user_id=user_id, application_id=application_id,
                                        previous_question_keys=previous_question_keys)
        if current != before: raise ValueError('Planning inputs changed; retry required')
        validate_plan(fresh, result.plan)
        ApplicationPlans.objects.update_or_create(application_id=application_id,
            defaults=dict(input_hash=before, version=VERSION, content=result.model_dump(mode='json')))
    return result


def reusable_plan(*, user_id, application_id, previous_question_keys=()):
    _, current = planning_input(user_id=user_id, application_id=application_id,
                               previous_question_keys=previous_question_keys)
    row = ApplicationPlans.objects.filter(application_id=application_id, input_hash=current, version=VERSION).first()
    return PlanningResult.model_validate(row.content) if row else None
