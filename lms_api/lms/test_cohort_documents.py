from io import BytesIO
from zipfile import ZipFile
from unittest.mock import Mock, patch
from django.db import ProgrammingError
from django.test import SimpleTestCase
from lms.cohort_documents import validate_document, upload_document, get_documents, MAX_BYTES


class CohortDocumentTests(SimpleTestCase):
    def test_missing_guard_migration_is_not_reported_as_index_failure(self):
        missing = ProgrammingError('missing cohort_deletion_jobs')
        cause = RuntimeError('missing relation'); cause.sqlstate = '42P01'
        missing.__cause__ = cause
        with patch('lms.cohort_documents.put_object') as put, \
             patch('lms.cohort_documents.connection') as conn, \
             patch('lms.cohort_documents.transaction.atomic'), \
             patch('lms.cohort_documents.document_records', return_value=['chunk']):
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(40, 'cohort_40'), (40, 'cohort_40')]
            cur.execute.side_effect = [None, None, missing]
            file = Mock(); file.name = 'policy.pdf'; file.read.return_value = b'%PDF-1.7'
            response = upload_document(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}),
                                       'cohort_40', 'policy', file)
            self.assertEqual(response.status_code, 503)
            put.assert_not_called()

    def test_file_type_and_size(self):
        self.assertEqual(validate_document('curriculum', 'course.pdf', b'%PDF-1.7')[0], '.pdf')
        doc = BytesIO()
        with ZipFile(doc, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>')
            z.writestr('word/document.xml', '<document/>')
        self.assertEqual(validate_document('policy', 'policy.docx', doc.getvalue())[0], '.docx')
        for kind, name, data in [('curriculum', 'course.docx', doc.getvalue()), ('policy', 'fake.pdf', b'not pdf'), ('policy', 'fake.docx', b'not zip'), ('policy', 'big.pdf', b'%PDF-'+b'x'*MAX_BYTES)]:
            with self.assertRaises(ValueError):
                validate_document(kind, name, data)

    def test_non_admin_cannot_read_upload_or_write(self):
        with patch('lms.cohort_documents.put_object') as put, patch('lms.cohort_documents.connection') as conn:
            file = Mock()
            response = upload_document(Mock(auth={'role':'student','is_active':True}), 'cohort_40', 'policy', file)
            self.assertEqual(response.status_code, 403)
            read = get_documents(Mock(auth={'role':'student','is_active':True}), 'cohort_40')
            self.assertEqual(read.status_code, 403)
            file.read.assert_not_called()
            put.assert_not_called()
            conn.cursor.assert_not_called()

    def test_read_uses_current_cohort_db_pointer_without_exposing_key(self):
        from datetime import datetime, timezone
        stamp = datetime(2026, 10, 8, tzinfo=timezone.utc)
        key = 'cohorts/cohort_40/policy/rag/' + 'a' * 32 + '.docx'
        curriculum_key = 'cohorts/cohort_40/curriculum/rag/' + 'b' * 32 + '.pdf'
        with patch('lms.cohort_documents.connection') as conn:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(40, 'cohort_40'), ('course.pdf', curriculum_key, True, stamp),
                                        ('rules.docx', key, True, stamp)]
            response = get_documents(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}), 'cohort_40')
        self.assertEqual(response['documents']['policy']['ragStatus'], 'ready')
        self.assertEqual(response['documents']['curriculum']['filename'], 'course.pdf')
        self.assertEqual(response['documents']['policy']['updatedAt'], stamp.isoformat())
        self.assertNotIn(key, str(response))
        self.assertEqual(cur.execute.call_args_list[0].args[1], ['cohort_40'])
        self.assertEqual(cur.execute.call_args_list[1].args[1], [40])
        self.assertEqual(cur.execute.call_args_list[2].args[1], ['cohort:40:policy'])

    def test_legacy_and_inactive_documents_are_not_marked_search_ready(self):
        with patch('lms.cohort_documents.connection') as conn:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(41, 'cohort_41'), ('old.pdf', 'legacy/course.pdf', True, None),
                                        ('old-policy.docx', 'cohorts/cohort_41/policy/rag/' + 'a' * 32 + '.docx', False, None)]
            response = get_documents(Mock(auth={'role': 'admin', 'is_active': True}), 'cohort_41')
        self.assertEqual(response['documents']['curriculum']['ragStatus'], 'registered')
        self.assertEqual(response['documents']['policy']['ragStatus'], 'inactive')

    def test_unknown_cohort_does_not_read_another_cohorts_documents(self):
        with patch('lms.cohort_documents.connection') as conn:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = None
            response = get_documents(Mock(auth={'role': 'admin', 'is_active': True}), 'missing')
            self.assertEqual(response.status_code, 404)
            self.assertEqual(cur.execute.call_count, 1)

    def test_policy_activated_only_after_scoped_indexing(self):
        with patch('lms.cohort_documents.put_object') as put, patch('lms.cohort_documents.connection') as conn, patch('lms.cohort_documents.transaction.atomic'), patch('lms.cohort_documents.document_records', return_value=['chunk']), patch('lms.cohort_documents.index_document') as index:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(40, 'cohort_40'), (40, 'cohort_40'), None]
            file = Mock(); file.name = 'policy.pdf'; file.read.return_value = b'%PDF-1.7'
            response = upload_document(Mock(auth={'id':1,'role':'admin','is_active':True}), 'cohort_40', 'policy', file)
            self.assertFalse(response['policyPending'])
            self.assertEqual(response['ragStatus'], 'ready')
            index.assert_called_once()
            self.assertTrue(put.call_args.args[0].startswith('cohorts/cohort_40/policy/'))
            self.assertEqual(cur.execute.call_args.args[1][0], 'cohort:40:policy')
            self.assertIn('is_active=true', cur.execute.call_args.args[0])

    def test_upload_failure_does_not_replace_existing_record(self):
        with patch('lms.cohort_documents.put_object', side_effect=RuntimeError), patch('lms.cohort_documents.connection') as conn, patch('lms.cohort_documents.transaction.atomic'), patch('lms.cohort_documents.document_records', return_value=['chunk']):
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(34, 'cohort_34'), (34, 'cohort_34'), None]
            file = Mock(); file.name = 'course.pdf'; file.read.return_value = b'%PDF-1.7'
            response = upload_document(Mock(auth={'id':1,'role':'admin','is_active':True}), 'cohort_34', 'curriculum', file)
            self.assertEqual(response.status_code, 502)
            self.assertEqual(cur.execute.call_count, 3)

    def test_index_failure_does_not_publish_or_replace_document(self):
        with patch('lms.cohort_documents.put_object'), patch('lms.cohort_documents.connection') as conn, \
             patch('lms.cohort_documents.document_records', return_value=['chunk']), \
             patch('lms.cohort_documents.index_document', side_effect=TimeoutError), \
             patch('lms.cohort_documents.transaction.atomic') as atomic:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(40, 'cohort-abc1234'), (40, 'cohort-abc1234'), None]
            file = Mock(); file.name = 'policy.pdf'; file.read.return_value = b'%PDF-1.7'
            result = upload_document(Mock(auth={'id':1,'role':'admin','is_active':True}), 'cohort-abc1234', 'policy', file)
            self.assertEqual(result.status_code, 502)
            atomic.assert_called_once()
            self.assertEqual(cur.execute.call_count, 3)

    def test_deleting_cohort_rejects_upload_before_external_write(self):
        with patch('lms.cohort_documents.put_object') as put, patch('lms.cohort_documents.index_document') as index, \
             patch('lms.cohort_documents.connection') as conn, patch('lms.cohort_documents.transaction.atomic'), \
             patch('lms.cohort_documents.document_records', return_value=['chunk']):
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(40, 'cohort_40'), (40, 'cohort_40'), (1,)]
            file = Mock(); file.name = 'policy.pdf'; file.read.return_value = b'%PDF-1.7'
            result = upload_document(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}), 'cohort_40', 'policy', file)
            self.assertEqual(result.status_code, 409)
            put.assert_not_called()
            index.assert_not_called()
