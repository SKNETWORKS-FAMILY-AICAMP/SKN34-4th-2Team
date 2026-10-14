"""Opt-in common entry adapters; no production route switch and no LLM calls.

Caller supplies a stable operation key or explicit workspace id. Entry source is
not identity. Jobs/roles are external references; opening never fetches them.
"""
from copy import deepcopy
import hashlib
import json
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import Applications, JobRequirementProfiles, Resumes, ResumeTailorings, Users
from .resume_experience_store import clone_bindings_for_tailored_resume, load_active_evidence


def _owned_resume(user_id, resume_id):
    return Resumes.objects.get(pk=resume_id, user_id=user_id)


def open_application(*, user_id, application_id):
    return Applications.objects.select_related('base_resume', 'tailored_resume').get(
        pk=application_id, user_id=user_id)


def _snapshot(value):
    value = value or {}
    allowed = {'snapshot_hash', 'analysis_version', 'company_name', 'job_title',
               'role_version', 'description', 'recruit_role_snapshot'}
    if not isinstance(value, dict) or set(value) - allowed:
        raise ValueError('Only compact target version/labels/manual description are allowed')
    if any(not isinstance(v, str) or len(v) > 2000 for k, v in value.items()
           if k != 'recruit_role_snapshot'):
        raise ValueError('Target snapshot values must be bounded strings')
    if 'recruit_role_snapshot' in value:
        role = value['recruit_role_snapshot']
        if not isinstance(role, dict) or len(json.dumps(role, ensure_ascii=False)) > 100000:
            raise ValueError('Invalid role snapshot')
    return dict(value)


@transaction.atomic
def create_application(*, user_id, base_resume_id, idempotency_key, entry_source='manual',
                       job_id=None, role_context_id=None, target_snapshot=None,
                       requirement_profile_key=None, carried_from_id=None):
    if entry_source not in {'resume_first', 'job_first', 'manual'}:
        raise ValueError('Invalid entry_source')
    if not isinstance(idempotency_key, str) or not idempotency_key.strip() or len(idempotency_key) > 128:
        raise ValueError('A stable idempotency_key is required')
    for ref in (job_id, role_context_id):
        if ref is not None and (not isinstance(ref, str) or not ref or len(ref) > 255):
            raise ValueError('Invalid external target reference')
    snapshot = _snapshot(target_snapshot)
    native_role = False
    if role_context_id:
        try:
            role_uuid = UUID(role_context_id)
        except ValueError:
            pass  # Historical external string references remain supported.
        else:
            from .models import RecruitRoles
            native_role = RecruitRoles.objects.filter(pk=role_uuid).exists()
    if native_role or 'recruit_role_snapshot' in snapshot:
        from .recruit_role_store import open_role, role_snapshot
        role = open_role(user_id=user_id, role_id=role_context_id)
        if role.job_id and job_id and role.job_id != job_id:
            raise ValueError('Role and selected posting reference mismatch')
        if job_id is None and role.job_id and snapshot.get('snapshot_hash'):
            job_id=role.job_id
        source = role_snapshot(role)
        supplied = snapshot.get('recruit_role_snapshot')
        # A company display rename is not a Role content version change. New
        # snapshots always use the server label; retries return the frozen row.
        if (supplied is not None and {k: v for k, v in supplied.items() if k != 'company_name'} !=
            {k: v for k, v in source.items() if k != 'company_name'}) or snapshot.get('role_version') != role.content_hash:
            raise ValueError('Role source/snapshot mismatch')
        role_context_id = str(role.pk)
        snapshot['recruit_role_snapshot'] = source
        snapshot = _snapshot(snapshot)
    if job_id and not snapshot.get('snapshot_hash'):
        raise ValueError('Job target requires the selected posting snapshot hash')
    if role_context_id and not snapshot.get('role_version'):
        raise ValueError('Role target requires a version reference')
    # Native Role UUID + content version define identity. Display labels in its
    # frozen source snapshot must not turn company renames into new operations.
    identity_snapshot = {k: v for k, v in snapshot.items() if k != 'recruit_role_snapshot'}
    identity = dict(base_resume_id=str(base_resume_id), job_id=job_id,
                    role_context_id=role_context_id, target_snapshot=identity_snapshot,
                    requirement_profile_key=requirement_profile_key,
                    carried_from_id=str(carried_from_id) if carried_from_id else None)
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    # Serialize creates for one owner; DB uniqueness remains the last line of defense.
    Users.objects.select_for_update().get(pk=user_id, is_active=True)
    existing = Applications.objects.filter(user_id=user_id, idempotency_key=idempotency_key).first()
    if existing:
        if existing.request_hash != digest:
            raise ValueError('Idempotency key reused with different request')
        return existing
    _owned_resume(user_id, base_resume_id)
    if carried_from_id:
        open_application(user_id=user_id, application_id=carried_from_id)
    from .requirement_profile_link import existing_profile
    profile=existing_profile(job_id,snapshot,requirement_profile_key)
    return Applications.objects.create(user_id=user_id, base_resume_id=base_resume_id,
        job_id=job_id, role_context_id=role_context_id, entry_source=entry_source,
        target_snapshot=snapshot, requirement_profile=profile,
        carried_from_id=carried_from_id, idempotency_key=idempotency_key, request_hash=digest)


def create_or_open_application(*, user_id, application_id=None, **kwargs):
    if application_id:
        app = open_application(user_id=user_id, application_id=application_id)
        for key in ('base_resume_id', 'job_id', 'role_context_id'):
            if key in kwargs and str(kwargs[key]) != str(getattr(app, key)):
                raise ValueError('Explicit workspace does not match requested target')
        return app
    return create_application(user_id=user_id, **kwargs)


def _enter_application(entry_source, start_tailoring, kwargs):
    app = create_or_open_application(entry_source=entry_source, **kwargs)
    if start_tailoring:
        ensure_tailored_resume(user_id=kwargs['user_id'], application_id=app.pk)
        app = open_application(user_id=kwargs['user_id'], application_id=app.pk)
    return app


def resume_first_application(*, start_tailoring=False, **kwargs):
    return _enter_application('resume_first', start_tailoring, kwargs)


def job_first_application(*, start_tailoring=False, **kwargs):
    return _enter_application('job_first', start_tailoring, kwargs)


def reopen_application(*, user_id, application_id):
    # Opening an archived/submitted workspace does not change its business status.
    return open_application(user_id=user_id, application_id=application_id)


def carry_application_context(*, user_id, application_id, idempotency_key, **overrides):
    source = open_application(user_id=user_id, application_id=application_id)
    args = dict(base_resume_id=source.base_resume_id, job_id=source.job_id,
                role_context_id=source.role_context_id, target_snapshot=source.target_snapshot,
                requirement_profile_key=source.requirement_profile_id, entry_source='manual')
    args.update(overrides)
    # Only NEW descendants can be created: no reparent/update operation, hence no cycles.
    return create_application(user_id=user_id, idempotency_key=idempotency_key,
                              carried_from_id=source.pk, **args)


@transaction.atomic
def attach_tailored_resume(*, user_id, application_id, tailored_resume_id):
    app = Applications.objects.select_for_update().get(pk=application_id, user_id=user_id)
    tailored = _owned_resume(user_id, tailored_resume_id)
    if tailored.base_resume_id != app.base_resume_id or tailored.is_base_resume:
        raise ValueError('Tailored resume must derive from this base')
    if tailored.linked_job_id != app.job_id:
        raise ValueError('Tailored resume target mismatch')
    if app.job_id:
        meta = ResumeTailorings.objects.get(resume=tailored)
        if meta.job_snapshot_hash != app.target_snapshot.get('snapshot_hash'):
            raise ValueError('Tailored resume posting version mismatch')
    if app.tailored_resume_id and app.tailored_resume_id != tailored.pk:
        raise ValueError('Workspace already has a tailored resume')
    if Applications.objects.filter(tailored_resume=tailored).exclude(pk=app.pk).exists():
        raise ValueError('Tailored documents cannot be shared across workspaces')
    clone_bindings_for_tailored_resume(user_id=user_id, source_resume_id=app.base_resume_id,
                                     tailored_resume_id=tailored.pk)
    app.tailored_resume = tailored
    app.save(update_fields=['tailored_resume', 'updated_at'])
    return app


@transaction.atomic
def ensure_tailored_resume(*, user_id, application_id):
    """Lazy application-scoped copy; reuse existing binding copier, not an AI writer.

    Unlike the v1 global (base, job, hash) cache, distinct workspaces need distinct
    mutable documents. Explicit legacy copies may be attached separately.
    """
    app = Applications.objects.select_for_update().get(pk=application_id, user_id=user_id)
    if app.tailored_resume_id:
        return _owned_resume(user_id, app.tailored_resume_id)
    base = Resumes.objects.select_for_update().get(pk=app.base_resume_id, user_id=user_id)
    content = deepcopy(base.content)
    copied = Resumes.objects.create(user_id=user_id, cohort_id=base.cohort_id,
        base_resume=base, linked_job_id=app.job_id, is_base_resume=False,
        legacy_id=f'application:{app.pk}', title=base.title, status='writing', content=content,
        created_at=timezone.now(), updated_at=timezone.now())
    ResumeTailorings.objects.create(resume=copied,
        source_resume_hash=hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        job_snapshot_hash=app.target_snapshot.get('snapshot_hash', ''),
        company_name=app.target_snapshot.get('company_name', ''),
        job_title=app.target_snapshot.get('job_title', ''))
    attach_tailored_resume(user_id=user_id, application_id=app.pk, tailored_resume_id=copied.pk)
    return copied


def application_evidence(*, user_id, application_id):
    """Read current shared evidence only. NEVER re-extract facts from resume text.

    Future extraction MUST reconcile same-experience inactive history before
    persisting resume_stated facts; this reader does not authorize resurrection.
    """
    app = open_application(user_id=user_id, application_id=application_id)
    from .models import ResumeExperienceBindings
    ids = ResumeExperienceBindings.objects.filter(resume_id=app.base_resume_id).values_list('experience_id', flat=True).distinct()
    return {str(eid): load_active_evidence(user_id=user_id, experience_id=eid) for eid in ids}
