"""Local document registration. No analysis, bindings, evidence or target linkage."""
from copy import deepcopy
import hashlib
import json
from django.conf import settings
from django.db import connection, transaction
from .models import Resumes, Users
from .local_resume_e2e_fixture import EMAIL

META = '_local_e2e_import'


def local_guard():
    if not getattr(settings, 'LOCAL_RESUME_E2E', False) or connection.settings_dict['HOST'] not in {'localhost', '127.0.0.1'}:
        raise RuntimeError('Local-only DB required; remote/RDS write prohibited')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def import_bundle(bundle, *, approved=False):
    local_guard()
    return _register_resume(bundle, approved=approved)


@transaction.atomic
def _register_resume(bundle, *, approved=False):
    if not approved or bundle.get('permission') not in {'self', 'explicitly_approved', 'sanitized'}:
        raise ValueError('Explicit approved/sanitized source required')
    if bundle.get('version') != 1 or not bundle.get('source_resume_id'):
        raise ValueError('Version and stable source_resume_id required')
    if any(bundle.get(k) for k in ('evidence', 'experiences', 'recordings', 'intent_answers', 'jobs', 'target_context')):
        raise ValueError('Resume registration accepts source content only, not analysis or job data')
    content = deepcopy(bundle['resume']['content'])
    if not isinstance(content, dict) or META in content:
        raise ValueError('Invalid resume content')
    title = bundle['resume']['title']
    if not isinstance(title, str) or not title.strip():
        raise ValueError('Resume title required')
    user = Users.objects.select_for_update().get(email=EMAIL, is_active=True)
    key = 'local-real:' + digest(bundle['source_resume_id'])
    identity = digest({'resume': bundle['resume'], 'source_text': bundle.get('source_text', '')})
    existing = Resumes.objects.filter(legacy_id=key, user=user).first()
    if existing:
        if existing.content.get(META, {}).get('registration_hash') != identity:
            raise ValueError('Source changed: use a new explicit version; never overwrite reviewed data')
        return existing
    content[META] = {'source_resume_id': bundle['source_resume_id'], 'registration_hash': identity,
        'permission': bundle['permission'], 'source_text': bundle.get('source_text', '')}
    return Resumes.objects.create(legacy_id=key, user=user, cohort=user.cohort,
        title=title, content=content, is_base_resume=False, status='local_test_copy')


def import_jobs(resume_id, jobs, *, approved=False):
    """Separate explicit job-copy operation; never called by resume registration."""
    local_guard()
    if not approved:
        raise ValueError('Explicit approved job source required')
    return _import_jobs(resume_id, jobs)


@transaction.atomic
def _import_jobs(resume_id, jobs):
    from .models import JobRequirementProfiles
    from .recruit_role_store import company_profile, submit_role
    from app.job_requirements import requirement_cache_key
    from app.application_writing.requirement_context import validate_requirements
    user = Users.objects.get(email=EMAIL, is_active=True)
    resume = Resumes.objects.select_for_update().get(pk=resume_id, user=user, status='local_test_copy')
    if META not in resume.content:
        raise ValueError('Registered local resume required')
    admin = Users.objects.get(firebase_uid='local-resume-e2e-admin', role='admin')
    stored = resume.content[META].setdefault('jobs', [])
    for job in jobs:
        if not job.get('job_id') or not job.get('snapshot_hash') or not job.get('description'):
            raise ValueError('Actual posting identity and original text required')
        profile = job.get('requirement_profile')
        if profile:
            if profile['key'] != requirement_cache_key(job):
                raise ValueError('Profile key must match posting snapshot, not role hash')
            validate_requirements(profile['requirements'])
            row, created = JobRequirementProfiles.objects.get_or_create(key=profile['key'], defaults={'requirements': profile['requirements']})
            if not created and row.requirements != profile['requirements']:
                raise ValueError('Conflicting existing profile; refusing overwrite')
        company = company_profile(user_id=admin.pk, company_name=job['company'])
        role = submit_role(user_id=user.pk, company_id=company.pk,
            season='LOCAL REAL '+digest([job['job_id'], job['snapshot_hash']]), role_name=job['title'],
            role_description=job['description'], job_id=job['job_id'],
            requirements={k: job.get(v, []) for k,v in [('required','required_skills'),('preferred','preferred_skills'),('responsibilities','responsibilities')]},
            questions=job.get('questions', []))
        copied = {**deepcopy(job), 'role_id': str(role.pk)}
        previous = next((j for j in stored if (j['job_id'], j['snapshot_hash']) == (job['job_id'], job['snapshot_hash'])), None)
        if previous and previous != copied:
            raise ValueError('Existing imported job changed; refusing overwrite')
        if not previous:
            stored.append(copied)
    resume.save(update_fields=['content'])
    return resume


def imported_resumes(user_id):
    return [r for r in Resumes.objects.filter(user_id=user_id, status='local_test_copy', base_resume__isnull=True) if META in r.content]


def imported_job(user_id, resume_id, role_id):
    resume = Resumes.objects.get(pk=resume_id, user_id=user_id, status='local_test_copy')
    return next(j for j in resume.content[META].get('jobs', []) if j['role_id'] == str(role_id))
