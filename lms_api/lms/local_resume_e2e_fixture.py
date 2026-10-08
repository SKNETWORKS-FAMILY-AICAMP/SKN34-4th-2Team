"""Fictional, idempotent fixtures. No production data, network, or extraction calls."""
import json
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.contrib.auth.hashers import make_password
from .models import Cohorts, Users, Resumes, ResumeEvidence
from .resume_experience_store import ensure_resume_item_binding, record_user_evidence
from .recruit_role_store import company_profile, submit_role

ROOT = Path(__file__).resolve().parents[2]
EMAIL = 'resume-e2e@example.test'
PASSWORD = 'LocalE2E-only!'


def fixture():
    return json.loads((ROOT / 'cover_letter_rag/evaluation/application_planning_cases.json').read_text(encoding='utf-8'))[0]


@transaction.atomic
def seed():
    if not getattr(settings, 'LOCAL_RESUME_E2E', False) or settings.DATABASES['default']['HOST'] not in {'localhost', '127.0.0.1'}:
        raise RuntimeError('Seed is local E2E only')
    cohort, _ = Cohorts.objects.get_or_create(code='local-resume-e2e', defaults=dict(name='Fictional E2E', status='active', is_active=True))
    user, _ = Users.objects.get_or_create(email=EMAIL, defaults=dict(firebase_uid='local-resume-e2e',
        password=make_password(PASSWORD), display_name='가상 E2E 학생', role='student', cohort=cohort,
        is_active=True, must_change_password=False))
    admin, _ = Users.objects.get_or_create(email='resume-e2e-admin@example.test', defaults=dict(
        firebase_uid='local-resume-e2e-admin', password=make_password(PASSWORD), display_name='Fixture admin',
        role='admin', is_active=True, must_change_password=False))
    data = fixture()
    content = {'projects': [dict(id=e['experience_id'], name=e['title'], description=' '.join(f['normalized_fact'] for f in e['evidence'])) for e in data['experiences']]}
    base, _ = Resumes.objects.get_or_create(legacy_id='local-resume-e2e-base', defaults=dict(user=user,
        cohort=cohort, is_base_resume=True, title='가상 학생 기본 이력서', content=content))
    for index, exp in enumerate(data['experiences']):
        binding = ensure_resume_item_binding(user_id=user.pk, resume_id=base.pk, section='projects', index=index)
        for fact in exp['evidence']:
            record_user_evidence(user_id=user.pk, experience_id=binding.experience_id,
                fact_type=fact['fact_type'], normalized_fact=fact['normalized_fact'],
                evidence_quote=fact['normalized_fact'], answer_text=fact['normalized_fact'], answer_source_id='local-e2e:' + fact['evidence_id'])
        if index == 1:
            old, _ = ResumeEvidence.objects.get_or_create(experience_id=binding.experience_id, source_id='local-e2e:correction-old',
                defaults=dict(fact_type='action', normalized_fact='모델 학습을 직접 구현', evidence_quote='모델 학습을 직접 구현',
                              source_type='resume_text', assertion_state='resume_stated'))
            record_user_evidence(user_id=user.pk, experience_id=binding.experience_id,
                fact_type='role', normalized_fact='모델 학습은 팀원이 수행했고 본인은 API 연동 담당',
                evidence_quote='모델 학습은 팀원이 수행했고 본인은 API 연동 담당',
                answer_text='모델 학습은 팀원이 수행했고 본인은 API 연동 담당', answer_source_id='local-e2e:correction-new',
                supersedes_evidence_id=old.pk)
    company = company_profile(user_id=admin.pk, company_name='가상 E2E 데이터 기업')
    role = submit_role(user_id=user.pk, company_id=company.pk, season='LOCAL E2E',
        role_name='Data Analyst / AI Service', role_description='가상 데이터 분석 및 AI 서비스 직무',
        requirements={'required': ['Python'], 'preferred': ['FastAPI'], 'responsibilities': ['데이터 서비스 개발']},
        questions=[dict(order=i+1, text=q) for i, q in enumerate(data['questions'])])
    return user, base, role
