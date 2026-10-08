"""Top-level module: intentionally avoids lms_server/Celery bootstrap."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.urls import path
if not getattr(settings, 'LOCAL_RESUME_E2E', False):
    raise ImproperlyConfigured('Local E2E URLconf requires local-only settings')
from lms import local_resume_e2e_api as views

urlpatterns = [path('api/local/resume-e2e/login', views.login),
    path('api/local/resume-e2e/catalog', views.catalog),
    path('api/local/resume-e2e/applications/open-or-create', views.create),
    path('api/local/resume-e2e/applications/<uuid:application_id>', views.read),
    path('api/local/resume-e2e/applications/<uuid:application_id>/tailored-resume', views.tailor),
    path('api/local/resume-e2e/applications/<uuid:application_id>/questions', views.questions),
    path('api/local/resume-e2e/applications/<uuid:application_id>/analyze', views.analyze),
    path('api/local/resume-e2e/applications/<uuid:application_id>/plan', views.plan),
    path('api/local/resume-e2e/applications/<uuid:application_id>/writer-readiness', views.writer_readiness),
    path('api/local/resume-e2e/applications/<uuid:application_id>/extract-evidence', views.extract_evidence),
    path('api/local/resume-e2e/applications/<uuid:application_id>/write', views.write)]
