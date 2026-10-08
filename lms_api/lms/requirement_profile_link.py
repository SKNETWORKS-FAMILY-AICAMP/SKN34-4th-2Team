"""Existing-profile lookup only. No extraction, jobs fetching, writes, or LLM."""
def expected_profile_key(job_id, snapshot):
    # Reuse the existing core import boundary and authoritative cache-key function.
    from . import application_question_store
    from app.job_requirements import requirement_cache_key
    if not job_id or not snapshot.get('snapshot_hash'):
        return None
    return requirement_cache_key(dict(job_id=job_id,snapshot_hash=snapshot['snapshot_hash']))


def validate_profile(profile, job_id, snapshot):
    from . import application_question_store
    from app.application_writing.requirement_context import validate_requirements
    if profile.key != expected_profile_key(job_id,snapshot):
        raise ValueError('Requirement profile does not match selected job snapshot/version')
    validate_requirements(profile.requirements)


def existing_profile(job_id,snapshot,explicit_key=None):
    from .models import JobRequirementProfiles
    key=explicit_key or expected_profile_key(job_id,snapshot)
    if key is None: return None
    profile=JobRequirementProfiles.objects.filter(pk=key).first()
    if explicit_key and profile is None: raise ValueError('Explicit requirement profile missing')
    if profile is not None: validate_profile(profile,job_id,snapshot)
    return profile
