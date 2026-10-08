"""Real PostgreSQL checks. Run only with resume_v2_postgres_test_settings."""

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from threading import Barrier
from unittest import skipUnless

import psycopg
from django.db import OperationalError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from .models import (
    Cohorts, ResumeEvidence, ResumeExperienceBindings, ResumeExperiences,
    Resumes, Users,
)
from .resume_experience_store import (
    build_v2_review_input, clone_bindings_for_tailored_resume, create_experience, ensure_resume_item_binding,
    load_active_evidence, record_resume_evidence, record_user_evidence,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'cover_letter_rag'))

# Fail during discovery, before Django creates a test DB, if production settings
# are accidentally selected. SQLite discovery skips the PG-only suite.
if connection.vendor == 'postgresql':
    config = connection.settings_dict
    if (config['HOST'], str(config['PORT']), config['USER']) != ('127.0.0.1', '55439', 'resume_v2_test_admin') or config['NAME'] not in {
        'resume_review_v2_test', 'test_resume_review_v2',
    }:
        raise RuntimeError('PostgreSQL verification must use resume_v2_postgres_test_settings')


def local_pg():
    config = connection.settings_dict
    if (config['HOST'], str(config['PORT']), config['USER'], config['NAME']) != (
        '127.0.0.1', '55439', 'resume_v2_test_admin', 'test_resume_review_v2',
    ):
        raise RuntimeError('these tests require the isolated PostgreSQL test database')
    return psycopg.connect(host=config['HOST'], port=config['PORT'], user=config['USER'],
                           dbname=config['NAME'], sslmode='disable', connect_timeout=5)


@skipUnless(connection.vendor == 'postgresql', 'requires real PostgreSQL')
class PostgresPersistenceTests(TransactionTestCase):
    def setUp(self):
        with local_pg() as conn:
            self.assertEqual(conn.execute('SELECT current_database(), current_user').fetchone(),
                             ('test_resume_review_v2', 'resume_v2_test_admin'))
        self.cohort = Cohorts.objects.create(code='v2-pg', name='V2', status='active', is_active=True)
        self.user = Users.objects.create(firebase_uid='fake-v2-pg', email='v2@example.test',
                                         password='unused', display_name='V2', role='student',
                                         cohort=self.cohort, is_active=True, must_change_password=False)
        self.other = Users.objects.create(firebase_uid='fake-other', password='unused', display_name='Other',
                                          role='student', cohort=self.cohort, is_active=True, must_change_password=False)
        self.resume = Resumes.objects.create(
            legacy_id='base-pg', cohort=self.cohort, user=self.user, title='Base', status='writing',
            is_base_resume=True, content={'projects': [
                {'id': 'project-123', 'name': 'LMS', 'description': '모델 학습을 수행했다'},
                {'id': 'project-456', 'name': 'LMS 고도화', 'description': '모델 학습을 수행했다'},
            ]},
        )
        self.binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                                  section='projects', index=0)
        self.old = record_resume_evidence(
            user_id=self.user.pk, experience_id=self.binding.experience_id, fact_type='action',
            normalized_fact='모델 학습을 수행했다', evidence_quote='모델 학습을 수행했다',
            source_id='base-pg:revision-0', source_text='모델 학습을 수행했다',
        )

    def answer(self, source='answer-A', fact='API 연동을 담당했다', **extra):
        return record_user_evidence(
            user_id=self.user.pk, experience_id=self.binding.experience_id, fact_type='action',
            normalized_fact=fact, evidence_quote=fact, answer_source_id=source, answer_text=fact, **extra,
        )

    def gateway(self):
        from app.firebase_gateway import FirebaseGateway
        gateway = FirebaseGateway.__new__(FirebaseGateway)
        gateway._pg = local_pg
        return gateway

    def test_experience_isolation_same_fact_and_type(self):
        other_exp = create_experience(user_id=self.user.pk, kind='project', title='Project 2')
        b1 = ResumeEvidence.objects.create(
            experience=other_exp, fact_type=self.old.fact_type, normalized_fact=self.old.normalized_fact,
            evidence_quote=self.old.evidence_quote, source_type='user_answer', source_id='B',
            assertion_state='user_asserted',
        )
        replacement = self.answer(supersedes_evidence_id=self.old.pk)
        self.old.refresh_from_db()
        b1.refresh_from_db()
        self.assertEqual(self.old.assertion_state, 'superseded')
        self.assertEqual(replacement.assertion_state, 'user_asserted')
        self.assertEqual(b1.assertion_state, 'user_asserted')
        self.assertEqual(load_active_evidence(user_id=self.user.pk, experience_id=other_exp.pk), [b1])
        with self.assertRaises(ValueError):
            self.answer(source='cross-experience', supersedes_evidence_id=b1.pk)

    def test_concurrent_corrections_wait_on_lock_then_one_is_stale(self):
        gate = Barrier(3)

        def worker(source, fact):
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute("SET application_name = 'v2-concurrent-correction'")
                    cursor.execute("SET lock_timeout = '5s'")
                    cursor.execute("SET statement_timeout = '10s'")
                gate.wait(timeout=5)
                try:
                    result = self.answer(source=source, fact=fact, supersedes_evidence_id=self.old.pk)
                    return ('ok', result.pk)
                except ValueError as exc:
                    return ('stale', str(exc))
            finally:
                connections['default'].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            with transaction.atomic():
                ResumeExperiences.objects.select_for_update().get(pk=self.binding.experience_id)
                futures = [pool.submit(worker, 'concurrent-A', 'API 연동을 담당했다'),
                           pool.submit(worker, 'concurrent-B', '데이터 전처리를 담당했다')]
                gate.wait(timeout=5)
                deadline = time.monotonic() + 4
                blocked = 0
                while time.monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("""SELECT count(*) FROM pg_stat_activity
                            WHERE application_name = 'v2-concurrent-correction'
                              AND wait_event_type = 'Lock'""")
                        blocked = cursor.fetchone()[0]
                    if blocked == 2:
                        break
                    time.sleep(0.02)
                self.assertEqual(blocked, 2, 'both independent sessions must wait on the held Experience lock')
            results = [future.result(timeout=10) for future in futures]
        self.assertCountEqual([result[0] for result in results], ['ok', 'stale'])
        self.assertEqual(ResumeEvidence.objects.filter(supersedes_evidence=self.old).count(), 1)
        self.assertEqual(len(load_active_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id)), 1)

    def test_same_answer_retry_is_idempotent(self):
        first = self.answer()
        second = self.answer()
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ResumeEvidence.objects.filter(source_id='answer-A').count(), 1)

    def test_correction_retry_is_idempotent_after_target_superseded(self):
        first = self.answer(supersedes_evidence_id=self.old.pk)
        second = self.answer(supersedes_evidence_id=self.old.pk)
        self.assertEqual(first.pk, second.pk)

    def test_identical_concurrent_retry_returns_one_successor(self):
        gate = Barrier(2)
        def worker():
            try:
                gate.wait(timeout=5)
                return self.answer(supersedes_evidence_id=self.old.pk).pk
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(worker), pool.submit(worker)]
            ids = [future.result(timeout=10) for future in futures]
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(ResumeEvidence.objects.filter(supersedes_evidence=self.old).count(), 1)

    def test_lock_timeout_rolls_back_without_new_successor(self):
        def worker():
            try:
                with connections['default'].cursor() as cursor:
                    cursor.execute("SET lock_timeout = '250ms'")
                try:
                    self.answer(source='timeout', supersedes_evidence_id=self.old.pk)
                except OperationalError as exc:
                    return getattr(exc.__cause__, 'sqlstate', None)
                return 'unexpected-success'
            finally:
                connections['default'].close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                ResumeExperiences.objects.select_for_update().get(pk=self.binding.experience_id)
                self.assertEqual(pool.submit(worker).result(timeout=5), '55P03')
        self.old.refresh_from_db()
        self.assertEqual(self.old.assertion_state, 'resume_stated')
        self.assertFalse(ResumeEvidence.objects.filter(source_id='timeout').exists())
        self.answer(source='after-timeout', supersedes_evidence_id=self.old.pk)

    def test_chain_and_active_adapter(self):
        e2 = self.answer(supersedes_evidence_id=self.old.pk)
        e3 = self.answer(source='answer-C', fact='API 인증 연동을 담당했다', supersedes_evidence_id=e2.pk)
        request = build_v2_review_input(user_id=self.user.pk, resume_id=self.resume.pk,
                                        item_key=self.binding.item_key)
        self.assertEqual([item.evidence_id for item in request.experience.existing_evidence], [str(e3.pk)])
        self.old.refresh_from_db()
        e2.refresh_from_db()
        self.assertEqual((self.old.assertion_state, e2.assertion_state), ('superseded', 'superseded'))

    def test_uncertain_and_cross_user_correction(self):
        uncertain = self.answer(source='unsure', uncertain_conflict_id=self.old.pk)
        self.old.refresh_from_db()
        self.assertEqual(self.old.assertion_state, 'resume_stated')
        self.assertEqual(uncertain.assertion_state, 'uncertain')
        self.assertEqual(load_active_evidence(user_id=self.user.pk, experience_id=self.binding.experience_id), [])
        with self.assertRaises(PermissionError):
            record_user_evidence(user_id=self.other.pk, experience_id=self.binding.experience_id,
                                 fact_type='action', normalized_fact='API', evidence_quote='API',
                                 answer_source_id='intruder', answer_text='API', supersedes_evidence_id=self.old.pk)

    def test_actual_gateway_review_apply_and_promoted_copy_bindings(self):
        gateway = self.gateway()
        job = {'job_id': 'test-job', 'snapshot_hash': 'snapshot-1', 'company': 'Test', 'title': 'Engineer'}
        before = (ResumeExperiences.objects.count(), ResumeEvidence.objects.count(), ResumeExperienceBindings.objects.count())
        for purpose in ('review', 'apply'):
            result = gateway.create_tailored_resume(self.cohort.code, 'base-pg', self.user.firebase_uid, job, purpose)
            copied = Resumes.objects.get(legacy_id=f"base-pg/tailored/{result['tailored_resume_id']}")
            self.assertEqual(copied.content['projects'][0]['id'], 'project-123')
            self.assertEqual(copied.experience_bindings.get().experience_id, self.binding.experience_id)
            # Retry the same immutable job snapshot: no second Binding or Experience.
            gateway.create_tailored_resume(self.cohort.code, 'base-pg', self.user.firebase_uid, job, purpose)
        promoted_id = gateway.promote_tailored_resume(self.cohort.code, 'base-pg', result['tailored_resume_id'], self.user.firebase_uid)
        promoted = Resumes.objects.get(legacy_id=promoted_id)
        self.assertEqual(promoted.content['projects'][0]['id'], 'project-123')
        self.assertEqual(promoted.experience_bindings.get().experience_id, self.binding.experience_id)
        self.assertEqual((ResumeExperiences.objects.count(), ResumeEvidence.objects.count()), before[:2])
        self.assertEqual(ResumeExperienceBindings.objects.count(), before[2] + 3)

    def test_real_django_save_roundtrip_and_reorder(self):
        from .commands import op_upsert_sql
        self.resume.refresh_from_db()
        content = deepcopy(self.resume.content)
        content['projects'] = [content['projects'][1],
                               {'id': 'new-project', 'name': 'New', 'description': 'new'},
                               content['projects'][0]]
        actor = {'id': self.user.pk, 'role': 'student', 'cohort_id': self.cohort.pk}
        with transaction.atomic(), connection.cursor() as cursor:
            op_upsert_sql(cursor, actor, {'table': 'resumes', 'action': 'update',
                                         'id': 'base-pg', 'content': content, 'sections': {'projects': True}})
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.content['projects'][2]['id'], 'project-123')
        request = build_v2_review_input(user_id=self.user.pk, resume_id=self.resume.pk, item_key=self.binding.item_key)
        self.assertEqual(request.experience.field_path, 'projects[2].description')
        self.assertEqual(request.experience.experience_id, str(self.binding.experience_id))

    def test_legacy_key_persists_through_actual_save(self):
        from .commands import op_upsert_sql
        self.resume.content['projects'] = [{'name': 'LMS'}, {'name': 'LMS 고도화'}]
        self.resume.save(update_fields=['content'])
        a = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk, section='projects', index=0)
        b = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk, section='projects', index=1)
        self.resume.refresh_from_db()
        actor = {'id': self.user.pk, 'role': 'student', 'cohort_id': self.cohort.pk}
        with transaction.atomic(), connection.cursor() as cursor:
            op_upsert_sql(cursor, actor, {'table': 'resumes', 'action': 'update', 'id': 'base-pg',
                                         'content': self.resume.content})
        again = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk, section='projects', index=0)
        self.assertEqual(a.item_key, again.item_key)
        self.assertEqual(a.experience_id, again.experience_id)
        self.assertNotEqual(a.experience_id, b.experience_id)

    def test_actual_create_command_preserves_item_id(self):
        from .commands import op_upsert_sql
        actor = {'id': self.user.pk, 'role': 'student', 'cohort_id': self.cohort.pk}
        content = {'projects': [{'id': 'new-client-id', 'name': 'Created', 'description': 'API 구현'}]}
        with transaction.atomic(), connection.cursor() as cursor:
            result = op_upsert_sql(cursor, actor, {
                'table': 'resumes', 'action': 'insert', 'id': 'new-resume', 'title': 'Created',
                'status': 'writing', 'content': content, 'revisionCount': 0, 'isBaseResume': False,
            })
        saved = Resumes.objects.get(legacy_id=result['id'])
        self.assertEqual(saved.content, content)
        self.assertEqual(saved.user_id, self.user.pk)

    def test_actual_apply_and_undo_preserve_item_id_and_binding(self):
        from app.resume_apply import ApplyRequest, UndoRequest
        from app.review_workflow import digest
        from .models import ResumeAiReviews
        before = deepcopy(self.resume.content)
        ResumeAiReviews.objects.create(
            legacy_id='base-pg/review-id', resume=self.resume, user=self.user, payload={},
            response={'input_hash': digest(before), 'sentence_reviews': [{
                'field_path': 'projects[0].description', 'status': 'improved', 'validation_issues': [],
                'original_quote': '모델 학습을 수행했다', 'suggested_revision': 'API 연동을 담당했다',
            }]},
        )
        applied = self.gateway().apply_or_undo(self.user.firebase_uid, ApplyRequest(
            cohort_id=self.cohort.code, resume_id='base-pg', request_id='apply-id', review_id='review-id',
            expected_input_hash=digest(before), selected_indices=[0],
        ))
        self.resume.refresh_from_db()
        self.assertEqual(self.resume.content['projects'][0]['id'], 'project-123')
        self.assertEqual(self.resume.content['projects'][0]['description'], 'API 연동을 담당했다')
        self.gateway().apply_or_undo(self.user.firebase_uid, UndoRequest(
            cohort_id=self.cohort.code, resume_id='base-pg', request_id='undo-id', application_id='apply-id',
            expected_input_hash=applied.input_hash,
        ), undo=True)
        self.resume.refresh_from_db()
        self.binding.refresh_from_db()
        self.assertEqual(self.resume.content, before)
        self.assertTrue(ResumeExperiences.objects.filter(pk=self.binding.experience_id).exists())

    def test_schema_constraints_and_delete_policy(self):
        with connection.cursor() as cursor:
            cursor.execute("""SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid IN ('resume_experiences'::regclass, 'resume_evidence'::regclass,
                                   'resume_experience_bindings'::regclass)""")
            constraints = dict(cursor.fetchall())
            cursor.execute("SELECT tablename, indexname FROM pg_indexes WHERE tablename LIKE 'resume_expe%' OR tablename = 'resume_evidence'")
            indexes = cursor.fetchall()
        self.assertIn('uq_resume_experience_item', constraints)
        self.assertGreaterEqual(sum('FOREIGN KEY' in value for value in constraints.values()), 6)
        self.assertGreaterEqual(len(indexes), 8)
        with self.assertRaises(ProtectedError):
            self.binding.experience.delete()
        unbound = create_experience(user_id=self.user.pk, kind='project', title='unbound')
        fact = ResumeEvidence.objects.create(experience=unbound, fact_type='action', normalized_fact='x',
                                            evidence_quote='x', source_id='x', source_type='resume_text',
                                            assertion_state='resume_stated')
        unbound.delete()
        self.assertFalse(ResumeEvidence.objects.filter(pk=fact.pk).exists())
        self.assertTrue(ResumeEvidence.objects.filter(pk=self.old.pk).exists())

    def test_adapter_query_count_is_constant(self):
        for n in range(20):
            self.answer(source=f'answer-{n}', fact=f'API {n}')
        with CaptureQueriesContext(connection) as queries:
            request = build_v2_review_input(user_id=self.user.pk, resume_id=self.resume.pk, item_key=self.binding.item_key)
        self.assertEqual(len(request.experience.existing_evidence), 21)
        self.assertEqual(len(queries), 3)

    def test_lazy_copy_reuses_binding_created_after_copy(self):
        # Second item has no binding at copy time.
        copied = Resumes.objects.create(user=self.user, cohort=self.cohort, base_resume=self.resume,
                                        content=deepcopy(self.resume.content))
        base_binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                                   section='projects', index=1)
        copy_binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=copied.pk,
                                                   section='projects', index=1)
        self.assertEqual(copy_binding.experience_id, base_binding.experience_id)

    def test_opening_copy_first_does_not_duplicate_stable_experience(self):
        copied = Resumes.objects.create(user=self.user, cohort=self.cohort, base_resume=self.resume,
                                        content=deepcopy(self.resume.content))
        copy_binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=copied.pk,
                                                   section='projects', index=1)
        base_binding = ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk,
                                                   section='projects', index=1)
        self.assertEqual(copy_binding.experience_id, base_binding.experience_id)

    def test_legacy_copy_without_shared_identity_is_blocked_conservatively(self):
        self.resume.content = {'projects': [{'name': 'LMS', 'description': 'API'}]}
        self.resume.save(update_fields=['content'])
        copied = Resumes.objects.create(user=self.user, cohort=self.cohort, base_resume=self.resume,
                                        content=deepcopy(self.resume.content))
        before = ResumeExperiences.objects.count()
        with self.assertRaisesRegex(ValueError, 'no stable identity'):
            ensure_resume_item_binding(user_id=self.user.pk, resume_id=copied.pk, section='projects', index=0)
        self.assertEqual(ResumeExperiences.objects.count(), before)

    def test_batch_clone_has_bounded_query_count(self):
        content = deepcopy(self.resume.content)
        content['projects'].extend({'id': f'bulk-{n}', 'name': f'Project {n}', 'description': 'API'} for n in range(10))
        self.resume.content = content
        self.resume.save(update_fields=['content'])
        for index in range(len(content['projects'])):
            ensure_resume_item_binding(user_id=self.user.pk, resume_id=self.resume.pk, section='projects', index=index)
        copied = Resumes.objects.create(user=self.user, cohort=self.cohort, base_resume=self.resume, content=content)
        with CaptureQueriesContext(connection) as queries:
            bindings = clone_bindings_for_tailored_resume(user_id=self.user.pk, source_resume_id=self.resume.pk,
                                                          tailored_resume_id=copied.pk)
        self.assertEqual(len(bindings), 12)
        self.assertLessEqual(len(queries), 9)

    def test_raw_sql_resume_deletes_remove_only_bindings(self):
        from .commands import op_upsert_sql
        gateway = self.gateway()
        job = {'job_id': 'test-job', 'snapshot_hash': 'snapshot-delete', 'company': 'Test'}
        result = gateway.create_tailored_resume(self.cohort.code, 'base-pg', self.user.firebase_uid, job)
        copied = Resumes.objects.get(legacy_id=f"base-pg/tailored/{result['tailored_resume_id']}")
        with local_pg() as conn:
            gateway._delete_owned_resume_row(conn, copied.legacy_id,
                                            {'user_pk': self.user.pk, 'cohort_pk': self.cohort.pk})
        self.assertFalse(Resumes.objects.filter(pk=copied.pk).exists())
        actor = {'id': self.user.pk, 'role': 'student', 'cohort_id': self.cohort.pk}
        with transaction.atomic(), connection.cursor() as cursor:
            op_upsert_sql(cursor, actor, {'table': 'resumes', 'action': 'delete', 'id': 'base-pg'})
        self.assertTrue(ResumeExperiences.objects.filter(pk=self.binding.experience_id).exists())
        self.assertTrue(ResumeEvidence.objects.filter(pk=self.old.pk).exists())
        self.assertEqual(ResumeExperienceBindings.objects.count(), 0)


@skipUnless(connection.vendor == 'postgresql', 'requires real PostgreSQL')
class PostgresMigrationTests(TransactionTestCase):
    def test_upgrade_existing_0007_fixture_and_rollback_reapply(self):
        old = [('lms', '0007_resume_tailorings')]
        latest = [('lms', '0011_resume_experience_evidence')]
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(old)
            apps = executor.loader.project_state(old).apps
            Cohort = apps.get_model('lms', 'Cohorts')
            User = apps.get_model('lms', 'Users')
            Resume = apps.get_model('lms', 'Resumes')
            Tailoring = apps.get_model('lms', 'ResumeTailorings')
            Review = apps.get_model('lms', 'ResumeAiReviews')
            cohort = Cohort.objects.create(code='old-fixture', name='Old', status='active', is_active=True)
            user = User.objects.create(firebase_uid='old-fake-user', password='unchanged', display_name='Old',
                                       role='student', cohort=cohort, is_active=True, must_change_password=False)
            base = Resume.objects.create(user=user, cohort=cohort, title='Old base', content={'projects': [{'id': 'old-id'}]}, is_base_resume=True)
            copied = Resume.objects.create(user=user, cohort=cohort, title='Old tailored', content=deepcopy(base.content), base_resume=base)
            Tailoring.objects.create(resume=copied, review_session={'turns': ['old review']})
            Review.objects.create(resume=copied, user=user, payload={'request_id': 'old'}, response={'findings': ['unchanged']})
            from app.resume_binding_copy import clone_existing_bindings
            with local_pg() as conn:
                self.assertEqual(clone_existing_bindings(conn, user_id=user.pk,
                                 source_resume_id=base.pk, target_resume_id=copied.pk), 0)
            def snapshot():
                with connection.cursor() as cursor:
                    result = []
                    for table in ('users', 'resumes', 'resume_tailorings', 'resume_ai_reviews'):
                        cursor.execute(f'SELECT to_jsonb(t) FROM {table} t ORDER BY id')
                        result.append(cursor.fetchall())
                    return result
            before = snapshot()
            MigrationExecutor(connection).migrate([('lms', '0010_submission_task_questions')])
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(snapshot(), before)
            with connection.cursor() as cursor:
                cursor.execute("SELECT to_regclass('public.resume_experiences')")
                self.assertEqual(cursor.fetchone()[0], 'resume_experiences')
            # Reversal drops only the new tables, so any v2 rows would be lost.
            MigrationExecutor(connection).migrate([('lms', '0010_submission_task_questions')])
            self.assertEqual(snapshot(), before)
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(snapshot(), before)
        finally:
            final_executor = MigrationExecutor(connection)
            final_executor.migrate(final_executor.loader.graph.leaf_nodes())
