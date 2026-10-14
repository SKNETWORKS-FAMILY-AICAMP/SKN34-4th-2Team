"""Workspace tests: isolated SQLite/PostgreSQL, no API/LLM/network calls."""
from copy import deepcopy
from unittest.mock import patch
from django.test import TestCase
from django.test import TransactionTestCase
from django.db import connection, connections
from django.db.migrations.executor import MigrationExecutor
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db.models.deletion import ProtectedError
from .models import (Applications, Cohorts, Users, Resumes, ResumeExperiences,
                     ResumeEvidence, ResumeExperienceBindings, JobRequirementProfiles)
from .application_workspace import (
    create_application, create_or_open_application, open_application,
    resume_first_application, job_first_application, ensure_tailored_resume,
    attach_tailored_resume, carry_application_context, reopen_application, application_evidence,
)
from .resume_experience_store import ensure_resume_item_binding, record_resume_evidence, record_user_evidence

# Reject accidental production settings before test DB creation.
if connection.vendor == 'postgresql':
    cfg = connection.settings_dict
    if (cfg['HOST'], str(cfg['PORT']), cfg['USER']) != ('127.0.0.1', '55439', 'resume_v2_test_admin') or cfg['NAME'] not in {'resume_review_v2_test', 'test_resume_review_v2'}:
        raise RuntimeError('Use the isolated resume_v2_postgres_test_settings')


class ApplicationWorkspaceTests(TestCase):
    def setUp(self):
        self.cohort = Cohorts.objects.create(code='app-test', name='App', status='active', is_active=True)
        self.user = Users.objects.create(password='unused', display_name='Fake', role='student',
            cohort=self.cohort, is_active=True, must_change_password=False)
        self.other = Users.objects.create(password='unused', display_name='Other', role='student',
            cohort=self.cohort, is_active=True, must_change_password=False)
        self.base = Resumes.objects.create(user=self.user, cohort=self.cohort, is_base_resume=True,
            content={'projects': [{'id': 'p1', 'name': 'P', 'description': '모델 학습을 직접 수행'}]})
        self.binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.base.pk,
                                                section='projects', index=0)
        self.old = record_resume_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id,
            fact_type='action', normalized_fact='모델 학습을 직접 수행', evidence_quote='모델 학습',
            source_id='resume1', source_text='모델 학습을 직접 수행')

    def args(self, key='request1', **extra):
        return dict(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key=key, **extra)

    def test_entries_converge_by_request_and_explicit_id(self):
        a = resume_first_application(**self.args())
        b = job_first_application(**self.args())
        c = job_first_application(user_id=self.user.pk, application_id=a.pk)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.pk, c.pk)
        self.assertEqual(a.entry_source, 'resume_first')

    def test_creation_no_copies_and_jobless_open(self):
        before = (ResumeExperiences.objects.count(), ResumeEvidence.objects.count(), Resumes.objects.count())
        a = create_application(**self.args())
        self.assertIsNone(a.job_id)
        self.assertIsNone(a.tailored_resume_id)
        self.assertEqual(open_application(user_id=self.user.pk, application_id=a.pk).pk, a.pk)
        self.assertEqual(before, (ResumeExperiences.objects.count(), ResumeEvidence.objects.count(), Resumes.objects.count()))

    def test_common_entry_adapters_can_start_and_reuse_tailoring(self):
        a = resume_first_application(start_tailoring=True, **self.args(
            job_id='j1', target_snapshot={'snapshot_hash': 'hash1'}))
        b = job_first_application(user_id=self.user.pk, application_id=a.pk, start_tailoring=True)
        self.assertEqual(a.tailored_resume_id, b.tailored_resume_id)
        self.assertEqual(Resumes.objects.count(), 2)

    def test_lazy_tailored_reuse_and_sharing(self):
        a = create_application(**self.args())
        t = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        again = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        self.assertEqual(t.pk, again.pk)
        self.assertEqual((Resumes.objects.count(), ResumeExperiences.objects.count(), ResumeEvidence.objects.count(),
                          ResumeExperienceBindings.objects.count()), (2, 1, 1, 2))
        self.assertEqual(t.experience_bindings.get().experience_id, self.binding.experience_id)

    def test_distinct_workspaces_have_distinct_mutable_documents(self):
        a, b = create_application(**self.args()), create_application(**self.args('second'))
        ta = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        tb = ensure_tailored_resume(user_id=self.user.pk, application_id=b.pk)
        a.status = 'ready'; a.save()
        ta.content = {'projects': []}; ta.save()
        b.refresh_from_db(); tb.refresh_from_db()
        self.assertEqual(b.status, 'draft')
        self.assertNotEqual(ta.pk, tb.pk)
        self.assertEqual(tb.content, self.base.content)
        self.assertEqual(ResumeExperiences.objects.count(), 1)

    def test_same_job_multiple_attempts_allowed(self):
        args = dict(job_id='j1', target_snapshot={'snapshot_hash': 'hash1'})
        a = create_application(**self.args(**args))
        b = create_application(**self.args('reapply', **args))
        self.assertNotEqual(a.pk, b.pk)

    def test_key_mismatch_blocked(self):
        create_application(**self.args())
        with self.assertRaises(ValueError):
            create_application(**self.args(job_id='j1', target_snapshot={'snapshot_hash': 'h'}))

    def test_explicit_id_target_mismatch_blocked(self):
        a = create_application(**self.args())
        with self.assertRaises(ValueError):
            create_or_open_application(user_id=self.user.pk, application_id=a.pk, job_id='wrong')

    def test_ownership(self):
        a = create_application(**self.args())
        with self.assertRaises(Applications.DoesNotExist):
            open_application(user_id=self.other.pk, application_id=a.pk)
        with self.assertRaises(Resumes.DoesNotExist):
            create_application(user_id=self.other.pk, base_resume_id=self.base.pk, idempotency_key='bad')
        foreign = Resumes.objects.create(user=self.other, cohort=self.cohort, content=deepcopy(self.base.content), base_resume=self.base)
        with self.assertRaises(Resumes.DoesNotExist):
            attach_tailored_resume(user_id=self.user.pk, application_id=a.pk, tailored_resume_id=foreign.pk)

    def test_carry_same_owner_new_document_and_retry(self):
        a = create_application(**self.args())
        b = carry_application_context(user_id=self.user.pk, application_id=a.pk, idempotency_key='carry')
        retry = carry_application_context(user_id=self.user.pk, application_id=a.pk, idempotency_key='carry')
        self.assertEqual(b.pk, retry.pk)
        self.assertEqual(b.carried_from_id, a.pk)
        self.assertIsNone(b.tailored_resume_id)
        with self.assertRaises(Applications.DoesNotExist):
            carry_application_context(user_id=self.other.pk, application_id=a.pk, idempotency_key='bad')

    def test_deleted_target_and_profile_do_not_block_open(self):
        from app.job_requirements import requirement_cache_key
        profile = JobRequirementProfiles.objects.create(key=requirement_cache_key(
            dict(job_id='deleted-job',snapshot_hash='old')), requirements=[])
        a = create_application(**self.args(job_id='deleted-job', target_snapshot={'snapshot_hash': 'old'},
                                          requirement_profile_key=profile.pk))
        profile.delete()
        opened = reopen_application(user_id=self.user.pk, application_id=a.pk)
        self.assertIsNone(opened.requirement_profile_id)
        self.assertEqual(opened.target_snapshot, {'snapshot_hash': 'old'})
        self.assertEqual(opened.job_id, 'deleted-job')

    def test_base_protected_tailored_set_null(self):
        a = create_application(**self.args())
        with self.assertRaises(ProtectedError): self.base.delete()
        t = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        t.delete(); a.refresh_from_db()
        self.assertIsNone(a.tailored_resume_id)

    def test_shared_correction_no_text_mutation_or_resurrection(self):
        a, b = create_application(**self.args()), create_application(**self.args('b'))
        t = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        before = deepcopy(t.content)
        new = record_user_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id,
            fact_type='action', normalized_fact='API 연동 담당', evidence_quote='API 연동',
            answer_source_id='correction', answer_text='저는 API 연동 담당', supersedes_evidence_id=self.old.pk)
        with patch('lms.application_workspace.record_resume_evidence', create=True, side_effect=AssertionError('no extraction')):
            for app in (a,b):
                evidence = application_evidence(user_id=self.user.pk, application_id=app.pk)
                self.assertEqual([e.pk for e in evidence[str(self.binding.experience_id)]], [new.pk])
        t.refresh_from_db()
        self.assertEqual(t.content, before)
        self.assertEqual(ResumeEvidence.objects.count(), 2)

    def test_target_validation(self):
        for extras in ({'job_id': 'j'}, {'role_context_id': 'r'}, {'target_snapshot': {'questions': []}}):
            with self.assertRaises(ValueError): create_application(**self.args(**extras))

    def test_tailored_attachment_wrong_target_or_other_workspace_blocked(self):
        a, b = create_application(**self.args()), create_application(**self.args('b'))
        t = ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        with self.assertRaises(ValueError):
            attach_tailored_resume(user_id=self.user.pk, application_id=b.pk, tailored_resume_id=t.pk)

    def test_failed_copy_rolls_back(self):
        a = create_application(**self.args())
        with patch('lms.application_workspace.clone_bindings_for_tailored_resume', side_effect=ValueError('failed')):
            with self.assertRaises(ValueError): ensure_tailored_resume(user_id=self.user.pk, application_id=a.pk)
        self.assertEqual(Resumes.objects.count(), 1)
        a.refresh_from_db(); self.assertIsNone(a.tailored_resume_id)


@skipUnless(connection.vendor == 'postgresql', 'requires PostgreSQL')
class ApplicationPostgresTests(TransactionTestCase):
    setUp = ApplicationWorkspaceTests.setUp
    args = ApplicationWorkspaceTests.args

    def test_concurrent_identical_create(self):
        gate = Barrier(2)
        args = self.args()
        def create():
            connections.close_all()
            try:
                gate.wait(timeout=10)
                return create_application(**args).pk
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            ids = [f.result(timeout=20) for f in futures]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Applications.objects.count(), 1)

    def test_concurrent_tailoring(self):
        app = create_application(**self.args())
        gate = Barrier(2)
        user_id, app_id = self.user.pk, app.pk
        def create():
            connections.close_all()
            try:
                gate.wait(timeout=10)
                return ensure_tailored_resume(user_id=user_id, application_id=app_id).pk
            finally: connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(create) for _ in range(2)]
            ids = [f.result(timeout=20) for f in futures]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual((Resumes.objects.count(), ResumeExperienceBindings.objects.count()), (2, 2))

    def test_application_migration_rollback_reapply_preserves_existing_core(self):
        def snapshot():
            with connection.cursor() as cur:
                rows = []
                for table in ('resumes', 'resume_experiences', 'resume_evidence', 'resume_experience_bindings'):
                    cur.execute(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')
                    rows.append(cur.fetchall())
                return rows
        before = snapshot()
        previous = [('lms', '0011_resume_experience_evidence')]
        latest = [('lms', '0012_application_workspace')]
        try:
            MigrationExecutor(connection).migrate(previous)
            self.assertEqual(snapshot(), before)
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(snapshot(), before)
            app = create_application(**self.args())
            self.assertEqual(app.base_resume_id, self.base.pk)
            with connection.cursor() as cur:
                cur.execute("SELECT contype, count(*) FROM pg_constraint WHERE conrelid='applications'::regclass GROUP BY contype")
                constraints = dict(cur.fetchall())
            self.assertEqual(constraints['f'], 5)
            self.assertEqual(constraints['u'], 2)
            self.assertEqual(constraints['c'], 4)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
