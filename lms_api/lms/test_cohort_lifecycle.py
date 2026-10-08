"""No database, S3 or Pinecone writes: deletion safety contract tests."""
from unittest.mock import Mock, patch

from django.db import ProgrammingError
from django.test import SimpleTestCase

from lms import cohort_lifecycle as lifecycle
from lms import commands
from lms.commands import op_create_cohort, op_set_cohort_status


class CohortLifecycleTests(SimpleTestCase):
    def test_final_db_delete_uses_exact_owned_rows_not_orm_collector(self):
        policy_key = 'cohorts/cohort_40/policy/rag/' + 'a' * 32 + '.pdf'
        curriculum_key = 'cohorts/cohort_40/curriculum/rag/' + 'b' * 32 + '.pdf'
        with patch.object(lifecycle, 'connection') as connection:
            cur = connection.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(17, policy_key), (curriculum_key,)]
            cur.rowcount = 1
            lifecycle._delete_database_rows(40, {policy_key, curriculum_key})
        statements = [call.args for call in cur.execute.call_args_list]
        self.assertEqual(len(statements), 6)
        self.assertIn('DELETE FROM policy_document_revisions', statements[2][0])
        self.assertEqual(statements[2][1], [17])
        self.assertIn('DELETE FROM policy_documents', statements[3][0])
        self.assertEqual(statements[3][1], [17, 'cohort:40:policy'])
        self.assertEqual(statements[4][1], [40])
        self.assertEqual(statements[5], ('DELETE FROM cohorts WHERE id=%s', [40]))

    def test_final_db_delete_rejects_pointer_changed_after_manifest(self):
        new_key = 'cohorts/cohort_40/policy/rag/' + 'c' * 32 + '.pdf'
        with patch.object(lifecycle, 'connection') as connection:
            cur = connection.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(17, new_key), None]
            with self.assertRaises(lifecycle.DeletionInspectionError):
                lifecycle._delete_database_rows(40, set())
            self.assertFalse(any('DELETE FROM' in call.args[0] for call in cur.execute.call_args_list))

    def test_run_deletion_finalizes_without_django_reverse_collector(self):
        job = Mock(targets=[], state='deleting', deleted_vectors=[], deleted_objects=[])
        cohort = Mock(id=40)
        with patch.object(lifecycle, 'connection') as connection, \
             patch.object(lifecycle.transaction, 'atomic'), \
             patch.object(lifecycle.CohortDeletionJobs.objects, 'get', return_value=job), \
             patch.object(lifecycle.Cohorts.objects, 'select_for_update') as cohorts, \
             patch.object(lifecycle, '_blockers', return_value=[]), \
             patch.object(lifecycle, '_delete_database_rows') as final_sql:
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
            cohorts.return_value.get.return_value = cohort
            lifecycle._run_deletion(40)
        final_sql.assert_called_once_with(40, set())
        cohort.delete.assert_not_called()
        self.assertEqual(job.state, 'complete')

    def test_blockers_use_real_fk_catalog_and_qualified_identifiers(self):
        with patch.object(lifecycle, 'connection') as connection:
            cur = connection.cursor.return_value.__enter__.return_value
            connection.ops.quote_name.side_effect = lambda value: '"' + value.replace('"', '""') + '"'
            cur.fetchall.side_effect = [[
                ('public', 'users', 'cohort_id', 1, 'public'),
                ('public', 'curriculum_pdfs', 'cohort_id', 1, 'public'),
                ('archive', 'curriculum_pdfs', 'cohort_id', 1, 'public'),
            ], [('users',), ('archive.curriculum_pdfs',)]]
            blockers = lifecycle._blockers(40)
        self.assertEqual(blockers, [{'table': 'archive.curriculum_pdfs', 'label': 'archive.curriculum_pdfs'},
                                    {'table': 'users', 'label': '연결 사용자'}])
        queries = [call.args[0] for call in cur.execute.call_args_list]
        self.assertEqual(len(queries), 2)  # Catalog and one batched existence query, never stale ORM assignments.
        self.assertIn('"public"."users"', queries[1])
        self.assertIn('"archive"."curriculum_pdfs"', queries[1])
        self.assertEqual(cur.execute.call_args_list[1].args[1], ['users', 40, 'archive.curriculum_pdfs', 40])

    def test_unsupported_composite_fk_fails_closed(self):
        with patch.object(lifecycle, 'connection') as connection:
            cur = connection.cursor.return_value.__enter__.return_value
            cur.fetchall.return_value = [('public', 'complex_relation', 'cohort_id', 2, 'public')]
            with self.assertRaises(lifecycle.DeletionInspectionError):
                lifecycle._blockers(40)
            self.assertEqual(cur.execute.call_count, 1)

    def test_unrelated_missing_table_is_not_reported_as_unapplied_0017(self):
        cause = RuntimeError('undefined table'); cause.sqlstate = '42P01'
        unrelated = ProgrammingError('relation "assignments" does not exist')
        unrelated.__cause__ = cause
        migration = ProgrammingError('relation "cohort_deletion_jobs" does not exist')
        migration.__cause__ = cause
        cohort = Mock(id=40, code='cohort_40')
        with patch.object(lifecycle.Cohorts.objects, 'filter') as cohorts, \
             patch.object(lifecycle, '_preview', side_effect=[unrelated, migration]):
            cohorts.return_value.first.return_value = cohort
            request = Mock(auth={'id': 1, 'role': 'admin', 'is_active': True})
            first = lifecycle.deletion_preview(request, 'cohort_40')
            second = lifecycle.deletion_preview(request, 'cohort_40')
        self.assertEqual(first.status_code, 503)
        self.assertNotIn('0017', first.content.decode())
        self.assertIn('0017', second.content.decode())

    def test_missing_guard_migration_is_explicit_and_fails_closed(self):
        cur = Mock()
        cur.fetchone.return_value = (40,)
        missing = ProgrammingError('missing cohort_deletion_jobs')
        cause = RuntimeError('missing relation'); cause.sqlstate = '42P01'
        missing.__cause__ = cause
        cur.execute.side_effect = [None, missing]
        with self.assertRaisesRegex(ValueError, 'migration 0017'):
            commands._assert_cohort_writable(cur, 40)

    def test_dedicated_cohort_writers_stop_before_insert_when_deleting(self):
        staff = {'id': 1, 'role': 'admin', 'display_name': '관리자'}
        with patch.object(commands, 'resolve_cohort', return_value=40), \
             patch.object(commands, '_assert_cohort_writable', side_effect=ValueError('deleting')):
            for operation, payload in [
                (commands.op_create_notice, {'cohortId': 'cohort_40', 'title': '공지'}),
                (commands.op_upsert_scheduled, {'cohortId': 'cohort_40', 'title': '예약'}),
                (commands.op_upsert_alert, {'cohortId': 'cohort_40', 'title': '알림'}),
                (commands.op_save_curriculum_pdf, {'cohortId': 'cohort_40', 'storageKey': 'file'}),
            ]:
                cur = Mock()
                with self.assertRaisesRegex(ValueError, 'deleting'):
                    operation(cur, staff, payload)
                self.assertFalse(any('INSERT INTO' in call.args[0] for call in cur.execute.call_args_list),
                                 operation.__name__)

    def test_generic_update_checks_source_and_destination_cohort(self):
        cur = Mock()
        with patch.object(commands, '_table_columns', return_value=['id', 'cohort_id', 'title']), \
             patch.object(commands, '_prepare_row', return_value={'cohort_id': 41, 'title': 'moved'}), \
             patch.object(commands, 'resolve_row', return_value={'id': 7, 'cohort_id': 40}), \
             patch.object(commands, '_assert_cohort_writable') as guard:
            commands.op_upsert_sql(cur, {'id': 1, 'role': 'admin'},
                                   {'table': 'materials', 'id': 7, 'action': 'update'})
            self.assertEqual({call.args[1] for call in guard.call_args_list}, {40, 41})

    def test_direct_notice_api_stops_before_insert_when_deleting(self):
        from lms import api
        staff = {'id': 1, 'role': 'admin', 'display_name': '관리자'}
        with patch.object(api, '_require_user', return_value=staff), \
             patch.object(api, '_notice_image_key', return_value=None), \
             patch.object(api, 'resolve_cohort', return_value=40), \
             patch.object(api, '_assert_cohort_writable', side_effect=ValueError('deleting')), \
             patch.object(api, 'connection') as connection, \
             patch.object(api.transaction, 'atomic'), \
             patch.object(api, 'schedule_notice_vector') as schedule:
            response = api.create_notice(Mock(), {'title': '새 공지'})
            self.assertEqual(response.status_code, 409)
            self.assertFalse(any('INSERT INTO notices' in call.args[0]
                                 for call in connection.cursor.return_value.__enter__.return_value.execute.call_args_list))
            schedule.assert_not_called()

    def test_archive_and_explicit_restore_update_status_only(self):
        with patch('lms.commands._assert_cohort_writable'):
            for previous, target in [('active', 'closed'), ('closed', 'planned')]:
                cur = Mock()
                cur.fetchone.return_value = (40, previous)
                result = op_set_cohort_status(cur, {'role': 'admin'},
                                              {'cohortId': 'cohort_40', 'status': target})
                self.assertEqual(result['status'], target)
                self.assertEqual(cur.execute.call_args.args,
                                 ('UPDATE cohorts SET status=%s WHERE id=%s', [target, 40]))
            cur = Mock()
            cur.fetchone.return_value = (40, 'active')
            with self.assertRaises(ValueError):
                op_set_cohort_status(cur, {'role': 'admin'},
                                     {'cohortId': 'cohort_40', 'status': 'planned'})

    def test_creation_rejects_existing_number_or_normalized_name_before_insert(self):
        for existing in [[('code-40', '40기', 40, 'active')],
                         [('code-40', '  SK  40기 ', None, 'closed')]]:
            cur = Mock()
            cur.fetchall.return_value = existing
            with self.assertRaisesRegex(ValueError, '이미 등록된 기수'):
                op_create_cohort(cur, {'role': 'admin'},
                                 {'cohortId': 'new-code', 'name': 'SK 40기', 'termNumber': 40})
            self.assertFalse(any('INSERT INTO cohorts' in call.args[0] for call in cur.execute.call_args_list))
        cur = Mock()
        cur.fetchall.return_value = []
        cur.fetchone.side_effect = [None, (41,)]
        result = op_create_cohort(cur, {'role': 'admin'},
                                  {'cohortId': 'new-code', 'name': 'New 41기', 'termNumber': 41})
        self.assertEqual(result['cohortId'], 'new-code')
        self.assertTrue(any('INSERT INTO cohorts' in call.args[0] for call in cur.execute.call_args_list))

        retired = Mock()
        retired.fetchall.return_value = []
        retired.fetchone.return_value = (1,)
        with self.assertRaisesRegex(ValueError, '삭제 이력이 있는 기수 코드'):
            op_create_cohort(retired, {'role': 'admin'}, {'cohortId': 'old-code', 'name': '새 이름'})
        self.assertFalse(any('INSERT INTO cohorts' in call.args[0] for call in retired.execute.call_args_list))

    def test_other_cohort_or_legacy_key_never_enters_cleanup_manifest(self):
        own = 'cohorts/cohort_40/policy/rag/' + 'a' * 32 + '.pdf'
        other = 'cohorts/cohort_41/policy/rag/' + 'a' * 32 + '.pdf'
        self.assertTrue(lifecycle._owned_key('cohort_40', 'policy', own))
        self.assertFalse(lifecycle._owned_key('cohort_40', 'policy', other))
        self.assertFalse(lifecycle._owned_key('cohort_40', 'policy', 'shared/policy.pdf'))
        job = Mock(cohort_code='cohort_40', targets=[{'key': other,
                    'namespace': lifecycle.document_namespace(other)}],
                   deleted_vectors=[], deleted_objects=[])
        with patch.object(lifecycle, '_delete_vector_namespace') as vectors, \
             patch.object(lifecycle, '_delete_stored_object') as objects:
            with self.assertRaisesRegex(ValueError, 'invalid_cleanup_manifest'):
                lifecycle._cleanup_targets(job)
            vectors.assert_not_called()
            objects.assert_not_called()

    def test_external_cleanup_retry_resumes_only_incomplete_steps(self):
        key = 'cohorts/cohort_40/curriculum/rag/' + 'b' * 32 + '.pdf'
        namespace = lifecycle.document_namespace(key)
        job = Mock(cohort_code='cohort_40', targets=[{'key': key, 'namespace': namespace}],
                   deleted_vectors=[], deleted_objects=[])
        with patch.object(lifecycle, '_delete_vector_namespace') as vectors, \
             patch.object(lifecycle, '_delete_stored_object', side_effect=[TimeoutError(), None]) as objects:
            with self.assertRaises(TimeoutError):
                lifecycle._cleanup_targets(job)
            self.assertEqual(job.deleted_vectors, [namespace])
            self.assertEqual(job.deleted_objects, [])
            lifecycle._cleanup_targets(job)
            vectors.assert_called_once_with(namespace)
            self.assertEqual(objects.call_count, 2)
            self.assertEqual(job.deleted_objects, [key])

    def test_preview_blocks_operational_records_and_unowned_pointer(self):
        cohort = Mock(id=40, code='cohort_40', name='40기')
        with patch.object(lifecycle, '_blockers', return_value=[{'table': 'users', 'label': '연결 사용자'}]), \
             patch.object(lifecycle, '_document_pointers', return_value=([{'kind': 'policy'}], ['policy'])), \
             patch.object(lifecycle.CohortDeletionJobs.objects, 'filter') as jobs:
            jobs.return_value.first.return_value = None
            preview = lifecycle._preview(cohort)
        self.assertFalse(preview['canDelete'])
        self.assertEqual(preview['unsafeDocuments'], ['policy'])

    def test_new_operational_record_blocks_final_delete_after_external_cleanup(self):
        job = Mock(targets=[], state='deleting', deleted_vectors=[], deleted_objects=[])
        cohort = Mock(id=40, code='cohort_40')
        with patch.object(lifecycle, 'connection') as connection, \
             patch.object(lifecycle.transaction, 'atomic'), \
             patch.object(lifecycle.CohortDeletionJobs.objects, 'get', return_value=job), \
             patch.object(lifecycle.CohortDeletionJobs.objects, 'filter') as jobs, \
             patch.object(lifecycle.Cohorts.objects, 'select_for_update') as cohorts, \
             patch.object(lifecycle, '_blockers', return_value=[{'table': 'users'}]):
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (True,)
            jobs.return_value.first.return_value = job
            cohorts.return_value.get.return_value = cohort
            with self.assertRaisesRegex(ValueError, 'cohort_received_operational_records'):
                lifecycle._run_deletion(40)
        cohort.delete.assert_not_called()
        self.assertEqual(job.state, 'failed')

    def test_non_admin_never_reads_preview_or_deletes(self):
        request = Mock(auth={'role': 'student', 'is_active': True})
        with patch.object(lifecycle.Cohorts.objects, 'filter') as cohorts:
            self.assertEqual(lifecycle.deletion_preview(request, 'cohort_40').status_code, 403)
            self.assertEqual(lifecycle.delete_cohort(request, 'cohort_40',
                             lifecycle.DeleteCohortInput(confirmName='40기')).status_code, 403)
            cohorts.assert_not_called()
