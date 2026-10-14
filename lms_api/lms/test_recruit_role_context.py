"""Isolated PostgreSQL tests; no RDS or LLM calls."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
import uuid

from django.db import connection, connections, IntegrityError, OperationalError, ProgrammingError, transaction
from django.db.models.deletion import Collector, SET_NULL
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase

from . import test_application_workspace as fixtures
from .models import (CompanyProfiles, RecruitRoles, ResumeExperiences, ResumeEvidence,
                     Users, Applications, ApplicationQuestions, ApplicationAnswers)
from .recruit_role_store import (company_profile, update_company, canonical_company_key, content_hash,
    submit_role, moderate_role, shared_roles, open_role, delete_role, create_role_application,
    import_role_questions, set_job_apply_method, validate_content)
from .application_question_store import _target, save_answer, import_questions
from .application_workspace import create_application


class RecruitRoleTests(TestCase):
    def setUp(self):
        fixtures.ApplicationWorkspaceTests.setUp(self)
        self.admin = Users.objects.create(password='unused', display_name='Moderator', role='admin',
            is_active=True, must_change_password=False)
        self.company = company_profile(user_id=self.admin.pk, company_name='(주) Test Company')

    def role(self, user=None, **extra):
        values = dict(user_id=(user or self.user).pk, company_id=self.company.pk,
            season='2026 하반기', role_name='Backend', role_description='API development',
            requirements={'required': ['Kubernetes']},
            questions=[{'order': 1, 'text': '지원 동기는?', 'character_limit': 1000, 'include_spaces': True}])
        values.update(extra)
        return submit_role(**values)

    def app(self, role, key='role-app', **extra):
        return create_role_application(user_id=self.user.pk, role_id=role.pk,
            base_resume_id=self.base.pk, idempotency_key=key, **extra)

    def test_company_identity_and_nullable_metadata(self):
        self.assertIsNone(self.company.homepage_url)
        role = self.role()
        other_role = self.role(role_name='Data')
        self.assertEqual(role.company_id, other_role.company_id)
        updated = update_company(user_id=self.admin.pk, company_id=self.company.pk,
                                 company_name='New display name', company_key='New lookup')
        self.assertEqual(updated.pk, self.company.pk)
        role.refresh_from_db()
        self.assertEqual(role.company_id, updated.pk)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CompanyProfiles.objects.create(company_key=updated.company_key, company_name='Duplicate')

    def test_company_canonical_key_is_lookup_not_identity(self):
        self.assertEqual(canonical_company_key(' (주) Test Company '), 'testcompany')
        again = company_profile(user_id=self.admin.pk, company_name='Test Company')
        self.assertEqual(again.pk, self.company.pk)
        with self.assertRaises(PermissionError):
            update_company(user_id=self.user.pk, company_id=again.pk, company_name='Unapproved')

    def test_hash_key_order_whitespace_and_actual_changes(self):
        a = content_hash('API\r\n development', {'required': ['SQL'], 'preferred': []}, [{'text': 'Q', 'order': 1}])
        b = content_hash(' API development ', {'preferred': [], 'required': ['SQL']}, [{'order': 1, 'text': 'Q'}])
        self.assertEqual(a, b)
        self.assertNotEqual(a, content_hash('API development', {'required': ['Redis']}, []))

    def test_question_validation_and_source_preservation(self):
        role = self.role(role_description='  API\r\n development  ')
        self.assertEqual(role.role_description, '  API\r\n development  ')
        for questions in ([{'text': 'Q', 'character_limit': -1}], [{'text': ''}],
                          [{'text': 'Q', 'order': 1}, {'text': 'R', 'order': 1}]):
            with self.assertRaises(ValueError):
                validate_content('D', {}, questions)

    def test_private_dedup_per_owner(self):
        a, retry, b = self.role(), self.role(), self.role(self.other)
        self.assertEqual(a.pk, retry.pk)
        self.assertNotEqual(a.pk, b.pk)
        with self.assertRaises(RecruitRoles.DoesNotExist):
            open_role(user_id=self.other.pk, role_id=a.pk)
        with self.assertRaises(RecruitRoles.DoesNotExist):
            delete_role(user_id=self.other.pk, role_id=a.pk)

    def test_null_creator_dedup_scope_survives_without_cross_owner_collapse(self):
        a, b = self.role(), self.role(self.other)
        # SET_NULL semantics, without unrelated existing User PROTECT relationships.
        RecruitRoles.objects.filter(pk__in=[a.pk, b.pk]).update(created_by=None)
        self.assertEqual(RecruitRoles.objects.filter(created_by=None).count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            RecruitRoles.objects.create(company=self.company, season=a.season, role_name=a.role_name,
                role_description=a.role_description, content_hash=a.content_hash,
                source_type='other', dedupe_owner=a.dedupe_owner)
        self.assertFalse(shared_roles().exists())

    def test_existing_global_user_delete_is_blocked_by_missing_legacy_table(self):
        user = Users.objects.create(password='unused', display_name='Temporary', role='student',
                                    is_active=True, must_change_password=False)
        missing_table_error = OperationalError if connection.vendor == 'sqlite' else ProgrammingError
        with self.assertRaisesMessage(missing_table_error, 'assignment_submissions'), transaction.atomic():
            user.delete()

    def test_new_set_null_handlers_retain_distinct_private_scopes(self):
        users = [Users.objects.create(password='unused', display_name='Temporary', role='student',
                                      is_active=True, must_change_password=False) for _ in range(2)]
        roles = [self.role(user) for user in users]
        # Exercise the new relation handlers ONLY. Full Users.delete is separately
        # documented/tested as blocked by existing unmanaged legacy tables.
        collector = Collector(using='default')
        field = RecruitRoles._meta.get_field('created_by')
        self.assertIs(field.remote_field.on_delete, SET_NULL)
        field.remote_field.on_delete(collector, field, roles, 'default')
        collector.delete()
        for role in roles:
            role.refresh_from_db()
            self.assertIsNone(role.created_by_id)
        self.assertNotEqual(roles[0].dedupe_owner, roles[1].dedupe_owner)
        self.assertIs(RecruitRoles._meta.get_field('verified_by').remote_field.on_delete, SET_NULL)

    def test_company_rename_does_not_break_role_application_retry(self):
        role = self.role()
        app = self.app(role)
        update_company(user_id=self.admin.pk, company_id=self.company.pk, company_name='Renamed')
        retry = self.app(role)
        self.assertEqual(app.pk, retry.pk)
        self.assertEqual(_target(retry)['recruit_role']['company_name'], '(주) Test Company')
        direct_retry = create_application(user_id=self.user.pk, base_resume_id=self.base.pk,
            idempotency_key='role-app', role_context_id=app.role_context_id, target_snapshot=app.target_snapshot)
        self.assertEqual(direct_retry.pk, app.pk)

    def test_native_snapshot_size_cap_cannot_be_bypassed_by_common_entry(self):
        role = self.role(role_description='x' * 100001)
        with self.assertRaises(ValueError):
            self.app(role)
        with self.assertRaises(ValueError):
            create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='large',
                role_context_id=str(role.pk), target_snapshot={'role_version': role.content_hash})

    def test_template_metadata_conflict_rolls_back_import(self):
        app = self.app(self.role())
        for metadata in ({'character_limit': 500}, {'count_unit': 'bytes'}, {'include_spaces': False}):
            with self.assertRaises(ValueError):
                import_questions(user_id=self.user.pk, application_id=app.pk,
                    questions=['공백 포함 1000자 이내 작성'], constraints_overrides=[metadata])
        self.assertEqual(app.questions.count(), 0)

    def test_database_rejects_invalid_source_verification_and_negative_counter(self):
        role = self.role()
        for field, value in [('source_type', 'invalid'), ('verification_status', 'invalid'), ('use_count', -1)]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                RecruitRoles.objects.filter(pk=role.pk).update(**{field: value})

    def test_official_dedup_and_shared_policy(self):
        official = self.role(source_type='company_site', source_url='https://example.com/jobs')
        self.assertFalse(shared_roles().exists())
        self.assertEqual(self.role(source_type='company_site', source_url='https://example.com/jobs').pk, official.pk)
        with self.assertRaises(PermissionError):
            moderate_role(user_id=self.user.pk, role_id=official.pk, status='verified')
        moderate_role(user_id=self.admin.pk, role_id=official.pk, status='verified')
        self.assertEqual(open_role(user_id=self.other.pk, role_id=official.pk).pk, official.pk)
        self.assertEqual(self.role(self.other, source_type='company_site', source_url='https://example.com/jobs').pk, official.pk)
        with self.assertRaises(PermissionError):
            delete_role(user_id=self.user.pk, role_id=official.pk)
        private = self.role(role_name='Private')
        moderate_role(user_id=self.admin.pk, role_id=private.pk, status='verified')
        self.assertNotIn(private.pk, shared_roles().values_list('pk', flat=True))

    def test_verified_official_requires_source_url(self):
        role = self.role(source_type='company_site')
        with self.assertRaises(ValueError):
            moderate_role(user_id=self.admin.pk, role_id=role.pk, status='verified')

    def test_private_role_cannot_be_opened_as_foreign_application(self):
        role = self.role(self.other)
        with self.assertRaises(RecruitRoles.DoesNotExist):
            self.app(role)
        with self.assertRaises(RecruitRoles.DoesNotExist):
            create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='raw-private',
                role_context_id=str(role.pk), target_snapshot={'role_version': role.content_hash})

    def test_native_reference_uses_same_authorized_boundary_and_legacy_reference_survives(self):
        role = self.role()
        app = create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='direct-native',
            role_context_id=str(role.pk).upper(), target_snapshot={'role_version': role.content_hash})
        self.assertEqual(app.role_context_id, str(role.pk))
        self.assertEqual(_target(app)['recruit_role']['role_name'], 'Backend')
        legacy = create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='legacy-role',
            role_context_id='external-role-old', target_snapshot={'role_version': 'old-version'})
        self.assertEqual(legacy.role_context_id, 'external-role-old')

    def test_job_only_role_only_both_and_retry(self):
        role = self.role()
        a = create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='job-only',
                               job_id='job1', target_snapshot={'snapshot_hash': 'jhash'})
        b = self.app(role)
        c = self.app(role, 'both', job_id='job1', target_snapshot={'snapshot_hash': 'jhash'})
        self.assertIsNone(a.role_context_id)
        self.assertIsNone(b.job_id)
        self.assertEqual(c.role_context_id, str(role.pk))
        self.assertEqual(b.pk, self.app(role).pk)

    def test_question_snapshot_and_metadata_no_applicant_facts(self):
        before = ResumeExperiences.objects.count(), ResumeEvidence.objects.count()
        role = self.role()
        app = self.app(role)
        rows = import_role_questions(user_id=self.user.pk, application_id=app.pk)
        q = rows[0]
        self.assertEqual((q.character_limit, q.count_unit, q.include_spaces), (1000, 'characters', True))
        role.questions = [{'order': 1, 'text': 'New Q'}]
        role.save(update_fields=['questions'])  # external/template update must not rewrite snapshots
        again = import_role_questions(user_id=self.user.pk, application_id=app.pk)
        self.assertEqual(again[0].pk, q.pk)
        self.assertEqual(again[0].raw_text, '지원 동기는?')
        role.refresh_from_db()
        self.assertEqual(role.use_count, 1)
        self.assertEqual(before, (ResumeExperiences.objects.count(), ResumeEvidence.objects.count()))
        app.refresh_from_db()
        self.assertEqual(_target(app)['recruit_role']['requirements'], {'required': ['Kubernetes']})
        self.assertNotIn('role_questions_imported', _target(app))

    def test_new_version_creates_new_role_and_old_application_context_stable(self):
        role = self.role()
        app = self.app(role)
        new = self.role(role_description='Changed description')
        self.assertNotEqual(new.pk, role.pk)
        self.assertEqual(_target(app)['recruit_role']['role_description'], 'API development')

    def test_deleted_role_surviving_owned_application_and_questions(self):
        role = self.role()
        app = self.app(role)
        q = import_role_questions(user_id=self.user.pk, application_id=app.pk)[0]
        answer = save_answer(user_id=self.user.pk, question_id=q.pk, content='Fake answer')
        delete_role(user_id=self.user.pk, role_id=role.pk)
        self.assertTrue(Applications.objects.filter(pk=app.pk).exists())
        self.assertTrue(ApplicationAnswers.objects.filter(pk=answer.pk).exists())
        self.assertEqual(import_role_questions(user_id=self.user.pk, application_id=app.pk)[0].pk, q.pk)

    def test_forged_role_snapshot_blocked(self):
        role = self.role()
        app = self.app(role)
        snapshot = dict(app.target_snapshot)
        snapshot['recruit_role_snapshot'] = dict(snapshot['recruit_role_snapshot'], role_description='Forged')
        with self.assertRaises(ValueError):
            create_application(user_id=self.user.pk, base_resume_id=self.base.pk, idempotency_key='forged',
                role_context_id=str(role.pk), target_snapshot=snapshot)

    @skipUnless(connection.vendor == 'postgresql', 'Raw jobs schema requires PostgreSQL')
    def test_job_apply_method_check_preserves_posted_at_and_role_on_job_delete(self):
        with connection.cursor() as c:
            c.execute("INSERT INTO jobs.jobs(job_id, posted_at, first_seen_at, last_seen_at) VALUES ('role-job','2026-09-01',now(),now())")
        role = self.role(job_id='role-job')
        for value in ['HOMEPAGE', 'SITE', 'EMAIL', 'OTHER', None]:
            set_job_apply_method(user_id=self.admin.pk, job_id='role-job', apply_method=value)
        with self.assertRaises(ValueError):
            set_job_apply_method(user_id=self.admin.pk, job_id='role-job', apply_method='INVALID')
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as c:
            c.execute("UPDATE jobs.jobs SET apply_method='INVALID' WHERE job_id='role-job'")
        with connection.cursor() as c:
            c.execute("SELECT posted_at FROM jobs.jobs WHERE job_id='role-job'")
            self.assertEqual(c.fetchone()[0], '2026-09-01')
            c.execute("DELETE FROM jobs.jobs WHERE job_id='role-job'")
        self.assertTrue(RecruitRoles.objects.filter(pk=role.pk).exists())


@skipUnless(connection.vendor == 'postgresql', 'Full migration graph requires PostgreSQL')
class RecruitRolePostgresTests(TransactionTestCase):
    def test_concurrent_same_owner_submit_dedup(self):
        user = Users.objects.create(password='unused', display_name='Fake', role='student', is_active=True,
                                    must_change_password=False)
        company = CompanyProfiles.objects.create(company_key='concurrent', company_name='Concurrent')
        barrier = Barrier(2)
        def run():
            try:
                barrier.wait(timeout=10)
                return submit_role(user_id=user.pk, company_id=company.pk, season='2026', role_name='API',
                    role_description='API', requirements={}, questions=[]).pk
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(a, b)

    def test_migration_0013_forward_rollback_reapply_preserves_domains(self):
        latest = ('lms', '0014_recruit_role_context')
        previous = ('lms', '0013_application_questions_answers')
        try:
            executor = MigrationExecutor(connection)
            executor.migrate([previous])
            state = executor.loader.project_state([previous]).apps
            cohort = state.get_model('lms', 'Cohorts').objects.create(code='role-migration', name='Role',
                status='active', is_active=True)
            user = state.get_model('lms', 'Users').objects.create(password='unused', display_name='Old', role='student',
                is_active=True, must_change_password=False)
            resume = state.get_model('lms', 'Resumes').objects.create(user_id=user.pk, cohort_id=cohort.pk, content={'projects': []})
            experience = state.get_model('lms', 'ResumeExperiences').objects.create(user_id=user.pk, kind='project', title='Existing')
            evidence = state.get_model('lms', 'ResumeEvidence').objects.create(experience_id=experience.pk,
                fact_type='action', normalized_fact='API', evidence_quote='API', source_type='resume_text',
                source_id='r', assertion_state='resume_stated')
            binding = state.get_model('lms', 'ResumeExperienceBindings').objects.create(resume_id=resume.pk,
                experience_id=experience.pk, item_key='existing', field_path='projects[0].description', display_order=0)
            app = state.get_model('lms', 'Applications').objects.create(user_id=user.pk, base_resume_id=resume.pk,
                idempotency_key='old', request_hash='a'*64, entry_source='manual')
            question = state.get_model('lms', 'ApplicationQuestions').objects.create(application_id=app.pk,
                order=0, raw_text='Old Q', import_key='b'*64, source_type='manual')
            answer = state.get_model('lms', 'ApplicationAnswers').objects.create(question_id=question.pk, content='Old answer')
            expected = [('ResumeExperiences',experience.pk), ('ResumeEvidence',evidence.pk),
                        ('ResumeExperienceBindings',binding.pk),
                        ('Applications',app.pk), ('ApplicationQuestions',question.pk), ('ApplicationAnswers',answer.pk)]
            for target in [latest, previous, latest]:
                executor = MigrationExecutor(connection)
                executor.migrate([target])
                models = executor.loader.project_state([target]).apps
                for name, pk in expected:
                    self.assertTrue(models.get_model('lms', name).objects.filter(pk=pk).exists())
            with connection.cursor() as c:
                c.execute("SELECT indexname FROM pg_indexes WHERE tablename='recruit_roles'")
                names = {row[0] for row in c.fetchall()}
            self.assertTrue({'uq_recruit_role_official', 'uq_recruit_role_private'} <= names)
            with connection.cursor() as c:
                c.execute("SELECT contype FROM pg_constraint WHERE conrelid='public.recruit_roles'::regclass")
                types = [row[0] for row in c.fetchall()]
            self.assertEqual(types.count('f'), 3)  # Company, creator, verifier
            self.assertIn('p', types)
            self.assertGreaterEqual(types.count('c'), 3)  # source scope, verification, nonnegative counter
        finally:
            MigrationExecutor(connection).migrate([latest])
