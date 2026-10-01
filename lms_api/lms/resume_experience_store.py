"""Opt-in persistence for offline Resume Review v2; no production v1 callers."""

import hashlib
import sys
import uuid
from pathlib import Path

from django.db import transaction
from django.db.models import Exists, OuterRef

from .models import ResumeEvidence, ResumeExperienceBindings, ResumeExperiences, Resumes


ACTIVE_STATES = ('resume_stated', 'user_asserted')
ITEM_KEY_FIELD = '_experience_item_key'
SECTIONS = {'projects': 'project', 'experience': 'employment', 'education': 'education',
            'trainingExperience': 'education', 'otherActivities': 'activity'}


def _item_key(section, item):
    native_id = item.get('id')
    if isinstance(native_id, str) and native_id:
        return f'{section}:{native_id}'
    return item.get(ITEM_KEY_FIELD)


def create_experience(*, user_id, kind, title, period_text=''):
    if kind not in set(SECTIONS.values()) | {'other'}:
        raise ValueError('unsupported experience kind')
    return ResumeExperiences.objects.create(
        user_id=user_id, kind=kind, title=title, period_text=period_text,
    )


def _owned_experience(experience_id, user_id, *, lock=False):
    query = ResumeExperiences.objects
    if lock:
        query = query.select_for_update()
    experience = query.filter(pk=experience_id, user_id=user_id).first()
    if experience is None:
        raise PermissionError('experience does not belong to user')
    return experience


def bind_resume_item(*, user_id, resume_id, experience_id, item_key, field_path, display_order):
    """Attach a stable item key; a position/field_path never identifies an Experience."""
    with transaction.atomic():
        resume = Resumes.objects.select_for_update().filter(pk=resume_id, user_id=user_id).first()
        if resume is None:
            raise PermissionError('resume does not belong to user')
        experience = _owned_experience(experience_id, user_id)
        if not item_key or len(item_key) > 80:
            raise ValueError('invalid item key')
        matches = [
            (section, index)
            for section in SECTIONS
            for index, item in enumerate((resume.content or {}).get(section, []))
            if isinstance(item, dict) and _item_key(section, item) == item_key
        ]
        if len(matches) != 1:
            raise ValueError('stable item key must identify exactly one resume item')
        section, index = matches[0]
        if field_path != f'{section}[{index}].description' or display_order != index:
            raise ValueError('binding locator does not match stable item key')
        binding, created = ResumeExperienceBindings.objects.get_or_create(
            resume=resume, item_key=item_key,
            defaults={'experience': experience, 'field_path': field_path, 'display_order': display_order},
        )
        if not created:
            if binding.experience_id != experience.id:
                raise ValueError('item already bound to another Experience')
            binding.field_path = field_path
            binding.display_order = display_order
            binding.save(update_fields=['field_path', 'display_order', 'updated_at'])
        return binding


def ensure_resume_item_binding(*, user_id, resume_id, section, index, _copy_chain=()):
    """Lazy, one-item migration. Persists a UUID key in the resume JSON on first use."""
    if section not in SECTIONS or not isinstance(index, int) or index < 0:
        raise ValueError('unsupported resume item')
    if resume_id in _copy_chain:
        raise ValueError('cyclic resume copy relationship')
    # Initialize a proven source before locking its copy, so opening the copy
    # first cannot give a stable item a second Experience. Lock ancestors first.
    probe = Resumes.objects.filter(pk=resume_id, user_id=user_id).first()
    if probe is None:
        raise PermissionError('resume does not belong to user')
    probe_items = (probe.content or {}).get(section, [])
    source_binding = None
    source_id = probe.source_tailored_resume_id or probe.base_resume_id
    if source_id and isinstance(probe_items, list) and index < len(probe_items) and isinstance(probe_items[index], dict):
        key = _item_key(section, probe_items[index])
        if not key:
            raise ValueError('legacy copy item has no stable identity; bind the source before copying')
        if key and not ResumeExperienceBindings.objects.filter(resume=probe, item_key=key).exists():
            source = Resumes.objects.filter(pk=source_id, user_id=user_id).first()
            if source is None:
                raise PermissionError('copy source does not belong to user')
            locations = [(name, pos) for name in SECTIONS
                         for pos, item in enumerate((source.content or {}).get(name, []))
                         if isinstance(item, dict) and _item_key(name, item) == key]
            if len(locations) > 1:
                raise ValueError('duplicate stable item key in copy source')
            if locations:
                name, pos = locations[0]
                source_binding = ensure_resume_item_binding(
                    user_id=user_id, resume_id=source_id, section=name, index=pos,
                    _copy_chain=(*_copy_chain, resume_id),
                )
            elif not probe_items[index].get('id'):
                raise ValueError('legacy copy key cannot be linked to its source item')
    with transaction.atomic():
        resume = Resumes.objects.select_for_update().filter(pk=resume_id, user_id=user_id).first()
        if resume is None:
            raise PermissionError('resume does not belong to user')
        content = resume.content if isinstance(resume.content, dict) else {}
        items = content.get(section)
        if not isinstance(items, list) or index >= len(items) or not isinstance(items[index], dict):
            raise ValueError('resume item not found')
        item = items[index]
        item_key = _item_key(section, item)
        if item_key is not None and (not isinstance(item_key, str) or not item_key):
            raise ValueError('invalid stable item key')
        if item_key and sum(
            _item_key(name, candidate) == item_key
            for name in SECTIONS for candidate in content.get(name, [])
            if isinstance(candidate, dict)
        ) > 1:
            raise ValueError('duplicate stable item key in resume')
        if not item_key:
            item_key = str(uuid.uuid4())
            item[ITEM_KEY_FIELD] = item_key
            resume.content = content
            resume.save(update_fields=['content'])
        field_path = f'{section}[{index}].description'
        binding = ResumeExperienceBindings.objects.filter(resume=resume, item_key=item_key).first()
        if binding is None:
            # A copy may have been created before the base item was bound. Reuse
            # an established source binding on lazy access, never infer by title.
            if source_binding and (source_binding.item_key != item_key or source_binding.resume_id != (
                resume.source_tailored_resume_id or resume.base_resume_id
            )):
                raise ValueError('resume copy source or stable item changed; retry binding')
            if source_binding:
                experience = source_binding.experience
            else:
                title = str(item.get('name') or item.get('company') or item.get('school') or '').strip()
                experience = create_experience(user_id=user_id, kind=SECTIONS[section], title=title,
                                               period_text=str(item.get('startDate') or ''))
            binding = bind_resume_item(user_id=user_id, resume_id=resume_id, experience_id=experience.id,
                                       item_key=item_key, field_path=field_path, display_order=index)
        else:
            _owned_experience(binding.experience_id, user_id)
            binding.field_path = field_path
            binding.display_order = index
            binding.save(update_fields=['field_path', 'display_order', 'updated_at'])
        return binding


def load_active_evidence(*, user_id, experience_id):
    _owned_experience(experience_id, user_id)
    unresolved = ResumeEvidence.objects.filter(
        experience_id=experience_id, assertion_state='uncertain', conflicts_with_evidence_id=OuterRef('pk'),
    )
    return list(ResumeEvidence.objects.filter(
        experience_id=experience_id, assertion_state__in=ACTIVE_STATES,
    ).annotate(has_unresolved_conflict=Exists(unresolved)).filter(
        has_unresolved_conflict=False,
    ).order_by('created_at', 'pk'))


def record_resume_evidence(*, user_id, experience_id, fact_type, normalized_fact,
                           evidence_quote, source_id, source_text):
    _owned_experience(experience_id, user_id)
    if not source_id or not evidence_quote or evidence_quote not in source_text:
        raise ValueError('source quote must occur in the supplied source text')
    return ResumeEvidence.objects.create(
        experience_id=experience_id, fact_type=fact_type, normalized_fact=normalized_fact,
        evidence_quote=evidence_quote, source_type='resume_text', source_id=source_id,
        assertion_state='resume_stated',
    )


def record_user_evidence(*, user_id, experience_id, fact_type, normalized_fact,
                         evidence_quote, answer_source_id, answer_text,
                         supersedes_evidence_id=None, uncertain_conflict_id=None):
    if supersedes_evidence_id and uncertain_conflict_id:
        raise ValueError('correction cannot be both certain and uncertain')
    if not answer_source_id or not evidence_quote or evidence_quote not in answer_text:
        raise ValueError('answer quote must occur in the supplied answer')
    if not normalized_fact.strip():
        raise ValueError('normalized fact required')
    with transaction.atomic():
        _owned_experience(experience_id, user_id, lock=True)
        # The Experience lock serializes retries as well as competing corrections.
        # A source can assert several atomic facts; each source/fact tuple is replayable.
        previous = ResumeEvidence.objects.filter(
            experience_id=experience_id, source_type='user_answer', source_id=answer_source_id,
            fact_type=fact_type, normalized_fact=normalized_fact,
        ).first()
        if previous is not None:
            if (previous.evidence_quote != evidence_quote
                    or str(previous.supersedes_evidence_id or '') != str(supersedes_evidence_id or '')
                    or str(previous.conflicts_with_evidence_id or '') != str(uncertain_conflict_id or '')):
                raise ValueError('source fact reused with different evidence or correction target')
            return previous
        target_id = supersedes_evidence_id or uncertain_conflict_id
        target = None
        if target_id:
            target = ResumeEvidence.objects.select_for_update().filter(
                pk=target_id, experience_id=experience_id, assertion_state__in=ACTIVE_STATES,
            ).first()
            if target is None:
                raise ValueError('correction target is not active in this Experience')
            if ResumeEvidence.objects.filter(
                experience_id=experience_id, assertion_state='uncertain', conflicts_with_evidence=target,
            ).exists() and supersedes_evidence_id:
                raise ValueError('resolve uncertain conflict before superseding')
        new = ResumeEvidence.objects.create(
            experience_id=experience_id, fact_type=fact_type, normalized_fact=normalized_fact,
            evidence_quote=evidence_quote, source_type='user_answer', source_id=answer_source_id,
            assertion_state='uncertain' if uncertain_conflict_id else 'user_asserted',
            supersedes_evidence=target if supersedes_evidence_id else None,
            conflicts_with_evidence=target if uncertain_conflict_id else None,
        )
        if supersedes_evidence_id:
            target.assertion_state = 'superseded'
            target.save(update_fields=['assertion_state', 'updated_at'])
        return new


def supersede_evidence(**kwargs):
    if not kwargs.get('supersedes_evidence_id'):
        raise ValueError('supersedes_evidence_id required')
    return record_user_evidence(**kwargs)


def clone_bindings_for_tailored_resume(*, user_id, source_resume_id, tailored_resume_id):
    """Copy only bindings for stable keys actually present in a proven resume copy."""
    with transaction.atomic():
        source = Resumes.objects.select_for_update().filter(pk=source_resume_id, user_id=user_id).first()
        target = Resumes.objects.select_for_update().filter(pk=tailored_resume_id, user_id=user_id).first()
        if source is None or target is None or source.pk == target.pk:
            raise PermissionError('both resumes must belong to the same user')
        if target.base_resume_id != source.pk and target.source_tailored_resume_id != source.pk:
            raise ValueError('resume copy relationship not established')
        target_locations = {}
        for section in SECTIONS:
            for index, item in enumerate((target.content or {}).get(section, [])):
                if isinstance(item, dict) and _item_key(section, item):
                    key = _item_key(section, item)
                    if key in target_locations:
                        raise ValueError('duplicate stable item key in tailored resume')
                    target_locations[key] = (f'{section}[{index}].description', index)
        existing = {row.item_key: row.experience_id for row in ResumeExperienceBindings.objects.filter(resume=target)}
        pending = []
        for binding in ResumeExperienceBindings.objects.filter(resume=source).select_related('experience'):
            if binding.experience.user_id != user_id:
                raise PermissionError('binding experience owner mismatch')
            if binding.item_key not in target_locations:
                continue
            field_path, display_order = target_locations[binding.item_key]
            if binding.item_key in existing and existing[binding.item_key] != binding.experience_id:
                raise ValueError('copy item already belongs to a different Experience')
            pending.append(ResumeExperienceBindings(
                resume=target, experience_id=binding.experience_id,
                item_key=binding.item_key, field_path=field_path,
                display_order=display_order,
            ))
        ResumeExperienceBindings.objects.bulk_create(
            pending, update_conflicts=True, update_fields=['field_path', 'display_order', 'updated_at'],
            unique_fields=['resume', 'item_key'],
        )
        return list(ResumeExperienceBindings.objects.filter(
            resume=target, item_key__in=[row.item_key for row in pending],
        ))


def build_v2_review_input(*, user_id, resume_id, item_key, question='', answer='', answer_source_id='',
                          job_requirements=()):
    """Persistence boundary. The offline v2 engine itself imports no Django modules."""
    # Django is launched from lms_api/, while the independent engine lives in a sibling tree.
    ai_root = str(Path(__file__).resolve().parents[2] / 'cover_letter_rag')
    if ai_root not in sys.path:
        sys.path.insert(0, ai_root)
    from app.resume_review_v2.models import (
        Evidence as DomainEvidence, Experience as DomainExperience, ReviewInput,
    )

    binding = ResumeExperienceBindings.objects.select_related('resume', 'experience').filter(
        resume_id=resume_id, resume__user_id=user_id, item_key=item_key,
        experience__user_id=user_id,
    ).first()
    if binding is None:
        raise PermissionError('owned binding not found')
    section, _, rest = binding.field_path.partition('[')
    if section not in SECTIONS or not rest:
        raise ValueError('unsupported binding locator')
    index_text, _, field = rest.partition('].')
    if not index_text.isdecimal() or not field:
        raise ValueError('invalid binding locator')
    items = (binding.resume.content or {}).get(section, [])
    index = int(index_text)
    if index >= len(items) or not isinstance(items[index], dict) or _item_key(section, items[index]) != item_key:
        locations = [
            (name, pos)
            for name in SECTIONS
            for pos, item in enumerate((binding.resume.content or {}).get(name, []))
            if isinstance(item, dict) and _item_key(name, item) == item_key
        ]
        if len(locations) != 1:
            raise ValueError('stable item key is missing or duplicated')
        section, index = locations[0]
        items = binding.resume.content[section]
        binding.field_path = f'{section}[{index}].description'
        binding.display_order = index
        binding.save(update_fields=['field_path', 'display_order', 'updated_at'])
    current_text = str(items[index].get(field) or '')
    evidence = [DomainEvidence(
        evidence_id=str(row.pk), experience_id=str(row.experience_id), fact_type=row.fact_type,
        normalized_fact=row.normalized_fact, evidence_quote=row.evidence_quote,
        source_type=row.source_type, source_id=row.source_id,
        assertion_state=row.assertion_state,
        # Historical supersession targets are intentionally not included in the active-only input.
        created_at=row.created_at, updated_at=row.updated_at,
    ) for row in load_active_evidence(user_id=user_id, experience_id=binding.experience_id)]
    return ReviewInput(
        experience=DomainExperience(
            experience_id=str(binding.experience_id), kind=binding.experience.kind,
            title=binding.experience.title, current_text=current_text,
            field_path=binding.field_path,
            content_hash=hashlib.sha256(current_text.encode('utf-8')).hexdigest(),
            existing_evidence=evidence,
        ),
        question=question, answer=answer, answer_source_id=answer_source_id,
        job_requirements=list(job_requirements),
    )
