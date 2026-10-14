"""Opt-in target context boundary. No applicant Evidence, crawling, or LLM calls.

Content versions are immutable through this service: submit a new version rather
than mutate a template already referenced by an Application. ORM is trusted
infrastructure, not a public permission boundary.
"""
import hashlib
import json
import re
import unicodedata

from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from .models import CompanyProfiles, RecruitRoles, Users, JobApplyMethod


def _actor(user_id):
    return Users.objects.get(pk=user_id, is_active=True)


def _admin(user_id):
    actor = _actor(user_id)
    if actor.role != 'admin':
        raise PermissionError('Admin moderation required')
    return actor


def canonical_company_key(name):
    text = unicodedata.normalize('NFKC', name).strip().casefold()
    text = re.sub(r'^(?:주식회사|\(주\)|㈜)\s*|\s*(?:주식회사|\(주\)|㈜)$', '', text)
    text = re.sub(r'\s+', '', text)
    if not text or len(text) > 255:
        raise ValueError('Invalid company lookup key')
    return text


def _canonical(value):
    if isinstance(value, str):
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', value)).strip()
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    return value


def content_hash(description, requirements, questions):
    body = _canonical(dict(role_description=description, requirements=requirements, questions=questions))
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def validate_content(description, requirements, questions):
    from .application_question_store import Constraints
    if not isinstance(description, str):
        raise ValueError('Description must preserve source text')
    # Existing extractor uses an array of JobRequirement objects (must/preferred/task).
    # Also accept the source template's required/preferred/responsibilities object.
    if isinstance(requirements, dict):
        if set(requirements) - {'required', 'preferred', 'responsibilities'} or any(
            not isinstance(v, list) or any(not isinstance(item, str) for item in v)
            for v in requirements.values()):
            raise ValueError('Invalid source requirements')
    elif isinstance(requirements, list):
        from app.job_requirements import JobRequirement
        requirements = [JobRequirement.model_validate(item).model_dump(mode='json') for item in requirements]
    else:
        raise ValueError('Invalid requirements')
    if not isinstance(questions, list):
        raise ValueError('Question templates must be a list')
    normalized, orders = [], set()
    for index, q in enumerate(questions):
        if not isinstance(q, dict) or set(q) - {'order', 'text', 'character_limit', 'count_unit', 'include_spaces'}:
            raise ValueError('Invalid question template')
        order = q.get('order', index + 1)
        if type(order) is not int or order < 0 or order in orders or not isinstance(q.get('text'), str) or not q['text'].strip():
            raise ValueError('Question order/text invalid')
        orders.add(order)
        metadata = {k: q[k] for k in ('character_limit', 'count_unit', 'include_spaces') if k in q}
        Constraints.model_validate(metadata)
        normalized.append(dict(order=order, text=q['text'], **metadata))
    return requirements, sorted(normalized, key=lambda q: q['order'])


def company_profile(*, user_id, company_name, company_key=None, **metadata):
    _admin(user_id)
    if not isinstance(company_name, str) or not company_name.strip() or len(company_name) > 255:
        raise ValueError('Company name required')
    if set(metadata) - {'company_type', 'logo_url', 'homepage_url'}:
        raise ValueError('Unknown company metadata')
    key = canonical_company_key(company_key or company_name)
    defaults = dict(company_name=company_name, **metadata)
    candidate = CompanyProfiles(company_key=key, **defaults)
    candidate.full_clean(validate_unique=False)
    row, _ = CompanyProfiles.objects.get_or_create(company_key=key, defaults=defaults)
    # Lookup is never an implicit rename/metadata overwrite.
    return row


def update_company(*, user_id, company_id, **changes):
    _admin(user_id)
    if set(changes) - {'company_name', 'company_key', 'company_type', 'logo_url', 'homepage_url'}:
        raise ValueError('Unknown company metadata')
    if 'company_key' in changes:
        changes['company_key'] = canonical_company_key(changes['company_key'])
    row = CompanyProfiles.objects.get(pk=company_id)
    for k, v in changes.items():
        setattr(row, k, v)
    row.full_clean()
    row.save()
    return row


def shared_roles():
    return RecruitRoles.objects.filter(source_type='company_site', verification_status='verified',
                                      source_url__isnull=False).exclude(source_url='')


def accessible_roles(user_id):
    actor = _actor(user_id)
    if actor.role == 'admin':
        return RecruitRoles.objects.all()
    return RecruitRoles.objects.filter(Q(created_by_id=user_id) | Q(pk__in=shared_roles().values('pk')))


def open_role(*, user_id, role_id):
    return accessible_roles(user_id).select_related('company').get(pk=role_id)


@transaction.atomic
def submit_role(*, user_id, company_id, season, role_name, role_description,
                requirements=None, questions=None, source_type='other', source_url=None, job_id=None):
    actor = _actor(user_id)
    if source_type not in {'company_site', 'other'}:
        raise ValueError('Unknown source')
    requirements, questions = validate_content(role_description,
        {} if requirements is None else requirements, [] if questions is None else questions)
    # Serialize submissions for one company; conditional DB uniqueness is final defense.
    company = CompanyProfiles.objects.select_for_update().get(pk=company_id)
    identity = dict(company=company, season=season.strip(), role_name=role_name.strip(),
                    content_hash=content_hash(role_description, requirements, questions), source_type=source_type)
    if source_type == 'other':
        identity['dedupe_owner'] = str(actor.pk)
    existing = RecruitRoles.objects.filter(**identity).first()
    if existing:
        # Do not expose another user's pending official submission.
        return open_role(user_id=user_id, role_id=existing.pk)
    row = RecruitRoles(**identity, role_description=role_description, requirements=requirements,
        questions=questions, source_url=source_url, job_id=job_id, created_by=actor)
    row.full_clean(validate_unique=False, validate_constraints=False)
    row.save()
    return row


@transaction.atomic
def moderate_role(*, user_id, role_id, status):
    actor = _admin(user_id)
    if status not in {'unverified', 'verified', 'rejected'}:
        raise ValueError('Unknown verification state')
    row = RecruitRoles.objects.select_for_update().get(pk=role_id)
    if status == 'verified' and row.source_type == 'company_site' and not row.source_url:
        raise ValueError('Official sharing requires a traceable source URL')
    row.verification_status = status
    row.verified_by = actor if status != 'unverified' else None
    row.verified_at = timezone.now() if status != 'unverified' else None
    row.save(update_fields=['verification_status', 'verified_by', 'verified_at', 'updated_at'])
    return row


@transaction.atomic
def delete_role(*, user_id, role_id):
    actor = _actor(user_id)
    row = accessible_roles(user_id).select_for_update().get(pk=role_id)
    if actor.role != 'admin' and (row.created_by_id != user_id or row.verification_status == 'verified'):
        raise PermissionError('Verified context requires admin moderation')
    row.delete()  # Application keeps its existing external reference + frozen snapshot.


def role_snapshot(role):
    return dict(role_id=str(role.pk), content_hash=role.content_hash, company_name=role.company.company_name,
        season=role.season, role_name=role.role_name, role_description=role.role_description,
        requirements=role.requirements, questions=role.questions)


def create_role_application(*, user_id, role_id, **kwargs):
    from .application_workspace import create_application
    with transaction.atomic():
        role = open_role(user_id=user_id, role_id=role_id)
        snapshot = dict(kwargs.pop('target_snapshot', {}) or {})
        snapshot.update(role_version=role.content_hash, recruit_role_snapshot=role_snapshot(role))
        app = create_application(user_id=user_id, role_context_id=str(role.pk), target_snapshot=snapshot, **kwargs)
        return app


@transaction.atomic
def import_role_questions(*, user_id, application_id):
    from .application_question_store import import_questions
    from .models import Applications
    app = Applications.objects.select_for_update().get(pk=application_id, user_id=user_id)
    snapshot = app.target_snapshot.get('recruit_role_snapshot')
    if not snapshot or snapshot['role_id'] != app.role_context_id:
        raise ValueError('No native RecruitRole snapshot')
    # If source still exists, check permission again; a deleted source uses owned snapshot.
    if RecruitRoles.objects.filter(pk=app.role_context_id).exists():
        open_role(user_id=user_id, role_id=app.role_context_id)
    templates = snapshot['questions']
    reference = f"{app.role_context_id}:{snapshot['content_hash']}"
    previously_imported = app.questions.filter(source_type='recruit_role', source_reference=reference).exists()
    rows = import_questions(user_id=user_id, application_id=app.pk,
        questions=[q['text'] for q in templates],
        constraints_overrides=[{k: q[k] for k in ('character_limit', 'count_unit', 'include_spaces') if k in q} for q in templates],
        source_type='recruit_role', source_reference=reference)
    # Increment once for the first import, not each retry (snapshot rows may be edited).
    # Count is derived telemetry; serialized Application import guards concurrent retries.
    if rows and not previously_imported:
        RecruitRoles.objects.filter(pk=app.role_context_id).update(use_count=F('use_count') + 1)
    return rows


def set_job_apply_method(*, user_id, job_id, apply_method):
    _admin(user_id)
    if apply_method is not None and apply_method not in JobApplyMethod.values:
        raise ValueError('Unknown apply method')
    with connection.cursor() as cursor:
        cursor.execute('UPDATE jobs.jobs SET apply_method=%s WHERE job_id=%s', [apply_method, job_id])
        if cursor.rowcount != 1:
            raise ValueError('Job not found')
